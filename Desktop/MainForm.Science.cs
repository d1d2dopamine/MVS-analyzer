using System.Globalization;

namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private string lastScienceText = "";
    private string lastScienceFolder = "";
    private string calibrationSettingsHash = "";
    private ProcessingSnapshot? loadedProcessing;

    private CalibrationState DesktopState() => new(datasetName, datasetHash, calibrationSource, lastCalibrationRepetitions,
        settings.CalibrationEffect, settings.CalibrationSeed, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate,
        settings.Alpha, settings.EquivalenceMargin, settings.SplitCalibration, calibration!.First().Tracks!, ReleaseInfo.Version,
        AnalysisEngine.EngineVersion, OutputExporter.FormulaVersion, OutputExporter.FormulaHash, Benchmarking.BenchmarkEnvironment.Hash,
        DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture), calibration, ProcessingSnapshot.From(settings), SettingsHash: SettingsContract.Fingerprint(settings));

    private void LoadCalibrationSnapshot()
    {
        try
        {
            if (data == null) return;
            using var dialog = new OpenFileDialog { Filter = "Calibration JSON (*.json)|*.json" };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            CalibrationState state = CalibrationPersistence.Read(dialog.FileName);
            if (state.DatasetHash != datasetHash) throw new InvalidDataException(T("Load the original dataset before restoring this calibration.", "Сначала загрузите исходный датасет этой калибровки."));
            if (state.Processing != loadedProcessing) throw new InvalidDataException(T("Match the saved processing/import settings and re-import the data first.", "Сначала задайте сохранённые настройки обработки/импорта и заново импортируйте файл."));
            CalibrationPersistence.Apply(state, settings); settings.Save();
            calibration = state.Rows; lastCalibrationRepetitions = state.Repetitions; selectedCalibrationRepetitions = state.Repetitions; calibrationSource = state.CalibrationSource;
            analysisHalf = state.SplitCalibration ? AnalysisEngine.SplitEntities(data, state.Seed).Analysis : null;
            results = null; lastArtifacts.Clear(); lastFigureFiles.Clear(); calibrationSettingsHash = SettingsContract.Fingerprint(settings); Navigate("calibration");
        }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }

    private ThemedNumericUpDown ScienceNumber(decimal value, decimal minimum, decimal maximum, int decimals = 0) => new()
    { Minimum = minimum, Maximum = maximum, Value = value, DecimalPlaces = decimals, Increment = decimals == 0 ? 1 : .05M, Width = 180 };

    private void ShowAdvancedMethods()
    {
        var page = Page(T("Additional methods", "Дополнительные методы"), T("Optional tools, separate from ordinary calibration. The normal workflow is unchanged.", "Необязательные инструменты вне обычной калибровки. Основной порядок работы не изменён."));
        var back = Button(T("← Back to Run", "← Назад к запуску"), false, 240); back.Click += (_, _) => Navigate("analysis"); page.Controls.Add(back);
        var n = ScienceNumber(200, 100, 10000); var reference = ScienceNumber(199, 99, 10000);
        var within = ScienceNumber(1.3M, 1.01M, 5, 2); var between = ScienceNumber(1.3M, 1.01M, 5, 2);
        var variance = Button(T("Analyse variance components", "Разделить компоненты дисперсии"), true, 330); variance.Height = 44; variance.Margin = new Padding(0, 4, 0, 8);
        variance.Click += async (_, _) =>
        {
            try
            {
                if (data != null && loadedProcessing != ProcessingSnapshot.From(settings)) throw new InvalidDataException(T("Processing changed. Re-import before fitting.", "Обработка изменилась. Повторите импорт перед оцениванием."));
                AnalysisData? input = data;
                if (input == null)
                {
                    List<Observation>? rows = ChooseScienceData(false); if (rows == null) return;
                    input = AnalysisEngine.Build(rows, settings.MinValue, settings.MaxValue, Math.Max(3, settings.MinMeasurements));
                }
                if (!ConfirmIndependent(input.Observations)) return;
                AnalysisData fixedData = AnalysisEngine.Build(input.Observations, settings.MinValue, settings.MaxValue, Math.Max(3, settings.MinMeasurements));
                int repeats = (int)n.Value, bootstrap = (int)reference.Value; double w = (double)within.Value, b = (double)between.Value;
                await RunScientificAsync(T("Variance components", "Компоненты дисперсии"),
                    (progress, token) => VarianceAnalysis.Run(fixedData, repeats, bootstrap, w, b, settings.CalibrationSeed, settings.Alpha, progress, token),
                    (report, folder) => { ScientificJson.Write(Path.Combine(folder, "variance_report.json"), report); ScientificJson.AtomicText(Path.Combine(folder, "variance_components.csv"), VarianceAnalysis.Csv(report)); ScientificJson.AtomicText(Path.Combine(folder, "variance_tests.csv"), ScientificTables.Csv(report.Tracks)); ScientificTables.WriteManifest(folder, "variance-components", report, ScientificMath.Hash(ScientificJson.Serialize(fixedData.Observations))); },
                    report => string.Join(Environment.NewLine, report.Groups.Select(g => $"{g.Group}: within={g.WithinVariance:G5}; between={g.BetweenVariance:G5}; {g.Status}")) + "\n\n" + string.Join(Environment.NewLine, report.Tracks.Select(t => $"{t.Track}: adjusted p={t.AdjustedP:G5}; power={t.Power:G4}; {t.Status}")));
            }
            catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        };
        page.Controls.Add(FlowCard(T("Within and between", "Внутри сущности и между сущностями"),
            T("Gaussian random-intercept model for independent groups. REML estimates; separate ML bootstrap tests. Effects multiply SD. This can take substantially longer than summary calibration.",
              "Гауссова модель со случайным интерсептом для независимых групп. Оценки REML, раздельные ML bootstrap-тесты. Множитель относится к SD. Расчёт может быть заметно дольше обычной калибровки."),
            FormRows((T("Evaluation simulations", "Оценочные симуляции"), n), (T("Null reference simulations", "Симуляции нулевого распределения"), reference),
                (T("Within SD multiplier", "Множитель внутрисущностного SD"), within), (T("Between SD multiplier", "Множитель межсущностного SD"), between)), variance, ColabButton(() => StartColab("variance", (int)n.Value, "variance", new[] { "--repetitions", ((int)n.Value).ToString(CultureInfo.InvariantCulture), "--bootstrap", ((int)reference.Value).ToString(CultureInfo.InvariantCulture), "--within-effect", within.Value.ToString(CultureInfo.InvariantCulture), "--between-effect", between.Value.ToString(CultureInfo.InvariantCulture), "--seed", settings.CalibrationSeed.ToString(CultureInfo.InvariantCulture), "--alpha", settings.Alpha.ToString(CultureInfo.InvariantCulture), "--min-measurements", Math.Max(3, settings.MinMeasurements).ToString(CultureInfo.InvariantCulture), "--min-value", settings.MinValue.ToString(CultureInfo.InvariantCulture), "--max-value", settings.MaxValue.ToString(CultureInfo.InvariantCulture) }))));

        var target = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList }; target.Items.AddRange(new object[] { "mean", "median", "geometric_mean", "within_variance", "between_variance" }); target.SelectedIndex = 0;
        var shape = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList }; shape.Items.AddRange(new object[] { "normal", "lognormal", "student_t5" }); shape.SelectedIndex = 0;
        var entities = ScienceNumber(20, 4, 1000); var measures = ScienceNumber(12, 3, 1000); var trials = ScienceNumber(500, 100, 10000);
        var estimate = Button(T("Run known-truth study", "Симуляция с известной истиной"), true, 330); estimate.Height = 44; estimate.Margin = new Padding(0, 4, 0, 8);
        estimate.Click += async (_, _) =>
        {
            string selectedShape = shape.SelectedItem?.ToString() ?? "normal"; bool log = selectedShape == "lognormal";
            var options = new EstimationOptions(target.SelectedItem?.ToString() ?? "mean", selectedShape, (int)entities.Value, (int)measures.Value, (int)trials.Value, 199,
                settings.CalibrationSeed, log ? 1 : 100, log ? .3 : 10, log ? .2 : 5);
            await RunScientificAsync(T("Estimation quality", "Качество оценивания"), (progress, token) => EstimationStudy.Run(options, progress, token),
                (report, folder) => { ScientificJson.Write(Path.Combine(folder, "estimation_report.json"), report); ScientificJson.AtomicText(Path.Combine(folder, "estimation_performance.csv"), ScientificTables.Csv(report.Performance)); ScientificJson.AtomicText(Path.Combine(folder, "estimation_draws.csv"), ScientificTables.Csv(report.Draws)); ScientificTables.WriteManifest(folder, "known-truth-estimation", options, ScientificMath.Hash(ScientificJson.Serialize(options))); },
                report => "Truth: " + report.Truth.ToString("G6") + "\n\n" + string.Join(Environment.NewLine, report.Performance.Select(x => $"{x.Estimator}: bias={x.Bias:G5}; MSE={x.Mse:G5}; coverage={x.Coverage:G4}; failures={x.Failures}")));
        };
        page.Controls.Add(FlowCard(T("Bias, MSE and efficiency", "Смещение, MSE и эффективность"),
            T("Synthetic data with a known target. This does not measure the unknown bias of your imported file. Gaussian defaults: location 100, within SD 10, between SD 5. Lognormal defaults: 1/.3/.2 on the log scale. Bootstrap: 199. Use CLI for custom parameters.",
              "Синтетические данные с известной целью. Это не оценка неизвестного смещения на вашем CSV. Гауссовы параметры: 100/10/5; логнормальные: 1/0,3/0,2 на лог-шкале. Bootstrap: 199. Произвольные параметры доступны в CLI."),
            FormRows((T("Estimand", "Оцениваемая величина"), target), (T("Data mechanism", "Механизм данных"), shape), (T("Entities", "Сущности"), entities), (T("Repeats per entity", "Измерения на сущность"), measures), (T("Simulation replications", "Повторы симуляции"), trials)), estimate, ColabButton(() => StartColab("estimation", (int)trials.Value, "estimation", new[] { "--target", target.SelectedItem?.ToString() ?? "mean", "--shape", shape.SelectedItem?.ToString() ?? "normal", "--entities", ((int)entities.Value).ToString(CultureInfo.InvariantCulture), "--measurements", ((int)measures.Value).ToString(CultureInfo.InvariantCulture), "--repetitions", ((int)trials.Value).ToString(CultureInfo.InvariantCulture), "--bootstrap", "199", "--seed", settings.CalibrationSeed.ToString(CultureInfo.InvariantCulture) }))));

        var meanTime = new CheckBox { Text = T("Linear time effect on mean", "Линейный эффект времени на среднее"), AutoSize = true };
        var scaleTime = new CheckBox { Text = T("Linear time effect on log variance", "Линейный эффект времени на лог-дисперсию"), AutoSize = true };
        var correlate = new CheckBox { Text = T("Correlate random location and scale", "Связь случайных эффектов уровня и масштаба"), AutoSize = true };
        var randomScale = new CheckBox { Text = T("Random scale effect", "Случайный эффект масштаба"), Checked = true, AutoSize = true };
        var melsm = Button(T("Open CSV and fit MELSM", "Открыть CSV и оценить MELSM"), true, 330); melsm.Height = 44; melsm.Margin = new Padding(0, 8, 0, 8);
        melsm.Click += async (_, _) =>
        {
            try
            {
                List<Observation>? rows = ChooseScienceData(true); if (rows == null) return;
                if ((meanTime.Checked || scaleTime.Checked) && !CsvImporter.LastSequenceWasProvided) throw new InvalidDataException(T("A valid integer sequence column is required for time effects.", "Для эффектов времени нужна корректная целочисленная колонка sequence."));
                var options = new MelsmOptions(meanTime.Checked, scaleTime.Checked, correlate.Checked, randomScale.Checked);
                await RunScientificAsync("MELSM", (progress, token) => MelsmAnalysis.Run(rows, options, progress, token),
                    (report, folder) => { if (settings.AnonymousReports) report = report with { RandomEffects = report.RandomEffects.Select(r => r with { Entity = "P_" + ScientificMath.Hash(r.Entity)[..12] }).ToArray() }; ScientificJson.Write(Path.Combine(folder, "melsm_report.json"), report); ScientificJson.AtomicText(Path.Combine(folder, "melsm_parameters.csv"), ScientificTables.Csv(report.Parameters)); ScientificJson.AtomicText(Path.Combine(folder, "melsm_random_effects.csv"), ScientificTables.Csv(report.RandomEffects)); ScientificTables.WriteManifest(folder, "experimental-melsm", options, ScientificMath.Hash(ScientificJson.Serialize(rows))); },
                    report => report.Status + "\n" + T("Pointwise approximate intervals; inspect diagnostics.", "Приближённые поточечные интервалы; проверьте диагностику.") + "\n\n" + string.Join(Environment.NewLine, report.Parameters.Select(x => $"{x.Name}: {x.Estimate:G6}; [{x.Low:G5}, {x.High:G5}]")));
            }
            catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        };
        page.Controls.Add(FlowCard(T("MELSM · experimental", "MELSM · экспериментальный режим"),
            T("Marginal maximum likelihood with adaptive quadrature. IDs are global: the same entity in several conditions remains one subject. Gaussian conditional errors; no AR(1), random slopes or automatic missing-data correction. Numerical convergence is not a scientific guarantee.",
              "Маргинальное максимальное правдоподобие с адаптивной квадратурой. ID глобальны: одна сущность в разных условиях остаётся одним субъектом. Условно гауссовы ошибки; без AR(1), случайных наклонов и автоматической коррекции пропусков. Сходимость не гарантирует правильность модели."), meanTime, scaleTime, correlate, randomScale, melsm, ColabButton(() =>
            {
                var arguments = new List<string> { "--min-value", settings.MinValue.ToString(CultureInfo.InvariantCulture), "--max-value", settings.MaxValue.ToString(CultureInfo.InvariantCulture) };
                if (meanTime.Checked) arguments.Add("--mean-time"); if (scaleTime.Checked) arguments.Add("--scale-time");
                if (correlate.Checked) arguments.Add("--correlate"); if (!randomScale.Checked) arguments.Add("--no-random-scale");
                StartColab("melsm", 0, "melsm", arguments.ToArray());
            })));
        AddDeveloperCard(page);
        if (!string.IsNullOrEmpty(lastScienceText))
        {
            var preview = new RichTextBox { Text = lastScienceText, ReadOnly = true, WordWrap = true, Height = 280, BorderStyle = BorderStyle.FixedSingle, Font = new Font("Consolas", 10), ScrollBars = RichTextBoxScrollBars.Vertical };
            var open = Button(T("Open result folder", "Открыть папку результата"), false, 230); open.Margin = new Padding(0, 10, 0, 0);
            open.Click += (_, _) => { if (Directory.Exists(lastScienceFolder)) System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(lastScienceFolder) { UseShellExecute = true }); };
            page.Controls.Add(FlowCard(T("Latest model result", "Последний модельный результат"), lastScienceFolder, preview, open));
        }
    }
    private List<Observation>? ChooseScienceData(bool allowSingleGroup)
    {
        using var dialog = new OpenFileDialog { Filter = "CSV / TSV (*.csv;*.tsv)|*.csv;*.tsv", Title = T("Choose measurements", "Выберите измерения") };
        if (dialog.ShowDialog(this) != DialogResult.OK) return null;
        ImportProfile? profile = PluginAssets.Current.ImportProfiles.FirstOrDefault(p => p.Id.Equals(settings.ImportProfileId, StringComparison.OrdinalIgnoreCase));
        return CsvImporter.Read(dialog.FileName, settings.MinValue, settings.MaxValue, profile, allowSingleGroup: allowSingleGroup);
    }
    private bool ConfirmIndependent(List<Observation> observations)
    {
        bool overlap = observations.GroupBy(x => x.Entity, StringComparer.OrdinalIgnoreCase).Any(g => g.Select(x => x.Group).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1);
        if (!overlap) return true;
        return MessageBox.Show(this, T("Entity IDs repeat across groups. Continue ONLY if they denote different, independent entities whose numbering restarts in each group. For the same subjects under different conditions choose MELSM. Are these independent entities?",
            "ID повторяются в разных группах. Продолжайте ТОЛЬКО если это разные независимые сущности с повторяющейся нумерацией. Для одних субъектов в разных условиях используйте MELSM. Это независимые сущности?"), "MVS", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) == DialogResult.Yes;
    }
    private async Task RunScientificAsync<TResult>(string caption, Func<IProgress<ProgressInfo>, CancellationToken, TResult> work, Action<TResult, string> save, Func<TResult, string> describe)
    {
        if (localOperationInProgress) return;
        using var destination = new FolderBrowserDialog { Description = T("Choose parent directory for a new result folder", "Выберите родительскую папку для нового результата") };
        if (destination.ShowDialog(this) != DialogResult.OK) return;
        string folder = Path.Combine(destination.SelectedPath, "MVS_science_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture) + "_" + Guid.NewGuid().ToString("N")[..6]);
        using var progress = new ProgressDialog(caption, T("Cancel", "Отмена"), settings.Language == "ru");
        try
        {
            await RunLocalTaskAsync(progress, async () =>
            {
            var reporter = new Progress<ProgressInfo>(progress.UpdateProgress);
            TResult report = await Task.Run(() => work(reporter, progress.Token));
            progress.Token.ThrowIfCancellationRequested(); Directory.CreateDirectory(folder);
            await Task.Run(() => save(report, folder));
            lastScienceText = describe(report); lastScienceFolder = folder;
            });
            Navigate("advanced");
        }
        catch (OperationCanceledException) { }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        finally { Activate(); }
    }
}
