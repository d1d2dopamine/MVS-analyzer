using System.Globalization;
using System.Text;

namespace MvsAnalyzer;

// Page bodies live here; MainForm.cs keeps the shell: theme, navigation, shared widgets.
internal sealed partial class MainForm
{
    private void ShowHome()
    {
        var page = Page(T("Home", "Главная"), T("Start a project or continue local work. Nothing is uploaded.", "Создайте проект или продолжите локальную работу. Ничего не загружается в сеть."));
        var banner = BrandBanner(); if (banner != null) page.Controls.Add(banner);
        var start = Card(T("Start", "Начало"), T("Use a guided workflow for a new MVS analysis.", "Используйте пошаговый сценарий для нового анализа MVS."), 170);
        var newProject = Button(T("New project", "Новый проект"), true); newProject.Click += (_, _) => { projectName = T("Untitled project", "Безымянный проект"); data = null; calibration = null; results = null; Navigate("project"); };
        var demo = Button(T("Guided example", "Демонстрационный пример")); demo.Location = new Point(225, 96); demo.Click += (_, _) => LoadDemo();
        start.Controls.Add(newProject); start.Controls.Add(demo); page.Controls.Add(start);
        var workflow = Card(T("Workflow", "Порядок работы"), T("Project  →  Data  →  Calibration  →  Analysis  →  Results", "Проект  →  Данные  →  Калибровка  →  Анализ  →  Результаты"), 150);
        var steps = new TableLayoutPanel { Location = new Point(20, 89), Size = new Size(888, 38), ColumnCount = 5, RowCount = 1, BackColor = Surface };
        for (int i = 0; i < 5; i++) steps.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        steps.Controls.Add(WorkflowStep(T("1  Project", "1  Проект"), data == null ? AccentLight : SuccessBg), 0, 0);
        steps.Controls.Add(WorkflowStep(data != null ? T("✓  Data", "✓  Данные") : T("2  Data", "2  Данные"), data != null ? SuccessBg : NeutralBadge), 1, 0);
        steps.Controls.Add(WorkflowStep(calibration != null ? T("✓  Calibration", "✓  Калибровка") : T("3  Calibration", "3  Калибровка"), calibration != null ? SuccessBg : NeutralBadge), 2, 0);
        steps.Controls.Add(WorkflowStep(results != null ? T("✓  Analysis", "✓  Анализ") : T("4  Analysis", "4  Анализ"), results != null ? SuccessBg : NeutralBadge), 3, 0);
        steps.Controls.Add(WorkflowStep(results != null ? T("✓  Results", "✓  Результаты") : T("5  Results", "5  Результаты"), results != null ? SuccessBg : NeutralBadge), 4, 0); workflow.Controls.Add(steps); page.Controls.Add(workflow);
        var principle = Card(T("What MVS does", "Что делает MVS"), T("MVS evaluates metric suitability for the current data context. Observed p-values are reported separately and never determine the MVS Score.", "MVS оценивает пригодность метрик для текущего контекста данных. Наблюдаемые p-value выводятся отдельно и не определяют MVS Score."), 120); page.Controls.Add(principle);
    }

    // Optional branding: when the embedded wordmark is missing the page simply starts with its first card.
    private Panel? BrandBanner()
    {
        Image? art = Branding.Banner;
        if (art == null) return null;
        int height = 96;
        int width = (int)Math.Round(art.Width * (height / (double)art.Height));
        var holder = new Panel { Width = ContentWidth, Height = height + 12, Margin = new Padding(0, 0, 0, 4) };
        holder.Controls.Add(new PictureBox { Image = art, SizeMode = PictureBoxSizeMode.Zoom, Size = new Size(width, height), Location = new Point(0, 0), BackColor = Color.Transparent });
        return holder;
    }

