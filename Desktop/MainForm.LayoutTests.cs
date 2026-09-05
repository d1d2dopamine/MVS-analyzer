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
        if (navItems.ContainsKey("models")) failures.Add("Unexpected scientific-model sidebar tab");
        return failures;
    }
    internal IEnumerable<TabControl> LayoutTabs() => currentPage?.Controls.OfType<TabControl>().ToArray() ?? Array.Empty<TabControl>();
}
