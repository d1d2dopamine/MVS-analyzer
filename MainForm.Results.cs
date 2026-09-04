namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private string ScientificNumber(double value, string format = "0.####") => double.IsFinite(value) ? value.ToString(format) : T("unavailable", "недоступно");
    private void ShowModernResults()
    {
        var page = Page(T("Results", "Результаты"), T("Read adjusted decisions, uncertainty and applicability before choosing a summary.", "Сначала оцените скорректированные выводы, неопределённость и применимость."));
        if (data == null || results == null)
        {
            var go = Button(T("Go to calibration", "Перейти к калибровке"), true, 230); go.Click += (_, _) => Navigate("calibration");
            page.Controls.Add(FlowCard(T("No completed analysis", "Анализ не завершён"), T("Import data, calibrate, then run the analysis.", "Импортируйте данные, выполните калибровку и анализ."), go)); return;
        }
        int differences = results.Count(r => r.Verdict == "difference"), equivalent = results.Count(r => r.Verdict == "equivalent");
        var answer = new Label { AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold), Margin = new Padding(0, 0, 0, 14),
            Text = T($"{differences} metric(s) reject the global null after correction; {equivalent} meet the approximate equivalence criterion.",
                $"{differences} метрик отвергают общую нулевую гипотезу после поправки; {equivalent} соответствуют приближённому критерию эквивалентности.") };
        var caveat = new Label { AutoSize = true, Margin = new Padding(0, 0, 0, 14), Text = T(
            "A non-significant result is not evidence of equality. For more than two groups the displayed largest pair and its interval are descriptive only. Sensitivity to a between-entity scenario is not a test of a latent variance component.",
            "Незначимый результат не доказывает равенство. При числе групп больше двух выбранная пара и её интервал — только описательные. Чувствительность к межсущностному сценарию не заменяет тест компоненты дисперсии.") };
        var models = Button(T("Open scientific models", "Открыть научные модели"), true, 280); models.Height = 44; models.Margin = new Padding(0, 4, 0, 8); models.Click += (_, _) => Navigate("models");
        page.Controls.Add(FlowCard(T("What this run supports", "Что позволяет заключить этот прогон"),
            T("Bonferroni correction covers the full fixed metric registry, not just selected candidates. Rank tests and bootstrap intervals remain approximate.",
              "Поправка Бонферрони охватывает весь фиксированный набор метрик, а не только кандидатов. Ранговые тесты и bootstrap-интервалы остаются приближёнными."), answer, caveat, models));
        var tabs = new ThemedTabControl { Width = ContentWidth, Height = 470, Margin = new Padding(0, 0, 0, 16) };
        var metricsTab = new TabPage(T("All metrics", "Все метрики"));
        var metricGrid = ModernResultsGrid(); metricGrid.Dock = DockStyle.Fill; metricsTab.Controls.Add(metricGrid); tabs.TabPages.Add(metricsTab);
        var tracksTab = new TabPage(T("Sensitivity tracks", "Треки чувствительности"));
        var trackGrid = ModernCalibrationGrid(calibration ?? new List<CalibrationRow>()); trackGrid.Dock = DockStyle.Fill; tracksTab.Controls.Add(trackGrid); tabs.TabPages.Add(tracksTab);
        var filesTab = new TabPage(T("Saved files", "Сохранённые файлы"));
        var files = Grid(); files.Dock = DockStyle.Fill;
        files.Columns.Add("kind", T("Type", "Тип")); files.Columns.Add("name", T("File", "Файл")); files.Columns.Add("path", T("Path", "Путь"));
        foreach (OutputArtifact file in lastArtifacts) files.Rows.Add(file.Kind, file.FileName, file.FullPath);
        filesTab.Controls.Add(files); tabs.TabPages.Add(filesTab);
        page.Controls.Add(tabs);
        string[] tracks = calibration?.FirstOrDefault()?.Tracks ?? AnalysisEngine.DefaultTracks;
        string candidateText = string.Join(Environment.NewLine, tracks.Select(track => SimulationScenarios.Describe(track, settings.Language == "ru") + ": " +
            (results.Any(r => r.CandidateIn(track)) ? string.Join(", ", results.Where(r => r.CandidateIn(track)).Select(r => r.Metric)) : T("no candidates", "нет кандидатов"))));
        var candidates = new Label { Text = candidateText, AutoSize = true, Margin = new Padding(0, 0, 0, 12) };
        var export = Button(T("Export results CSV", "Экспорт результатов CSV"), false, 260); export.Click += (_, _) => ExportResults();
        page.Controls.Add(FlowCard(T("Candidates by question", "Кандидаты по задачам"),
            T("Gates use the upper Wilson bound for FPR and lower Wilson bound for power. There is no score ≥60 rule. An empty set is allowed. The score is a detection index, not estimation accuracy.",
              "Пороги используют верхнюю границу Wilson для FPR и нижнюю для мощности. Правила «балл ≥60» больше нет. Пустой набор допустим. Балл характеризует обнаружение, а не точность оценивания."), candidates, export));
        var diagnostics = new Label { AutoSize = true, Text = string.Join(Environment.NewLine, data.Warnings) + "\n\n" +
            T("Calibration source: ", "Источник калибровки: ") + calibrationSource + "\n" +
            T("Application / engine: ", "Приложение / движок: ") + ReleaseInfo.Version + " / " + ReleaseInfo.EngineVersion + "\n" +
            "Formula: " + OutputExporter.FormulaVersion + "\n" + T("Seed: ", "Seed: ") + settings.CalibrationSeed };
        page.Controls.Add(FlowCard(T("Assumptions and provenance", "Предпосылки и воспроизводимость"),
            T("Robustness, split-entity repeatability and pooled-median coverage are descriptive diagnostics. They are not coverage of the displayed effect interval and do not enter the score.",
              "Устойчивость, повторяемость по разбиениям сущностей и покрытие объединённой медианы — описательные диагностики. Это не покрытие интервала эффекта; они не входят в балл."), diagnostics));
    }
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
