using System.Globalization;
using System.Text;

namespace MvsAnalyzer;

internal sealed partial class MainForm : Form
{
    private readonly AppSettings settings;
    private readonly Panel sidebar = new() { Dock = DockStyle.Left, Width = 218, Padding = new Padding(10, 12, 10, 10), AutoScroll = true };
    private readonly Panel topbar = new() { Dock = DockStyle.Top, Height = 46, Padding = new Padding(18, 5, 20, 5) };
    private readonly Panel host = new BufferedPanel { Dock = DockStyle.Fill, Padding = new Padding(24, 20, 24, 20) };
    private readonly Panel statusbar = new() { Dock = DockStyle.Bottom, Height = 31, Padding = new Padding(18, 6, 18, 4) };
    private readonly Label statusLabel = new() { AutoSize = true };
    private readonly Label projectStatus = new() { AutoSize = true, TextAlign = ContentAlignment.MiddleRight, Dock = DockStyle.Right, Padding = new Padding(0, 8, 0, 0) };
    private readonly Dictionary<string, Panel> navItems = new();
    private readonly List<RunRecord> history = new();
    private FlowLayoutPanel? currentPage;
    private string activePage = "home";
    private string projectName = "Untitled project";
    private string projectDescription = "";
    private string projectMode = "Exploratory";
    private string datasetName = "No dataset";
    private string datasetHash = "";
    private string auditFolder = "";
    private AuditReport? auditReport;
    private AnalysisData? data;
    private List<CalibrationRow>? calibration;
    private List<ResultRow>? results;
    private int lastCalibrationRepetitions;
    private AnalysisData? analysisHalf;
    private string calibrationSource = "same_dataset";
    private readonly List<string> lastFigureFiles = new();
    private readonly List<OutputArtifact> lastArtifacts = new();

