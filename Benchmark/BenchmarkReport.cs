using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace MvsAnalyzer.Benchmarking;

internal sealed class BenchmarkReportResult
{
    public required string Folder { get; init; }
    public required string FiguresFolder { get; init; }
    public required BenchmarkOutcome Outcome { get; init; }
    public required List<string> Figures { get; init; }
    public required List<string> Files { get; init; }
}

/// <summary>
/// Runs the benchmark and writes everything a sceptical reader would ask for: the figures, the raw
/// rates behind every bar, the pre-registered scorecard, a manifest that pins the protocol and the
/// engine, and a checksum file so a downloaded copy can be verified.
/// </summary>
internal static class BenchmarkReport
{
    private static string AppVersion
    {
        get
        {
            Version? version = typeof(BenchmarkReport).Assembly.GetName().Version;
            return version == null ? "unknown" : version.ToString(3);
        }
    }

    public static BenchmarkReportResult RunAndWrite(
        BenchmarkProfile profile,
        int seed,
        string root,
        string realDataFolder,
        bool russian,
        IProgress<ProgressInfo>? progress,
        CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(root))
            throw new InvalidDataException("Choose a folder for the benchmark output first.");

        BenchmarkOutcome outcome = BenchmarkRunner.Run(profile, seed, realDataFolder, russian, progress, token);

        string folder = Unique(Path.Combine(root, "MVS_Benchmark_" + outcome.RunId));
        Directory.CreateDirectory(folder);
        string figuresFolder = Path.Combine(folder, "figures");
        Directory.CreateDirectory(figuresFolder);

        progress?.Report(new ProgressInfo(.99,
            russian ? "Сохранение графиков" : "Saving the figures", figuresFolder));
        List<string> figures = BenchmarkFigures.Generate(outcome, figuresFolder, russian);

        progress?.Report(new ProgressInfo(.995,
            russian ? "Сохранение таблиц и отчёта" : "Saving the tables and the report", folder));
        var files = new List<string>
        {
            Write(folder, "benchmark_report.md", Markdown(outcome, russian)),
            Write(folder, "benchmark_summary.csv", SummaryCsv(outcome)),
            Write(folder, "benchmark_metrics.csv", MetricsCsv(outcome)),
            Write(folder, "benchmark_choices.csv", ChoicesCsv(outcome)),
            Write(folder, "benchmark_stability.csv", StabilityCsv(outcome)),
            Write(folder, "benchmark_verdicts.csv", VerdictsCsv(outcome)),
            Write(folder, "benchmark_protocol.txt", BenchmarkProtocol.Specification)
        };
        files.Add(Write(folder, "benchmark_manifest.json", Manifest(outcome, figures, files)));

        var everything = new List<string>(files);
        everything.AddRange(figures);
        everything.Sort(StringComparer.Ordinal);
        var sums = new StringBuilder();
        foreach (string file in everything)
            sums.Append(OutputExporter.HashFile(file)).Append("  ")
                .Append(Path.GetRelativePath(folder, file).Replace('\\', '/')).Append('\n');
        files.Add(Write(folder, "SHA256SUMS.txt", sums.ToString()));

        AppendJournal(outcome, folder);