    private void ShowProject()
    {
        var page = Page(T("Project", "Проект"), T("Describe the study before importing data.", "Опишите исследование перед импортом данных."));
        var card = Card(T("Project details", "Сведения о проекте"), T("These fields are included in the local analysis manifest.", "Эти поля включаются в локальный манифест анализа."), 310);
        card.Controls.Add(new Label { Text = T("Project name", "Название проекта"), AutoSize = true, Location = new Point(20, 90) });
        var name = new TextBox { Text = projectName, Location = new Point(20, 115), Width = 430 };
        card.Controls.Add(new Label { Text = T("Description", "Описание"), AutoSize = true, Location = new Point(20, 153) });
        var description = new TextBox { Text = projectDescription, Location = new Point(20, 177), Width = 650, Height = 48, Multiline = true };
        card.Controls.Add(new Label { Text = T("Mode", "Режим"), AutoSize = true, Location = new Point(690, 90) });
        var mode = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(690, 115), Width = 190 }; mode.Items.AddRange(new object[] { "Exploratory", "Confirmatory" }); mode.SelectedItem = projectMode;
        void SaveProject() { projectName = string.IsNullOrWhiteSpace(name.Text) ? "Untitled project" : name.Text.Trim(); projectDescription = description.Text.Trim(); projectMode = mode.SelectedItem?.ToString() ?? "Exploratory"; projectStatus.Text = $"{projectName}   ·   {ProjectStage()}"; }
        name.TextChanged += (_, _) => SaveProject(); description.TextChanged += (_, _) => SaveProject(); mode.SelectedIndexChanged += (_, _) => SaveProject();
        card.Controls.Add(new Label { Text = T("Changes are saved as you type.", "Изменения сохраняются сразу."), AutoSize = true, ForeColor = Secondary, Location = new Point(20, 252) });
        card.Controls.Add(name); card.Controls.Add(description); card.Controls.Add(mode); page.Controls.Add(card);
        var next = Card(T("Next step", "Следующий шаг"), T("Import trial-level measurement data or use the guided example.", "Импортируйте данные измерений по пробам или используйте пример."), 155); var go = Button(T("Continue to Data", "Перейти к данным"), true); go.Location = new Point(20, 105); go.Click += (_, _) => Navigate("data"); next.Controls.Add(go); page.Controls.Add(next);
    }

    private void ShowData()
    {
        var page = Page(T("Data", "Данные"), T("Import, recognize and verify the dataset before calibration.", "Импортируйте, распознайте и проверьте данные перед калибровкой."));
        var import = Card(T("Data source", "Источник данных"), T("Supported now: CSV and TSV. The original file is never modified.", "Сейчас поддерживаются CSV и TSV. Исходный файл никогда не изменяется."), 170);
        var open = Button(T("Open CSV / TSV", "Открыть CSV / TSV"), true); open.Location = new Point(20, 110); open.Click += (_, _) => OpenFile();
        var demo = Button(T("Load guided example", "Загрузить пример")); demo.Location = new Point(225, 110); demo.Click += (_, _) => LoadDemo(); import.Controls.Add(open); import.Controls.Add(demo);
        List<ImportProfile> importProfiles = PluginAssets.Current.ImportProfiles;
        if (importProfiles.Count > 0)
        {
            import.Controls.Add(new Label { Text = T("Import profile", "Профиль импорта"), AutoSize = true, ForeColor = Secondary, Location = new Point(445, 90) });
            var profileBox = new ThemedComboBox { Location = new Point(445, 112), Width = 300 };
            profileBox.Items.Add(T("Built-in recognition", "Встроенное распознавание"));
            foreach (ImportProfile item in importProfiles) profileBox.Items.Add(item.Name);
            int chosenProfile = importProfiles.FindIndex(x => string.Equals(x.Id, settings.ImportProfileId, StringComparison.OrdinalIgnoreCase));
            profileBox.SelectedIndex = chosenProfile >= 0 ? chosenProfile + 1 : 0;
            profileBox.SelectedIndexChanged += (_, _) => { settings.ImportProfileId = profileBox.SelectedIndex <= 0 ? "" : importProfiles[profileBox.SelectedIndex - 1].Id; settings.Save(); };
            import.Controls.Add(profileBox);
        }
        page.Controls.Add(import);
        if (data == null)
        {
            var empty = Card(T("No dataset loaded", "Данные не загружены"), T("Expected columns include participant/subject/id, rt/rt_ms/reaction_time and group/condition.", "Ожидаются столбцы participant/subject/id, rt/rt_ms/reaction_time и group/condition."), 120); page.Controls.Add(empty); return;
        }
        var summary = Card(T("Recognition summary", "Результат распознавания"), $"{datasetName}   ·   {data.ValidRows:N0} {T("valid rows", "валидных строк")}   ·   {data.TotalEntities} {PluginAssets.Term("entities", T("entities", "объектов"))}", 265);
        var grid = Grid(); grid.Location = new Point(20, 82); grid.Size = new Size(885, 145); grid.Columns.Add("field", T("Field", "Поле")); grid.Columns.Add("value", T("Detected value", "Распознано"));
        grid.Rows.Add(T("Entity", "Объект"), data.EntityColumn); grid.Rows.Add(T("Measurement value", "Значение измерения"), data.ValueColumn); grid.Rows.Add(T("Group", "Группа"), data.GroupColumn); grid.Rows.Add(T("Distribution proxy", "Оценка распределения"), data.DistributionProxy); summary.Controls.Add(grid); page.Controls.Add(summary);
        List<string> pluginIssues = PluginAssets.Check(data, settings.Language == "ru");
        var quality = Card(T("Data quality", "Качество данных"), T("All checks must be reviewed before calibration.", "Перед калибровкой необходимо просмотреть проверки."), pluginIssues.Count > 0 ? 290 : 230);
        if (pluginIssues.Count > 0) quality.Controls.Add(new Label { Text = T("Plugin checks: ", "Проверки плагинов: ") + string.Join("   ·   ", pluginIssues), AutoSize = true, MaximumSize = new Size(840, 0), ForeColor = Color.FromArgb(176, 66, 27), Location = new Point(20, 158) });
        quality.Controls.Add(Badge($"✓ Value {settings.MinValue}–{settings.MaxValue}", SuccessBg, 20, 88)); quality.Controls.Add(Badge($"✓ Min measurements: {settings.MinMeasurements}", SuccessBg, 190, 88));
        quality.Controls.Add(new Label { Text = $"{string.Join("   ·   ", data.GroupNames.Select((g, i) => $"{g}: {data.GroupCounts[i]}"))}   ·   {T("Median measurements", "Медиана измерений")}: {data.MedianMeasurements:0}", AutoSize = true, Location = new Point(20, 130), ForeColor = Secondary });
        var calibrate = Button(T("Continue to Calibration", "Перейти к калибровке"), true, 230); calibrate.Location = new Point(20, pluginIssues.Count > 0 ? 228 : 170); calibrate.Click += (_, _) => Navigate("calibration"); quality.Controls.Add(calibrate); page.Controls.Add(quality);
        if (!Guided)
        {
            var protocol = Card(T("Cleaning protocol", "Протокол очистки"), T("Laboratory/Expert view records the active rules without modifying the source file.", "Режим Laboratory/Expert фиксирует активные правила, не изменяя исходный файл."), 145);
            protocol.Controls.Add(new Label { Text = $"Value: {settings.MinValue}–{settings.MaxValue}   ·   {T("Minimum measurements", "Минимум измерений")}: {settings.MinMeasurements}   ·   {T("Invalid rows excluded", "Невалидные строки исключаются")}", AutoSize = true, Location = new Point(20, 92), ForeColor = Secondary });
            page.Controls.Add(protocol);
        }
    }

    private void ShowCalibration()
    {
        var page = Page(T("Calibration", "Калибровка"), T("Estimate metric behavior for this exact data structure before analysis.", "Оцените поведение метрик для этой структуры данных перед анализом."));
        if (data == null)
        {
            var missing = Card(T("Data required", "Нужны данные"), T("Import and verify a dataset before creating a calibration profile.", "Перед созданием профиля импортируйте и проверьте данные."), 160); var go = Button(T("Go to Data", "Перейти к данным"), true); go.Location = new Point(20, 108); go.Click += (_, _) => Navigate("data"); missing.Controls.Add(go); page.Controls.Add(missing); return;
        }
        var profile = Card(T("Calibration profile", "Профиль калибровки"), $"{datasetName}   ·   {data.TotalEntities} {T("entities", "объектов")}   ·   {data.DistributionProxy}", Expert ? 245 : 215);
        profile.Controls.Add(new Label { Text = T("Depth", "Глубина"), AutoSize = true, Location = new Point(20, 86) });
        var repetitionOptions = Guided ? new List<int> { 2000 } : Expert ? new List<int> { 500, 2000, 10000, settings.CustomRepetitions } : new List<int> { 500, 2000, 10000 };
        var depth = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 110), Width = 250 };
        if (Guided) depth.Items.Add(T("Standard — 2,000 (recommended)", "Стандартно — 2 000 (рекомендуется)"));
        else { depth.Items.Add(T("Quick — 500", "Быстро — 500")); depth.Items.Add(T("Standard — 2,000", "Стандартно — 2 000")); depth.Items.Add(T("Thorough — 10,000", "Тщательно — 10 000")); if (Expert) depth.Items.Add($"Custom — {settings.CustomRepetitions:N0}"); }
        depth.SelectedIndex = Guided ? 0 : 1;
        var hint = new Label { Text = Guided ? T("Safe defaults are locked in Guided mode.", "В режиме Guided используются безопасные значения по умолчанию.") : T("Standard is recommended for ordinary laboratory work.", "Standard рекомендуется для обычной лабораторной работы."), AutoSize = true, ForeColor = Secondary, Location = new Point(290, 114) };
        if (Expert) profile.Controls.Add(new Label { Text = $"Seed: {settings.CalibrationSeed}   ·   Effect multiplier: {settings.CalibrationEffect:0.00}", AutoSize = true, ForeColor = Secondary, Location = new Point(20, 153) });
        var run = Button(T("Run calibration", "Запустить калибровку"), true); run.Location = new Point(20, Expert ? 190 : 160); run.Click += async (_, _) => await RunCalibrationAsync(repetitionOptions[depth.SelectedIndex]);
        profile.Controls.Add(depth); profile.Controls.Add(hint); profile.Controls.Add(run); page.Controls.Add(profile);
        if (calibration != null)
        {
            var output = Card(T("Local calibration results", "Результаты локальной калибровки"), T("Observed p-values are not used in these scores.", "Наблюдаемые p-value не используются в этих оценках."), 350);
            var grid = CalibrationGrid(calibration.OrderByDescending(x => x.Score).ToList()); grid.Location = new Point(20, 82); grid.Size = new Size(885, 220); output.Controls.Add(grid);
            var analyze = Button(T("Continue to Analysis", "Перейти к анализу"), true, 210); analyze.Location = new Point(20, 306); analyze.Click += (_, _) => Navigate("analysis"); output.Controls.Add(analyze); page.Controls.Add(output);
        }
    }

    private void ShowAnalysis()
    {
        var page = Page(T("Run", "Запуск"), T("Review the locked run summary before calculating results.", "Проверьте итоговую конфигурацию перед расчётом результатов."));
        if (calibration == null || data == null)
        {
            var missing = Card(T("Calibration required", "Требуется калибровка"), T("Analysis remains locked until a local calibration profile is complete.", "Анализ недоступен, пока не завершён локальный профиль калибровки."), 160); var go = Button(T("Go to Calibration", "Перейти к калибровке"), true, 210); go.Location = new Point(20, 108); go.Click += (_, _) => Navigate("calibration"); missing.Controls.Add(go); page.Controls.Add(missing); return;
        }
        var summary = Card(T("Run summary", "Сводка запуска"), T("All ten metrics will be calculated. Candidate selection uses calibration only.", "Будут рассчитаны все десять метрик. Выбор кандидатов использует только калибровку."), 300);
        var grid = Grid(); grid.Location = new Point(20, 82); grid.Size = new Size(885, 162); grid.Columns.Add("item", T("Item", "Параметр")); grid.Columns.Add("value", T("Value", "Значение"));
        grid.Rows.Add(T("Project", "Проект"), projectName); grid.Rows.Add(T("Dataset", "Датасет"), datasetName); grid.Rows.Add(T("Design", "Дизайн"), data.GroupNames.Length + " independent groups"); grid.Rows.Add(T("Mode", "Режим"), projectMode); grid.Rows.Add(T("Metrics", "Метрики"), "All 10");
        // The figure state has to be visible BEFORE the run, not discovered in an empty folder afterwards.
        int templateCount = settings.FigureTemplates.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Length;
        grid.Rows.Add(T("Figures", "Графики"), settings.GenerateFigures ? $"{T("on", "вкл")} · {templateCount} {T("templates", "шаблон(ов)")} · {settings.FigureFormat.ToUpperInvariant()} · {settings.FigureExportMode}" : T("off", "выкл"));
        summary.Controls.Add(grid);
        var start = Button(T("Start analysis", "Начать анализ"), true, 190); start.Location = new Point(20, 252); start.Click += async (_, _) => await RunAnalysisAsync(); summary.Controls.Add(start); page.Controls.Add(summary);
        var integrity = Card(T("Integrity rule", "Правило целостности"), T("MVS Score weights are frozen. Observed study significance cannot change calibration scores or Candidate Set membership.", "Веса MVS Score зафиксированы. Значимость исследования не может менять калибровочные оценки или состав Candidate Set."), 120); page.Controls.Add(integrity);
        var figures = Card(T("Figures after analysis", "Графики после анализа"), T("Choose whether this run should save publication-ready figures locally.", "Выберите, нужно ли локально сохранить графики после этого анализа."), 300);
        var enabled = new CheckBox { Text = T("Generate figures after analysis", "Создать графики после анализа"), Checked = settings.GenerateFigures, AutoSize = true, Location = new Point(20, 88) };
        var mode = new ThemedComboBox { Location = new Point(20, 122), Width = 210 }; mode.Items.AddRange(new object[] { T("Separate images", "Отдельные изображения"), T("Combined dashboard", "Общая панель"), T("Both", "Оба варианта") }); mode.SelectedIndex = settings.FigureExportMode switch { "dashboard" => 1, "both" => 2, _ => 0 };
        var format = new ThemedComboBox { Location = new Point(245, 122), Width = 120 }; format.Items.AddRange(new object[] { "PNG", "SVG" }); format.SelectedIndex = settings.FigureFormat == "svg" ? 1 : 0;
        var folder = new TextBox { Text = settings.FigureOutputFolder, Location = new Point(20, 163), Width = 650, PlaceholderText = T("Choose an output folder", "Выберите папку для сохранения") };
        var browse = Button(T("Browse", "Обзор"), false, 110); browse.Location = new Point(690, 159); browse.Click += (_, _) => { using var d = new FolderBrowserDialog { SelectedPath = folder.Text }; if (d.ShowDialog() == DialogResult.OK) { folder.Text = d.SelectedPath; settings.FigureFolderConfirmed = true; } };
        var configure = Button(T("Configure templates", "Настроить шаблоны"), false, 190); configure.Location = new Point(20, 218); configure.Click += (_, _) => Navigate("figures");
        string FigureRunHint() => !enabled.Checked ? T("Figures are off for this run.", "Графики для этого запуска выключены.") : string.IsNullOrWhiteSpace(folder.Text) ? T("No folder chosen: figures go to the run folder in Downloads.", "Папка не выбрана: графики сохранятся в папку запуска в «Загрузках».") : T("Saved automatically for this run.", "Сохранено автоматически для этого запуска.");
        var figureHint = new Label { Text = FigureRunHint(), AutoSize = true, MaximumSize = new Size(700, 0), ForeColor = Secondary, Location = new Point(230, 224) };
        void SaveFigureRun() { settings.GenerateFigures = enabled.Checked; settings.FigureExportMode = mode.SelectedIndex switch { 1 => "dashboard", 2 => "both", _ => "separate" }; settings.FigureFormat = format.SelectedIndex == 1 ? "svg" : "png"; settings.FigureOutputFolder = folder.Text.Trim(); settings.FigureFolderConfirmed = !string.IsNullOrWhiteSpace(folder.Text); settings.Save(); figureHint.Text = FigureRunHint(); }
        enabled.CheckedChanged += (_, _) => SaveFigureRun(); mode.SelectedIndexChanged += (_, _) => SaveFigureRun(); format.SelectedIndexChanged += (_, _) => SaveFigureRun(); folder.TextChanged += (_, _) => SaveFigureRun();
        figures.Controls.Add(enabled); figures.Controls.Add(mode); figures.Controls.Add(format); figures.Controls.Add(folder); figures.Controls.Add(browse); figures.Controls.Add(configure); figures.Controls.Add(figureHint); page.Controls.Add(figures);
    }

    private void ShowResults()
    {
        var page = Page(T("Results", "Результаты"), T("Review the overview first, then inspect every metric and diagnostic field.", "Сначала просмотрите обзор, затем изучите все метрики и диагностику."));
        if (results == null || data == null)
        {
            var missing = Card(T("No completed analysis", "Нет завершённого анализа"), T("Complete calibration and analysis to generate results.", "Завершите калибровку и анализ для получения результатов."), 160); var go = Button(T("Go to Analysis", "Перейти к анализу"), true); go.Location = new Point(20, 108); go.Click += (_, _) => Navigate("analysis"); missing.Controls.Add(go); page.Controls.Add(missing); return;
        }
        // One card answers the question. Everything a statistician needs hides behind one button.
        ResultRow? best = results.FirstOrDefault(x => x.Candidate) ?? results.FirstOrDefault(x => x.Applicable);
        int said = results.Count(x => x.Verdict == "difference"), same = results.Count(x => x.Verdict == "equivalent"), unsure = results.Count(x => x.Verdict == "insufficient");
        int judged = results.Count(x => x.Applicable);
        // Two metrics both saying "difference" is not agreement if they point at different groups.
        // On dirty data the spread metrics single out the noisiest group while the level metrics
        // single out the shifted one, and calling that a consensus hides the disagreement.
        string leadPair = best?.EffectPair ?? "";
        string leadReversed = string.IsNullOrEmpty(leadPair) ? "" : string.Join(" > ", leadPair.Split(new[] { " > " }, StringSplitOptions.None).Reverse());
        int samePair = results.Count(x => x.Verdict == "difference" && x.EffectPair == leadPair && !string.IsNullOrEmpty(leadPair));
        int otherPair = results.Count(x => x.Verdict == "difference" && !string.IsNullOrEmpty(x.EffectPair) && x.EffectPair != leadPair);
        bool reversed = results.Any(x => x.Verdict == "difference" && x.EffectPair == leadReversed && !string.IsNullOrEmpty(leadReversed));
        var card = Card(T("Verdict", "Вердикт"), "", 262);
        string answer, stateText; Color stateColor;
        if (best == null)
        {
            answer = T("No metric can be judged on this data.", "Ни одну метрику на этих данных оценить нельзя.");
            stateText = T("Not enough data", "Данных не хватает"); stateColor = Color.FromArgb(176, 66, 27);
        }
        else if (best.Verdict == "difference")
        {
            string where = string.IsNullOrEmpty(best.EffectPair) ? "" : ": " + best.EffectPair.Replace(" > ", T(" above ", " выше "));
            string howMuch = double.IsFinite(best.EffectPercent) ? T(" by about ", " примерно на ") + best.EffectPercent.ToString("0.#") + " %" : "";
            answer = T("Groups differ on metric ", "Группы различаются по метрике ") + best.Metric + where + howMuch + ".";
            bool strong = best.Candidate && double.IsFinite(best.PValue) && best.PValue < settings.Alpha / 5 && !best.FprInflated;
            stateText = strong ? T("Confident", "Уверенно") : T("Weak", "Слабо");
            stateColor = strong ? Color.FromArgb(16, 124, 16) : Color.FromArgb(176, 66, 27);
        }
        else if (best.Verdict == "equivalent")
        {
            answer = T("Groups are practically the same on metric ", "Группы практически одинаковы по метрике ") + best.Metric + ".";
            stateText = T("No difference", "Разницы нет"); stateColor = Secondary;
        }
        else
        {
            answer = T("The data cannot decide on metric ", "Данные не позволяют решить по метрике ") + best.Metric + ".";
            stateText = T("Not enough data", "Данных не хватает"); stateColor = Color.FromArgb(176, 66, 27);
        }
        card.Controls.Add(new Label { Text = answer, Font = new Font("Segoe UI", 15, FontStyle.Bold), AutoSize = true, MaximumSize = new Size(ContentWidth - 60, 0), Location = new Point(20, 54) });
        card.Controls.Add(new Label { Text = stateText, Font = new Font("Segoe UI", 10, FontStyle.Bold), ForeColor = stateColor, AutoSize = true, Location = new Point(20, 100) });
        string stats = "";
        if (best != null)
        {
            string interval = double.IsFinite(best.EffectLow) && double.IsFinite(best.EffectHigh) ? "  95% " + T("CI", "ДИ") + " " + best.EffectLow.ToString("0.00") + " … " + best.EffectHigh.ToString("0.00") : "";
            string pText = double.IsFinite(best.PValue) ? (best.PValue < .0001 ? "p < 0.0001" : "p = " + best.PValue.ToString("0.0000")) : "";
            stats = T("Cliffs delta ", "дельта Клиффа ") + (double.IsFinite(best.Effect) ? best.Effect.ToString("0.00") : "") + interval + "  " + pText;
        }
        card.Controls.Add(new Label { Text = stats, AutoSize = true, ForeColor = Secondary, Location = new Point(140, 101) });
        string agreement;
        if (reversed) agreement = T("Warning: the metrics contradict each other, the same pair of groups got opposite directions.", "Внимание: метрики противоречат друг другу — одна и та же пара групп получила разные направления.");
        else if (best == null) agreement = "";
        else agreement = samePair + T(" metrics point at the same pair ", " метрик указывают на ту же пару ") + leadPair + T(", another pair is named by ", ", другую пару называют ") + otherPair + T(", could not decide ", ", не смогли решить ") + unsure + ".";
        bool mixed = reversed || otherPair > 0;
        card.Controls.Add(new Label { Text = agreement, AutoSize = true, MaximumSize = new Size(ContentWidth - 60, 0), ForeColor = mixed ? Color.FromArgb(176, 66, 27) : TextColor, Font = mixed ? new Font("Segoe UI", 10, FontStyle.Bold) : new Font("Segoe UI", 10), Location = new Point(20, 132) });
        if (mixed && !reversed) card.Controls.Add(new Label { Text = T("Some metrics report a different pair of groups, they may be catching spread rather than a shift.", "Часть метрик говорит о другой паре групп — возможно, они ловят разброс, а не сдвиг."), AutoSize = true, MaximumSize = new Size(ContentWidth - 60, 0), ForeColor = Color.FromArgb(176, 66, 27), Location = new Point(20, 152) });
        string sensitivity;
        if (best != null && best.FprInflated) sensitivity = T("Calibration is unreliable: the metric fires even where there is no difference. Do not trust this verdict.", "Калибровка ненадёжна: метрика срабатывает и там, где разницы нет. Вердикту доверять нельзя.");
        else if (best != null && double.IsFinite(best.Mde)) sensitivity = T("A difference smaller than ", "Разницу меньше ") + MdeText(best.Mde) + T(" would have gone unnoticed on this data.", " эти данные бы не заметили.");
        else sensitivity = T("Even a 20 % difference would have gone unnoticed on this data.", "Даже разницу в 20 % эти данные бы не заметили.");
        bool alarm = best != null && best.FprInflated;
        card.Controls.Add(new Label { Text = sensitivity, AutoSize = true, MaximumSize = new Size(ContentWidth - 60, 0), ForeColor = alarm ? Color.FromArgb(176, 66, 27) : Secondary, Location = new Point(20, 160) });
        string techText = calibrationSource == "split_half" ? T("The metric was chosen on one half of the entities and the answer computed on the other.", "Метрика выбрана на одной половине объектов, ответ посчитан на другой.") : T("Calibration and answer were built on the same entities.", "Калибровка и ответ построены на одних и тех же объектах.");
        if (best != null)
        {
            techText += "\n" + $"MVS Score {best.Score:0.0}   \u00b7   power {best.Power:0.00}   \u00b7   FPR {best.Fpr:0.000}   \u00b7   robustness {best.Robustness:0.00}   \u00b7   repeatability {best.Repeatability:0.00}   \u00b7   coverage {best.Coverage:0.00}";
            ResultRow? runnerUp = results.FirstOrDefault(x => x != best && x.Applicable);
            if (runnerUp != null) techText += "\n" + T("Next", "Следующая") + ": " + runnerUp.Metric + " (" + T("gap", "отрыв") + " " + (best.Score - runnerUp.Score).ToString("0.0") + ")";
            int nearMiss = results.Count(x => x.NearMiss);
            if (nearMiss > 0) techText += "\n" + nearMiss + T(" more metrics came close, read the table.", " метрик подошли вплотную — смотрите таблицу.");
            if (!best.Candidate) techText += "\n" + T("No metric passed the candidate rules, this is only the highest scoring one.", "Ни одна метрика не прошла правила кандидата — показана просто лучшая по баллу.");
        }
        var tech = new Label { Text = techText, AutoSize = true, MaximumSize = new Size(ContentWidth - 60, 0), ForeColor = Secondary, Location = new Point(20, 226), Visible = false };
        var techToggle = Button(T("How this was computed", "Как это посчитано"), false, 220);
        techToggle.Location = new Point(20, 190);
        techToggle.Click += (_, _) =>
        {
            tech.Visible = !tech.Visible;
            techToggle.Text = tech.Visible ? T("Hide the computation", "Скрыть расчёт") : T("How this was computed", "Как это посчитано");
            card.Height = tech.Visible ? 246 + tech.PreferredHeight : 262;
        };
        card.Controls.Add(techToggle); card.Controls.Add(tech);
        page.Controls.Add(card);
        var tabs = new ThemedTabControl { Width = ContentWidth, Height = 510, Margin = new Padding(0, 0, 0, 12) };
        var overview = new TabPage(T("Overview", "Обзор")); var all = new TabPage(T("All metrics", "Все метрики")); var diagnostics = new TabPage(T("Diagnostics", "Диагностика")); var reproducibility = new TabPage(T("Reproducibility", "Воспроизводимость")); var savedFiles = new TabPage(T("Saved files", "Сохранённые файлы"));
        overview.Controls.Add(new Label { Text = T("Candidate Set", "Набор кандидатов"), Font = new Font("Segoe UI", 16, FontStyle.Bold), AutoSize = true, Location = new Point(22, 22) });
        overview.Controls.Add(new Label { Text = (results.Any(x => x.Candidate) ? string.Join("   ·   ", results.Where(x => x.Candidate).Select(x => x.Metric)) : T("No metric passed the quality thresholds", "Ни одна метрика не прошла пороги качества")), AutoSize = true, BackColor = SuccessBg, Padding = new Padding(12, 8, 12, 8), Location = new Point(24, 65) });
        overview.Controls.Add(new Label { Text = T("Candidate membership requires FPR ≤ 0.075, power ≥ 0.70 and MVS Score ≥ 60. The set may be empty; observed p-values remain separate.", "Кандидат должен иметь FPR ≤ 0,075, мощность ≥ 0,70 и MVS Score ≥ 60. Набор может быть пустым; наблюдаемые p-value остаются отдельно."), AutoSize = true, MaximumSize = new Size(820, 0), ForeColor = Secondary, Location = new Point(24, 125) });
        var export = Button(T("Export CSV", "Экспорт CSV"), true, 150); export.Location = new Point(24, 185); export.Click += (_, _) => ExportResults(); overview.Controls.Add(export);
        if (lastFigureFiles.Count > 0)
        {
            overview.Controls.Add(new Label { Text = $"{T("Figures", "Графики")}: {lastFigureFiles.Count}\n{settings.FigureOutputFolder}", AutoSize = true, MaximumSize = new Size(780, 0), ForeColor = Secondary, Location = new Point(24, 245) });
            var changeFolder = Button(T("Change figure folder", "Изменить папку графиков"), false, 190); changeFolder.Location = new Point(24, 300); changeFolder.Click += (_, _) => Navigate("figures"); overview.Controls.Add(changeFolder);
        }
        var g = ResultsGrid(); g.Dock = DockStyle.Fill; all.Controls.Add(g);
        diagnostics.Controls.Add(new Label { Text = $"{T("Entities", "Объекты")}: {data.TotalEntities}\n{T("Valid rows", "Валидные строки")}: {data.ValidRows:N0}\n{T("Median measurements", "Медиана измерений")}: {data.MedianMeasurements:0}\n{T("Distribution proxy", "Оценка распределения")}: {data.DistributionProxy}\n\n{T("Interpret calibrated FPR and power together with uncertainty. Coverage and repeatability are measured, not assumed: coverage from bootstrap intervals, repeatability from split-half resampling of the entities.", "Интерпретируйте FPR и мощность вместе с неопределённостью. Coverage и повторяемость теперь измеряются, а не постулируются: coverage — через бутстреп-интервалы, повторяемость — через разбиение объектов пополам.")}", AutoSize = true, MaximumSize = new Size(820, 0), Location = new Point(24, 24) });
        reproducibility.Controls.Add(new Label { Text = $"Application: MVS Analyzer v1.3.3\nProject: {projectName}\nDataset: {(settings.AnonymousReports ? "[hidden]" : datasetName)}\nInterface mode: {settings.InterfaceMode}\nStudy mode: {projectMode}\nSeed: {settings.CalibrationSeed}\nMetrics: 10\nCalibration: raw-value bootstrap scenarios\nNetwork: disabled\nFormula: {OutputExporter.FormulaVersion}\nFormula weights: frozen", AutoSize = true, Font = new Font("Consolas", 10), Location = new Point(24, 24) });
        if (lastArtifacts.Count == 0) savedFiles.Controls.Add(new Label { Text = T("No files were saved automatically for this run. Configure Outputs before the next analysis.", "В этом запуске файлы автоматически не сохранялись. Настройте раздел «Файлы» перед следующим анализом."), AutoSize = true, MaximumSize = new Size(820, 0), Location = new Point(24, 24) });
        else
        {
            var filesGrid = Grid(); filesGrid.Location = new Point(18, 18); filesGrid.Size = new Size(870, 330); filesGrid.Columns.Add("kind", T("Type", "Тип")); filesGrid.Columns.Add("name", T("File name", "Имя файла")); filesGrid.Columns.Add("path", T("Full path", "Полный путь")); filesGrid.Columns.Add("size", T("Size", "Размер"));
            foreach (OutputArtifact artifact in lastArtifacts) filesGrid.Rows.Add(artifact.Kind, artifact.FileName, artifact.FullPath, $"{artifact.SizeBytes / 1024d:0.0} KB"); savedFiles.Controls.Add(filesGrid);
            var copy = Button(T("Copy selected path", "Копировать выбранный путь"), true, 210); copy.Location = new Point(18, 365); copy.Click += (_, _) => { if (filesGrid.SelectedRows.Count > 0) Clipboard.SetText(filesGrid.SelectedRows[0].Cells[2].Value?.ToString() ?? ""); }; savedFiles.Controls.Add(copy);
            var copyFolder = Button(T("Copy output folder", "Копировать путь папки"), false, 210); copyFolder.Location = new Point(245, 365); copyFolder.Click += (_, _) => Clipboard.SetText(Path.GetDirectoryName(lastArtifacts[0].FullPath) ?? ""); savedFiles.Controls.Add(copyFolder);
        }
        tabs.TabPages.Add(overview); tabs.TabPages.Add(all); tabs.TabPages.Add(savedFiles);
        if (!Guided) { tabs.TabPages.Add(diagnostics); tabs.TabPages.Add(reproducibility); }
        page.Controls.Add(tabs);
    }

    private void ShowFigures()
    {
        var page = Page(T("Figures", "Графики"), T("Select built-in templates, export format and a local destination.", "Выберите шаблоны, формат экспорта и локальную папку."));
        var export = Card(T("Export settings", "Настройки экспорта"), T("The choice is saved, but can be changed before every analysis.", "Выбор сохраняется, но его можно изменить перед каждым анализом."), 320);
        var enabled = new CheckBox { Text = T("Generate figures after analysis", "Создавать графики после анализа"), Checked = settings.GenerateFigures, AutoSize = true, Location = new Point(20, 82) };
        var mode = new ThemedComboBox { Location = new Point(20, 118), Width = 220 }; mode.Items.AddRange(new object[] { T("Separate images", "Отдельные изображения"), T("Combined dashboard", "Общая панель"), T("Both", "Оба варианта") }); mode.SelectedIndex = settings.FigureExportMode switch { "dashboard" => 1, "both" => 2, _ => 0 };
        var format = new ThemedComboBox { Location = new Point(255, 118), Width = 120 }; format.Items.AddRange(new object[] { "PNG", "SVG" }); format.SelectedIndex = settings.FigureFormat == "svg" ? 1 : 0;
        var folder = new TextBox { Text = settings.FigureOutputFolder, Location = new Point(20, 158), Width = 650 };
        var browse = Button(T("Browse", "Обзор"), false, 110); browse.Location = new Point(690, 154); browse.Click += (_, _) => { using var d = new FolderBrowserDialog { SelectedPath = folder.Text }; if (d.ShowDialog() == DialogResult.OK) { folder.Text = d.SelectedPath; settings.FigureFolderConfirmed = true; } };
        void SaveFigureSettings() { settings.GenerateFigures = enabled.Checked; settings.FigureExportMode = mode.SelectedIndex switch { 1 => "dashboard", 2 => "both", _ => "separate" }; settings.FigureFormat = format.SelectedIndex == 1 ? "svg" : "png"; settings.FigureOutputFolder = folder.Text.Trim(); settings.FigureFolderConfirmed = !string.IsNullOrWhiteSpace(folder.Text); settings.Save(); }
        enabled.CheckedChanged += (_, _) => SaveFigureSettings(); mode.SelectedIndexChanged += (_, _) => SaveFigureSettings(); format.SelectedIndexChanged += (_, _) => SaveFigureSettings(); folder.TextChanged += (_, _) => SaveFigureSettings();
        string destinationHint = settings.GenerateFigures
            ? T("Figures are written into the run subfolder of this folder, together with the CSV files.", "Графики сохраняются в подпапку запуска внутри этой папки, рядом с CSV.")
            : T("Figure export is currently OFF. Nothing will be drawn after an analysis.", "Экспорт графиков сейчас ВЫКЛЮЧЕН. После анализа ничего не создаётся.");
        export.Controls.Add(new Label { Text = destinationHint, AutoSize = true, MaximumSize = new Size(760, 0), ForeColor = Secondary, Location = new Point(20, 250) });
        var openFolder = Button(T("Open folder", "Открыть папку"), false, 170); openFolder.Location = new Point(20, 208); openFolder.Click += (_, _) => OpenFolder(folder.Text.Trim());
        export.Controls.Add(openFolder);
        export.Controls.Add(enabled); export.Controls.Add(mode); export.Controls.Add(format); export.Controls.Add(folder); export.Controls.Add(browse); page.Controls.Add(export);

        var templates = Card(T("Figure templates", "Шаблоны графиков"), T("Select any combination. Custom and plugin templates are stored as safe JSON.", "Выберите любую комбинацию. Пользовательские и плагин-шаблоны хранятся как безопасный JSON."), 360);
        var list = new CheckedListBox { Location = new Point(20, 82), Size = new Size(600, 210), CheckOnClick = true, BackColor = Surface, ForeColor = TextColor };
        var available = new List<FigureTemplateChoice> { new("value_distribution", T("Measurement distribution", "Распределение измерений")), new("mvs_score", "MVS Score"), new("fpr_power", "FPR vs Power"), new("group_comparison", T("Group comparison", "Сравнение групп")), new("sequence_course", T("Sequence course", "Динамика последовательности")), new("data_quality", T("Entity data quality", "Качество данных объектов")) };
        string customFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "figure-templates"); Directory.CreateDirectory(customFolder);
        foreach (string file in Directory.GetFiles(customFolder, "*.json")) available.Add(new FigureTemplateChoice(Path.GetFileNameWithoutExtension(file), T("Custom: ", "Пользовательский: ") + Path.GetFileNameWithoutExtension(file)));
        foreach (string file in PluginManager.EnabledTemplateFiles()) available.Add(new FigureTemplateChoice(Path.GetFileNameWithoutExtension(file), T("Plugin: ", "Плагин: ") + Path.GetFileNameWithoutExtension(file)));
        var selected = settings.FigureTemplates.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToHashSet();
        foreach (var item in available) list.Items.Add(item, selected.Contains(item.Id));
        var templateHint = new Label { AutoSize = true, MaximumSize = new Size(700, 0), ForeColor = Secondary, Location = new Point(20, 300) };
        string TemplateHint() => $"{T("Selected", "Выбрано")}: {list.CheckedItems.Count}" + (list.CheckedItems.Count == 0 && settings.GenerateFigures ? "   ·   " + T("no figure will be produced", "графики создаваться не будут") : "");
        templateHint.Text = TemplateHint();
        list.ItemCheck += (_, _) => BeginInvoke(new Action(() => { settings.FigureTemplates = string.Join(',', list.CheckedItems.Cast<FigureTemplateChoice>().Select(x => x.Id)); settings.Save(); templateHint.Text = TemplateHint(); }));
        var create = Button(T("Create custom figure", "Создать свой график"), false, 210); create.Location = new Point(20, 322); create.Click += (_, _) => { using var builder = new FigureBuilderForm(Dark, Surface, TextColor, Accent, settings.Language == "ru"); if (builder.ShowDialog(this) == DialogResult.OK) Navigate("figures"); };
        templates.Controls.Add(list); templates.Controls.Add(templateHint); templates.Controls.Add(create); page.Controls.Add(templates);
        if (lastFigureFiles.Count > 0)
        {
            var generated = Card(T("Generated in the last run", "Создано в последнем запуске"), string.Join(Environment.NewLine, lastFigureFiles), Math.Min(280, 100 + lastFigureFiles.Count * 24)); page.Controls.Add(generated);
        }
    }

    private void ShowPlugins()
    {
        var page = Page(T("Plugins", "Плагины"), T("Only declarative visualization and import/export packages are accepted. Executable code is rejected.", "Разрешены только декларативные пакеты визуализации и импорта/экспорта. Исполняемый код отклоняется."));
        PluginAssets.Invalidate();
        List<PluginManifest> plugins = PluginManager.ListInstalled();
        var card = Card(T("Installed plugins", "Установленные плагины"), T("Every package is checked for unsafe paths and executable files and receives a SHA-256 record.", "Каждый пакет проверяется на небезопасные пути и исполняемые файлы и получает запись SHA-256."), 430);
        var grid = Grid(); grid.Location = new Point(20, 82); grid.Size = new Size(885, 260); foreach (string c in new[] { T("Name", "Название"), T("Type", "Тип"), T("Version", "Версия"), T("Author", "Автор"), T("Enabled", "Включён"), "SHA-256" }) grid.Columns.Add(c, c);
        foreach (PluginManifest p in plugins) grid.Rows.Add(p.Name, p.Type, p.Version, p.Author, p.Enabled ? T("Yes", "Да") : T("No", "Нет"), p.PackageHash.Length > 12 ? p.PackageHash[..12] + "…" : p.PackageHash);
        var install = Button(T("Install package", "Установить пакет"), true, 170); install.Location = new Point(20, 360); install.Click += (_, _) => { using var d = new OpenFileDialog { Filter = "MVS plugin (*.zip;*.mvsplugin)|*.zip;*.mvsplugin" }; if (d.ShowDialog() != DialogResult.OK) return; try { PluginManager.Install(d.FileName); Navigate("plugins"); } catch (Exception ex) { MessageBox.Show(ex.Message, T("Plugin rejected", "Плагин отклонён"), MessageBoxButtons.OK, MessageBoxIcon.Error); } };
        var toggle = Button(T("Enable / disable", "Включить / отключить"), false, 180); toggle.Location = new Point(210, 360); toggle.Click += (_, _) => { if (grid.SelectedRows.Count == 0) return; int i = grid.SelectedRows[0].Index; if (i < plugins.Count) { PluginManager.SetEnabled(plugins[i], !plugins[i].Enabled); Navigate("plugins"); } };
        var remove = Button(T("Remove", "Удалить"), false, 120); remove.Location = new Point(410, 360); remove.Click += (_, _) => { if (grid.SelectedRows.Count == 0) return; int i = grid.SelectedRows[0].Index; if (i < plugins.Count && MessageBox.Show(T("Remove selected plugin?", "Удалить выбранный плагин?"), "MVS", MessageBoxButtons.YesNo) == DialogResult.Yes) { PluginManager.Remove(plugins[i]); Navigate("plugins"); } };
        card.Controls.Add(grid); card.Controls.Add(install); card.Controls.Add(toggle); card.Controls.Add(remove); page.Controls.Add(card);
        PluginContributions contributions = PluginAssets.Current;
        var extra = Card(T("What the enabled plugins add", "Что добавляют включённые плагины"), T("Declarative contributions found inside the packages. Everything below is data, not code.", "Декларативные дополнения из пакетов. Всё ниже — данные, а не код."), contributions.Errors.Count > 0 ? 360 : 320);
        var extraGrid = Grid(); extraGrid.Location = new Point(20, 82); extraGrid.Size = new Size(885, 152);
        extraGrid.Columns.Add("kind", T("Contribution", "Дополнение")); extraGrid.Columns.Add("count", T("Count", "Кол-во")); extraGrid.Columns.Add("items", T("Items", "Элементы"));
        extraGrid.Rows.Add(T("Figure templates", "Шаблоны графиков"), contributions.FigureTemplates.Count, string.Join(", ", contributions.FigureTemplates.Select(Path.GetFileNameWithoutExtension)));
        extraGrid.Rows.Add(T("Import profiles", "Профили импорта"), contributions.ImportProfiles.Count, string.Join(", ", contributions.ImportProfiles.Select(x => x.Name)));
        extraGrid.Rows.Add(T("Settings profiles", "Профили настроек"), contributions.SettingsProfiles.Count, string.Join(", ", contributions.SettingsProfiles.Select(x => x.Name)));
        extraGrid.Rows.Add(T("Report templates", "Шаблоны отчётов"), contributions.ReportTemplates.Count, string.Join(", ", contributions.ReportTemplates.Select(x => x.Name)));
        extraGrid.Rows.Add(T("Validation rules", "Правила проверки"), contributions.ValidationRules.Count, string.Join(", ", contributions.ValidationRules.Select(x => x.Id)));
        extraGrid.Rows.Add(T("Terminology", "Терминология"), contributions.Terms.Count, string.Join(", ", contributions.Terms.Keys.Take(8)));
        extra.Controls.Add(extraGrid);
        if (contributions.SettingsProfiles.Count > 0)
        {
            var settingsBox = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 250), Width = 300 };
            settingsBox.Items.Add(T("Do not apply a profile", "Не применять профиль"));
            foreach (SettingsProfile item in contributions.SettingsProfiles) settingsBox.Items.Add(item.Name);
            settingsBox.SelectedIndex = 0;
            var profileStatus = new Label { AutoSize = true, MaximumSize = new Size(520, 0), ForeColor = Secondary, Location = new Point(340, 254) };
            settingsBox.SelectedIndexChanged += (_, _) =>
            {
                if (settingsBox.SelectedIndex <= 0) { profileStatus.Text = ""; return; }
                SettingsProfile picked = contributions.SettingsProfiles[settingsBox.SelectedIndex - 1];
                int applied = PluginAssets.Apply(picked, settings); settings.Save();
                profileStatus.Text = $"{picked.Name}: {applied} {T("settings applied", "настроек применено")}";
            };
            extra.Controls.Add(settingsBox); extra.Controls.Add(profileStatus);
        }
        if (contributions.Errors.Count > 0) extra.Controls.Add(new Label { Text = T("Rejected files: ", "Отклонённые файлы: ") + string.Join("   ·   ", contributions.Errors.Select(x => $"{x.Plugin}/{x.File}: {x.Message}")), AutoSize = true, MaximumSize = new Size(860, 0), ForeColor = Color.FromArgb(176, 66, 27), Location = new Point(20, 292) });
        page.Controls.Add(extra);
        page.Controls.Add(Card(T("Security boundary", "Граница безопасности"), T("Packages may contain JSON templates, icons and declarative import/export schemas. DLL, EXE, scripts and commands are not allowed and cannot modify the ten built-in metrics or frozen MVS formula.", "Пакеты могут содержать JSON-шаблоны, иконки и декларативные схемы импорта/экспорта. DLL, EXE, скрипты и команды запрещены и не могут менять десять встроенных метрик или фиксированную формулу MVS."), 135));
    }

    private void ShowOutputs()
    {
        var page = Page(T("Outputs", "Файлы"), T("Choose exactly what every analysis saves and where it is stored.", "Выберите, какие файлы сохраняет каждый анализ и где они находятся."));
        var destination = Card(T("Output destination", "Папка результатов"), T("Each run receives its own timestamped subfolder. Existing files are never overwritten.", "Каждый запуск получает отдельную папку с датой и временем. Существующие файлы не перезаписываются."), 255);
        var folder = new TextBox { Text = settings.FigureOutputFolder, Location = new Point(20, 88), Width = 650, PlaceholderText = T("Choose a parent folder", "Выберите основную папку") };
        var browse = Button(T("Browse", "Обзор"), false, 110); browse.Location = new Point(690, 84); browse.Click += (_, _) => { using var dialog = new FolderBrowserDialog { SelectedPath = folder.Text }; if (dialog.ShowDialog() == DialogResult.OK) folder.Text = dialog.SelectedPath; };
        destination.Controls.Add(new Label { Text = T("File prefix", "Префикс файлов"), AutoSize = true, Location = new Point(20, 133) }); var prefix = new TextBox { Text = settings.OutputPrefix, Location = new Point(20, 158), Width = 220 };
        void SaveDestination() { settings.FigureOutputFolder = folder.Text.Trim(); settings.FigureFolderConfirmed = !string.IsNullOrWhiteSpace(folder.Text); settings.OutputPrefix = string.IsNullOrWhiteSpace(prefix.Text) ? "MVS" : prefix.Text.Trim(); settings.Save(); }
        folder.TextChanged += (_, _) => SaveDestination(); prefix.TextChanged += (_, _) => SaveDestination();
        destination.Controls.Add(new Label { Text = T("Changes are saved immediately.", "Изменения сохраняются сразу."), AutoSize = true, ForeColor = Secondary, Location = new Point(270, 162) });
        destination.Controls.Add(folder); destination.Controls.Add(browse); destination.Controls.Add(prefix); page.Controls.Add(destination);

        var automatic = Card(T("Automatic files", "Автоматическое сохранение"), T("All selected files are written after a successful analysis.", "Все выбранные файлы записываются после успешного анализа."), 315);
        var resultCsv = new CheckBox { Text = T("Results table — results.csv", "Таблица результатов — results.csv"), Checked = settings.AutoExportResults, AutoSize = true, Location = new Point(20, 85) };
        var calibrationCsv = new CheckBox { Text = T("Calibration table — calibration.csv", "Таблица калибровки — calibration.csv"), Checked = settings.AutoExportCalibration, AutoSize = true, Location = new Point(20, 120) };
        var qualityCsv = new CheckBox { Text = T("Entity quality table — data_quality.csv", "Качество данных объектов — data_quality.csv"), Checked = settings.AutoExportQuality, AutoSize = true, Location = new Point(20, 155) };
        var manifest = new CheckBox { Text = T("Reproducibility manifest — run_manifest.json", "Манифест воспроизводимости — run_manifest.json"), Checked = settings.AutoExportManifest, AutoSize = true, Location = new Point(20, 190) };
        int outputTemplates = settings.FigureTemplates.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Length;
        var figures = new CheckBox { Text = T($"Selected figures from the Figures section ({outputTemplates})", $"Выбранные графики из раздела «Графики» ({outputTemplates})"), Checked = settings.GenerateFigures, AutoSize = true, Location = new Point(20, 225) };
        void SaveOutputs() { settings.AutoExportResults = resultCsv.Checked; settings.AutoExportCalibration = calibrationCsv.Checked; settings.AutoExportQuality = qualityCsv.Checked; settings.AutoExportManifest = manifest.Checked; settings.GenerateFigures = figures.Checked; settings.Save(); }
        resultCsv.CheckedChanged += (_, _) => SaveOutputs(); calibrationCsv.CheckedChanged += (_, _) => SaveOutputs(); qualityCsv.CheckedChanged += (_, _) => SaveOutputs(); manifest.CheckedChanged += (_, _) => SaveOutputs(); figures.CheckedChanged += (_, _) => SaveOutputs();
        automatic.Controls.Add(new Label { Text = T("Every checkbox is saved immediately.", "Каждая галочка сохраняется сразу."), AutoSize = true, ForeColor = Secondary, Location = new Point(20, 262) });
        automatic.Controls.Add(resultCsv); automatic.Controls.Add(calibrationCsv); automatic.Controls.Add(qualityCsv); automatic.Controls.Add(manifest); automatic.Controls.Add(figures); page.Controls.Add(automatic);

        var files = Card(T("Files from the last run", "Файлы последнего запуска"), lastArtifacts.Count == 0 ? T("No saved files in this session yet.", "В этом сеансе сохранённых файлов пока нет.") : T("Full names and paths are shown below.", "Ниже показаны полные имена и пути."), 360);
        if (lastArtifacts.Count > 0) { var grid = Grid(); grid.Location = new Point(20, 82); grid.Size = new Size(885, 235); grid.Columns.Add("type", T("Type", "Тип")); grid.Columns.Add("name", T("File", "Файл")); grid.Columns.Add("path", T("Full path", "Полный путь")); foreach (var item in lastArtifacts) grid.Rows.Add(item.Kind, item.FileName, item.FullPath); files.Controls.Add(grid); }
        page.Controls.Add(files);
    }

    private void ShowHistory()
    {
        var page = Page(T("History", "История"), T("Completed runs in the current application session.", "Завершённые запуски текущего сеанса приложения."));
        var card = Card(T("Run history", "История запусков"), history.Count == 0 ? T("No completed runs yet.", "Завершённых запусков пока нет.") : T("Each analysis creates a separate record.", "Каждый анализ создаёт отдельную запись."), 390);
        var grid = Grid(); grid.Location = new Point(20, 82); grid.Size = new Size(885, 270); foreach (string c in new[] { T("Time", "Время"), T("Project", "Проект"), T("Dataset", "Датасет"), "N", T("Profile", "Профиль"), "Candidate Set" }) grid.Columns.Add(c, c);
        foreach (var r in history) grid.Rows.Add(r.Time.ToString("g"), r.Project, settings.AnonymousReports ? "[hidden]" : r.Dataset, r.Entities, r.Profile, r.CandidateSet); card.Controls.Add(grid); page.Controls.Add(card);
        var note = Card(T("Persistence", "Сохранение"), T("Persistent project files and signed local run manifests are planned for the next integrity update.", "Постоянные файлы проектов и подписанные локальные манифесты запланированы для следующего обновления целостности."), 110); page.Controls.Add(note);
    }

    private void ShowSettings()
    {
        var page = Page(T("Settings", "Настройки"), T("Ordinary options are shown first. Scientific defaults remain protected.", "Сначала показаны обычные параметры. Научные значения по умолчанию защищены."));
        var modeCard = Card(T("Interface mode", "Режим интерфейса"), T("All modes use the same analysis engine; they expose different levels of detail.", "Все режимы используют одно вычислительное ядро и отличаются уровнем детализации."), 230);
        var interfaceMode = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 88), Width = 220 };
        interfaceMode.Items.AddRange(new object[] { "Guided", "Laboratory", "Expert" }); interfaceMode.SelectedIndex = settings.InterfaceMode switch { "laboratory" => 1, "expert" => 2, _ => 0 };
        var modeExplanation = new Label { Text = settings.InterfaceMode switch { "laboratory" => T("Cleaning protocol, calibration profiles, history and reproducibility.", "Протокол очистки, профили калибровки, история и воспроизводимость."), "expert" => T("Adds seed, simulation count, effect settings and full diagnostics.", "Добавляет seed, число симуляций, эффект и полную диагностику."), _ => T("Only required steps and safe defaults are shown.", "Показываются только обязательные шаги и безопасные значения.") }, AutoSize = true, MaximumSize = new Size(620, 0), Location = new Point(260, 91), ForeColor = Secondary };
        interfaceMode.SelectedIndexChanged += (_, _) => modeExplanation.Text = interfaceMode.SelectedIndex switch { 1 => T("Cleaning protocol, calibration profiles, history and reproducibility.", "Протокол очистки, профили калибровки, история и воспроизводимость."), 2 => T("Adds seed, simulation count, effect settings and full diagnostics.", "Добавляет seed, число симуляций, эффект и полную диагностику."), _ => T("Only required steps and safe defaults are shown.", "Показываются только обязательные шаги и безопасные значения.") };
        interfaceMode.SelectedIndexChanged += (_, _) => { settings.InterfaceMode = interfaceMode.SelectedIndex switch { 1 => "laboratory", 2 => "expert", _ => "guided" }; settings.Save(); ApplyModeVisibility(); BeginInvoke(new Action(() => Navigate("settings"))); };
        modeCard.Controls.Add(interfaceMode); modeCard.Controls.Add(modeExplanation); page.Controls.Add(modeCard);
        var rigour = Card(T("Scientific rigour", "Научная строгость"), T("Split calibration and the equivalence margin change the verdict, not the score.", "Раздельная калибровка и граница эквивалентности влияют на вердикт, но не на балл."), 210);
        var split = new CheckBox { Text = T("Split calibration: choose the metric and compute the answer on different halves of the entities", "Раздельная калибровка: выбирать метрику и считать ответ на разных половинах объектов"), Checked = settings.SplitCalibration, AutoSize = true, Location = new Point(20, 86) };
        split.CheckedChanged += (_, _) => { settings.SplitCalibration = split.Checked; settings.Save(); };
        rigour.Controls.Add(split);
        rigour.Controls.Add(new Label { Text = T("Removes the reproach that the metric was chosen on the same rows, but needs at least eight entities per group and costs power.", "Снимает упрёк в подгонке, но требует не менее восьми объектов в каждой группе и снижает мощность."), AutoSize = true, MaximumSize = new Size(ContentWidth - 80, 0), ForeColor = Secondary, Location = new Point(40, 110) });
        // The Russian caption is longer than the English one, so the field position is measured, not fixed.
        var marginLabel = new Label { Text = T("Equivalence margin", "Граница эквивалентности"), AutoSize = true, Location = new Point(20, 158) };
        rigour.Controls.Add(marginLabel);
        int marginX = 36 + TextRenderer.MeasureText(marginLabel.Text, marginLabel.Font).Width;
        var margin = new ThemedNumericUpDown { Minimum = .02m, Maximum = .60m, DecimalPlaces = 3, Increment = .01m, Value = (decimal)settings.EquivalenceMargin, Location = new Point(marginX, 154), Width = 96 };
        margin.ValueChanged += (_, _) => { settings.EquivalenceMargin = (double)margin.Value; settings.Save(); };
        rigour.Controls.Add(margin);
        rigour.Controls.Add(new Label { Text = T("A difference smaller than this counts as practically zero (Cliffs delta).", "Разница меньше этого значения считается практически нулём (дельта Клиффа)."), AutoSize = true, MaximumSize = new Size(ContentWidth - marginX - 160, 0), ForeColor = Secondary, Location = new Point(marginX + 112, 158) });
        page.Controls.Add(rigour);
        var about = Card(T("About", "О программе"), T("MVS — Metrics Value System. The program does not validate a metric against a reference; it shows which metric carries more value on your data.", "MVS — Metrics Value System, система оценки ценности метрик. Программа не валидирует метрику по эталону, а показывает, какая метрика ценнее на ваших данных."), 150);
        about.Controls.Add(new Label { Text = $"MVS Analyzer 1.3.3   ·   {AnalysisEngine.EngineVersion}   ·   {OutputExporter.FormulaVersion}", AutoSize = true, Font = new Font("Segoe UI", 10, FontStyle.Bold), Location = new Point(20, 92) });
        about.Controls.Add(new Label { Text = $"Formula hash: {OutputExporter.FormulaHash}", AutoSize = true, ForeColor = Secondary, Location = new Point(20, 116) });
        page.Controls.Add(about);
        var general = Card(T("General and appearance", "Общие и оформление"), T("Language and theme changes apply immediately.", "Изменения языка и темы применяются сразу."), 310);
        general.Controls.Add(new Label { Text = T("Language", "Язык"), AutoSize = true, Location = new Point(20, 84) }); var language = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 108), Width = 180 }; language.Items.AddRange(new object[] { "English", "Русский" }); language.SelectedIndex = settings.Language == "ru" ? 1 : 0;
        general.Controls.Add(new Label { Text = T("Theme", "Тема"), AutoSize = true, Location = new Point(230, 84) }); var theme = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(230, 108), Width = 180 }; theme.Items.AddRange(new object[] { "System", "Light", "Dark" }); theme.SelectedIndex = settings.Theme switch { "light" => 1, "dark" => 2, _ => 0 };
        general.Controls.Add(new Label { Text = T("Complete language packs: English, Russian. Deutsch, Español, Français and Português are planned.", "Полные языковые пакеты: английский и русский. Немецкий, испанский, французский и португальский запланированы."), AutoSize = true, MaximumSize = new Size(820, 0), ForeColor = Secondary, Location = new Point(20, 150) });
        language.SelectedIndexChanged += (_, _) => { settings.Language = language.SelectedIndex == 1 ? "ru" : "en"; settings.Save(); RefreshChromeText(); ApplyTheme(); BeginInvoke(new Action(() => Navigate("settings"))); };
        theme.SelectedIndexChanged += (_, _) => { settings.Theme = theme.SelectedIndex switch { 1 => "light", 2 => "dark", _ => "system" }; settings.Save(); ApplyTheme(); BeginInvoke(new Action(() => Navigate("settings"))); };
        var resetLanguage = Button(T("Show language screen next start", "Показать выбор языка при следующем запуске"), false, 290); resetLanguage.Location = new Point(20, 205); resetLanguage.Click += (_, _) => { string marker = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "language.txt"); if (File.Exists(marker)) File.Delete(marker); resetLanguage.Enabled = false; resetLanguage.Text = T("Will appear on next start", "Появится при следующем запуске"); };
        general.Controls.Add(language); general.Controls.Add(theme); general.Controls.Add(resetLanguage); page.Controls.Add(general);
        var processing = Card(T("Data processing", "Обработка данных"), T("Set transparent validation limits. Changes apply to the next imported dataset.", "Настройте прозрачные пределы проверки. Изменения применятся к следующему импортированному датасету."), 260);
        processing.Controls.Add(new Label { Text = T("Minimum value", "Минимальное значение"), AutoSize = true, Location = new Point(20, 88) }); var minRt = new ThemedNumericUpDown { Minimum = -1000000, Maximum = 999999, Value = Math.Clamp(settings.MinValue, -1000000, 999999), Location = new Point(20, 114), Width = 180 };
        processing.Controls.Add(new Label { Text = T("Maximum value", "Максимальное значение"), AutoSize = true, Location = new Point(245, 88) }); var maxRt = new ThemedNumericUpDown { Minimum = -999999, Maximum = 1000000, Value = Math.Clamp(settings.MaxValue, -999999, 1000000), Location = new Point(245, 114), Width = 180 };
        processing.Controls.Add(new Label { Text = T("Minimum valid measurements", "Минимум валидных измерений"), AutoSize = true, Location = new Point(470, 88) }); var minTrials = new ThemedNumericUpDown { Minimum = 2, Maximum = 10000, Value = settings.MinMeasurements, Location = new Point(470, 114), Width = 180 };
        var processingHint = new Label { Text = T("Changes are saved immediately.", "Изменения сохраняются сразу."), AutoSize = true, MaximumSize = new Size(820, 0), ForeColor = Secondary, Location = new Point(20, 178) };
        void SaveProcessing() { if (minRt.Value >= maxRt.Value) { processingHint.ForeColor = Color.FromArgb(176, 66, 27); processingHint.Text = T("Minimum value must be lower than maximum value - not saved.", "Минимум должен быть меньше максимума — не сохранено."); return; } settings.MinValue = (int)minRt.Value; settings.MaxValue = (int)maxRt.Value; settings.MinMeasurements = (int)minTrials.Value; settings.Save(); processingHint.ForeColor = Secondary; processingHint.Text = T("Saved.", "Сохранено."); }
        minRt.ValueChanged += (_, _) => SaveProcessing(); maxRt.ValueChanged += (_, _) => SaveProcessing(); minTrials.ValueChanged += (_, _) => SaveProcessing();
        processing.Controls.Add(minRt); processing.Controls.Add(maxRt); processing.Controls.Add(minTrials); processing.Controls.Add(processingHint); page.Controls.Add(processing);
        var privacy = Card(T("Privacy and integrity", "Конфиденциальность и целостность"), T("No server, telemetry or account. Reports can hide local dataset names.", "Нет сервера, телеметрии и аккаунта. В отчётах можно скрывать локальные имена файлов."), 165);
        var anonymous = new CheckBox { Text = T("Hide dataset names and pseudonymize participant IDs", "Скрывать имена датасетов и псевдонимизировать объектов"), Checked = settings.AnonymousReports, AutoSize = true, Location = new Point(20, 86) }; anonymous.CheckedChanged += (_, _) => { settings.AnonymousReports = anonymous.Checked; settings.Save(); }; privacy.Controls.Add(anonymous); page.Controls.Add(privacy);
        var advanced = Card(T("Advanced scientific settings", "Расширенные научные настройки"), T("Formula weights are frozen and cannot be changed in normal mode. Custom models must receive a new version and formula hash.", "Веса формулы зафиксированы и не меняются в обычном режиме. Пользовательская модель должна получить новую версию и хеш формулы."), 120); page.Controls.Add(advanced);
        {
            var expert = Card(T("Calibration and simulation", "Калибровка и симуляция"), T("Configure a raw-value scenario. The effect is applied to the last group.", "Настройте сценарий на исходных значениях. Эффект применяется к последней группе."), 385);
            expert.Controls.Add(new Label { Text = "Seed", AutoSize = true, Location = new Point(20, 82) });
            var seed = new ThemedNumericUpDown { Minimum = 1, Maximum = int.MaxValue, Value = Math.Clamp(settings.CalibrationSeed, 1, int.MaxValue), Location = new Point(20, 106), Width = 190 };
            expert.Controls.Add(new Label { Text = T("Simulations", "Симуляции"), AutoSize = true, Location = new Point(240, 82) });
            var repetitions = new ThemedNumericUpDown { Minimum = 100, Maximum = 100000, Increment = 100, Value = Math.Clamp(settings.CustomRepetitions, 100, 100000), Location = new Point(240, 106), Width = 190 };
            expert.Controls.Add(new Label { Text = T("Effect multiplier", "Множитель эффекта"), AutoSize = true, Location = new Point(460, 82) });
            var effect = new ThemedNumericUpDown { DecimalPlaces = 2, Minimum = 1.01M, Maximum = 3.00M, Increment = .01M, Value = Math.Clamp((decimal)settings.CalibrationEffect, 1.01M, 3.00M), Location = new Point(460, 106), Width = 180 };
            expert.Controls.Add(new Label { Text = T("Scenario", "Сценарий"), AutoSize = true, Location = new Point(20, 158) });
            var scenario = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 182), Width = 250 }; scenario.Items.AddRange(new object[] { T("Increase level", "Рост уровня"), T("Decrease level", "Снижение уровня"), T("Increase variability", "Рост вариативности") }); scenario.SelectedIndex = settings.SimulationScenario switch { SimulationScenarios.Decrease => 1, SimulationScenarios.Variability => 2, _ => 0 };
            expert.Controls.Add(new Label { Text = T("Outliers, %", "Выбросы, %"), AutoSize = true, Location = new Point(300, 158) });
            var outliers = new ThemedNumericUpDown { DecimalPlaces = 1, Minimum = 0, Maximum = 25, Increment = .5M, Value = Math.Clamp((decimal)(settings.OutlierRate * 100), 0, 25), Location = new Point(300, 182), Width = 150 };
            expert.Controls.Add(new Label { Text = T("Missing, %", "Пропуски, %"), AutoSize = true, Location = new Point(480, 158) });
            var missing = new ThemedNumericUpDown { DecimalPlaces = 1, Minimum = 0, Maximum = 50, Increment = .5M, Value = Math.Clamp((decimal)(settings.MissingRate * 100), 0, 50), Location = new Point(480, 182), Width = 150 };
            void SaveExpert() { settings.CalibrationSeed = (int)seed.Value; settings.CustomRepetitions = (int)repetitions.Value; settings.CalibrationEffect = (double)effect.Value; settings.SimulationScenario = scenario.SelectedIndex switch { 1 => SimulationScenarios.Decrease, 2 => SimulationScenarios.Variability, _ => SimulationScenarios.Location }; settings.OutlierRate = (double)outliers.Value / 100; settings.MissingRate = (double)missing.Value / 100; settings.Save(); }
            seed.ValueChanged += (_, _) => SaveExpert(); repetitions.ValueChanged += (_, _) => SaveExpert(); effect.ValueChanged += (_, _) => SaveExpert(); scenario.SelectedIndexChanged += (_, _) => SaveExpert(); outliers.ValueChanged += (_, _) => SaveExpert(); missing.ValueChanged += (_, _) => SaveExpert();
            expert.Controls.Add(new Label { Text = T("Changes are saved immediately and used by the next calibration.", "Изменения сохраняются сразу и применяются к следующей калибровке."), AutoSize = true, MaximumSize = new Size(820, 0), ForeColor = Secondary, Location = new Point(20, 248) });
            expert.Controls.Add(seed); expert.Controls.Add(repetitions); expert.Controls.Add(effect); expert.Controls.Add(scenario); expert.Controls.Add(outliers); expert.Controls.Add(missing); page.Controls.Add(expert);
        }
        AddDeveloperCard(page);
    }

    private void ShowHelp()
    {
        var page = Page(T("Help", "Справка"), T("A short guide to the local MVS workflow.", "Краткая справка по локальному сценарию MVS."));
        foreach (var item in new[] {
            (T("1. Import data", "1. Импортируйте данные"), T("Use trial-level CSV or TSV with participant, RT and group columns.", "Используйте CSV или TSV по пробам со столбцами участника, RT и группы.")),
            (T("2. Review quality", "2. Проверьте качество"), T("Confirm recognized fields, valid Value range and participant counts.", "Проверьте распознанные поля, диапазон RT и число объектов.")),
            (T("3. Calibrate", "3. Выполните калибровку"), T("Calibration estimates metric behavior for the current data structure.", "Калибровка оценивает поведение метрик для текущей структуры данных.")),
            (T("4. Analyze", "4. Запустите анализ"), T("All ten metrics are calculated; observed p-values remain separate.", "Рассчитываются все десять метрик; наблюдаемые p-value остаются отдельно.")),
            (T("5. Export", "5. Экспортируйте"), T("Export the full result table and retain the project source separately.", "Экспортируйте полную таблицу и отдельно сохраняйте исходники проекта.")) }) page.Controls.Add(Card(item.Item1, item.Item2, 105));
    }

    private void ShowAudit()
    {
        var page = Page(T("Audit", "Аудит"), T("Verify saved runs: file hashes, the frozen formula, calibration settings and the run journal.", "Проверка сохранённых прогонов: хеши файлов, замороженная формула, настройки калибровки и журнал прогонов."));
        var scan = Card(T("Scan a folder", "Проверить папку"), T("Choose the folder that contains run subfolders. Files are only read, never modified.", "Выберите папку с папками прогонов. Файлы только читаются и не изменяются."), 205);
        var folder = new TextBox { Text = auditFolder.Length > 0 ? auditFolder : settings.FigureOutputFolder, Location = new Point(20, 92), Width = 650, PlaceholderText = T("Folder with saved runs", "Папка с сохранёнными прогонами") };
        var browse = Button(T("Browse", "Обзор"), false, 110); browse.Location = new Point(690, 88);
        browse.Click += (_, _) => { using var dialog = new FolderBrowserDialog { SelectedPath = folder.Text }; if (dialog.ShowDialog() == DialogResult.OK) folder.Text = dialog.SelectedPath; };
        var verify = Button(T("Run verification", "Проверить"), true, 200); verify.Location = new Point(20, 140);
        verify.Click += (_, _) =>
        {
            try { auditFolder = folder.Text.Trim(); auditReport = RunAuditor.Audit(auditFolder); Navigate("audit"); }
            catch (Exception ex) { MessageBox.Show(ex.Message, T("Verification failed", "Проверка не выполнена"), MessageBoxButtons.OK, MessageBoxIcon.Error); }
        };
        scan.Controls.Add(folder); scan.Controls.Add(browse); scan.Controls.Add(verify); page.Controls.Add(scan);

        if (auditReport == null)
        {
            page.Controls.Add(Card(T("What this can and cannot prove", "Что это доказывает, а что нет"), T("Matching hashes prove that saved results were not edited after the run. The journal additionally exposes runs that were deleted or hidden. Neither can prove that a study was honest \u2014 only that the record is complete and untouched.", "Совпадение хешей доказывает, что сохранённые результаты не правили после прогона. Журнал дополнительно показывает удалённые или скрытые прогоны. Ни то, ни другое не доказывает честность исследования \u2014 только полноту и неизменность записи."), 160));
            return;
        }

        AuditReport report = auditReport;
        Color problemColor = Dark ? Color.FromArgb(92, 40, 40) : Color.FromArgb(253, 231, 231);
        string verdictText = report.Verdict == RunAuditor.Fail ? T("Problems found \u2014 this record cannot be trusted", "Обнаружены проблемы \u2014 записи нельзя доверять")
            : report.Verdict == RunAuditor.Warn ? T("Passed with remarks", "Пройдено с замечаниями") : T("Verification passed", "Проверка пройдена");
        var verdict = Card(T("Verdict", "Вердикт"), $"{report.Runs.Count} {T("runs checked", "прогонов проверено")}   \u00b7   {report.JournalEntries} {T("journal entries", "записей в журнале")}", 145);
        verdict.Controls.Add(Badge(verdictText, report.Verdict == RunAuditor.Ok ? SuccessBg : report.Verdict == RunAuditor.Warn ? NeutralBadge : problemColor, 20, 92));
        page.Controls.Add(verdict);

        var runsCard = Card(T("Checked runs", "Проверенные прогоны"), T("One row per run_manifest.json found in the folder.", "Одна строка на каждый найденный run_manifest.json."), 300);
        var runsGrid = Grid(); runsGrid.Location = new Point(20, 82); runsGrid.Size = new Size(885, 195);
        foreach (string column in new[] { T("Run", "Прогон"), T("Project", "Проект"), T("Data hash", "Хеш данных"), "Seed", T("Effect", "Эффект"), T("Candidate Set", "Кандидаты"), T("Status", "Статус") }) runsGrid.Columns.Add(column, column);
        foreach (RunAudit run in report.Runs)
        {
            bool failed = run.Findings.Any(f => f.Severity == RunAuditor.Fail);
            string status = failed ? T("Failed", "Нарушено") : run.Findings.Any(f => f.Severity == RunAuditor.Warn) ? T("Remarks", "Замечания") : T("Intact", "Цело");
            int row = runsGrid.Rows.Add(run.RunId, run.Project, run.DatasetHash.Length > 12 ? run.DatasetHash[..12] + "\u2026" : run.DatasetHash, run.Seed.ToString(), run.Effect.ToString("0.00"), run.CandidateSet.Length == 0 ? T("(empty)", "(пусто)") : run.CandidateSet, status);
            if (failed) runsGrid.Rows[row].DefaultCellStyle.BackColor = problemColor;
        }
        runsCard.Controls.Add(runsGrid); page.Controls.Add(runsCard);

        var findingsCard = Card(T("Findings", "Замечания"), T("Everything the verification noticed, most serious first.", "Всё, что заметила проверка, начиная с самого серьёзного."), 345);
        var findingsGrid = Grid(); findingsGrid.Location = new Point(20, 82); findingsGrid.Size = new Size(885, 240);
        foreach (string column in new[] { T("Level", "Уровень"), T("Code", "Код"), T("Run", "Прогон"), T("Detail", "Описание") }) findingsGrid.Columns.Add(column, column);
        var everything = report.Findings.Select(f => (Finding: f, Run: "\u2014"))
            .Concat(report.Runs.SelectMany(r => r.Findings.Select(f => (Finding: f, Run: r.RunId))))
            .OrderBy(x => x.Finding.Severity == RunAuditor.Fail ? 0 : x.Finding.Severity == RunAuditor.Warn ? 1 : 2).ToList();
        foreach (var item in everything)
        {
            string level = item.Finding.Severity == RunAuditor.Fail ? T("Problem", "Проблема") : item.Finding.Severity == RunAuditor.Warn ? T("Remark", "Замечание") : T("OK", "Норма");
            int row = findingsGrid.Rows.Add(level, item.Finding.Code, item.Run, settings.Language == "ru" ? item.Finding.MessageRu : item.Finding.Message);
            if (item.Finding.Severity == RunAuditor.Fail) findingsGrid.Rows[row].DefaultCellStyle.BackColor = problemColor;
        }
        findingsCard.Controls.Add(findingsGrid); page.Controls.Add(findingsCard);

        var journalCard = Card(T("Run journal", "Журнал прогонов"), T("Every analysis appends one line whose hash locks the previous line. Deleting an inconvenient run breaks the chain and is reported above.", "Каждый анализ добавляет строку, хеш которой закрепляет предыдущую. Удаление неудобного прогона рвёт цепочку, и проверка это покажет."), 175);
        journalCard.Controls.Add(new Label { Text = RunAuditor.JournalPath, AutoSize = true, MaximumSize = new Size(865, 0), ForeColor = Secondary, Location = new Point(20, 96) });
        var copyJournal = Button(T("Copy journal path", "Копировать путь журнала"), false, 230); copyJournal.Location = new Point(20, 124); copyJournal.Click += (_, _) => Clipboard.SetText(RunAuditor.JournalPath);
        journalCard.Controls.Add(copyJournal); page.Controls.Add(journalCard);
    }
}
