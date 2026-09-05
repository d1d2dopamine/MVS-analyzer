namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private string ScientificNumber(double value, string format = "0.####") => double.IsFinite(value) ? value.ToString(format) : T("unavailable", "недоступно");
    private void ShowResults()
    {
        var page = Page(T("Results", "Результаты"), T("A clear overview first; every metric, uncertainty and saved file remains available below.", "Сначала — понятный обзор; ниже доступны все метрики, неопределённость и сохранённые файлы."));
        if (data == null || results == null)
        {
            var go = Button(T("Go to Run", "Перейти к запуску"), true, 230); go.Click += (_, _) => Navigate("analysis");
            page.Controls.Add(FlowCard(T("No completed analysis", "Нет завершённого анализа"), T("Complete or import calibration, then run the analysis.", "Завершите или импортируйте калибровку, затем выполните анализ."), go)); return;
        }
        int differences = results.Count(r => r.Verdict == "difference"), equivalent = results.Count(r => r.Verdict == "equivalent");
        ResultRow? lead = results.Where(r => r.CandidateInAnyTrack).OrderByDescending(r => r.BestTrackScore).FirstOrDefault() ?? results.Where(r => r.Applicable).OrderByDescending(r => r.BestTrackScore).FirstOrDefault();
        string answer = differences > 0
            ? T($"Differences detected on {differences} of {results.Count} metrics", $"Различия обнаружены по {differences} из {results.Count} метрик")
            : equivalent > 0 ? T("Some metrics meet approximate equivalence", "Часть метрик соответствует приближённой эквивалентности")
            : T("The analysis does not establish a difference", "Анализ не позволяет установить различие");
        var headline = new Label { Text = answer, Font = new Font("Segoe UI", 16, FontStyle.Bold), AutoSize = false, Margin = new Padding(0, 0, 0, 12) };
        var detail = new Label { Text = lead == null ? T("No applicable metric.", "Нет применимой метрики.") :
            T("Leading calibrated metric: ", "Ведущая метрика по калибровке: ") + lead.Metric + "   ·   " + VerdictText(lead.Verdict) +
            "   ·   adjusted p = " + ScientificNumber(lead.AdjustedP), AutoSize = false };
        var interpretation = new Label { AutoSize = false, ForeColor = Secondary, Text = T(
            "Decisions use the full-registry correction, not only the candidates. A non-significant result does not establish equality. Different metrics can detect different aspects of the data.",
            "Решения учитывают поправку по всему набору метрик, а не только кандидатам. Незначимый результат не доказывает равенство. Разные метрики могут обнаруживать разные свойства данных.") };
        var technical = new Label { AutoSize = false, Visible = false, ForeColor = Secondary, Text = lead == null ? "" :
            T("Descriptive pair: ", "Описательная пара: ") + lead.EffectPair + "\nCliff's delta = " + ScientificNumber(lead.Effect) +
            "   ·   95% CI: " + ScientificNumber(lead.EffectLow) + " … " + ScientificNumber(lead.EffectHigh) + "\n" +
            T("For more than two groups this selected pair and its interval are descriptive, not a separate multiplicity-adjusted pairwise conclusion.",
              "При числе групп больше двух выбранная пара и её интервал — описание, а не отдельный парный вывод с поправкой на множественные сравнения.") };
        var explain = Button(T("How this was computed", "Как это посчитано"), false, 260);
        explain.Click += (_, _) => { technical.Visible = !technical.Visible; explain.Text = technical.Visible ? T("Hide computation", "Скрыть расчёт") : T("How this was computed", "Как это посчитано"); };
        page.Controls.Add(FlowCard(T("Verdict", "Вердикт"), "", headline, detail, interpretation, explain, technical));

        var tabs = new ThemedTabControl { Name = "result-tabs", Width = ContentWidth, Height = 510,
            MinimumSize = new Size(0, 380), Margin = new Padding(0, 0, 0, 16), Multiline = true };
        var overview = new TabPage(T("Overview", "Обзор")) { AutoScroll = true, Padding = new Padding(18) };
        var overviewFlow = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true };
        string[] tracks = calibration?.FirstOrDefault()?.Tracks ?? AnalysisEngine.DefaultTracks;
        var title = new Label { Text = T("Candidates by research question", "Кандидаты по исследовательским задачам"), Font = new Font("Segoe UI", 13, FontStyle.Bold), AutoSize = false };
        var candidateText = new Label { AutoSize = false, Text = string.Join("\n\n", tracks.Select(track =>
            SimulationScenarios.Describe(track, settings.Language == "ru") + ":\n" + (results.Any(r => r.CandidateIn(track))
                ? string.Join("   ·   ", results.Where(r => r.CandidateIn(track)).Select(r => r.Metric)) : T("No candidate passed the calibration gates.", "Ни одна метрика не прошла пороги калибровки.")))) };
        var rule = new Label { AutoSize = false, ForeColor = Secondary, Text = T(
            "Candidates use the Wilson upper FPR bound and lower power bound. The detection score does not measure estimation accuracy. MDE is reported only when the simulated grid supports an estimate.",
            "Кандидаты отбираются по верхней границе FPR и нижней границе мощности Wilson. Балл обнаружения не измеряет точность оценки. MDE показан только когда сетка симуляций поддерживает оценку.") };
        var export = Button(T("Export CSV", "Экспорт CSV"), true, 210); export.Click += (_, _) => ExportResults();
        overviewFlow.Controls.AddRange(new Control[] { title, candidateText, rule, export });
        void FitOverview()
        {
            int w = Math.Max(200, overviewFlow.ClientSize.Width - 30);
            foreach (Control child in overviewFlow.Controls)
            {
                child.Margin = new Padding(0, 0, 0, 16);
                if (child is Label) { child.Width = w; child.Height = WrappedHeight(child, w); }
            }
        }
        overviewFlow.SizeChanged += (_, _) => FitOverview(); overview.Controls.Add(overviewFlow); tabs.TabPages.Add(overview);
        var all = new TabPage(T("All metrics", "Все метрики")); var grid = ModernResultsGrid(); grid.Dock = DockStyle.Fill; all.Controls.Add(grid); tabs.TabPages.Add(all);
        var sensitivity = new TabPage(T("Sensitivity", "Чувствительность")); var curves = ModernCalibrationGrid(calibration ?? new List<CalibrationRow>()); curves.Dock = DockStyle.Fill; sensitivity.Controls.Add(curves); tabs.TabPages.Add(sensitivity);
        var filesPage = new TabPage(T("Saved files", "Файлы"));
        var filePanel = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, ColumnCount = 1, Padding = new Padding(12) };
        filePanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); filePanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
        var files = Grid(); files.Dock = DockStyle.Fill; files.Columns.Add("kind", T("Type", "Тип")); files.Columns.Add("name", T("File", "Файл")); files.Columns.Add("path", T("Path", "Путь"));
        foreach (OutputArtifact file in lastArtifacts) files.Rows.Add(file.Kind, file.FileName, file.FullPath);
        var open = Button(T("Open output folder", "Открыть папку результатов"), false, 270); open.Enabled = lastArtifacts.Count > 0;
        open.Click += (_, _) => { if (lastArtifacts.Count > 0) OpenFolder(Path.GetDirectoryName(lastArtifacts[0].FullPath)!); };
        filePanel.Controls.Add(files, 0, 0); filePanel.Controls.Add(open, 0, 1); filesPage.Controls.Add(filePanel); tabs.TabPages.Add(filesPage);
        if (!Guided)
        {
            var diagnostics = new TabPage(T("Diagnostics", "Диагностика"));
            diagnostics.Controls.Add(ResultTextBox(string.Join("\n", data.Warnings) + "\n\n" + data.ImportSummary + "\n\n" + T(
                "Robustness, repeatability and pooled-median coverage are descriptive diagnostics, not coverage of the displayed group effect. They do not enter the detection score.",
                "Устойчивость, повторяемость и покрытие объединённой медианы — описательные диагностики, а не покрытие показанного группового эффекта. Они не входят в балл обнаружения.")));
            tabs.TabPages.Add(diagnostics);
            var provenance = new TabPage(T("Provenance", "Воспроизводимость"));
            provenance.Controls.Add(ResultTextBox($"MVS Analyzer {ReleaseInfo.Version} / engine {ReleaseInfo.EngineVersion}\n" +
                $"Formula: {OutputExporter.FormulaVersion}\n{OutputExporter.FormulaHash}\n\n" +
                $"Dataset SHA-256: {datasetHash}\nSeed: {settings.CalibrationSeed}\nCalibration: {calibrationSource}\n" +
                $"Simulations: {lastCalibrationRepetitions}\nMetrics: {AnalysisEngine.MetricKeys.Length}\nAlpha: {settings.Alpha}\nPolicy: {DecisionPolicy.Id}"));
            tabs.TabPages.Add(provenance);
        }
        page.Controls.Add(tabs); FitOverview();
    }
    private RichTextBox ResultTextBox(string text) => new() { Text = text.Trim(), Dock = DockStyle.Fill, ReadOnly = true,
        WordWrap = true, Font = new Font("Segoe UI", 10), BorderStyle = BorderStyle.None, ScrollBars = RichTextBoxScrollBars.Vertical, BackColor = Surface, ForeColor = TextColor };
    private DataGridView ModernResultsGrid()
    {
        var grid = Grid();
        foreach (string name in new[] { T("Metric", "Метрика"), T("Group medians", "Медианы групп"), "Raw p", "Adjusted p", T("Verdict", "Вывод"), "Delta (first − second)", "95% descriptive CI", T("Pair", "Пара"), T("CI status", "Статус ДИ"), T("Candidate tracks", "Треки кандидата") }) grid.Columns.Add(name, name);
        foreach (ResultRow row in results ?? new List<ResultRow>())
            grid.Rows.Add(row.Metric, row.GroupSummary, ScientificNumber(row.PValue), ScientificNumber(row.AdjustedP), VerdictText(row.Verdict),
                ScientificNumber(row.Effect), ScientificNumber(row.EffectLow) + " … " + ScientificNumber(row.EffectHigh), row.EffectPair, row.EffectIntervalStatus, row.CandidateTracks);
        return grid;
    }
    private DataGridView ModernCalibrationGrid(List<CalibrationRow> rows)
    {
        var grid = Grid();
        foreach (string name in new[] { T("Metric", "Метрика"), T("Track", "Трек"), "FPR [Wilson 95%]", "Power [Wilson 95%]", "MCSE(power)", "MDE", T("MDE status", "Статус MDE"), T("Failed / total", "Сбои / всего"), T("Detection index", "Индекс обнаружения") }) grid.Columns.Add(name, name);
        foreach (CalibrationRow row in rows)
            for (int i = 0; i < (row.Tracks?.Length ?? 0); i++)
                grid.Rows.Add(row.Metric, SimulationScenarios.Describe(row.Tracks![i], settings.Language == "ru"),
                    ScientificNumber(row.Fpr) + " [" + ScientificNumber(row.FprLow) + "; " + ScientificNumber(row.FprHigh) + "]",
                    ScientificNumber(row.TrackPowers![i]) + " [" + ScientificNumber(row.TrackPowerLow![i]) + "; " + ScientificNumber(row.TrackPowerHigh![i]) + "]",
                    ScientificNumber(ScientificMath.Mcse(row.TrackPowers[i], row.Repetitions)), MdeText(row.TrackMdes![i]), row.TrackMdeStatus![i], row.TrackFailures![i] + " / " + row.Repetitions, ScientificNumber(row.TrackScores![i], "0.0"));
        return grid;
    }
}
