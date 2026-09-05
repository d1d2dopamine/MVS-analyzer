using System.Globalization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer;

/// <summary>
/// The developer section at the bottom of Settings. It lives in its own partial file so that adding
/// the benchmark costs the rest of the window exactly one line of change.
/// </summary>
internal sealed partial class MainForm
{
    private string lastBenchmarkFolder = "";

    private void AddDeveloperCard(FlowLayoutPanel page)
    {
        var card = Card(
            T("Developer — benchmark", "Для разработчика — бенчмарк"),
            T("Runs the declared protocol against data whose truth is known, then writes the figures, the tables and a checksummed manifest into a folder that opens when the run ends. Nothing leaves this machine.",
              "Прогоняет заранее записанный протокол на данных с известной истиной и сохраняет графики, таблицы и манифест в папку, которая откроется по окончании. Ничто не покидает этот компьютер."),
            490);

        BenchmarkOptions options = BenchmarkOptions.Load();
        if (string.IsNullOrWhiteSpace(options.OutputFolder)) options.OutputFolder = DefaultBenchmarkRoot();

        card.Controls.Add(new Label { Text = T("Depth", "Глубина"), AutoSize = true, Location = new Point(20, 82) });
        var depth = new ThemedComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(20, 106), Width = 320 };
        foreach (BenchmarkProfile item in BenchmarkProtocol.Profiles)
            depth.Items.Add(T(item.Name, item.NameRu) + "  ·  " + T(item.Estimate, item.EstimateRu));
        depth.SelectedIndex = Math.Clamp(
            Array.FindIndex(BenchmarkProtocol.Profiles, x => x.Id == options.ProfileId),
            0, BenchmarkProtocol.Profiles.Length - 1);
        card.Controls.Add(depth);

        card.Controls.Add(new Label { Text = "Seed", AutoSize = true, Location = new Point(370, 82) });
        var seed = new ThemedNumericUpDown
        {
            Minimum = 1,
            Maximum = int.MaxValue,
            Value = Math.Clamp(options.Seed, 1, int.MaxValue),
            Location = new Point(370, 106),
            Width = 190
        };
        card.Controls.Add(seed);

        card.Controls.Add(new Label { Text = T("Results folder", "Папка для результатов"), AutoSize = true, Location = new Point(20, 154) });
        var outputBox = new TextBox { Text = options.OutputFolder, Location = new Point(20, 178), Width = 600 };
        card.Controls.Add(outputBox);
        var browseOutput = Button(T("Browse", "Обзор"), false, 120);
        browseOutput.Location = new Point(632, 176);
        card.Controls.Add(browseOutput);

        card.Controls.Add(new Label
        {
            Text = T("Folder with real recordings (optional)", "Папка с реальными записями (необязательно)"),
            AutoSize = true,
            Location = new Point(20, 224)
        });
        var realBox = new TextBox { Text = options.RealDataFolder, Location = new Point(20, 248), Width = 600 };
        card.Controls.Add(realBox);
        var browseReal = Button(T("Browse", "Обзор"), false, 120);
        browseReal.Location = new Point(632, 246);
        card.Controls.Add(browseReal);

        var status = new Label
        {
            Text = T("The figures are written as PNG files ready to publish.", "Графики сохраняются в PNG, готовые к публикации."),
            AutoSize = true,
            MaximumSize = new Size(720, 0),
            ForeColor = Secondary,
            Location = new Point(20, 350)
        };

        var run = Button(T("Run benchmark", "Запустить бенчмарк"), true, 260);
        run.Location = new Point(20, 300);
        card.Controls.Add(run);

        var openLast = Button(T("Open last results", "Открыть последние результаты"), false, 240);
        openLast.Location = new Point(292, 300);
        openLast.Enabled = lastBenchmarkFolder.Length > 0 && Directory.Exists(lastBenchmarkFolder);
        card.Controls.Add(openLast);

        var colab = ColabButton(() =>
        {
            if (!string.IsNullOrWhiteSpace(realBox.Text)) { MessageBox.Show(this, T("The Colab benchmark button currently runs the synthetic protocol only; real recordings were not included.", "Кнопка Colab запускает только синтетический протокол; реальные записи не включаются.")); return; }
            StartColab("benchmark", 0, "benchmark", new[] { "--profile", BenchmarkProtocol.Profiles[depth.SelectedIndex].Id, "--seed", ((int)seed.Value).ToString(CultureInfo.InvariantCulture) });
        });
        colab.Location = new Point(20, 410); card.Controls.Add(colab);
        card.Controls.Add(status);
        card.Controls.Add(new Label
        {
            Text = BenchmarkProtocol.Version + "   ·   " + BenchmarkProtocol.Hash,
            AutoSize = true,
            ForeColor = Secondary,
            Location = new Point(20, 465)
        });

        void Save()
        {
            options.ProfileId = BenchmarkProtocol.Profiles[Math.Clamp(depth.SelectedIndex, 0, BenchmarkProtocol.Profiles.Length - 1)].Id;
            options.Seed = (int)seed.Value;
            options.OutputFolder = outputBox.Text.Trim();
            options.RealDataFolder = realBox.Text.Trim();
            options.Save();
        }

        depth.SelectedIndexChanged += (_, _) => Save();
        seed.ValueChanged += (_, _) => Save();
        outputBox.TextChanged += (_, _) => Save();
        realBox.TextChanged += (_, _) => Save();