        return new BenchmarkReportResult
        {
            Folder = folder,
            FiguresFolder = figuresFolder,
            Outcome = outcome,
            Figures = figures,
            Files = files
        };
    }

    private static string Unique(string folder)
    {
        if (!Directory.Exists(folder)) return folder;
        for (int i = 2; i < 500; i++)
        {
            string candidate = folder + "_" + i.ToString(CultureInfo.InvariantCulture);
            if (!Directory.Exists(candidate)) return candidate;
        }
        return folder + "_" + Guid.NewGuid().ToString("N").Substring(0, 6);
    }

    private static string Write(string folder, string name, string content)
    {
        string path = Path.Combine(folder, name);
        File.WriteAllText(path, content, new UTF8Encoding(false));
        return path;
    }

    private static string C(string value)
    {
        if (value.IndexOf(',') < 0 && value.IndexOf('"') < 0 && value.IndexOf('\n') < 0) return value;
        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    private static string N(double value) =>
        double.IsFinite(value) ? value.ToString("0.######", CultureInfo.InvariantCulture) : "";

    private static string I(int value) => value.ToString(CultureInfo.InvariantCulture);

    // ---------------- tables ----------------

    private static string SummaryCsv(BenchmarkOutcome outcome)
    {
        var text = new StringBuilder();
        text.Append("condition,stage,design,shape,mode,effect,contamination,source,planned,completed,failed,");
        text.Append("procedure,procedure_label,rejections,rate,standard_error,wilson_low,wilson_high,claim_rate\n");
        foreach (ConditionSummary summary in outcome.Conditions)
        {
            BenchmarkCondition condition = summary.Condition;
            for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
            {
                (double low, double high) = summary.Interval(procedure);
                text.Append(C(condition.Id)).Append(',')
                    .Append(C(condition.Stage)).Append(',')
                    .Append(C(condition.DesignId)).Append(',')
                    .Append(C(condition.Shape)).Append(',')
                    .Append(C(condition.Mode)).Append(',')
                    .Append(N(condition.Effect)).Append(',')
                    .Append(N(condition.Contamination)).Append(',')
                    .Append(C(condition.Source)).Append(',')
                    .Append(I(condition.Replications)).Append(',')
                    .Append(I(summary.Completed)).Append(',')
                    .Append(I(summary.Failed)).Append(',')
                    .Append(C(BenchmarkProcedures.Ids[procedure])).Append(',')
                    .Append(C(BenchmarkProcedures.Label(procedure, false))).Append(',')
                    .Append(I(summary.Rejections[procedure])).Append(',')
                    .Append(N(summary.Rate(procedure))).Append(',')
                    .Append(N(summary.StandardError(procedure))).Append(',')
                    .Append(N(low)).Append(',')
                    .Append(N(high)).Append(',')
                    .Append(N(summary.ClaimRate(procedure))).Append('\n');
            }
        }
        return text.ToString();
    }

    private static string MetricsCsv(BenchmarkOutcome outcome)
    {
        var text = new StringBuilder();
        text.Append("condition,stage,mode,effect,contamination,metric,rejections,completed,rate\n");
        foreach (ConditionSummary summary in outcome.Conditions)
        {
            for (int metric = 0; metric < summary.MetricRejections.Length; metric++)
            {
                text.Append(C(summary.Condition.Id)).Append(',')
                    .Append(C(summary.Condition.Stage)).Append(',')
                    .Append(C(summary.Condition.Mode)).Append(',')
                    .Append(N(summary.Condition.Effect)).Append(',')
                    .Append(N(summary.Condition.Contamination)).Append(',')
                    .Append(C(AnalysisEngine.MetricKeys[metric])).Append(',')
                    .Append(I(summary.MetricRejections[metric])).Append(',')
                    .Append(I(summary.Completed)).Append(',')
                    .Append(N(summary.MetricRate(metric))).Append('\n');
            }
        }
        return text.ToString();
    }

    private static string ChoicesCsv(BenchmarkOutcome outcome)
    {
        var text = new StringBuilder();
        text.Append("condition,procedure,metric,count,share\n");
        int metrics = AnalysisEngine.MetricKeys.Length;
        foreach (ConditionSummary summary in outcome.Conditions)
        {
            for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
            {
                int[] counts = summary.ChosenCounts[procedure];
                for (int slot = 0; slot < counts.Length; slot++)
                {
                    if (counts[slot] == 0) continue;
                    text.Append(C(summary.Condition.Id)).Append(',')
                        .Append(C(BenchmarkProcedures.Ids[procedure])).Append(',')
                        .Append(C(slot >= metrics ? "none" : AnalysisEngine.MetricKeys[slot])).Append(',')
                        .Append(I(counts[slot])).Append(',')
                        .Append(N(summary.Completed == 0 ? double.NaN : counts[slot] / (double)summary.Completed)).Append('\n');
                }
            }
        }
        return text.ToString();
    }

    private static string StabilityCsv(BenchmarkOutcome outcome)
    {
        var text = new StringBuilder();
        text.Append("split,kendall_tau\n");
        for (int i = 0; i < outcome.Stability.Tau.Length; i++)
            text.Append(I(i + 1)).Append(',').Append(N(outcome.Stability.Tau[i])).Append('\n');
        return text.ToString();
    }

    private static string VerdictsCsv(BenchmarkOutcome outcome)
    {
        var text = new StringBuilder();
        text.Append("id,result,threshold,observed,question\n");
        foreach (HypothesisVerdict verdict in outcome.Verdicts)
            text.Append(C(verdict.Id)).Append(',')
                .Append(C(verdict.Result)).Append(',')
                .Append(C(verdict.Threshold)).Append(',')
                .Append(C(verdict.Observed)).Append(',')
                .Append(C(verdict.Question)).Append('\n');
        return text.ToString();
    }

    // ---------------- manifest ----------------

    private static string J(string value)
    {
        var text = new StringBuilder();
        foreach (char c in value)
        {
            if (c == '"' || c == '\\') text.Append('\\').Append(c);
            else if (c == '\n') text.Append("\\n");
            else if (c == '\r') text.Append("\\r");
            else if (c == '\t') text.Append("\\t");
            else if (c < ' ') text.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            else text.Append(c);
        }
        return text.ToString();
    }

    private static string Manifest(BenchmarkOutcome outcome, List<string> figures, List<string> files)
    {
        var text = new StringBuilder();
        text.Append("{\n");
        text.Append("  \"kind\": \"mvs-benchmark\",\n");
        text.Append("  \"protocolVersion\": \"").Append(J(BenchmarkProtocol.Version)).Append("\",\n");
        text.Append("  \"protocolHash\": \"").Append(J(BenchmarkProtocol.Hash)).Append("\",\n");
        text.Append("  \"protocolHashFrozen\": \"").Append(J(BenchmarkProtocol.FrozenHash)).Append("\",\n");
        text.Append("  \"protocolUnchanged\": ").Append(BenchmarkProtocol.HashIsFrozen ? "true" : "false").Append(",\n");
        text.Append("  \"appVersion\": \"").Append(J(AppVersion)).Append("\",\n");
        text.Append("  \"engineVersion\": \"").Append(J(AnalysisEngine.EngineVersion)).Append("\",\n");
        text.Append("  \"formulaVersion\": \"").Append(J(OutputExporter.FormulaVersion)).Append("\",\n");
        text.Append("  \"formulaHash\": \"").Append(J(OutputExporter.FormulaHash)).Append("\",\n");
        text.Append("  \"runId\": \"").Append(J(outcome.RunId)).Append("\",\n");
        text.Append("  \"seed\": ").Append(I(outcome.Seed)).Append(",\n");
        text.Append("  \"profile\": \"").Append(J(outcome.Profile.Id)).Append("\",\n");
        text.Append("  \"startedUtc\": \"").Append(outcome.StartedUtc.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)).Append("\",\n");
        text.Append("  \"finishedUtc\": \"").Append(outcome.FinishedUtc.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)).Append("\",\n");
        text.Append("  \"durationSeconds\": ").Append(I((int)outcome.Duration.TotalSeconds)).Append(",\n");
        text.Append("  \"threads\": ").Append(I(outcome.Threads)).Append(",\n");
        text.Append("  \"runtime\": \"").Append(J(Environment.Version.ToString())).Append("\",\n");
        text.Append("  \"os\": \"").Append(J(Environment.OSVersion.VersionString)).Append("\",\n");
        text.Append("  \"overall\": \"").Append(J(outcome.Overall)).Append("\",\n");

        text.Append("  \"replications\": { \"primary\": ").Append(I(outcome.Profile.PrimaryReplications))
            .Append(", \"grid\": ").Append(I(outcome.Profile.GridReplications))
            .Append(", \"calibration\": ").Append(I(outcome.Profile.CalibrationRepetitions))
            .Append(", \"stability\": ").Append(I(outcome.Profile.StabilityRepeats))
            .Append(", \"determinism\": ").Append(I(outcome.Profile.DeterminismReplications)).Append(" },\n");

        text.Append("  \"thresholds\": { \"alpha\": ").Append(N(BenchmarkProtocol.Alpha))
            .Append(", \"cherryPickFprPass\": ").Append(N(BenchmarkProtocol.CherryPickFprPass))
            .Append(", \"mvsFprPass\": ").Append(N(BenchmarkProtocol.MvsFprPass))
            .Append(", \"mvsFprFail\": ").Append(N(BenchmarkProtocol.MvsFprFail))
            .Append(", \"powerLossPass\": ").Append(N(BenchmarkProtocol.PowerLossPass))
            .Append(", \"powerLossFail\": ").Append(N(BenchmarkProtocol.PowerLossFail))
            .Append(", \"tauPass\": ").Append(N(BenchmarkProtocol.TauPass))
            .Append(", \"tauFail\": ").Append(N(BenchmarkProtocol.TauFail))
            .Append(", \"topOneAgreementPass\": ").Append(N(BenchmarkProtocol.TopOneAgreementPass)).Append(" },\n");

        text.Append("  \"determinism\": { \"first\": \"").Append(J(outcome.DeterminismFirst))
            .Append("\", \"second\": \"").Append(J(outcome.DeterminismSecond))
            .Append("\", \"identical\": ")
            .Append(string.Equals(outcome.DeterminismFirst, outcome.DeterminismSecond, StringComparison.Ordinal) ? "true" : "false")
            .Append(" },\n");

        text.Append("  \"stability\": { \"medianTau\": ").Append(N(outcome.Stability.MedianTau))
            .Append(", \"lowerQuartileTau\": ").Append(N(outcome.Stability.LowerQuartileTau))
            .Append(", \"topOneAgreement\": ").Append(N(outcome.Stability.TopOneAgreement))
            .Append(", \"splits\": ").Append(I(outcome.Stability.Repeats))
            .Append(", \"failed\": ").Append(I(outcome.Stability.Failed)).Append(" },\n");

        text.Append("  \"lockedPilotMetric\": {");
        bool firstPair = true;
        foreach (KeyValuePair<string, int> pair in outcome.LockedPilotMetric)
        {
            if (!firstPair) text.Append(',');
            firstPair = false;
            int index = Math.Clamp(pair.Value, 0, AnalysisEngine.MetricKeys.Length - 1);
            text.Append(" \"").Append(J(pair.Key)).Append("\": \"").Append(J(AnalysisEngine.MetricKeys[index])).Append('"');
        }
        text.Append(" },\n");

        text.Append("  \"verdicts\": [\n");
        for (int i = 0; i < outcome.Verdicts.Count; i++)
        {
            HypothesisVerdict verdict = outcome.Verdicts[i];
            text.Append("    { \"id\": \"").Append(J(verdict.Id))
                .Append("\", \"result\": \"").Append(J(verdict.Result))
                .Append("\", \"threshold\": \"").Append(J(verdict.Threshold))
                .Append("\", \"observed\": \"").Append(J(verdict.Observed))
                .Append("\", \"question\": \"").Append(J(verdict.Question)).Append("\" }");
            text.Append(i == outcome.Verdicts.Count - 1 ? "\n" : ",\n");
        }
        text.Append("  ],\n");

        text.Append("  \"conditions\": [\n");
        for (int i = 0; i < outcome.Conditions.Count; i++)
        {
            ConditionSummary summary = outcome.Conditions[i];
            text.Append("    { \"id\": \"").Append(J(summary.Condition.Id))
                .Append("\", \"stage\": \"").Append(J(summary.Condition.Stage))
                .Append("\", \"design\": \"").Append(J(summary.Condition.DesignId))
                .Append("\", \"shape\": \"").Append(J(summary.Condition.Shape))
                .Append("\", \"mode\": \"").Append(J(summary.Condition.Mode))
                .Append("\", \"effect\": ").Append(N(summary.Condition.Effect))
                .Append(", \"contamination\": ").Append(N(summary.Condition.Contamination))
                .Append(", \"completed\": ").Append(I(summary.Completed))
                .Append(", \"failed\": ").Append(I(summary.Failed))
                .Append(", \"digest\": \"").Append(J(summary.DecisionDigest)).Append("\" }");
            text.Append(i == outcome.Conditions.Count - 1 ? "\n" : ",\n");
        }
        text.Append("  ],\n");

        var names = new List<string>();
        foreach (string file in files) names.Add(Path.GetFileName(file));
        foreach (string file in figures) names.Add("figures/" + Path.GetFileName(file));
        names.Sort(StringComparer.Ordinal);
        text.Append("  \"files\": [");
        for (int i = 0; i < names.Count; i++)
        {
            text.Append(" \"").Append(J(names[i])).Append('"');
            if (i < names.Count - 1) text.Append(',');
        }
        text.Append(" ],\n");

        text.Append("  \"notes\": [");
        for (int i = 0; i < outcome.Notes.Count; i++)
        {
            text.Append(" \"").Append(J(outcome.Notes[i])).Append('"');
            if (i < outcome.Notes.Count - 1) text.Append(',');
        }
        text.Append(" ]\n");
        text.Append("}\n");
        return text.ToString();
    }

    // ---------------- narrative report ----------------

    private static string T(bool russian, string english, string translated) => russian ? translated : english;

    private static string Markdown(BenchmarkOutcome outcome, bool russian)
    {
        var text = new StringBuilder();
        ConditionSummary? primary = outcome.Find("primary_null");

        text.Append(T(russian, "# MVS benchmark report\n\n", "# Отчёт бенчмарка MVS\n\n"));
        text.Append(T(russian, "Run ", "Прогон ")).Append(outcome.RunId)
            .Append(T(russian, ", profile ", ", профиль ")).Append(russian ? outcome.Profile.NameRu : outcome.Profile.Name)
            .Append(", seed ").Append(I(outcome.Seed))
            .Append(T(russian, ", duration ", ", длительность ")).Append(I((int)outcome.Duration.TotalMinutes))
            .Append(T(russian, " min.\n\n", " мин.\n\n"));

        text.Append(T(russian, "| Item | Value |\n|---|---|\n", "| Параметр | Значение |\n|---|---|\n"));
        text.Append(T(russian, "| Protocol | ", "| Протокол | ")).Append(BenchmarkProtocol.Version).Append(" |\n");
        text.Append(T(russian, "| Protocol hash | `", "| Хеш протокола | `")).Append(BenchmarkProtocol.Hash).Append("` |\n");
        text.Append(T(russian, "| Protocol unchanged | ", "| Протокол не изменялся | "))
            .Append(BenchmarkProtocol.HashIsFrozen ? T(russian, "yes", "да") : T(russian, "**NO**", "**НЕТ**")).Append(" |\n");
        text.Append(T(russian, "| Engine | ", "| Движок | ")).Append(AnalysisEngine.EngineVersion).Append(" |\n");
        text.Append(T(russian, "| Formula | ", "| Формула | ")).Append(OutputExporter.FormulaVersion)
            .Append(" (`").Append(OutputExporter.FormulaHash).Append("`) |\n");
        text.Append(T(russian, "| Application | ", "| Приложение | ")).Append(AppVersion).Append(" |\n");
        text.Append(T(russian, "| Threads | ", "| Потоков | ")).Append(I(outcome.Threads)).Append(" |\n\n");

        text.Append(T(russian, "## Verdict\n\n", "## Итог\n\n"));
        string overall = outcome.Overall == "go"
            ? T(russian, "**ALL PRE-REGISTERED THRESHOLDS WERE MET.**", "**ВСЕ ЗАРАНЕЕ ЗАПИСАННЫЕ ПОРОГИ ПРОЙДЕНЫ.**")
            : outcome.Overall == "no-go"
                ? T(russian, "**AT LEAST ONE THRESHOLD WAS MISSED.**", "**НЕ ПРОЙДЕН КАК МИНИМУМ ОДИН ПОРОГ.**")
                : T(russian, "**NOTHING FAILED, BUT NOT EVERYTHING CLEARED THE BAR.**", "**ПРОВАЛОВ НЕТ, НО НЕ ВСЁ ДОСТИГЛО ПОРОГА.**");
        text.Append(overall).Append("\n\n");

        text.Append(T(russian,
            "| Hypothesis | Question | Threshold | Observed | Result |\n|---|---|---|---|---|\n",
            "| Гипотеза | Вопрос | Порог | Наблюдается | Результат |\n|---|---|---|---|---|\n"));
        foreach (HypothesisVerdict verdict in outcome.Verdicts)
        {
            string mark = verdict.Result == "pass" ? T(russian, "pass", "пройден")
                : verdict.Result == "fail" ? T(russian, "**fail**", "**провал**")
                : T(russian, "inconclusive", "неясно");
            text.Append("| ").Append(verdict.Id)
                .Append(" | ").Append(russian ? verdict.QuestionRu : verdict.Question)
                .Append(" | ").Append(russian ? verdict.ThresholdRu : verdict.Threshold)
                .Append(" | ").Append(verdict.Observed)
                .Append(" | ").Append(mark).Append(" |\n");
        }
        text.Append('\n');

        text.Append(T(russian, "## Headline: data with no effect in it\n\n", "## Главное: данные без эффекта\n\n"));
        if (primary != null)
        {
            text.Append(T(russian, "Two groups drawn from one population, ", "Две группы из одной генеральной совокупности, "))
                .Append(I(primary.Completed))
                .Append(T(russian, " repetitions. Every discovery here is a false one.\n\n",
                    " повторений. Любое открытие здесь ложное.\n\n"));
            text.Append(T(russian,
                "| Rule for choosing a metric | False discoveries | 95% interval |\n|---|---|---|\n",
                "| Правило выбора метрики | Ложные открытия | 95% интервал |\n|---|---|---|\n"));
            for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
            {
                (double low, double high) = primary.Interval(procedure);
                text.Append("| ").Append(BenchmarkProcedures.Label(procedure, russian))
                    .Append(" | ").Append(BenchmarkRunner.Pct(primary.Rate(procedure)))
                    .Append(" | ").Append(BenchmarkRunner.Pct(low)).Append(" – ").Append(BenchmarkRunner.Pct(high)).Append(" |\n");
            }
            text.Append('\n');
        }

        text.Append(T(russian, "## Power\n\n", "## Мощность\n\n"));
        text.Append(T(russian,
            "| Condition | Cherry-pick | Bonferroni | Fixed median | MVS gated | Oracle |\n|---|---|---|---|---|---|\n",
            "| Условие | Перебор | Bonferroni | Фикс. медиана | MVS с порогом | Оракул |\n|---|---|---|---|---|---|\n"));
        foreach (ConditionSummary summary in outcome.Stage("power"))
        {
            int oracle = summary.OracleMetric();
            text.Append("| ").Append(summary.Condition.Mode).Append(" ×")
                .Append(summary.Condition.Effect.ToString("0.00", CultureInfo.InvariantCulture))
                .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.CherryPick)))
                .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.Bonferroni)))
                .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.FixedMedian)))
                .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.MvsStrict)))
                .Append(" | ").Append(oracle >= 0
                    ? BenchmarkRunner.Pct(summary.MetricRate(oracle)) + " (" + AnalysisEngine.MetricKeys[oracle] + ")"
                    : "n/a")
                .Append(" |\n");
        }
        text.Append('\n');

        text.Append(T(russian, "## Dirty data, other shapes, real recordings\n\n",
            "## Грязные данные, другие формы, реальные записи\n\n"));
        text.Append(T(russian,
            "| Condition | Cherry-pick | MVS gated | Repetitions |\n|---|---|---|---|\n",
            "| Условие | Перебор | MVS с порогом | Повторений |\n|---|---|---|---|\n"));
        foreach (string stage in new[] { "robust", "shape", "real" })
        {
            foreach (ConditionSummary summary in outcome.Stage(stage))
            {
                text.Append("| ").Append(summary.Condition.Id)
                    .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.CherryPick)))
                    .Append(" | ").Append(BenchmarkRunner.Pct(summary.Rate(BenchmarkProcedures.MvsStrict)))
                    .Append(" | ").Append(I(summary.Completed)).Append(" |\n");
            }
        }
        text.Append('\n');

        text.Append(T(russian, "## Stability of the choice\n\n", "## Устойчивость выбора\n\n"));
        text.Append(T(russian, "Median Kendall tau ", "Медианная тау Кендалла ")).Append(BenchmarkRunner.Num(outcome.Stability.MedianTau))
            .Append(T(russian, ", lower quartile ", ", нижний квартиль ")).Append(BenchmarkRunner.Num(outcome.Stability.LowerQuartileTau))
            .Append(T(russian, ", the same metric came first in ", ", та же метрика оказалась первой в "))
            .Append(BenchmarkRunner.Pct(outcome.Stability.TopOneAgreement))
            .Append(T(russian, " of ", " из ")).Append(I(outcome.Stability.Repeats))
            .Append(T(russian, " splits.\n\n", " разбиений.\n\n"));

        text.Append(T(russian, "## Reproducibility\n\n", "## Воспроизводимость\n\n"));
        text.Append(T(russian, "First pass: `", "Первый прогон: `")).Append(outcome.DeterminismFirst).Append("`\n\n");
        text.Append(T(russian, "Replay: `", "Повтор: `")).Append(outcome.DeterminismSecond).Append("`\n\n");
        text.Append(T(russian, "To repeat this entire run:\n\n", "Повторить весь прогон:\n\n"));
        text.Append("```\nMVS_Analyzer.exe --benchmark --profile ").Append(outcome.Profile.Id)
            .Append(" --seed ").Append(I(outcome.Seed)).Append(" --out <folder>\n```\n\n");

        if (outcome.Notes.Count > 0)
        {
            text.Append(T(russian, "## Notes\n\n", "## Замечания\n\n"));
            foreach (string note in outcome.Notes) text.Append("- ").Append(note).Append('\n');
            text.Append('\n');
        }

        text.Append(T(russian, "## What this benchmark does not prove\n\n", "## Чего этот бенчмарк не доказывает\n\n"));
        text.Append(T(russian,
            "- The synthetic conditions are built from the same family of shapes the engine expects. That is a home advantage, and it is stated here on purpose.\n" +
            "- Two groups, one variable, independent entities. Paired designs, covariates and time series are outside this protocol.\n" +
            "- The plasmode stage reuses real recordings only if a folder of them was supplied. Without it, nothing here has touched measured data.\n" +
            "- Error control is a property of the procedure, not a promise about any single study.\n\n",
            "- Синтетические условия построены из того же семейства распределений, которое ожидает движок. Это игра на своём поле, и здесь это сказано намеренно.\n" +
            "- Две группы, одна переменная, независимые объекты. Парные схемы, ковариаты и временные ряды вне этого протокола.\n" +
            "- Стадия plasmode использует реальные записи только если была указана папка с ними. Без неё ничто здесь не касалось измеренных данных.\n" +
            "- Контроль ошибки — свойство процедуры, а не обещание про отдельно взятое исследование.\n\n"));

        return text.ToString();
    }

    // ---------------- append-only journal ----------------

    /// <summary>
    /// Every benchmark run adds one line to a local append-only journal, each line carrying the hash
    /// of the line before it. Deleting or rewriting a disappointing run breaks the chain, and a broken
    /// chain is visible to anyone who reads the file. The application's own run journal is left alone.
    /// </summary>
    private static void AppendJournal(BenchmarkOutcome outcome, string folder)
    {
        try
        {
            string root = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer");
            Directory.CreateDirectory(root);
            string path = Path.Combine(root, "benchmark_journal.jsonl");

            string previous = "";
            if (File.Exists(path))
            {
                string[] lines = File.ReadAllLines(path);
                for (int i = lines.Length - 1; i >= 0; i--)
                {
                    string line = lines[i];
                    int marker = line.LastIndexOf("\"chain\":\"", StringComparison.Ordinal);
                    if (marker < 0) continue;
                    int start = marker + 9;
                    int end = line.IndexOf('"', start);
                    if (end > start) previous = line.Substring(start, end - start);
                    break;
                }
            }

            var payload = new StringBuilder();
            payload.Append("{\"time\":\"").Append(DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture))
                .Append("\",\"runId\":\"").Append(J(outcome.RunId))
                .Append("\",\"seed\":").Append(I(outcome.Seed))
                .Append(",\"profile\":\"").Append(J(outcome.Profile.Id))
                .Append("\",\"protocol\":\"").Append(J(BenchmarkProtocol.Version))
                .Append("\",\"protocolHash\":\"").Append(J(BenchmarkProtocol.Hash))
                .Append("\",\"engine\":\"").Append(J(AnalysisEngine.EngineVersion))
                .Append("\",\"formulaHash\":\"").Append(J(OutputExporter.FormulaHash))
                .Append("\",\"overall\":\"").Append(J(outcome.Overall))
                .Append("\",\"folder\":\"").Append(J(folder))
                .Append("\",\"previous\":\"").Append(J(previous)).Append('"');

            string chain = Sha256(previous + payload.ToString());
            payload.Append(",\"chain\":\"").Append(chain).Append("\"}");
            File.AppendAllText(path, payload.ToString() + Environment.NewLine, new UTF8Encoding(false));
        }
        catch
        {
            // A journal that cannot be written must never cost the user the run they just waited for.
        }
    }

    private static string Sha256(string text)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(text));
        var hex = new StringBuilder(digest.Length * 2);
        foreach (byte value in digest) hex.Append(value.ToString("x2", CultureInfo.InvariantCulture));
        return hex.ToString();
    }
}