    // "System" now follows the Windows apps theme, not the high-contrast flag.
    private static bool SystemUsesDarkTheme()
    {
        try { object? value = Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1); return value is int flag && flag == 0; }
        catch { return false; }
    }
    private bool Dark => settings.Theme == "dark" || (settings.Theme == "system" && (SystemUsesDarkTheme() || SystemInformation.HighContrast));
    private Color Bg => Dark ? Color.FromArgb(31, 31, 31) : Color.FromArgb(246, 247, 249);
    private Color Surface => Dark ? Color.FromArgb(43, 43, 43) : Color.White;
    private Color TextColor => Dark ? Color.FromArgb(245, 245, 245) : Color.FromArgb(36, 36, 36);
    private Color Secondary => Dark ? Color.FromArgb(190, 190, 190) : Color.FromArgb(97, 97, 97);
    private Color Border => Dark ? Color.FromArgb(66, 66, 66) : Color.FromArgb(224, 224, 224);
    private Color Accent => Color.FromArgb(15, 108, 189);
    private Color AccentLight => Dark ? Color.FromArgb(31, 74, 108) : Color.FromArgb(232, 242, 252);
    private Color SuccessBg => Dark ? Color.FromArgb(35, 82, 48) : Color.FromArgb(226, 243, 228);
    private Color NeutralBadge => Dark ? Color.FromArgb(62, 62, 62) : Color.FromArgb(242, 242, 242);
    private string T(string en, string ru) => settings.Language == "ru" ? ru : en;
    private bool Guided => settings.InterfaceMode == "guided";
    private bool Expert => settings.InterfaceMode == "expert";

    public MainForm(AppSettings appSettings, bool layoutTest = false)
    {
        layoutTestMode = layoutTest; settings = appSettings; projectName = T("Untitled project", "Безымянный проект"); Text = "MVS Analyzer — Release v1.4.0 · Engine 1.6.0"; try { Icon = Branding.AppIcon ?? System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { } StartPosition = FormStartPosition.CenterScreen; AutoScaleMode = AutoScaleMode.Dpi;
        MinimumSize = new Size(1040, 680); ClientSize = new Size(1240, 780); Font = new Font("Segoe UI", 10);
        DoubleBuffered = true; KeyPreview = true; if (!layoutTest) RestoreWindow();
        host.Resize += (_, _) => FitContentWidth();
        FormClosing += (_, _) => { if (!layoutTest) SaveWindow(); colabBridge?.Dispose(); };
        BuildShell(); ApplyModeVisibility(); ApplyTheme(); Navigate("home");
        Shown += (_, _) => FitContentWidth();
        DpiChanged += (_, _) => { foreach (var item in colabButtons) if (!item.Button.IsDisposed) item.Button.Image = Branding.ColabIcon(DeviceDpi); FitContentWidth(); };
    }

    private void BuildShell()
    {
        var brand = new Label { Text = "MVS Analyzer", Font = new Font("Segoe UI", 12, FontStyle.Bold), AutoSize = false, Size = new Size(188, 26), Location = new Point(14, 10) };
        var brandSub = new Label { Text = "Release v1.4.0 · Engine 1.6.0", Font = new Font("Segoe UI", 8), AutoSize = false, Size = new Size(188, 18), Location = new Point(15, 34), ForeColor = Secondary };
        sidebar.Controls.Add(brand); sidebar.Controls.Add(brandSub);
        int y = 62;
        AddNav("home", "\uE80F", T("Home", "Главная"), y, () => Navigate("home")); y += 46;
        AddNav("project", "\uE8B7", T("Project", "Проект"), y, () => Navigate("project")); y += 46;
        AddNav("data", "\uE80A", T("Data", "Данные"), y, () => Navigate("data")); y += 46;
        AddNav("calibration", "\uE9D9", T("Calibration", "Калибровка"), y, () => Navigate("calibration")); y += 46;
        AddNav("analysis", "\uE768", T("Run", "Запуск"), y, () => Navigate("analysis")); y += 46;
        AddNav("colab", "\uE753", "Google Colab", y, () => ShowColabPanel()); y += 46;
        AddNav("results", "\uE9D2", T("Results", "Результаты"), y, () => Navigate("results")); y += 46;
        AddNav("figures", "\uEB9F", T("Figures", "Графики"), y, () => Navigate("figures")); y += 46;
        AddNav("outputs", "\uE74E", T("Outputs", "Файлы"), y, () => Navigate("outputs")); y += 46;
        AddNav("history", "\uE81C", T("History", "История"), y, () => Navigate("history")); y += 46;
        AddNav("audit", "\uE72E", T("Audit", "Аудит"), y, () => Navigate("audit")); y += 56;
        AddNav("plugins", "\uE74C", T("Plugins", "Плагины"), y, () => Navigate("plugins")); y += 46;
        AddNav("settings", "\uE713", T("Settings", "Настройки"), y, () => Navigate("settings")); y += 46;
        AddNav("help", "\uE897", T("Help", "Справка"), y, () => Navigate("help"));

        sidebar.Paint += (_, e) => { using var pen = new Pen(Border); e.Graphics.DrawLine(pen, sidebar.Width - 1, 0, sidebar.Width - 1, sidebar.Height); };
        topbar.Paint += (_, e) => { using var pen = new Pen(Border); e.Graphics.DrawLine(pen, 0, topbar.Height - 1, topbar.Width, topbar.Height - 1); };
        statusbar.Paint += (_, e) => { using var pen = new Pen(Border); e.Graphics.DrawLine(pen, 0, 0, statusbar.Width, 0); };
        topbar.Controls.Add(projectStatus);
        statusLabel.Text = T("Local calculations · Hosted notebooks upload data only when you choose · v1.4.0", "Локальные расчёты · Внешний ноутбук загружает данные по вашему выбору · v1.4.0");
        statusbar.Controls.Add(statusLabel);
        Controls.Add(host); Controls.Add(statusbar); Controls.Add(topbar); Controls.Add(sidebar);
    }

    private void AddNav(string key, string glyph, string text, int y, Action action)
    {
        var panel = new Panel { Location = new Point(8, y), Size = new Size(198, 40), Cursor = Cursors.Hand };
        var marker = new Panel { Name = "marker", Location = new Point(0, 6), Size = new Size(3, 28), BackColor = Color.Transparent };
        var icon = new Label { Text = glyph, Font = new Font("Segoe MDL2 Assets", 12), Location = new Point(14, 10), Size = new Size(24, 22), Cursor = Cursors.Hand };
        var label = new Label { Name = "navText", Text = text, Location = new Point(45, 9), Size = new Size(145, 24), Cursor = Cursors.Hand };
        EventHandler click = (_, _) => action(); panel.Click += click; icon.Click += click; label.Click += click;
        EventHandler enter = (_, _) => { if (activePage != key) panel.BackColor = NeutralBadge; };
        EventHandler leave = (_, _) => { if (activePage != key) panel.BackColor = Color.Transparent; };
        panel.MouseEnter += enter; icon.MouseEnter += enter; label.MouseEnter += enter;
        panel.MouseLeave += leave; icon.MouseLeave += leave; label.MouseLeave += leave;
        panel.Controls.Add(marker); panel.Controls.Add(icon); panel.Controls.Add(label); sidebar.Controls.Add(panel); navItems[key] = panel;
    }

    private void RefreshChromeText()
    {
        var labels = new Dictionary<string, string> {
            ["home"] = T("Home", "Главная"), ["project"] = T("Project", "Проект"), ["data"] = T("Data", "Данные"),
            ["calibration"] = T("Calibration", "Калибровка"), ["analysis"] = T("Analysis", "Анализ"), ["results"] = T("Results", "Результаты"),
            ["colab"] = "Google Colab", ["figures"] = T("Figures", "Графики"), ["outputs"] = T("Outputs", "Файлы"), ["history"] = T("History", "История"), ["audit"] = T("Audit", "Аудит"), ["plugins"] = T("Plugins", "Плагины"), ["settings"] = T("Settings", "Настройки"), ["help"] = T("Help", "Справка") };
        foreach (var pair in labels)
        {
            var label = navItems[pair.Key].Controls.Find("navText", false).FirstOrDefault(); if (label != null) label.Text = pair.Value;
        }
        statusLabel.Text = T("Local calculations · Hosted notebooks upload data only when you choose · v1.4.0", "Локальные расчёты · Внешний ноутбук загружает данные по вашему выбору · v1.4.0");
    }

    private void ApplyModeVisibility()
    {
        navItems["history"].Visible = !Guided;
        int auditTop = Guided ? navItems["history"].Top : navItems["history"].Bottom + 6;
        navItems["audit"].Top = auditTop;
        int pluginTop = auditTop + 56;
        navItems["plugins"].Top = pluginTop; navItems["settings"].Top = pluginTop + 46; navItems["help"].Top = pluginTop + 92;
    }

    private void Navigate(string key)
    {
        Redraw.Suspend(host); host.SuspendLayout();
        try
        {
        activePage = key; legacyLayouts.Clear(); foreach (var pair in navItems)
        {
            pair.Value.BackColor = pair.Key == key ? AccentLight : Color.Transparent;
            var marker = pair.Value.Controls.Find("marker", false).FirstOrDefault(); if (marker != null) marker.BackColor = pair.Key == key ? Accent : Color.Transparent;
        }
        projectStatus.Text = $"{projectName}   ·   {ProjectStage()}";
        switch (key)
        {
            case "home": ShowHome(); break; case "project": ShowProject(); break; case "data": ShowData(); break;
            case "colab": ShowColab(); break;
            case "calibration": ShowCalibration(); break; case "analysis": ShowAnalysis(); break; case "results": ShowResults(); break; case "advanced": ShowAdvancedMethods(); break;
            case "figures": ShowFigures(); break; case "outputs": ShowOutputs(); break; case "history": ShowHistory(); break; case "audit": ShowAudit(); break; case "plugins": ShowPlugins(); break; case "settings": ShowSettings(); break; case "help": ShowHelp(); break;
        }
        FitContentWidth();
        ApplyTheme();
        }
        finally { host.ResumeLayout(true); Redraw.Resume(host); }
    }
    private string ProjectStage() => results != null ? T("Results ready", "Результаты готовы") : calibration != null ? T("Ready to analyze", "Готов к анализу") : data != null ? T("Calibration required", "Нужна калибровка") : T("No data", "Нет данных");
    private FlowLayoutPanel Page(string title, string subtitle)
    {
        foreach (Control old in host.Controls.Cast<Control>().ToArray()) old.Dispose();
        host.Controls.Clear();
        foreach (CardPanel old in legacyLayouts.Keys.Where(x => x.IsDisposed).ToArray()) legacyLayouts.Remove(old);
        var page = new BufferedFlowPanel { Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(4), BackColor = Bg };
        var intro = new Panel { Name = "page-intro", Width = ContentWidth, Height = string.IsNullOrEmpty(subtitle) ? 54 : 83, Margin = new Padding(0, 0, 0, 12) };
        intro.Controls.Add(new Label { Text = title, Font = new Font("Segoe UI", 21, FontStyle.Bold), AutoSize = true, Location = new Point(0, 2) });
        if (!string.IsNullOrEmpty(subtitle)) intro.Controls.Add(new Label { Text = subtitle, AutoSize = true, MaximumSize = new Size(ContentWidth - 30, 0), ForeColor = Secondary, Location = new Point(2, 45) });
        page.Controls.Add(intro); host.Controls.Add(page); currentPage = page; FitIntro(intro); return page;
    }
    private Panel Card(string title, string subtitle, int height = 150)
    {
        var card = new CardPanel { Width = ContentWidth, Height = height, AutoScroll = false, AutoSize = false, BackColor = Surface, BorderColor = Border, Margin = new Padding(0, 0, 0, 16), Padding = new Padding(20) };
        card.Controls.Add(new Label { Text = title, Font = new Font("Segoe UI", 12, FontStyle.Bold), AutoSize = true, Location = new Point(20, 18) });
        card.Controls.Add(new Label { Text = subtitle, AutoSize = true, MaximumSize = new Size(ContentWidth - 65, 0), ForeColor = Secondary, Location = new Point(20, 50) }); return card;
    }
    private Button Button(string text, bool primary = false, int width = 190)
    {
        return new Button { Text = text, Width = width, Height = 38, FlatStyle = FlatStyle.Flat, BackColor = primary ? Accent : Surface, ForeColor = primary ? Color.White : TextColor, Location = new Point(20, 96), UseVisualStyleBackColor = false, Tag = primary ? "primary" : "secondary" };
    }
    private Label Badge(string text, Color back, int x, int y = 18) => new() { Text = text, AutoSize = true, BackColor = back, ForeColor = TextColor, Padding = new Padding(8, 4, 8, 4), Location = new Point(x, y) };
    private Label WorkflowStep(string text, Color back) => new() { Text = text, Dock = DockStyle.Fill, Margin = new Padding(5, 0, 5, 0), BackColor = back, ForeColor = TextColor, TextAlign = ContentAlignment.MiddleCenter };

    private void OpenFile()
    {
        using var dialog = new OpenFileDialog { Filter = "CSV / TSV (*.csv;*.tsv;*.txt)|*.csv;*.tsv;*.txt|All files (*.*)|*.*", Title = T("Open measurement data", "Открыть данные измерений") };
        if (dialog.ShowDialog() != DialogResult.OK) return;
        ImportProfile? importProfile = PluginAssets.Current.ImportProfiles.FirstOrDefault(x => string.Equals(x.Id, settings.ImportProfileId, StringComparison.OrdinalIgnoreCase));
        try { List<Observation> observations = CsvImporter.Read(dialog.FileName, settings.MinValue, settings.MaxValue, importProfile); data = AnalysisEngine.Build(observations, settings.MinValue, settings.MaxValue, settings.MinMeasurements); data.ImportSummary = CsvImporter.LastImportSummary; datasetPath = dialog.FileName; datasetName = Path.GetFileName(dialog.FileName); datasetHash = OutputExporter.HashFile(dialog.FileName); calibration = null; results = null; analysisHalf = null; calibrationSettingsHash = ""; lastArtifacts.Clear(); lastFigureFiles.Clear(); loadedProcessing = ProcessingSnapshot.From(settings); Navigate("data"); }
        catch (Exception ex) { MessageBox.Show(ex.Message, T("Import error", "Ошибка импорта"), MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
    private void LoadDemo()
    {
        data = AnalysisEngine.Build(AnalysisEngine.Demo(), settings.MinValue, settings.MaxValue, settings.MinMeasurements); datasetPath = ""; datasetName = "universal_example.csv"; datasetHash = ScientificMath.Hash(ScientificJson.Serialize(data.Observations)); calibration = null; results = null; analysisHalf = null; calibrationSettingsHash = ""; lastArtifacts.Clear(); lastFigureFiles.Clear(); loadedProcessing = ProcessingSnapshot.From(settings); Navigate("data");
    }

    private async Task RunCalibrationAsync(int repetitions)
    {
        if (data == null) return;
        try { SettingsContract.Validate(settings); }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS"); return; }
        if (loadedProcessing != null && loadedProcessing != ProcessingSnapshot.From(settings))
        { MessageBox.Show(this, T("Processing changed. Re-import the file before calibrating.", "Обработка изменилась. Импортируйте файл заново перед калибровкой.")); return; }
        if (!ConfirmIndependent(data.Observations)) return;
        calibration = null; results = null; analysisHalf = null; calibrationSettingsHash = ""; lastArtifacts.Clear(); lastFigureFiles.Clear();
        using var progress = new ProgressDialog(T("Calibrating MVS", "Калибровка MVS"), T("Cancel", "Отмена"), settings.Language == "ru");
        progress.UpdateProgress(new ProgressInfo(0, T("Preparing simulations", "Подготовка симуляций"), $"0 / {repetitions:N0}")); progress.Show(this); progress.Refresh(); Enabled = false; var shownAt = DateTime.UtcNow;
        try
        {
            await Task.Delay(120);
            AnalysisData source = data;
            analysisHalf = null; calibrationSource = "same_dataset";
            if (settings.SplitCalibration)
            {
                var halves = AnalysisEngine.SplitEntities(data, settings.CalibrationSeed);
                source = halves.Calibration; analysisHalf = halves.Analysis; source.ImportSummary = data.ImportSummary; analysisHalf.ImportSummary = data.ImportSummary; calibrationSource = "split_half";
            }
            var reporter = new Progress<ProgressInfo>(progress.UpdateProgress);
            calibration = await Task.Run(() => AnalysisEngine.Calibrate(source, repetitions, settings.CalibrationEffect, settings.CalibrationSeed, reporter, progress.Token, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate, settings.Alpha, AnalysisEngine.DefaultTracks));
            lastCalibrationRepetitions = repetitions;
            calibrationSettingsHash = SettingsContract.Fingerprint(settings);
            progress.UpdateProgress(new ProgressInfo(1, T("Calibration complete", "Калибровка завершена"), $"{repetitions:N0} / {repetitions:N0}"));
            int remaining = Math.Max(0, 400 - (int)(DateTime.UtcNow - shownAt).TotalMilliseconds); if (remaining > 0) await Task.Delay(remaining);
            progress.Close(); Navigate("calibration");
        }
        catch (OperationCanceledException) { progress.Close(); }
        catch (Exception ex) { progress.Close(); MessageBox.Show(ex.Message, T("Calibration failed", "Калибровка не выполнена"), MessageBoxButtons.OK, MessageBoxIcon.Error); }
        finally { Enabled = true; Activate(); }
    }

    private async Task RunAnalysisAsync()
    {
        if (data == null || calibration == null) return;
        string currentFingerprint;
        try { currentFingerprint = SettingsContract.Fingerprint(settings); }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS"); return; }
        if (calibrationSettingsHash != currentFingerprint)
        { calibration = null; results = null; analysisHalf = null; MessageBox.Show(this, T("Scientific settings changed. Recalibrate before analysing.", "Научные настройки изменились. Повторите калибровку перед анализом.")); Navigate("calibration"); return; }
        if (OutputExporter.AnyAutomaticOutput(settings) && (!settings.FigureFolderConfirmed || string.IsNullOrWhiteSpace(settings.FigureOutputFolder)))
        {
            using var folderDialog = new FolderBrowserDialog { Description = T("Choose where all analysis files will be saved", "Выберите папку для всех файлов анализа") };
            if (folderDialog.ShowDialog(this) != DialogResult.OK) { MessageBox.Show(T("Analysis was not started because an output folder was not selected.", "Анализ не запущен, потому что папка результатов не выбрана."), "MVS"); return; }
            settings.FigureOutputFolder = folderDialog.SelectedPath; settings.FigureFolderConfirmed = true; settings.Save();
        }
        using var progress = new ProgressDialog(T("Analyzing data", "Анализ данных"), T("Cancel", "Отмена"), settings.Language == "ru");
        progress.UpdateProgress(new ProgressInfo(0, T("Preparing analysis", "Подготовка анализа"), T("Validating inputs", "Проверка входных данных"))); progress.Show(this); progress.Refresh(); Enabled = false; var shownAt = DateTime.UtcNow;
        try
        {
            await Task.Delay(120); var reporter = new Progress<ProgressInfo>(info => progress.UpdateProgress(info with { Fraction = .9 * info.Fraction })); results = await Task.Run(() => AnalysisEngine.Results(analysisHalf ?? data, calibration, reporter, progress.Token, settings.Alpha, settings.EquivalenceMargin, settings.CalibrationSeed));
            lastFigureFiles.Clear(); lastArtifacts.Clear(); string? outputError = null; string? runFolder = null; string? figureWarning = null;
            if (OutputExporter.AnyAutomaticOutput(settings))
            {
                progress.UpdateProgress(new ProgressInfo(.94, T("Saving analysis files", "Сохранение файлов анализа"), settings.FigureOutputFolder));
                try
                {
                    string runId = DateTime.Now.ToString("yyyy-MM-dd_HHmmss"); runFolder = OutputExporter.PrepareRunFolder(settings, runId);
                    string statePath = Path.Combine(runFolder, CalibrationPersistence.FileName);
                    CalibrationPersistence.Write(statePath, DesktopState());
                    lastArtifacts.Add(OutputExporter.FromFile("Calibration state", statePath));
                    if (settings.GenerateFigures)
                    {
                        lastFigureFiles.AddRange(await Task.Run(() => FigureGenerator.Generate(analysisHalf ?? data, results, settings, runId, runFolder)));
                        // Only count images that really exist on disk, otherwise the manifest lies.
                        lastFigureFiles.RemoveAll(path => !File.Exists(path));
                        lastArtifacts.AddRange(lastFigureFiles.Select(path => OutputExporter.FromFile(T("Figure", "График"), path)));
                        if (lastFigureFiles.Count == 0) figureWarning = T("Figure export was enabled, but no image was written.", "Экспорт графиков включён, но ни одного изображения не создано.");
                    }
                    // Plugin report templates are rendered before the manifest so they are listed and hashed in it.
                    foreach (string report in PluginAssets.WriteReports(runFolder, runId, projectName, datasetName, analysisHalf ?? data, results, settings)) lastArtifacts.Add(OutputExporter.FromFile(T("Report", "Отчёт"), report));
                    lastArtifacts.AddRange(await Task.Run(() => OutputExporter.Export(runFolder, runId, projectName, projectDescription, projectMode, datasetName, datasetHash, analysisHalf ?? data, calibration, results, settings, lastCalibrationRepetitions, lastArtifacts, calibrationSource)));
                    RunAuditor.AppendJournal(runId, runFolder, datasetHash, settings, lastCalibrationRepetitions, string.Join(", ", results.Where(x => x.CandidateInAnyTrack).Select(x => x.Metric)));
                }
                catch (Exception ex) { outputError = ex.Message; }
            }
            progress.UpdateProgress(new ProgressInfo(1, T("Analysis complete", "Анализ завершён"), T("Preparing results", "Подготовка результатов")));
            int remaining = Math.Max(0, 400 - (int)(DateTime.UtcNow - shownAt).TotalMilliseconds); if (remaining > 0) await Task.Delay(remaining); progress.Close();
            history.Insert(0, new RunRecord(DateTime.Now, projectName, datasetName, data.TotalEntities, $"{settings.InterfaceMode} / {lastCalibrationRepetitions:N0}", string.Join(", ", results.Where(x => x.CandidateInAnyTrack).Select(x => x.Metric)))); Navigate("results");
            if (outputError != null) MessageBox.Show(T("Analysis completed, but some files could not be saved: ", "Анализ завершён, но некоторые файлы не удалось сохранить: ") + outputError, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            else if (lastArtifacts.Count > 0)
            {
                // The old message never said how many figures were written, so a silent zero looked like success.
                string summary = $"{T("Saved files", "Сохранено файлов")}: {lastArtifacts.Count}   ·   {T("figures", "графиков")}: {lastFigureFiles.Count}\n{runFolder}";
                if (figureWarning != null) summary += "\n\n" + figureWarning;
                summary += "\n\n" + T("Open the run folder?", "Открыть папку запуска?");
                if (MessageBox.Show(summary, "MVS", MessageBoxButtons.YesNo, MessageBoxIcon.Information) == DialogResult.Yes && runFolder != null) OpenFolder(runFolder);
            }
        }
        catch (OperationCanceledException) { progress.Close(); }
        catch (Exception ex) { progress.Close(); MessageBox.Show(ex.Message, T("Analysis failed", "Анализ не выполнен"), MessageBoxButtons.OK, MessageBoxIcon.Error); }
        finally { Enabled = true; Activate(); }
    }

    /// <summary>Opens a saved run folder in Explorer so the files do not have to be hunted for.</summary>
    internal static void OpenFolder(string path)
    {
        try { if (Directory.Exists(path)) System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", "\"" + path + "\"") { UseShellExecute = true }); }
        catch { }
    }

    private int ContentWidth => Math.Max(460, host.ClientSize.Width - host.Padding.Horizontal - SystemInformation.VerticalScrollBarWidth - 12);

    /// <summary>Keeps the page as wide as the window instead of a fixed 930 px column.</summary>
    private bool fittingContent;
    private void FitContentWidth()
    {
        if (currentPage == null || fittingContent || IsDisposed) return;
        fittingContent = true;
        try
        {
            int width = ContentWidth;
            currentPage.SuspendLayout();
            foreach (Control child in currentPage.Controls)
            {
                child.Width = width;
                if (child is CardPanel card && !Equals(card.Tag, "stack-card")) FitLegacyCard(card);
                if (child is ThemedTabControl tabs) { tabs.MinimumSize = new Size(0, 380); tabs.Height = Math.Max(460, host.ClientSize.Height - 90); }
                if (child.Name == "page-intro") FitIntro(child);
            }
            currentPage.ResumeLayout(true);
        }
        finally { fittingContent = false; }
    }

    private static string WindowFile => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "window.txt");

    private void RestoreWindow()
    {
        try
        {
            if (!File.Exists(WindowFile)) return;
            string[] parts = File.ReadAllText(WindowFile).Split(';');
            if (parts.Length < 3) return;
            if (int.TryParse(parts[0], out int w) && int.TryParse(parts[1], out int h) && w >= MinimumSize.Width && h >= MinimumSize.Height)
            {
                Rectangle area = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1920, 1080);
                ClientSize = new Size(Math.Min(w, area.Width), Math.Min(h, area.Height));
            }
            if (parts[2] == "max") WindowState = FormWindowState.Maximized;
        }
        catch { }
    }

    private void SaveWindow()
    {
        try
        {
            Size size = WindowState == FormWindowState.Normal ? ClientSize : RestoreBounds.Size;
            Directory.CreateDirectory(Path.GetDirectoryName(WindowFile)!);
            File.WriteAllText(WindowFile, $"{size.Width};{size.Height};{(WindowState == FormWindowState.Maximized ? "max" : "normal")}");
        }
        catch { }
    }

    /// <summary>Ctrl+1..0 jump straight to a section.</summary>
    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        var shortcuts = new Dictionary<Keys, string>
        {
            [Keys.D1] = "home", [Keys.D2] = "project", [Keys.D3] = "data", [Keys.D4] = "calibration", [Keys.D5] = "analysis",
            [Keys.D6] = "results", [Keys.D7] = "figures", [Keys.D8] = "outputs", [Keys.D9] = "audit", [Keys.D0] = "settings",
        };
        if ((keyData & Keys.Control) == Keys.Control && shortcuts.TryGetValue(keyData & Keys.KeyCode, out string? target))
        {
            Navigate(target);
            return true;
        }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    private DataGridView Grid()
    {
        var grid = new BufferedGrid
        {
            ReadOnly = true, AllowUserToAddRows = false, AllowUserToDeleteRows = false, AllowUserToResizeRows = false, AllowUserToOrderColumns = true,
            RowHeadersVisible = false, AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.DisplayedCells, ScrollBars = ScrollBars.Both, BackgroundColor = Surface,
            BorderStyle = BorderStyle.None, CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal,
            ColumnHeadersBorderStyle = DataGridViewHeaderBorderStyle.Single, ColumnHeadersHeight = 48,
            ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize,
            SelectionMode = DataGridViewSelectionMode.FullRowSelect, EnableHeadersVisualStyles = false, GridColor = Border,
        };
        grid.RowTemplate.Height = 32;
        grid.ColumnAdded += (_, e) => { e.Column.MinimumWidth = 90; };
        grid.DefaultCellStyle.Padding = new Padding(8, 0, 8, 0);
        grid.ColumnHeadersDefaultCellStyle.Padding = new Padding(8, 0, 8, 0);
        grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
        return grid;
    }
    private DataGridView CalibrationGrid(List<CalibrationRow> rows) => ModernCalibrationGrid(rows);
    private DataGridView ResultsGrid() => ModernResultsGrid();
    internal string VerdictText(string verdict) => verdict switch
    {
        "difference" => T("Difference", "\u0415\u0441\u0442\u044c \u0440\u0430\u0437\u043d\u0438\u0446\u0430"),
        "equivalent" => T("Approximately equivalent", "Приближённая эквивалентность"),
        "not_applicable" => T("Not applicable", "\u041d\u0435\u043f\u0440\u0438\u043c\u0435\u043d\u0438\u043c\u0430"),
        _ => T("Not enough data", "\u0414\u0430\u043d\u043d\u044b\u0445 \u043d\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442")
    };
    internal string MdeText(double mde) => double.IsFinite(mde) ? (mde * 100).ToString("0.#") + " %" : T("Unavailable — see status", "Недоступно — см. статус");
    private void ExportResults()
    {
        if (results == null) return; using var dialog = new SaveFileDialog { Filter = "CSV (*.csv)|*.csv", FileName = "mvs_results.csv" }; if (dialog.ShowDialog() != DialogResult.OK) return;
        File.WriteAllText(dialog.FileName, OutputExporter.ResultsCsv(results), new UTF8Encoding(true));
    }

    private void ApplyTheme()
    {
        BackColor = Bg; ForeColor = TextColor; sidebar.BackColor = Surface; topbar.BackColor = Surface; host.BackColor = Bg; statusbar.BackColor = Surface;
        ApplyThemeRecursive(this);
        statusLabel.ForeColor = Secondary; projectStatus.ForeColor = Secondary;
    }
    private void ApplyThemeRecursive(Control control)
    {
        foreach (Control child in control.Controls)
        {
            if (child is ThemedComboBox themedCombo) themedCombo.ApplyTheme(Dark, Surface, TextColor, Accent);
            else if (child is ThemedTabControl themedTabs) themedTabs.ApplyTheme(Dark, Surface, TextColor, Accent);
            else if (child is ThemedNumericUpDown themedNumber) themedNumber.ApplyTheme(Surface, TextColor);
            else if (child is DataGridView grid)
            {
                grid.EnableHeadersVisualStyles = false; grid.BackgroundColor = Surface; grid.GridColor = Border;
                grid.DefaultCellStyle.BackColor = Surface; grid.DefaultCellStyle.ForeColor = TextColor; grid.RowsDefaultCellStyle.BackColor = Surface; grid.RowsDefaultCellStyle.ForeColor = TextColor;
                grid.AlternatingRowsDefaultCellStyle.BackColor = Dark ? Color.FromArgb(49, 49, 49) : Color.FromArgb(250, 250, 250); grid.AlternatingRowsDefaultCellStyle.ForeColor = TextColor;
                grid.ColumnHeadersDefaultCellStyle.BackColor = Dark ? Color.FromArgb(55, 55, 55) : Color.FromArgb(238, 238, 238); grid.ColumnHeadersDefaultCellStyle.ForeColor = TextColor;
                grid.DefaultCellStyle.SelectionBackColor = Dark ? Color.FromArgb(38, 79, 112) : Color.FromArgb(204, 228, 247); grid.DefaultCellStyle.SelectionForeColor = TextColor;
            }
            else if (child is TextBoxBase or ComboBox or NumericUpDown or TabControl or TabPage or CheckedListBox or ListBox) { child.BackColor = Surface; child.ForeColor = TextColor; }
            else if (child is Button button)
            {
                bool primary = Equals(button.Tag, "primary"); button.UseVisualStyleBackColor = false; button.FlatStyle = FlatStyle.Flat;
                button.BackColor = primary ? Accent : Surface; button.ForeColor = primary ? Color.White : TextColor; button.FlatAppearance.BorderColor = primary ? Accent : Border;
                button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(11, 92, 163) : AccentLight;
                button.FlatAppearance.MouseDownBackColor = primary ? Color.FromArgb(9, 76, 135) : Border;
            }
            else if (child is CardPanel card) { card.BackColor = Surface; card.BorderColor = Border; }
            else if (child is Panel panel && panel != sidebar && panel != topbar && panel != statusbar && panel.Parent != sidebar) panel.BackColor = panel.Parent is CardPanel || panel.Parent?.Parent is CardPanel || panel.BorderStyle == BorderStyle.FixedSingle ? Surface : Bg;
            ApplyThemeRecursive(child);
        }
    }
}