        browseOutput.Click += (_, _) =>
        {
            using var dialog = new FolderBrowserDialog { Description = T("Where should the benchmark results go?", "Куда сохранить результаты бенчмарка?") };
            if (outputBox.Text.Length > 0 && Directory.Exists(outputBox.Text)) dialog.SelectedPath = outputBox.Text;
            if (dialog.ShowDialog(this) == DialogResult.OK) outputBox.Text = dialog.SelectedPath;
        };

        browseReal.Click += (_, _) =>
        {
            using var dialog = new FolderBrowserDialog { Description = T("Folder with prepared CSV recordings", "Папка с подготовленными CSV-записями") };
            if (realBox.Text.Length > 0 && Directory.Exists(realBox.Text)) dialog.SelectedPath = realBox.Text;
            if (dialog.ShowDialog(this) == DialogResult.OK) realBox.Text = dialog.SelectedPath;
        };

        openLast.Click += (_, _) =>
        {
            if (lastBenchmarkFolder.Length > 0) OpenFolder(lastBenchmarkFolder);
        };

        run.Click += async (_, _) =>
        {
            Save();
            BenchmarkProfile chosen = BenchmarkProtocol.Profiles[Math.Clamp(depth.SelectedIndex, 0, BenchmarkProtocol.Profiles.Length - 1)];
            await RunBenchmarkAsync(chosen, (int)seed.Value, outputBox.Text.Trim(), realBox.Text.Trim(), status, openLast);
        };

        page.Controls.Add(card);
    }

    private async Task RunBenchmarkAsync(BenchmarkProfile profile, int seed, string outputRoot, string realData, Label status, Button openLast)
    {
        if (localOperationInProgress) return;
        if (outputRoot.Length == 0)
        {
            status.ForeColor = Color.FromArgb(176, 66, 27);
            status.Text = T("Choose a results folder first.", "Сначала выберите папку для результатов.");
            return;
        }

        bool russian = settings.Language == "ru";
        using var progress = new ProgressDialog(
            T("Running benchmark", "Прогон бенчмарка"),
            T("Cancel", "Отмена"),
            russian);

        BenchmarkReportResult? report = null;
        string failure = "";
        bool cancelled = false;
        try
        {
            await RunLocalTaskAsync(progress, async () =>
            {
            var reporter = new Progress<ProgressInfo>(progress.UpdateProgress);
            CancellationToken token = progress.Token;
            report = await Task.Run(
                () => BenchmarkReport.RunAndWrite(profile, seed, outputRoot, realData, russian, reporter, token),
                token);
            });
        }
        catch (OperationCanceledException)
        {
            cancelled = true;
        }
        catch (Exception error)
        {
            failure = error.Message;
        }
        finally
        {
            Activate();
        }

        if (cancelled)
        {
            status.ForeColor = Secondary;
            status.Text = T("Cancelled. Nothing was written.", "Отменено. Ничего не сохранено.");
            return;
        }

        if (failure.Length > 0 || report == null)
        {
            status.ForeColor = Color.FromArgb(176, 66, 27);
            status.Text = T("The benchmark stopped: ", "Бенчмарк остановлен: ") + failure;
            MessageBox.Show(this, failure, T("Benchmark", "Бенчмарк"), MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        lastBenchmarkFolder = report.Folder;
        openLast.Enabled = true;

        BenchmarkOutcome outcome = report.Outcome;
        ConditionSummary? primary = outcome.Find("primary_null");
        string headline = primary == null
            ? ""
            : T("Picking the best of twelve metrics: ", "Выбор лучшей из двенадцати метрик: ") +
              BenchmarkRunner.Pct(primary.Rate(BenchmarkProcedures.CherryPick)) +
              T(" false discoveries. Same data through MVS: ", " ложных открытий. Те же данные через MVS: ") +
              BenchmarkRunner.Pct(primary.Rate(BenchmarkProcedures.MvsStrict)) + ".";

        string verdict = outcome.Overall switch
        {
            "go" => T("Every declared threshold was met.", "Все заранее записанные пороги выполнены."),
            "no-go" => T("At least one threshold was missed.", "Не выполнен как минимум один порог."),
            _ => T("Nothing failed, but not everything cleared the bar.", "Провалов нет, но не всё прошло порог."),
        };

        status.ForeColor = Secondary;
        status.Text = verdict + "  " + headline;

        string message = verdict + "\n\n" + headline + "\n\n" +
            T("Figures written: ", "Графиков сохранено: ") + report.Figures.Count.ToString(CultureInfo.InvariantCulture) + "\n" +
            T("Folder: ", "Папка: ") + report.Folder + "\n\n" +
            T("Seed ", "Seed ") + seed.ToString(CultureInfo.InvariantCulture) +
            T(" reproduces this run exactly.", " воспроизводит этот прогон точно.");

        MessageBox.Show(this, message, T("Benchmark finished", "Бенчмарк завершён"), MessageBoxButtons.OK, MessageBoxIcon.Information);
        OpenFolder(report.FiguresFolder);
    }

    private static string DefaultBenchmarkRoot()
    {
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (home.Length == 0) return Environment.CurrentDirectory;
        string downloads = Path.Combine(home, "Downloads");
        return Directory.Exists(downloads) ? downloads : home;
    }
}
