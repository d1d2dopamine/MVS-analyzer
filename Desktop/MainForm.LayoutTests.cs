namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    // Fixture-only entry point used by the Windows layout harness. It never starts a model,
    // opens a browser, writes settings or starts the loopback listener.
    internal void ShowLayoutFixture(string page, bool populated = true)
    {
        if (!layoutTestMode) throw new InvalidOperationException("Layout fixture mode is required.");
        if (populated)
        {
            data = AnalysisEngine.Build(AnalysisEngine.Demo());
            datasetName = "UI fixture · synthetic data, not scientific results.csv";
            datasetHash = new string('a', 64); loadedProcessing = ProcessingSnapshot.From(settings);
            string[] tracks = AnalysisEngine.DefaultTracks;
            calibration = AnalysisEngine.MetricKeys.Select((key, i) => new CalibrationRow(key, .003, .85, 88,
                Tracks: tracks, TrackPowers: new[] { .85, .76, .68 }, TrackScores: new[] { 88d, 82d, 75d },
                TrackMdes: new[] { .1, double.NaN, double.NaN }, TrackCurves: new[] { "", "", "" },
                Repetitions: 2000, FprLow: .001, FprHigh: .009, TrackPowerLow: new[] { .82, .73, .65 },
                TrackPowerHigh: new[] { .88, .79, .71 }, TrackFailures: new[] { 0, 0, 0 },
                TrackMdeStatus: new[] { "estimated_on_grid", "no_crossing", "no_crossing" })).ToList();
            results = AnalysisEngine.MetricKeys.Select((key, i) => new ResultRow(key, 100, 105, 5, .0002, .003, .85, 88, true,
                GroupSummary: "Reference group: 100 · Experimental group: 105", Effect: -.45, EffectLow: -.62,
                EffectHigh: -.24, Verdict: "difference", EffectPair: "Reference group vs Experimental group",
                Tracks: tracks, TrackPowers: new[] { .85, .76, .68 }, TrackScores: new[] { 88d, 82d, 75d },
                TrackMdes: new[] { .1, double.NaN, double.NaN }, TrackCandidates: new[] { true, true, false },
                AdjustedP: .0024, EffectIntervalStatus: "descriptive_selected_pair")).ToList();
            lastCalibrationRepetitions = 2000; calibrationSettingsHash = SettingsContract.Fingerprint(settings);
        }
        else { data = null; calibration = null; results = null; }
        Navigate(page); FitContentWidth();
        statusLabel.Text = "UI FIXTURE — synthetic display values, not scientific results";
    }
    internal IReadOnlyList<string> InspectLayout()
    {
        var failures = new List<string>();
        if (currentPage == null) { failures.Add("No page"); return failures; }
        foreach (CardPanel card in currentPage.Controls.OfType<CardPanel>())
        {
            if (card.Height < 90) failures.Add("Collapsed card: " + card.Height);
            var children = card.Controls.Cast<Control>().Where(c => c.Visible).ToArray();
            foreach (Control child in children)
            {
                if (child.Left < 0 || child.Top < 0 || child.Right > card.ClientSize.Width + 2 || child.Bottom > card.ClientSize.Height + 2)
                    failures.Add("Outside card: " + child.GetType().Name + " " + child.Text[..Math.Min(child.Text.Length, 35)] + " " + child.Bounds);
                if (child is Button button && button.Name == "run-via-colab" && button.Image == null) failures.Add("Missing Colab icon");
            }
            for (int i = 0; i < children.Length; i++)
                for (int j = i + 1; j < children.Length; j++)
                    if (children[i].Bounds.IntersectsWith(children[j].Bounds)) failures.Add("Overlapping card children: " + children[i].Text + " / " + children[j].Text);
        }
        foreach (TabControl tabs in currentPage.Controls.OfType<TabControl>())
            if (tabs.Height < 380 || tabs.Width < 400 || tabs.DisplayRectangle.Height < 270) failures.Add("Collapsed result tabs");
        if (navItems.ContainsKey("colab")) failures.Add("Colab must not be a sidebar page");
        InspectActionRows(currentPage, failures);
        if (navItems.ContainsKey("models")) failures.Add("Unexpected scientific-model sidebar tab");
        return failures;
    }
    internal IEnumerable<TabControl> LayoutTabs() => currentPage?.Controls.OfType<TabControl>().ToArray() ?? Array.Empty<TabControl>();
    private static void InspectActionRows(Control root, List<string> failures)
    {
        foreach (Control child in root.Controls)
        {
            if (child is ActionButtonPanel row)
            {
                var buttons = row.Controls.OfType<Button>().ToArray();
                foreach (Button button in buttons)
                    if (button.Left < 0 || button.Top < 0 || button.Right > row.ClientSize.Width + 1 || button.Bottom > row.ClientSize.Height + 1)
                        failures.Add("Outside action row: " + button.Text);
                foreach (var band in buttons.GroupBy(b => b.Top))
                    if (band.Select(b => b.Height).Distinct().Count() != 1) failures.Add("Unequal button heights");
                for (int i = 0; i < buttons.Length; i++)
                    for (int j = i + 1; j < buttons.Length; j++)
                        if (buttons[i].Bounds.IntersectsWith(buttons[j].Bounds)) failures.Add("Overlapping action buttons");
            }
            if (child is not DataGridView) InspectActionRows(child, failures);
        }
    }

    internal Form ShowColabLayoutFixture(string phase)
    {
        if (!layoutTestMode) throw new InvalidOperationException("Layout fixture mode is required.");
        string previousPage = activePage;
        Control? previousContent = currentPage;
        ShowColabPanel();
        if (activePage != previousPage || !ReferenceEquals(currentPage, previousContent))
            throw new InvalidOperationException("Opening Colab replaced the main page.");
        var view = colabPanel!;
        view.State.Text = ColabPhaseLabel(phase);
        view.Runtime.Text = "CPU: 2 · RAM: 12.7 GiB · GPU: Tesla T4";
        view.Detail.Text = phase == "failed" ? T("The job failed. Saved files were retained. Reconnect or inspect the notebook error before retrying.",
            "Задание завершилось с ошибкой. Сохранённые файлы не удалены. Перед повтором проверьте сообщение в ноутбуке или переподключитесь.")
            : T("UI fixture: synthetic display values. No notebook connection or computation is started.",
                "Проверка интерфейса: условные значения. Подключение к ноутбуку и вычисления не запускаются.");
        bool busy = ColabSessionStore.Working(phase);
        view.Progress.Style = ProgressBarStyle.Continuous; view.Progress.Value = busy ? 42 : phase == "complete" ? 100 : 0;
        view.Calibrate.Enabled = phase == "ready"; view.Analyze.Enabled = phase == "calibrated";
        view.Download.Enabled = phase is "complete" or "calibrated"; view.Stop.Enabled = busy;
        view.Code.Enabled = phase != "offline";
        colabWindow!.FitCards(); return colabWindow;
    }

    internal IReadOnlyList<string> InspectColabLayout()
    {
        var failures = new List<string>();
        if (colabWindow == null || !colabWindow.TopLevel || !colabWindow.ShowInTaskbar) { failures.Add("Colab is not a separate top-level window"); return failures; }
        foreach (CardPanel card in colabWindow.Content.Controls.OfType<CardPanel>())
        {
            var children = card.Controls.Cast<Control>().Where(c => c.Visible).ToArray();
            foreach (Control child in children)
                if (child.Left < 0 || child.Top < 0 || child.Right > card.ClientSize.Width + 2 || child.Bottom > card.ClientSize.Height + 2)
                    failures.Add("Outside Colab card: " + child.Text);
            for (int i = 0; i < children.Length; i++)
                for (int j = i + 1; j < children.Length; j++)
                    if (children[i].Bounds.IntersectsWith(children[j].Bounds)) failures.Add("Overlapping Colab controls");
        }
        InspectActionRows(colabWindow, failures);
        return failures;
    }

    internal async Task ExerciseProgressLayoutAsync(Action<Form> inspect, bool cancel = false)
    {
        if (!layoutTestMode) throw new InvalidOperationException("Layout fixture mode is required.");
        using var progress = new ProgressDialog(T("Calibration", "Калибровка"), T("Cancel", "Отмена"), settings.Language == "ru");
        await RunLocalTaskAsync(progress, async () =>
        {
            progress.UpdateProgress(new ProgressInfo(.42, T("Calibrating measurements", "Калибровка измерений"),
                T("Long progress details must stay within the dialog, including a long output file path.", "Длинные сведения о прогрессе и путь к файлу должны оставаться внутри окна, не перекрывая кнопку отмены.")));
            await Task.Delay(30);
            if (!Enabled || !host.Enabled) throw new InvalidOperationException("Managed Enabled changed during a calculation.");
            if (progress.BackColor != Surface || progress.ForeColor != TextColor) throw new InvalidOperationException("Progress dialog lost the app theme.");
            inspect(progress);
            if (cancel) { progress.Close(); progress.Token.ThrowIfCancellationRequested(); }
        });
    }

}
