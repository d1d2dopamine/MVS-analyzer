using System.Diagnostics;
using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Collections.Concurrent;

namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private string datasetPath = "";
    private int selectedCalibrationRepetitions = 2000;
    private ColabBridge? colabBridge;
    private ColabSessionStore? colabSessions;
    private readonly ConcurrentDictionary<string, ColabRunPlan> colabPlans = new();
    private readonly object colabGate = new();
    private string colabPanelKey = "";
    private readonly List<(Button Button, Label Status, string Action, Func<int> Repetitions)> colabButtons = new();
    private bool layoutTestMode;
    private ColabSessionStore Sessions => colabSessions ??= new ColabSessionStore(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "Colab"));
    private string CalibrationKey(int repetitions) => ColabSessionStore.KeyFor(datasetHash, SettingsContract.Fingerprint(settings), repetitions, "standard");

    private Button ColabButton(Action action)
    {
        var button = Button(T("Run via Colab", "Запустить через Colab"), false, 285);
        button.Name = "run-via-colab"; button.Height = 44; button.Image = Branding.ColabIcon(DeviceDpi);
        button.ImageAlign = ContentAlignment.MiddleLeft; button.TextImageRelation = TextImageRelation.ImageBeforeText;
        button.Padding = new Padding(10, 0, 10, 0); button.TextAlign = ContentAlignment.MiddleCenter;
        button.AccessibleName = T("Run via Google Colab", "Запустить через Google Colab");
        button.Click += (_, _) => action(); return button;
    }
    private void AddColabRunCard(FlowLayoutPanel page, string action, Func<int> repetitions)
    {
        var status = new Label { Text = T("No data has been sent. Local execution remains available above.", "Данные не отправлены. Локальный запуск доступен выше."), ForeColor = Secondary, AutoSize = false };
        var run = ColabButton(() => {
            if (layoutTestMode) { ShowColabPanel(); return; }
            string key = data == null ? "" : CalibrationKey(repetitions());
            if (key.Length > 0 && Sessions.Find(key) != null) ShowColabPanel(key);
            else { ShowColabPanel(); StartColab(action, repetitions()); }
        });
        var import = Button(T("Import result…", "Импортировать результат…"), false, 245);
        import.Click += (_, _) => ImportColabBundle();
        page.Controls.Add(FlowCard("Google Colab", T(
            "Optional cloud execution in a separate control window. Connect the notebook once, then calibrate, analyze, stop and download here.",
            "Необязательный облачный расчёт в отдельном окне. Подключите ноутбук один раз, затем управляйте калибровкой, анализом, остановкой и скачиванием."),
            new ActionButtonPanel(false, 2, run, import), status));
        colabButtons.Add((run, status, action, repetitions));
        var timer = new System.Windows.Forms.Timer { Interval = 2500 };
        timer.Tick += (_, _) => RefreshColabButtons(); run.Disposed += (_, _) => { timer.Stop(); timer.Dispose(); };
        if (!layoutTestMode) { timer.Start(); RefreshColabButtons(); }
    }
    private void RefreshColabButtons()
    {
        colabButtons.RemoveAll(x => x.Button.IsDisposed);
        if (layoutTestMode || data == null) return;
        foreach (var item in colabButtons)
        {
            try
            {
                int n = item.Repetitions(); string key = CalibrationKey(n); ColabSession? session = Sessions.Find(key);
                bool complete = Sessions.HasCalibration(key, datasetHash, SettingsContract.Fingerprint(settings), n);
                bool busy = Sessions.Busy(session, DateTime.UtcNow);
                bool opening = Sessions.Pending(session, DateTime.UtcNow);
                // The entry point is also the recovery path. Never disable it because of a lease.
                item.Button.Enabled = true;
                item.Button.Text = session != null ? T("Open Colab window", "Открыть окно Colab") : T("Run via Colab", "Запустить через Colab");
                item.Status.Text = busy ? T("MVS is calculating in Colab. Progress and Stop are available in the separate window.", "MVS считает в Colab. Прогресс и остановка доступны в отдельном окне.")
                    : opening ? T("Waiting for the first cell. The code can be copied again from the Colab window.", "Ожидается первая ячейка. Код можно снова скопировать из окна Colab.")
                    : complete ? T("Calibration is verified and retained, even when the notebook is disconnected.", "Калибровка проверена и сохранена, даже если блокнот отключён.")
                    : Sessions.Live(session, DateTime.UtcNow) ? T("The MVS runtime is connected. Use the control window.", "Среда MVS подключена. Откройте окно управления.")
                    : session != null ? T("No live confirmation. Reopen the same notebook or reconnect; a new copy is not required.", "Нет подтверждения связи. Откройте тот же блокнот или переподключитесь — новая копия не нужна.")
                    : T("No data has been sent. Local execution remains available.", "Данные не отправлены. Локальный запуск остаётся доступен.");
            }
            catch (Exception error) { item.Button.Enabled = false; item.Status.Text = error.Message; }
        }
    }
    private void OpenLinkedColab(int repetitions)
    {
        try
        {
            OpenBrowser(Sessions.NotebookFor(CalibrationKey(repetitions)));
        }
        catch (Exception error) { MessageBox.Show(ColabDialogOwner, error.Message, "MVS"); }
    }
    private void StartColab(string action, int repetitions, string kind = "standard", string[]? extraArguments = null)
    {
        try
        {
            if (layoutTestMode || localOperationInProgress) return;
            // Additional methods are job kinds, not controller commands. The old code sent
            // "variance"/"melsm"/"estimation"/"benchmark" and Launch rejected every button.
            action = NormalizeColabAction(action, kind);
            SettingsContract.Validate(settings);
            string[] arguments = extraArguments ?? Array.Empty<string>();
            bool needsData = kind is "standard" or "variance" or "melsm";
            string source = "", inputHash = "synthetic";
            if (needsData)
            {
                if (kind == "melsm" || data == null)
                {
                    using var pick = new OpenFileDialog { Filter = "CSV / TSV (*.csv;*.tsv)|*.csv;*.tsv" };
                    if (pick.ShowDialog(ColabDialogOwner) != DialogResult.OK) return;
                    source = pick.FileName;
                }
                else
                {
                    if (loadedProcessing != null && loadedProcessing != ProcessingSnapshot.From(settings)) throw new InvalidDataException(T("Processing changed. Re-import first.", "Обработка изменилась. Сначала повторите импорт."));
                    source = EnsureDatasetFile();
                    if (OutputExporter.HashFile(source) != datasetHash) throw new InvalidDataException(T("The source file changed. Re-import it before remote execution.", "Исходный файл изменился. Повторите импорт перед удалённым запуском."));
                }
                inputHash = OutputExporter.HashFile(source);
                if (kind is "standard" or "variance")
                {
                    ImportProfile? profile = PluginAssets.Current.ImportProfiles.FirstOrDefault(x => x.Id == settings.ImportProfileId);
                    List<Observation> observations = CsvImporter.Read(source, settings.MinValue, settings.MaxValue, profile);
                    if (!ConfirmIndependent(observations)) return;
                    bool overlap = observations.GroupBy(x => x.Entity, StringComparer.OrdinalIgnoreCase).Any(g => g.Select(x => x.Group).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1);
                    if (overlap && !arguments.Contains("--allow-group-scoped-ids")) arguments = arguments.Append("--allow-group-scoped-ids").ToArray();
                }
            }
            string fingerprint = SettingsContract.Fingerprint(settings);
            // Group-scoped ID acknowledgement affects interpretation, not the calibrated numeric settings.
            string key = ColabSessionStore.KeyFor(inputHash, fingerprint, repetitions, kind, kind == "standard" ? null : arguments);
            colabPanelKey = key;
            ColabSession? prior = Sessions.Find(key);
            if (Sessions.Pending(prior, DateTime.UtcNow) || Sessions.Busy(prior, DateTime.UtcNow))
            { ShowColabPanel(key); return; }
            if (kind == "standard" && action == "calibrate" && Sessions.HasCalibration(key, inputHash, fingerprint, repetitions))
            { ReceiveColabState(new ColabRunPlan(key, kind, action, inputHash, fingerprint, repetitions, arguments)); ShowColabPanel(key); return; }
            if (Sessions.Live(prior, DateTime.UtcNow) && prior!.ControlsReady && colabPlans.ContainsKey(key))
            { lock (colabGate) Sessions.QueueAction(key, action); ShowColabPanel(key); return; }
            if (MessageBox.Show(ColabDialogOwner, needsData
                ? T("The selected measurements and settings will be uploaded to your Google Colab runtime when you run its first cell. Allow this job?", "Выбранные измерения и настройки будут переданы в ваш Google Colab при запуске первой ячейки. Разрешить это задание?")
                : T("Open a synthetic study in Google Colab? Your measurements will not be included.", "Открыть синтетическое исследование в Google Colab? Ваши измерения передаваться не будут."), "Google Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Information) != DialogResult.Yes) return;
            lock (colabGate)
            {
                Sessions.GetOrCreate(key, kind, action);
                string directory = Sessions.DirectoryFor(key); Directory.CreateDirectory(directory);
                if (kind == "standard" && calibration != null && data != null && inputHash == datasetHash &&
                    calibrationSettingsHash == fingerprint && lastCalibrationRepetitions == repetitions)
                    CalibrationPersistence.Write(Sessions.CalibrationPath(key), DesktopState());
                var plan = new ColabRunPlan(key, kind, action, inputHash, fingerprint, repetitions, arguments);
                BuildColabArchive(plan, source);
                colabPlans[key] = plan;
                colabBridge ??= new ColabBridge(HandleColabRequest);
                Sessions.Launch(key, action);
            }
            ShowColabPanel(key);
            TryCopyColabCode(key);
            // The connection dialog gives a single explicit Open notebook action, avoiding
            // duplicate tabs and focus theft before the user can copy the connection code.
            ShowColabConnection(key);
        }
        catch (Exception error) { MessageBox.Show(ColabDialogOwner, error.Message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    internal static string NormalizeColabAction(string action, string kind)
    {
        if (kind is "variance" or "melsm" or "estimation" or "benchmark")
        {
            if (action == "prepare") return "prepare";
            if (action == kind || action == "analyze") return "analyze";
            throw new InvalidDataException("Unknown Colab method action.");
        }
        if (kind != "standard" || action is not ("prepare" or "calibrate" or "analyze")) throw new InvalidDataException("Unknown Colab job/action.");
        return action;
    }

    private string EnsureDatasetFile()
    {
        if (datasetPath.Length > 0 && File.Exists(datasetPath)) return datasetPath;
        if (data == null) throw new InvalidDataException("No dataset is loaded.");
        if (settings.ImportProfileId.Length != 0) throw new InvalidDataException(T("Select built-in recognition and reload the demo before exporting it.", "Выберите встроенное распознавание и заново загрузите пример перед экспортом."));
        string folder = Path.Combine(Sessions.Folder, "generated"); Directory.CreateDirectory(folder);
        datasetPath = Path.Combine(folder, "demo.csv");
        static string Cell(string value) => "\"" + value.Replace("\"", "\"\"") + "\"";
        var csv = new StringBuilder("entity,group,value,sequence,variable,unit\n");
        foreach (Observation row in data.Observations) csv.AppendLine(string.Join(",", Cell(row.Entity), Cell(row.Group), row.Value.ToString("R", CultureInfo.InvariantCulture), row.Sequence.ToString(CultureInfo.InvariantCulture), Cell(row.Variable), Cell(row.Unit)));
        ScientificJson.AtomicText(datasetPath, csv.ToString()); datasetHash = OutputExporter.HashFile(datasetPath); return datasetPath;
    }
    private void BuildColabArchive(ColabRunPlan plan, string source)
    {
        string directory = Sessions.DirectoryFor(plan.Key), target = Sessions.ArchivePath(plan.Key), temporary = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
        if (source.Length > 0 && new FileInfo(source).Length > 64L * 1024 * 1024) throw new InvalidDataException("The automatic Colab transfer limit is 64 MB. Use a manual upload for larger datasets.");
        try
        {
        using (var zip = ZipFile.Open(temporary, ZipArchiveMode.Create))
        {
            void Text(string name, string text) { using var writer = new StreamWriter(zip.CreateEntry(name).Open(), new UTF8Encoding(false)); writer.Write(text); }
            Text("colab_job.json", ScientificJson.Serialize(plan));
            if (source.Length > 0)
            {
                zip.CreateEntryFromFile(source, "data.csv", CompressionLevel.Optimal);
                RemoteJobFile job = RemoteJob.Describe(plan.Kind, "data.csv", plan.DatasetHash, projectName, projectDescription, settings, plan.Repetitions);
                Text("job.json", RemoteJob.Serialize(job));
                ImportProfile? profile = PluginAssets.Current.ImportProfiles.FirstOrDefault(x => x.Id == settings.ImportProfileId);
                if (profile != null) Text("import_profile.json", ScientificJson.Serialize(profile));
            }
            if (File.Exists(Sessions.CalibrationPath(plan.Key))) zip.CreateEntryFromFile(Sessions.CalibrationPath(plan.Key), "calibration/" + CalibrationPersistence.FileName);
            byte[] sourceBytes = Branding.ResourceBytes("colab-cli-source.zip") ?? throw new InvalidDataException("The embedded Colab CLI source is missing. Regenerate the Colab payload before building the application.");
            byte[] runtime = Branding.ResourceBytes("mvs_colab.py") ?? throw new InvalidDataException("The embedded Colab controller is missing.");
            Text("runtime/manifest.json", ScientificJson.Serialize(new { schema = 1, bootstrapApi = 1, path = "runtime/mvs_colab.py",
                sha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(runtime)).ToLowerInvariant(),
                transport = ColabCompatibility.Wire, appVersion = ReleaseInfo.Version, engineVersion = ReleaseInfo.EngineVersion,
                formulaHash = OutputExporter.FormulaHash, stateSchema = ReleaseInfo.StateSchema }));
            using (Stream controller = zip.CreateEntry("runtime/mvs_colab.py", CompressionLevel.Optimal).Open()) controller.Write(runtime);
            using Stream output = zip.CreateEntry("cli-source.zip", CompressionLevel.Optimal).Open(); output.Write(sourceBytes);
        }
        File.Move(temporary, target, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private ColabHttpReply HandleColabRequest(string token, string route, byte[] bytes)
    {
        // Status import, token revocation and command changes are serialized together.
        lock (colabGate)
        {
            ColabSession? session = Sessions.ByToken(token);
            if (session == null || session.Phase == "disconnected" || !colabPlans.TryGetValue(session.Key, out ColabRunPlan? plan))
                return ColabBridge.Error(403, "connection_revoked", "The connection code expired or was revoked. Keep MVS open, copy a fresh code and reconnect the first notebook cell.");
            if (route == "hello") return new(Encoding.UTF8.GetBytes(ScientificJson.Serialize(new { transport = ColabCompatibility.Wire, jobKey = plan.Key })));
            if (route == "job") return new(Encoding.UTF8.GetBytes(ScientificJson.Serialize(new { archive = Convert.ToBase64String(File.ReadAllBytes(Sessions.ArchivePath(plan.Key))) })));
            if (route == "request") return new(Encoding.UTF8.GetBytes(ScientificJson.Serialize(plan with {
                RequestedAction = session.RequestedAction, CommandId = session.CommandId })));
            using JsonDocument doc = JsonDocument.Parse(bytes); JsonElement root = doc.RootElement;
            string Value(string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()! : "";
            if (Value("key") != plan.Key) throw new ColabProtocolException(409, "wrong_job", "This notebook controls a different prepared job. Reconnect explicitly.");
            ColabCompatibility.ValidatePeer(root, Value("revision"));
            long sequence = root.GetProperty("sequence").GetInt64();
            int? percent = root.TryGetProperty("percent", out var pct) && pct.ValueKind != JsonValueKind.Null ? pct.GetInt32() : null;
            bool controls = root.TryGetProperty("controlsReady", out var ready) && ready.ValueKind == JsonValueKind.True;
            string packetHash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
            if (Sessions.IsExactStatusRetry(token, plan.Key, Value("epoch"), sequence, packetHash))
                return new(Encoding.UTF8.GetBytes("{\"ok\":true,\"duplicate\":true}"));
            if (session.Epoch.Length > 0 && session.Epoch != Value("epoch"))
                throw new ColabProtocolException(409, "runtime_conflict", "Another runtime owns this code. Stop the old controller and reconnect with a fresh code.");
            if (sequence <= session.Sequence)
                throw new ColabProtocolException(409, "stale_status", "A different or delayed status used an old sequence. Reconnect this notebook; do not reuse its code in a second runtime.");
            Sessions.CheckObservation(token, plan.Key, Value("epoch"), Value("commandId"), sequence);
            string calibrationBytes = Value("calibrationBase64"), result = Value("resultsBase64");
            string incoming = Sessions.CalibrationPath(plan.Key) + ".incoming-" + Guid.NewGuid().ToString("N");
            byte[]? resultBytes = null, manifestBytes = null;
            try
            {
                if (calibrationBytes.Length > 0)
                {
                    byte[] decoded = Convert.FromBase64String(calibrationBytes);
                    if (decoded.Length > 8 * 1024 * 1024) throw new InvalidDataException("Unexpected calibration size.");
                    File.WriteAllBytes(incoming, decoded); CalibrationState state = CalibrationPersistence.Read(incoming);
                    if (state.DatasetHash != plan.DatasetHash || state.SettingsHash != plan.SettingsHash || state.Repetitions != plan.Repetitions)
                        throw new InvalidDataException("Calibration belongs to a different job.");
                }
                if (result.Length > 0)
                {
                    resultBytes = Convert.FromBase64String(result); manifestBytes = Convert.FromBase64String(Value("manifestBase64"));
                    ValidateColabResults(resultBytes, manifestBytes, plan);
                }
                // A rejected result cannot create a successful completion state.
                if (File.Exists(incoming)) File.Move(incoming, Sessions.CalibrationPath(plan.Key), true);
                if (resultBytes != null && manifestBytes != null)
                {
                    ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(plan.Key), "results.json"), Encoding.UTF8.GetString(resultBytes));
                    ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(plan.Key), "run_manifest.json"), Encoding.UTF8.GetString(manifestBytes));
                }
                Sessions.Observe(token, plan.Key, Value("notebookUrl"), Value("epoch"), Value("phase"), Value("commandId"), sequence,
                    percent, Value("message"), Value("runtime"), controls, packetHash);
            }
            finally { if (File.Exists(incoming)) File.Delete(incoming); }
            if (!IsDisposed && IsHandleCreated)
            {
                try { BeginInvoke(new Action(() => {
                    if (IsDisposed) return;
                    if (calibrationBytes.Length > 0 || result.Length > 0) ReceiveColabState(plan);
                    RefreshColabButtons(); RefreshColabPanel();
                })); }
                catch (InvalidOperationException) { /* Window closed after dispatch; the verified files are retained. */ }
            }
            return new(Encoding.UTF8.GetBytes("{\"ok\":true}"));
        }
    }
    private void RefreshColabArchiveCalibration(ColabRunPlan plan)
    {
        if (!Sessions.HasCalibration(plan.Key, plan.DatasetHash, plan.SettingsHash, plan.Repetitions)) return;
        string archive = Sessions.ArchivePath(plan.Key), temporary = archive + ".refresh-" + Guid.NewGuid().ToString("N");
        try
        {
            File.Copy(archive, temporary);
            using (ZipArchive zip = ZipFile.Open(temporary, ZipArchiveMode.Update))
            {
                string name = "calibration/" + CalibrationPersistence.FileName;
                zip.GetEntry(name)?.Delete();
                zip.CreateEntryFromFile(Sessions.CalibrationPath(plan.Key), name, CompressionLevel.Optimal);
            }
            File.Move(temporary, archive, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    private void ReceiveColabState(ColabRunPlan plan)
    {
        if (localOperationInProgress)
        {
            statusLabel.Text = T("Colab files received separately — local calculation is unchanged.", "Файлы Colab получены отдельно — локальный расчёт не изменён.");
            return;
        }
        if (data == null || plan.Kind != "standard") { RefreshColabButtons(); return; }
        try
        {
            if (plan.DatasetHash != datasetHash || plan.SettingsHash != SettingsContract.Fingerprint(settings) ||
                !Sessions.HasCalibration(plan.Key, datasetHash, plan.SettingsHash, plan.Repetitions)) { RefreshColabButtons(); return; }
            CalibrationState state = CalibrationPersistence.Read(Sessions.CalibrationPath(plan.Key));
            bool first = calibration == null || lastCalibrationRepetitions != state.Repetitions || calibrationSettingsHash != state.SettingsHash;
            calibration = state.Rows; lastCalibrationRepetitions = state.Repetitions; selectedCalibrationRepetitions = state.Repetitions;
            calibrationSource = state.CalibrationSource; calibrationSettingsHash = state.SettingsHash;
            if (first) { lastArtifacts.Clear(); lastFigureFiles.Clear(); analysisHalf = state.SplitCalibration ? AnalysisEngine.SplitEntities(data, state.Seed).Analysis : null; results = null; }
            string resultPath = Path.Combine(Sessions.DirectoryFor(plan.Key), "results.json");
            if (File.Exists(resultPath))
            {
                results = ValidateColabResults(File.ReadAllBytes(resultPath), File.ReadAllBytes(Path.Combine(Sessions.DirectoryFor(plan.Key), "run_manifest.json")), plan);
                if (!lastArtifacts.Any(a => a.FullPath == resultPath)) lastArtifacts.Add(OutputExporter.FromFile("Colab results", resultPath));
            }
            RefreshColabButtons();
            if (first && activePage == "calibration") Navigate("calibration");
            statusLabel.Text = results != null ? T("Colab results received — open Results", "Получены результаты Colab — откройте «Результаты»") : T("Colab calibration verified", "Калибровка Colab проверена");
        }
        catch (Exception error) { statusLabel.Text = "Colab: " + error.Message; }
    }
    private void ImportColabBundle()
    {
        using var pick = new OpenFileDialog { Filter = "MVS Colab results (*.zip)|*.zip" };
        if (pick.ShowDialog(ColabDialogOwner) != DialogResult.OK) return;
        try
        {
            using ZipArchive zip = ZipFile.OpenRead(pick.FileName);
            ZipArchiveEntry entry = zip.Entries.FirstOrDefault(e => e.FullName == "calibration/calibration_state.json") ?? throw new InvalidDataException("The archive has no calibration state.");
            if (entry.Length > 8 * 1024 * 1024) throw new InvalidDataException("Unexpected calibration size.");
            string temporary = Path.GetTempFileName();
            try
            {
                entry.ExtractToFile(temporary, true); CalibrationState state = CalibrationPersistence.Read(temporary);
                if (data == null || state.DatasetHash != datasetHash || state.SettingsHash != SettingsContract.Fingerprint(settings)) throw new InvalidDataException(T("Load the matching dataset and settings first.", "Сначала загрузите соответствующие данные и настройки."));
                string key = CalibrationKey(state.Repetitions); Sessions.GetOrCreate(key, "standard", "analyze"); Directory.CreateDirectory(Sessions.DirectoryFor(key));
                var plan = new ColabRunPlan(key, "standard", "analyze", state.DatasetHash, state.SettingsHash, state.Repetitions, Array.Empty<string>());
                ZipArchiveEntry? result = zip.GetEntry("analysis/results.json");
                if (result != null)
                {
                    ZipArchiveEntry manifest = zip.GetEntry("analysis/run_manifest.json") ?? throw new InvalidDataException("The result manifest is missing.");
                    byte[] resultBytes = ReadColabEntry(result), manifestBytes = ReadColabEntry(manifest);
                    ValidateColabResults(resultBytes, manifestBytes, plan);
                    ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(key), "results.json"), Encoding.UTF8.GetString(resultBytes));
                    ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(key), "run_manifest.json"), Encoding.UTF8.GetString(manifestBytes));
                }
                File.Copy(temporary, Sessions.CalibrationPath(key), true);
                colabPanelKey = key;
                ReceiveColabState(plan);
                if (result != null) lastArtifacts.Add(OutputExporter.FromFile("Colab result archive", pick.FileName));
                Navigate(results == null ? "calibration" : "results");
            }
            finally { File.Delete(temporary); }
        }
        catch (Exception error) { MessageBox.Show(ColabDialogOwner, error.Message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private static byte[] ReadColabEntry(ZipArchiveEntry entry)
    {
        if (entry.Length > 8 * 1024 * 1024) throw new InvalidDataException("Unexpected result size.");
        using Stream input = entry.Open(); using var output = new MemoryStream(); byte[] buffer = new byte[8192]; int read;
        while ((read = input.Read(buffer)) > 0)
        { if (output.Length + read > 8 * 1024 * 1024) throw new InvalidDataException("Unexpected expanded result size."); output.Write(buffer, 0, read); }
        return output.ToArray();
    }
    private static List<ResultRow> ValidateColabResults(byte[] bytes, byte[] manifestBytes, ColabRunPlan plan)
    {
        using JsonDocument manifest = JsonDocument.Parse(manifestBytes); JsonElement info = manifest.RootElement;
        if (info.GetProperty("inputData").GetProperty("sha256").GetString() != plan.DatasetHash ||
            info.GetProperty("calibration").GetProperty("settingsHash").GetString() != plan.SettingsHash ||
            info.GetProperty("calibration").GetProperty("repetitions").GetInt32() != plan.Repetitions)
            throw new InvalidDataException("The result belongs to different input data or calibration settings.");
        string hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        bool covered = info.GetProperty("files").EnumerateArray().Any(file =>
            file.GetProperty("FileName").GetString() == "results.json" && file.GetProperty("sha256").GetString() == hash && file.GetProperty("SizeBytes").GetInt64() == bytes.LongLength);
        if (!covered) throw new InvalidDataException("The results checksum does not match its manifest.");
        using JsonDocument result = JsonDocument.Parse(bytes); JsonElement root = result.RootElement;
        if (root.GetProperty("schemaVersion").GetInt32() != ReleaseInfo.StateSchema || root.GetProperty("policy").GetString() != DecisionPolicy.Id)
            throw new InvalidDataException("Incompatible result table.");
        List<ResultRow> rows = JsonSerializer.Deserialize<List<ResultRow>>(root.GetProperty("rows").GetRawText(), ScientificJson.Options) ?? throw new InvalidDataException("Empty result table.");
        if (rows.Count != AnalysisEngine.MetricKeys.Length || rows.Any(row => row == null) ||
            !rows.Select(row => row.Metric).ToHashSet(StringComparer.Ordinal).SetEquals(AnalysisEngine.MetricKeys))
            throw new InvalidDataException("The result metric registry is incomplete or incompatible.");
        return rows;
    }
    private static void OpenBrowser(string url) => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
}
