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
    private readonly ConcurrentDictionary<string, string> colabBindings = new();
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
        var run = ColabButton(() => StartColab(action, repetitions()));
        var reopen = Button(T("Open linked notebook", "Открыть связанный ноутбук"), false, 285);
        reopen.Click += (_, _) => OpenLinkedColab(repetitions());
        var import = Button(T("Import Colab result…", "Импортировать результат Colab…"), false, 285);
        import.Click += (_, _) => ImportColabBundle();
        page.Controls.Add(FlowCard("Google Colab", T(
            "Use Google's runtime instead of this PC. Pair once in the first cell using the connection code copied by the button. Afterwards the app tracks this MVS job; completed calibration is reused rather than repeated.",
            "Расчёт на стороне Google вместо этого ПК. Один раз вставьте в первую ячейку код подключения, который копирует кнопка. После этого приложение отслеживает задание MVS; готовая калибровка используется повторно."), run, reopen, import, status));
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
                bool busy = Sessions.Live(session, DateTime.UtcNow) && session!.Phase is "preparing" or "calibrating" or "analyzing" or "running";
                bool opening = Sessions.Pending(session, DateTime.UtcNow);
                item.Button.Enabled = !busy && !opening && !(item.Action == "calibrate" && complete);
                item.Status.Text = complete && item.Action == "calibrate"
                    ? T("✓ Calibration is complete and verified. Re-running this same calibration in Colab is disabled.", "✓ Калибровка завершена и проверена. Повторный запуск этой же калибровки в Colab отключён.")
                    : busy ? T("Colab is working. Use Open linked notebook to return to it.", "Colab выполняет расчёт. Вернуться можно кнопкой «Открыть связанный ноутбук».")
                    : opening ? T("Waiting for the notebook's first cell. The connection code is on the clipboard.", "Ожидание первой ячейки ноутбука. Код подключения находится в буфере обмена.")
                    : Sessions.Live(session, DateTime.UtcNow) ? T("Linked MVS runtime is available. The same notebook will be reused.", "Связанный runtime MVS доступен. Будет открыт тот же ноутбук.")
                    : session != null ? T("No live confirmation from Colab. Stored calibration is retained; reconnect or import the downloaded result.", "Нет подтверждения активного Colab. Сохранённая калибровка не потеряна; переподключитесь или импортируйте скачанный результат.")
                    : T("No data has been sent. Local execution remains available.", "Данные не отправлены. Локальный запуск остаётся доступен.");
            }
            catch (Exception error) { item.Button.Enabled = false; item.Status.Text = error.Message; }
        }
    }
    private void OpenLinkedColab(int repetitions)
    {
        try
        {
            ColabSession? session = Sessions.Find(CalibrationKey(repetitions));
            if (session == null || !ColabSessionStore.ValidNotebookUrl(session.NotebookUrl))
            { MessageBox.Show(this, T("No notebook has registered yet. Run the first Colab cell and keep the MVS application open.", "Ноутбук ещё не зарегистрирован. Выполните первую ячейку Colab и оставьте приложение MVS открытым.")); return; }
            OpenBrowser(session.NotebookUrl);
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS"); }
    }
    private void StartColab(string action, int repetitions, string kind = "standard", string[]? extraArguments = null)
    {
        try
        {
            if (layoutTestMode) return;
            SettingsContract.Validate(settings);
            string[] arguments = extraArguments ?? Array.Empty<string>();
            bool needsData = kind is "standard" or "variance" or "melsm";
            string source = "", inputHash = "synthetic";
            if (needsData)
            {
                if (kind == "melsm" || data == null)
                {
                    using var pick = new OpenFileDialog { Filter = "CSV / TSV (*.csv;*.tsv)|*.csv;*.tsv" };
                    if (pick.ShowDialog(this) != DialogResult.OK) return;
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
            if (kind == "standard" && action == "calibrate" && Sessions.HasCalibration(key, inputHash, fingerprint, repetitions)) { RefreshColabButtons(); return; }
            ColabSession? prior = Sessions.Find(key);
            if (Sessions.Pending(prior, DateTime.UtcNow) || Sessions.Live(prior, DateTime.UtcNow) && prior!.Phase is "preparing" or "calibrating" or "analyzing" or "running")
            { if (prior != null && ColabSessionStore.ValidNotebookUrl(prior.NotebookUrl)) OpenBrowser(prior.NotebookUrl); return; }
            if (MessageBox.Show(this, needsData
                ? T("The selected measurements and settings will be uploaded to your Google Colab runtime when you run its first cell. Allow this job?", "Выбранные измерения и настройки будут переданы в ваш Google Colab при запуске первой ячейки. Разрешить это задание?")
                : T("Open a synthetic study in Google Colab? Your measurements will not be included.", "Открыть синтетическое исследование в Google Colab? Ваши измерения передаваться не будут."), "Google Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Information) != DialogResult.Yes) return;
            ColabSession? reusable = Sessions.Live(prior, DateTime.UtcNow) && prior != null && ColabSessionStore.ValidNotebookUrl(prior.NotebookUrl) ? prior : Sessions.Reusable();
            if (reusable != null && !colabPlans.ContainsKey(reusable.Key)) reusable = null;
            ColabSession session = Sessions.GetOrCreate(key, kind, action);
            if (reusable != null)
            {
                foreach (var binding in colabBindings.Where(x => x.Value == reusable.Key).ToArray()) colabBindings[binding.Key] = key;
                colabBindings[reusable.Token] = key;
            }
            colabBindings[session.Token] = key;
            string directory = Sessions.DirectoryFor(key); Directory.CreateDirectory(directory);
            if (kind == "standard" && calibration != null && data != null && inputHash == datasetHash &&
                calibrationSettingsHash == fingerprint && lastCalibrationRepetitions == repetitions)
                CalibrationPersistence.Write(Sessions.CalibrationPath(key), DesktopState());
            var plan = new ColabRunPlan(key, kind, action, inputHash, fingerprint, repetitions, arguments);
            colabPlans[key] = plan;
            BuildColabArchive(plan, source);
            colabBridge ??= new ColabBridge(HandleColabRequest);
            string code = $"http://127.0.0.1:{colabBridge.Port}/v1/{session.Token}";
            Clipboard.SetText(code);
            string url = Sessions.Launch(key, action, reusable); OpenBrowser(url); RefreshColabButtons();
            if (reusable == null) MessageBox.Show(this, T("The connection code has been copied. Run the first Colab cell and paste it into the connection prompt. Allow browser access to this computer if asked. This is needed only once per notebook connection. Keep MVS open. If automatic connection is blocked, upload the job ZIP instead.",
                "Код подключения скопирован. Выполните первую ячейку Colab и вставьте код в появившееся поле подключения. Если браузер спросит о доступе к этому компьютеру — разрешите. Это нужно один раз на подключение ноутбука. Оставьте MVS открытым. Если соединение блокируется, загрузите ZIP задания вручную.") + "\n\n" + Sessions.ArchivePath(key), "Google Colab");
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
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
            using Stream output = zip.CreateEntry("cli-source.zip", CompressionLevel.Optimal).Open(); output.Write(sourceBytes);
        }
        File.Move(temporary, target, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private ColabHttpReply HandleColabRequest(string token, string route, byte[] bytes)
    {
        ColabSession? session = Sessions.ByToken(token);
        if (session == null || !colabPlans.TryGetValue(colabBindings.GetValueOrDefault(token, session.Key), out ColabRunPlan? plan)) return new(Array.Empty<byte>(), Status: 403);
        if (route == "job") return new(Encoding.UTF8.GetBytes(ScientificJson.Serialize(new { archive = Convert.ToBase64String(File.ReadAllBytes(Sessions.ArchivePath(plan.Key))) })));
        if (route == "request") return new(Encoding.UTF8.GetBytes(ScientificJson.Serialize(plan with { RequestedAction = Sessions.Find(plan.Key)!.RequestedAction })));
        using JsonDocument doc = JsonDocument.Parse(bytes); JsonElement root = doc.RootElement;
        string Value(string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()! : "";
        if (Value("key") != plan.Key) throw new InvalidDataException("Wrong job identity.");
        string calibrationBytes = Value("calibrationBase64");
        if (calibrationBytes.Length > 0)
        {
            byte[] decoded = Convert.FromBase64String(calibrationBytes);
            string path = Sessions.CalibrationPath(plan.Key) + ".incoming-" + Guid.NewGuid().ToString("N");
            try
            {
                File.WriteAllBytes(path, decoded); CalibrationState state = CalibrationPersistence.Read(path);
                if (state.DatasetHash != plan.DatasetHash || state.SettingsHash != plan.SettingsHash || state.Repetitions != plan.Repetitions) throw new InvalidDataException("Calibration belongs to a different job.");
                File.Move(path, Sessions.CalibrationPath(plan.Key), true);
            }
            finally { if (File.Exists(path)) File.Delete(path); }
        }
        string result = Value("resultsBase64");
        if (result.Length > 0)
        {
            byte[] decoded = Convert.FromBase64String(result);
            byte[] manifest = Convert.FromBase64String(Value("manifestBase64"));
            ValidateColabResults(decoded, manifest, plan);
            ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(plan.Key), "results.json"), Encoding.UTF8.GetString(decoded));
            ScientificJson.AtomicText(Path.Combine(Sessions.DirectoryFor(plan.Key), "run_manifest.json"), Encoding.UTF8.GetString(manifest));
        }
        Sessions.Observe(plan.Key, Value("notebookUrl"), Value("epoch"), Value("phase"));
        if (!IsDisposed && IsHandleCreated) BeginInvoke(new Action(() => ReceiveColabState(plan)));
        return new(Encoding.UTF8.GetBytes("{\"ok\":true}"));
    }
    private void ReceiveColabState(ColabRunPlan plan)
    {
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
        if (pick.ShowDialog(this) != DialogResult.OK) return;
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
                File.Copy(temporary, Sessions.CalibrationPath(key), true);
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
                ReceiveColabState(plan);
                if (result != null) lastArtifacts.Add(OutputExporter.FromFile("Colab result archive", pick.FileName));
                Navigate(results == null ? "calibration" : "results");
            }
            finally { File.Delete(temporary); }
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
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
