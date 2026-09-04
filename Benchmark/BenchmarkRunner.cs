using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace MvsAnalyzer.Benchmarking;

internal sealed record BenchmarkCondition(
    string Id,
    string Stage,
    string DesignId,
    string Shape,
    string Mode,
    double Effect,
    double Contamination,
    int Replications,
    string Source);

internal sealed class ConditionSummary
{
    public required BenchmarkCondition Condition { get; init; }
    public required int Completed { get; init; }
    public required int Failed { get; init; }
    public required int[] Rejections { get; init; }
    public required int[] Claims { get; init; }
    public required int[] MetricRejections { get; init; }
    /// <summary>Completed replications per half, split by replication index parity.</summary>
    public required int[] CompletedHalf { get; init; }
    /// <summary>Per-metric rejections per half, so the oracle can be chosen and scored on different data.</summary>
    public required int[][] MetricRejectionsHalf { get; init; }
    public required int[][] ChosenCounts { get; init; }
    public required string DecisionDigest { get; init; }
    public required string FirstError { get; init; }

    public bool IsNull => Condition.Mode == "none" || Condition.Effect <= 1.0000001;

    public double Rate(int procedure) => Completed == 0 ? double.NaN : Rejections[procedure] / (double)Completed;

    public double ClaimRate(int procedure) => Completed == 0 ? double.NaN : Claims[procedure] / (double)Completed;

    public double MetricRate(int metric) => Completed == 0 ? double.NaN : MetricRejections[metric] / (double)Completed;

    public double StandardError(int procedure) => BenchmarkMath.ProportionStandardError(Rate(procedure), Completed);

    public (double Low, double High) Interval(int procedure) => BenchmarkMath.WilsonInterval(Rejections[procedure], Completed);

    public double MetricRateIn(int half, int metric) =>
        CompletedHalf[half] == 0 ? double.NaN : MetricRejectionsHalf[half][metric] / (double)CompletedHalf[half];

    /// <summary>
    /// The metric a truth-aware oracle would fix in advance, chosen on one half of the replications
    /// and scored on the other.
    ///
    /// OracleMetric below chooses and scores on the same replications. That takes the maximum of several
    /// noisy rates, so it reports a power the oracle does not actually have: at thirty replications,
    /// where the Monte Carlo standard error is about 4.6 points, the winner is inflated by roughly
    /// one to two of those. The whole of that inflation was being charged to MVS as lost power, which
    /// made hypothesis B look worse than the truth. It is kept only so the two can be printed side by
    /// side and the size of the old bias stays visible.
    /// </summary>
    public int OracleMetricHeldOut()
    {
        int best = -1;
        double bestRate = double.NegativeInfinity;
        for (int m = 0; m < MetricRejectionsHalf[0].Length; m++)
        {
            double rate = MetricRateIn(0, m);
            if (double.IsFinite(rate) && rate > bestRate) { bestRate = rate; best = m; }
        }
        return best;
    }

    /// <summary>Power of the held-out oracle, measured on the half that did not choose it.</summary>
    public double OraclePowerHeldOut()
    {
        int oracle = OracleMetricHeldOut();
        return oracle < 0 ? double.NaN : MetricRateIn(1, oracle);
    }

    /// <summary>Selection-biased oracle, kept for comparison only. See OracleMetricHeldOut.</summary>
    public int OracleMetric()
    {
        int best = -1;
        double bestRate = double.NegativeInfinity;
        for (int m = 0; m < MetricRejections.Length; m++)
        {
            double rate = MetricRate(m);
            if (double.IsFinite(rate) && rate > bestRate) { bestRate = rate; best = m; }
        }
        return best;
    }
}

internal sealed class StabilitySummary
{
    public required double[] Tau { get; init; }
    public required int Repeats { get; init; }
    public required int TopOneMatches { get; init; }
    public required int[] TopMetricCounts { get; init; }
    public required int Failed { get; init; }

    public double MedianTau => BenchmarkMath.Median(Tau);

    public double LowerQuartileTau => BenchmarkMath.Quantile(Tau, .25);

    public double TopOneAgreement => Repeats == 0 ? double.NaN : TopOneMatches / (double)Repeats;
}

internal sealed record HypothesisVerdict(
    string Id,
    string Question,
    string QuestionRu,
    string Threshold,
    string ThresholdRu,
    string Observed,
    string Result);

internal sealed class BenchmarkOutcome
{
    public required BenchmarkProfile Profile { get; init; }
    public required int Seed { get; init; }
    public required string RunId { get; init; }
    public required DateTime StartedUtc { get; init; }
    public required DateTime FinishedUtc { get; init; }
    public required List<ConditionSummary> Conditions { get; init; }
    public required StabilitySummary Stability { get; init; }
    public required string DeterminismFirst { get; init; }
    public required string DeterminismSecond { get; init; }
    public required Dictionary<string, int> LockedPilotMetric { get; init; }
    public required int Threads { get; init; }
    public required List<string> Notes { get; init; }
    public required List<HypothesisVerdict> Verdicts { get; init; }
    public required string Overall { get; init; }

    public TimeSpan Duration => FinishedUtc - StartedUtc;

    public ConditionSummary? Find(string id)
    {
        foreach (ConditionSummary summary in Conditions)
            if (summary.Condition.Id == id) return summary;
        return null;
    }

    public List<ConditionSummary> Stage(string stage)
    {
        var found = new List<ConditionSummary>();
        foreach (ConditionSummary summary in Conditions)
            if (summary.Condition.Stage == stage) found.Add(summary);
        return found;
    }
}

internal static class BenchmarkRunner
{
    private const int MinValue = -1000000;
    private const int MaxValue = 1000000;
    private const int MinMeasurements = 6;

    private const int StagePilot = 0;
    private const int StagePrimary = 1;
    private const int StagePower = 2;
    private const int StageRobust = 3;
    private const int StageShape = 4;
    private const int StageStability = 5;
    private const int StageDeterminism = 6;
    private const int StagePlasmode = 7;

    private sealed class NullProgress : IProgress<ProgressInfo>
    {
        public static readonly NullProgress Instance = new();
        public void Report(ProgressInfo value) { }
    }

    private sealed class ReplicationOutcome
    {
        public bool[] Rejected = Array.Empty<bool>();
        public bool[] Claimed = Array.Empty<bool>();
        public int[] Chosen = Array.Empty<int>();
        public bool[] MetricRejected = Array.Empty<bool>();
        public bool Failed;
        public string Error = "";
    }

    private sealed class ConditionPlan
    {
        public required BenchmarkCondition Condition { get; init; }
        public required BenchmarkDesign Design { get; init; }
        public required InjectionMode Mode { get; init; }
        public required int Stage { get; init; }
        public required int Stream { get; init; }
        public required int LockedMetric { get; init; }
        public RealDataset? Real { get; init; }
    }

    private sealed class WorkCounter
    {
        private int done;
        public int Total { get; set; }
        public int Increment() => Interlocked.Increment(ref done);
        public int Done => Volatile.Read(ref done);
    }

    /// <summary>
    /// Overrides the worker count. Zero means decide from the machine.
    ///
    /// This is safe to expose because the thread count cannot change a result: every replication
    /// owns its own random stream, so the parallel loops are bit-identical however the work is
    /// scheduled. It is needed because the default leaves one core free for a desktop, and a
    /// hosted notebook with two cores has no desktop and would run on a single worker.
    /// </summary>
    public static int ThreadOverride { get; set; }

    public static BenchmarkOutcome Run(
        BenchmarkProfile profile,
        int seed,
        string realDataFolder,
        bool russian,
        IProgress<ProgressInfo>? progress,
        CancellationToken token)
    {
        DateTime started = DateTime.UtcNow;
        var notes = new List<string>();
        ulong runSeed = (ulong)(uint)seed;
        int threads = ThreadOverride > 0 ? ThreadOverride : Math.Max(1, Environment.ProcessorCount - 1);
        int calibrations = profile.CalibrationRepetitions;

        if (!BenchmarkProtocol.HashIsFrozen)
            notes.Add("WARNING: the protocol text no longer matches the frozen hash. This run is not comparable with published runs.");

        Report(progress, 0, russian ? "Подготовка" : "Preparing", russian ? "Закрепление метрики на пилотных данных" : "Locking the pilot metric");

        List<RealDataset> real = BenchmarkDatasets.LoadReal(realDataFolder, MinMeasurements, notes);

        // The designs the protocol names, each with the shape it is tested under.
        BenchmarkDesign gaitHeavy = BenchmarkDatasets.Gait;
        BenchmarkDesign gaitNormal = BenchmarkDatasets.WithShape(BenchmarkDatasets.Gait, DataShape.Normal);
        BenchmarkDesign gaitLognormal = BenchmarkDatasets.WithShape(BenchmarkDatasets.Gait, DataShape.Lognormal);
        BenchmarkDesign voice = BenchmarkDatasets.Voice;

        var pilot = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (BenchmarkDesign design in new[] { gaitHeavy, gaitNormal, gaitLognormal, voice })
        {
            token.ThrowIfCancellationRequested();
            string key = DesignKey(design);
            if (pilot.ContainsKey(key)) continue;
            pilot[key] = LockPilotMetric(design, runSeed, calibrations, token, notes);
        }

        var plans = new List<ConditionPlan>();
        plans.Add(Plan("primary_null", "primary", gaitHeavy, InjectionMode.None, 1.0, 0, profile.PrimaryReplications, StagePrimary, pilot));

        foreach (double effect in BenchmarkProtocol.LocationGrid)
            plans.Add(Plan("power_location_" + Tag(effect), "power", gaitHeavy, InjectionMode.Location, effect, 0, profile.GridReplications, StagePower, pilot));
        foreach (double effect in BenchmarkProtocol.DispersionGrid)
            plans.Add(Plan("power_dispersion_" + Tag(effect), "power", gaitHeavy, InjectionMode.Dispersion, effect, 0, profile.GridReplications, StagePower, pilot));

        foreach (double contamination in BenchmarkProtocol.ContaminationGrid)
            plans.Add(Plan("robust_null_" + Tag(contamination), "robust", gaitHeavy, InjectionMode.None, 1.0, contamination, profile.GridReplications, StageRobust, pilot));

        plans.Add(Plan("shape_normal_null", "shape", gaitNormal, InjectionMode.None, 1.0, 0, profile.GridReplications, StageShape, pilot));
        plans.Add(Plan("shape_lognormal_null", "shape", gaitLognormal, InjectionMode.None, 1.0, 0, profile.GridReplications, StageShape, pilot));
        plans.Add(Plan("design_voice_null", "shape", voice, InjectionMode.None, 1.0, 0, profile.GridReplications, StageShape, pilot));
        plans.Add(Plan("design_voice_location_105", "shape", voice, InjectionMode.Location, BenchmarkProtocol.PrimaryLocationEffect, 0, profile.GridReplications, StageShape, pilot));

        foreach (RealDataset dataset in real)
        {
            plans.Add(PlanReal("real_" + dataset.Name + "_null", voiceLike: gaitHeavy, dataset: dataset, mode: InjectionMode.None, effect: 1.0, replications: profile.GridReplications, pilot: pilot));
            plans.Add(PlanReal("real_" + dataset.Name + "_location_105", voiceLike: gaitHeavy, dataset: dataset, mode: InjectionMode.Location, effect: BenchmarkProtocol.PrimaryLocationEffect, replications: profile.GridReplications, pilot: pilot));
        }

        ConditionPlan determinism = Plan("determinism_replay", "determinism", gaitHeavy, InjectionMode.None, 1.0, 0, profile.DeterminismReplications, StageDeterminism, pilot);

        var counter = new WorkCounter();
        int total = 0;
        foreach (ConditionPlan plan in plans) total += plan.Condition.Replications;
        total += profile.StabilityRepeats;
        total += profile.DeterminismReplications * 2;
        counter.Total = Math.Max(1, total);

        var summaries = new List<ConditionSummary>();
        foreach (ConditionPlan plan in plans)
        {
            token.ThrowIfCancellationRequested();
            summaries.Add(RunCondition(plan, runSeed, calibrations, threads, counter, progress, russian, token));
        }

        StabilitySummary stability = RunStability(gaitHeavy, runSeed, profile.StabilityRepeats, calibrations, threads, counter, progress, russian, token);

        ConditionSummary firstPass = RunCondition(determinism, runSeed, calibrations, threads, counter, progress, russian, token);
        ConditionSummary secondPass = RunCondition(determinism, runSeed, calibrations, threads, counter, progress, russian, token);
        summaries.Add(firstPass);

        foreach (ConditionSummary summary in summaries)
            if (summary.Failed > 0 && summary.FirstError.Length > 0)
                notes.Add(summary.Condition.Id + ": " + summary.Failed.ToString(CultureInfo.InvariantCulture) + " replications failed (" + summary.FirstError + ")");

        var outcome = new BenchmarkOutcome
        {
            Profile = profile,
            Seed = seed,
            RunId = DateTime.Now.ToString("yyyy-MM-dd_HHmmss", CultureInfo.InvariantCulture),
            StartedUtc = started,
            FinishedUtc = DateTime.UtcNow,
            Conditions = summaries,
            Stability = stability,
            DeterminismFirst = firstPass.DecisionDigest,
            DeterminismSecond = secondPass.DecisionDigest,
            LockedPilotMetric = pilot,
            Threads = threads,
            Notes = notes,
            Verdicts = new List<HypothesisVerdict>(),
            Overall = "pending"
        };

        List<HypothesisVerdict> verdicts = Evaluate(outcome);
        return new BenchmarkOutcome
        {
            Profile = outcome.Profile,
            Seed = outcome.Seed,
            RunId = outcome.RunId,
            StartedUtc = outcome.StartedUtc,
            FinishedUtc = outcome.FinishedUtc,
            Conditions = outcome.Conditions,
            Stability = outcome.Stability,
            DeterminismFirst = outcome.DeterminismFirst,
            DeterminismSecond = outcome.DeterminismSecond,
            LockedPilotMetric = outcome.LockedPilotMetric,
            Threads = outcome.Threads,
            Notes = outcome.Notes,
            Verdicts = verdicts,
            Overall = Overall(verdicts)
        };
    }

    // ---------------- planning ----------------

    private static string DesignKey(BenchmarkDesign design) => design.Id + "/" + BenchmarkDatasets.ShapeId(design.Shape);

    private static int StreamOf(BenchmarkDesign design)
    {
        int designIndex = design.Id == BenchmarkDatasets.Voice.Id ? 1 : 0;
        return designIndex * 10 + (int)design.Shape;
    }

    private static string Tag(double value) => ((int)Math.Round(value * 100)).ToString(CultureInfo.InvariantCulture);

    // String.GetHashCode is randomised per process, so it must never touch a seed. This little
    // FNV-1a walk gives the same answer on every machine and every run, which is the whole point.
    private static int StableIndex(string text)
    {
        unchecked
        {
            uint hash = 2166136261u;
            foreach (char c in text)
            {
                hash ^= c;
                hash *= 16777619u;
            }
            return (int)(hash % 40u);
        }
    }

    private static ConditionPlan Plan(
        string id, string stage, BenchmarkDesign design, InjectionMode mode,
        double effect, double contamination, int replications, int stageIndex,
        Dictionary<string, int> pilot)
    {
        return new ConditionPlan
        {
            Condition = new BenchmarkCondition(
                id, stage, design.Id, BenchmarkDatasets.ShapeId(design.Shape),
                BenchmarkDatasets.ModeId(mode), effect, contamination,
                Math.Max(1, replications), "synthetic"),
            Design = design,
            Mode = mode,
            Stage = stageIndex,
            Stream = StreamOf(design),
            LockedMetric = pilot.TryGetValue(DesignKey(design), out int locked) ? locked : 0
        };
    }

    private static ConditionPlan PlanReal(
        string id, BenchmarkDesign voiceLike, RealDataset dataset, InjectionMode mode,
        double effect, int replications, Dictionary<string, int> pilot)
    {
        return new ConditionPlan
        {
            Condition = new BenchmarkCondition(
                id, "real", dataset.Name, "measured",
                BenchmarkDatasets.ModeId(mode), effect, 0,
                Math.Max(1, replications), "plasmode:" + dataset.FileHash),
            Design = voiceLike,
            Mode = mode,
            Stage = StagePlasmode,
            Stream = 50 + StableIndex(dataset.Name),
            LockedMetric = pilot.TryGetValue(DesignKey(voiceLike), out int locked) ? locked : 0,
            Real = dataset
        };
    }

    // ---------------- execution ----------------

    private static int LockPilotMetric(BenchmarkDesign design, ulong runSeed, int calibrations, CancellationToken token, List<string> notes)
    {
        try
        {
            var random = new BenchmarkRandom(BenchmarkRandom.Derive(runSeed, (ulong)StagePilot, (ulong)StreamOf(design), 0UL));
            List<Observation> rows = BenchmarkDatasets.Generate(design, InjectionMode.None, 1, 0, random);
            AnalysisData data = AnalysisEngine.Build(rows, MinValue, MaxValue, MinMeasurements);
            List<CalibrationRow> calibration = Calibrate(data, calibrations, NextSeed(random), token);
            (int strict, int lenient) = SelectMetrics(calibration);
            if (strict >= 0) return strict;
            if (lenient >= 0) return lenient;
            notes.Add("Pilot calibration for " + DesignKey(design) + " produced no usable metric; the median was locked instead.");
            return 0;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            notes.Add("Pilot calibration for " + DesignKey(design) + " failed (" + ex.Message + "); the median was locked instead.");
            return 0;
        }
    }

    private static ConditionSummary RunCondition(
        ConditionPlan plan, ulong runSeed, int calibrations, int threads,
        WorkCounter counter, IProgress<ProgressInfo>? progress, bool russian, CancellationToken token)
    {
        int replications = plan.Condition.Replications;
        var outcomes = new ReplicationOutcome?[replications];
        var options = new ParallelOptions { MaxDegreeOfParallelism = threads, CancellationToken = token };
        int step = Math.Max(1, counter.Total / 220);
        string action = russian ? "Прогон бенчмарка" : "Running the benchmark";

        Parallel.For(0, replications, options, index =>
        {
            outcomes[index] = RunReplication(plan, runSeed, index, calibrations, token);
            int done = counter.Increment();
            if (progress != null && (done % step == 0 || done >= counter.Total))
                Report(progress, done / (double)counter.Total, action,
                    plan.Condition.Id + "  ·  " + done.ToString(CultureInfo.InvariantCulture) + " / " + counter.Total.ToString(CultureInfo.InvariantCulture));
        });

        int metrics = AnalysisEngine.MetricKeys.Length;
        int procedures = BenchmarkProcedures.Count;
        var rejections = new int[procedures];
        var claims = new int[procedures];
        var metricRejections = new int[metrics];
        // Replications are split by index parity so the oracle can be chosen on one half and
        // scored on the other. Parity is fixed by the replication index, not by arrival order,
        // so the split stays identical no matter how the parallel loop schedules the work.
        var completedHalf = new int[2];
        var metricRejectionsHalf = new int[2][];
        metricRejectionsHalf[0] = new int[metrics];
        metricRejectionsHalf[1] = new int[metrics];
        var chosen = new int[procedures][];
        for (int p = 0; p < procedures; p++) chosen[p] = new int[metrics + 1];
        int completed = 0;
        int failed = 0;
        string firstError = "";
        var digest = new StringBuilder();

        for (int i = 0; i < replications; i++)
        {
            ReplicationOutcome? item = outcomes[i];
            if (item == null || item.Failed)
            {
                failed++;
                if (firstError.Length == 0 && item != null) firstError = item.Error;
                continue;
            }
            completed++;
            int half = i % 2;
            completedHalf[half]++;
            for (int p = 0; p < procedures; p++)
            {
                if (item.Rejected[p]) rejections[p]++;
                if (item.Claimed[p]) claims[p]++;
                int pick = item.Chosen[p];
                chosen[p][pick < 0 || pick >= metrics ? metrics : pick]++;
                digest.Append(item.Rejected[p] ? '1' : '0');
                digest.Append(item.Claimed[p] ? '1' : '0');
                digest.Append(pick.ToString(CultureInfo.InvariantCulture));
                digest.Append(',');
            }
            digest.Append('|');
            for (int m = 0; m < metrics; m++)
            {
                if (item.MetricRejected[m]) { metricRejections[m]++; metricRejectionsHalf[half][m]++; }
                digest.Append(item.MetricRejected[m] ? '1' : '0');
            }
            digest.Append('\n');
        }

        return new ConditionSummary
        {
            Condition = plan.Condition,
            Completed = completed,
            Failed = failed,
            Rejections = rejections,
            Claims = claims,
            MetricRejections = metricRejections,
            CompletedHalf = completedHalf,
            MetricRejectionsHalf = metricRejectionsHalf,
            ChosenCounts = chosen,
            DecisionDigest = Sha256(digest.ToString()),
            FirstError = firstError
        };
    }

    private static ReplicationOutcome RunReplication(ConditionPlan plan, ulong runSeed, int replication, int calibrations, CancellationToken token)
    {
        int metrics = AnalysisEngine.MetricKeys.Length;
        int procedures = BenchmarkProcedures.Count;
        var outcome = new ReplicationOutcome
        {
            Rejected = new bool[procedures],
            Claimed = new bool[procedures],
            Chosen = new int[procedures],
            MetricRejected = new bool[metrics]
        };
        try
        {
            token.ThrowIfCancellationRequested();
            var random = new BenchmarkRandom(BenchmarkRandom.Derive(runSeed, (ulong)plan.Stage, (ulong)plan.Stream, (ulong)replication));
            List<Observation> rows = plan.Real != null
                ? BenchmarkDatasets.Plasmode(plan.Real, plan.Mode, plan.Condition.Effect, plan.Design.EntitiesPerGroup, plan.Design.MeasurementsPerEntity, random)
                : BenchmarkDatasets.Generate(plan.Design, plan.Mode, plan.Condition.Effect, plan.Condition.Contamination, random);
            AnalysisData data = AnalysisEngine.Build(rows, MinValue, MaxValue, MinMeasurements);
            double[] p = PValues(data, metrics);

            double alpha = BenchmarkProtocol.Alpha;
            double smallest = double.PositiveInfinity;
            for (int m = 0; m < metrics; m++)
            {
                outcome.MetricRejected[m] = double.IsFinite(p[m]) && p[m] < alpha;
                if (double.IsFinite(p[m]) && p[m] < smallest) smallest = p[m];
            }

            List<CalibrationRow> calibration = Calibrate(data, calibrations, NextSeed(random), token);
            (int strict, int lenient) = SelectMetrics(calibration);

            for (int procedure = 0; procedure < procedures; procedure++)
            {
                outcome.Claimed[procedure] = true;
                outcome.Chosen[procedure] = -1;
            }

            // Try all registered metrics and report whichever looks best: the habit the program exists to replace.
            outcome.Rejected[BenchmarkProcedures.CherryPick] = double.IsFinite(smallest) && smallest < alpha;
            outcome.Chosen[BenchmarkProcedures.CherryPick] = ArgMinFinite(p);

            // The textbook repair. Valid, and the benchmark measures what it costs.
            outcome.Rejected[BenchmarkProcedures.Bonferroni] = double.IsFinite(smallest) && smallest < alpha / metrics;
            outcome.Chosen[BenchmarkProcedures.Bonferroni] = ArgMinFinite(p);

            Decide(outcome, BenchmarkProcedures.FixedMedian, 0, p, alpha);
            Decide(outcome, BenchmarkProcedures.FixedCv, 2, p, alpha);
            Decide(outcome, BenchmarkProcedures.MvsPilot, plan.LockedMetric, p, alpha);

            if (strict >= 0)
            {
                Decide(outcome, BenchmarkProcedures.MvsStrict, strict, p, alpha);
            }
            else
            {
                // No metric cleared the gate, so the honest answer is that this dataset cannot
                // support a claim. Not a rejection, and recorded as a withheld claim.
                outcome.Claimed[BenchmarkProcedures.MvsStrict] = false;
                outcome.Rejected[BenchmarkProcedures.MvsStrict] = false;
                outcome.Chosen[BenchmarkProcedures.MvsStrict] = -1;
            }

            // Shipped inference reports every applicable metric with full-registry correction.
            // Candidate labels prioritize measures; they do NOT filter away the other displayed tests.
            // MvsTwoTrack is retained as an internal legacy slot, not the public procedure name.
            int[] applicable = Enumerable.Range(0, metrics).Where(i => calibration[i].Applicable && double.IsFinite(p[i])).ToArray();
            outcome.Claimed[BenchmarkProcedures.MvsTwoTrack] = applicable.Length > 0;
            outcome.Rejected[BenchmarkProcedures.MvsTwoTrack] = applicable.Any(i => DecisionPolicy.Reject(p[i], alpha, metrics));
            outcome.Chosen[BenchmarkProcedures.MvsTwoTrack] = applicable.OrderBy(i => p[i]).DefaultIfEmpty(-1).First();

            int fallback = lenient >= 0 ? lenient : 0;
            Decide(outcome, BenchmarkProcedures.MvsLenient, fallback, p, alpha);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            outcome.Failed = true;
            outcome.Error = ex.GetType().Name + ": " + ex.Message;
        }
        return outcome;
    }

    private static void Decide(ReplicationOutcome outcome, int procedure, int metric, double[] p, double alpha)
    {
        if (metric < 0 || metric >= p.Length)
        {
            outcome.Claimed[procedure] = false;
            outcome.Rejected[procedure] = false;
            outcome.Chosen[procedure] = -1;
            return;
        }
        outcome.Chosen[procedure] = metric;
        outcome.Claimed[procedure] = true;
        outcome.Rejected[procedure] = double.IsFinite(p[metric]) && p[metric] < alpha;
    }

    private static StabilitySummary RunStability(
        BenchmarkDesign design, ulong runSeed, int repeats, int calibrations, int threads,
        WorkCounter counter, IProgress<ProgressInfo>? progress, bool russian, CancellationToken token)
    {
        int metrics = AnalysisEngine.MetricKeys.Length;
        var tau = new double[repeats];
        var matched = new bool[repeats];
        var top = new int[repeats];
        var broke = new bool[repeats];
        var options = new ParallelOptions { MaxDegreeOfParallelism = threads, CancellationToken = token };
        int step = Math.Max(1, counter.Total / 220);
        string action = russian ? "Устойчивость выбора метрики" : "Stability of the metric choice";

        Parallel.For(0, repeats, options, index =>
        {
            try
            {
                var random = new BenchmarkRandom(BenchmarkRandom.Derive(runSeed, (ulong)StageStability, (ulong)StreamOf(design), (ulong)index));
                List<Observation> rows = BenchmarkDatasets.Generate(design, InjectionMode.None, 1, 0, random);
                AnalysisData data = AnalysisEngine.Build(rows, MinValue, MaxValue, MinMeasurements);
                (AnalysisData left, AnalysisData right) = AnalysisEngine.SplitEntities(data, NextSeed(random));
                int seedLeft = NextSeed(random);
                int seedRight = NextSeed(random);
                double[] scoresLeft = Scores(Calibrate(left, calibrations, seedLeft, token), metrics);
                double[] scoresRight = Scores(Calibrate(right, calibrations, seedRight, token), metrics);
                tau[index] = BenchmarkMath.KendallTau(scoresLeft, scoresRight);
                int topLeft = ArgMax(scoresLeft);
                int topRight = ArgMax(scoresRight);
                top[index] = topLeft;
                matched[index] = topLeft >= 0 && topLeft == topRight;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception)
            {
                broke[index] = true;
                tau[index] = double.NaN;
                top[index] = -1;
            }
            int done = counter.Increment();
            if (progress != null && (done % step == 0 || done >= counter.Total))
                Report(progress, done / (double)counter.Total, action,
                    done.ToString(CultureInfo.InvariantCulture) + " / " + counter.Total.ToString(CultureInfo.InvariantCulture));
        });

        var counts = new int[metrics];
        int good = 0;
        int agreements = 0;
        int failed = 0;
        var usable = new List<double>();
        for (int i = 0; i < repeats; i++)
        {
            if (broke[i] || !double.IsFinite(tau[i])) { failed++; continue; }
            good++;
            usable.Add(tau[i]);
            if (matched[i]) agreements++;
            if (top[i] >= 0 && top[i] < metrics) counts[top[i]]++;
        }

        return new StabilitySummary
        {
            Tau = usable.ToArray(),
            Repeats = good,
            TopOneMatches = agreements,
            TopMetricCounts = counts,
            Failed = failed
        };
    }

    // ---------------- engine helpers ----------------

    private static List<CalibrationRow> Calibrate(AnalysisData data, int repetitions, int seed, CancellationToken token) =>
        AnalysisEngine.Calibrate(
            data, repetitions, BenchmarkProtocol.CalibrationEffect, seed,
            NullProgress.Instance, token, BenchmarkProtocol.CalibrationScenario,
            BenchmarkProtocol.CalibrationOutlierRate, BenchmarkProtocol.CalibrationMissingRate,
            BenchmarkProtocol.Alpha, AnalysisEngine.DefaultTracks);

    /// <summary>
    /// Keeps the engine's own seeds small. The current engine derives streams with SHA-256; this historical bound is retained for stable benchmark stream allocation.
    /// </summary>
    private static int NextSeed(BenchmarkRandom random) => (int)(random.NextUInt64() % 50000000UL) + 1;

    private static double[] PValues(AnalysisData data, int metrics)
    {
        var values = new double[metrics];
        string[] groups = data.GroupNames;
        for (int metric = 0; metric < metrics; metric++)
        {
            var arrays = new double[groups.Length][];
            for (int g = 0; g < groups.Length; g++)
            {
                var column = new List<double>();
                foreach (EntityResult entity in data.Entities)
                {
                    if (!entity.Group.Equals(groups[g], StringComparison.OrdinalIgnoreCase)) continue;
                    double value = entity.Metrics[metric];
                    if (double.IsFinite(value)) column.Add(value);
                }
                arrays[g] = column.ToArray();
            }
            bool usable = true;
            foreach (double[] array in arrays) if (array.Length < 4) usable = false;
            if (!usable) { values[metric] = double.NaN; continue; }
            values[metric] = groups.Length == 2
                ? AnalysisEngine.MannWhitneyP(arrays[0], arrays[1])
                : AnalysisEngine.KruskalWallisP(arrays);
        }
        return values;
    }

    /// <summary>
    /// Reproduces the shipped selection rule exactly: highest MVS score among applicable metrics,
    /// with the gate that the results page applies before it calls a metric a candidate. Ties fall
    /// to the earlier metric so the answer does not depend on sort stability.
    /// </summary>
    private static (int Strict, int Lenient) SelectMetrics(List<CalibrationRow> calibration)
    {
        int gated = -1;
        int best = -1;
        double gatedScore = double.NegativeInfinity;
        double bestScore = double.NegativeInfinity;
        for (int i = 0; i < calibration.Count; i++)
        {
            CalibrationRow row = calibration[i];
            if (!row.Applicable || !double.IsFinite(row.Score)) continue;
            if (row.Score > bestScore) { bestScore = row.Score; best = i; }
            bool passes = row.PassesGateIn(SimulationScenarios.Location);
            if (passes && row.Score > gatedScore) { gatedScore = row.Score; gated = i; }
        }
        return (gated, best);
    }

    /// <summary>
    /// The winner inside one track: highest score among the metrics that clear the gate for that
    /// track. A spread metric is judged on its spread power, never on how well it detects a shift
    /// of the centre, which is the question it was losing before 1.4.0.
    /// </summary>
    private static int SelectMetricForTrack(List<CalibrationRow> calibration, string track)
    {
        int gated = -1;
        double gatedScore = double.NegativeInfinity;
        for (int i = 0; i < calibration.Count; i++)
        {
            CalibrationRow row = calibration[i];
            if (!row.PassesGateIn(track)) continue;
            double score = row.ScoreIn(track);
            if (double.IsFinite(score) && score > gatedScore) { gatedScore = score; gated = i; }
        }
        return gated;
    }

    private static double[] Scores(List<CalibrationRow> calibration, int metrics)
    {
        var scores = new double[metrics];
        for (int i = 0; i < metrics; i++)
            scores[i] = i < calibration.Count && double.IsFinite(calibration[i].Score) ? calibration[i].Score : 0;
        return scores;
    }

    private static int ArgMax(double[] values)
    {
        int best = -1;
        double bestValue = double.NegativeInfinity;
        for (int i = 0; i < values.Length; i++)
            if (double.IsFinite(values[i]) && values[i] > bestValue) { bestValue = values[i]; best = i; }
        return best;
    }

    private static int ArgMinFinite(double[] values)
    {
        int best = -1;
        double bestValue = double.PositiveInfinity;
        for (int i = 0; i < values.Length; i++)
            if (double.IsFinite(values[i]) && values[i] < bestValue) { bestValue = values[i]; best = i; }
        return best;
    }

    private static void Report(IProgress<ProgressInfo>? progress, double fraction, string action, string details)
    {
        progress?.Report(new ProgressInfo(Math.Clamp(fraction, 0, 1), action, details));
    }

    private static string Sha256(string text)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(text));
        return Convert.ToHexString(digest).ToLowerInvariant();
    }

    // ---------------- declared scoring ----------------

    public static List<HypothesisVerdict> Evaluate(BenchmarkOutcome outcome)
    {
        var verdicts = new List<HypothesisVerdict>();
        ConditionSummary? primary = outcome.Find("primary_null");

        // A. Does selecting a metric inflate the false-positive rate, and does the gate stop it?
        if (primary != null)
        {
            double cherry = primary.Rate(BenchmarkProcedures.CherryPick);
            double gated = primary.Rate(BenchmarkProcedures.MvsStrict);
            double twoTrack = primary.Rate(BenchmarkProcedures.MvsTwoTrack);
            // A is judged on whatever the program actually ships, which from 1.4.0 is the
            // two-track procedure. Adding a second track adds a second chance to reject, so its
            // false alarm rate has to be measured, not assumed to be inherited from one track.
            string result = "inconclusive";
            if (double.IsFinite(cherry) && double.IsFinite(twoTrack))
            {
                if (twoTrack > BenchmarkProtocol.MvsFprFail) result = "fail";
                else if (cherry >= BenchmarkProtocol.CherryPickFprPass && twoTrack <= BenchmarkProtocol.MvsFprPass) result = "pass";
            }
            verdicts.Add(new HypothesisVerdict("A",
                "Metric shopping inflates the false-positive rate and the MVS gate holds it at the nominal level",
                "Перебор метрик разгоняет долю ложных открытий, а порог MVS держит её на заявленном уровне",
                "cherry-pick >= 0.15 and the shipped MVS default <= 0.075; fail above 0.10",
                "перебор >= 0,15 и MVS <= 0,075; провал при MVS > 0,10",
                "cherry-pick " + Pct(cherry) + ", MVS two-track " + Pct(twoTrack) + ", single-track " + Pct(gated),
                result));
        }

        // B. What does that control cost in power against a truth-aware oracle?
        var lossParts = new List<string>();
        string powerResult = "inconclusive";
        double worstLoss = double.NaN;
        foreach (string id in new[] { "power_location_" + Tag(BenchmarkProtocol.PrimaryLocationEffect), "power_dispersion_" + Tag(BenchmarkProtocol.PrimaryDispersionEffect) })
        {
            ConditionSummary? condition = outcome.Find(id);
            if (condition == null) continue;
            // The oracle is chosen on one half of the replications and scored on the other, and
            // MVS is represented by the shipped default. The old same-data oracle and the old
            // single-track power are printed alongside, so the change in the gap can be read off
            // rather than taken on trust.
            int oracle = condition.OracleMetricHeldOut();
            double oraclePower = condition.OraclePowerHeldOut();
            int biasedOracle = condition.OracleMetric();
            double biasedPower = biasedOracle >= 0 ? condition.MetricRate(biasedOracle) : double.NaN;
            double gatedPower = condition.Rate(BenchmarkProcedures.MvsStrict);
            double twoTrackPower = condition.Rate(BenchmarkProcedures.MvsTwoTrack);
            double loss = oraclePower - twoTrackPower;
            if (double.IsFinite(loss) && (!double.IsFinite(worstLoss) || loss > worstLoss)) worstLoss = loss;
            lossParts.Add(condition.Condition.Mode + " two-track " + Pct(twoTrackPower) +
                ", single-track " + Pct(gatedPower) + " vs held-out oracle " +
                (oracle >= 0 ? AnalysisEngine.MetricKeys[oracle] : "n/a") + " " + Pct(oraclePower) +
                " (same-data oracle " + Pct(biasedPower) + ")");
        }
        if (double.IsFinite(worstLoss))
            powerResult = worstLoss > BenchmarkProtocol.PowerLossFail ? "fail"
                : worstLoss <= BenchmarkProtocol.PowerLossPass ? "pass" : "inconclusive";
        verdicts.Add(new HypothesisVerdict("B",
            "Controlling the error rate costs little power against a metric chosen with knowledge of the truth",
            "Контроль ошибок стоит немного мощности по сравнению с метрикой, выбранной со знанием истины",
            "loss <= 7 points; fail above 15 points",
            "потеря <= 7 п.п.; провал выше 15 п.п.",
            (double.IsFinite(worstLoss) ? "worst loss " + Points(worstLoss) + "  ·  " : "") + string.Join("; ", lossParts),
            powerResult));

        // C. Does the metric choice survive being shown only half of the entities?
        double tau = outcome.Stability.MedianTau;
        double agreement = outcome.Stability.TopOneAgreement;
        string stabilityResult = "inconclusive";
        if (double.IsFinite(tau) && double.IsFinite(agreement))
        {
            if (tau < BenchmarkProtocol.TauFail) stabilityResult = "fail";
            else if (tau >= BenchmarkProtocol.TauPass && agreement >= BenchmarkProtocol.TopOneAgreementPass) stabilityResult = "pass";
        }
        verdicts.Add(new HypothesisVerdict("C",
            "The ranking of metrics is stable across independent halves of the same study",
            "Порядок метрик устойчив на независимых половинах одного исследования",
            "median Kendall tau >= 0.70 and top-1 agreement >= 0.60; fail if tau < 0.40",
            "медианная тау Кендалла >= 0,70 и совпадение лидера >= 0,60; провал при тау < 0,40",
            "tau " + Num(tau) + ", top-1 agreement " + Pct(agreement) + " over " + outcome.Stability.Repeats.ToString(CultureInfo.InvariantCulture) + " splits",
            stabilityResult));

        // D. Does the control survive dirty data?
        ConditionSummary? heavy = outcome.Find("robust_null_" + Tag(BenchmarkProtocol.RobustContamination));
        ConditionSummary? light = outcome.Find("robust_null_" + Tag(BenchmarkProtocol.EarlyContamination));
        string robustResult = "inconclusive";
        double heavyRate = heavy != null ? heavy.Rate(BenchmarkProcedures.MvsStrict) : double.NaN;
        double lightRate = light != null ? light.Rate(BenchmarkProcedures.MvsStrict) : double.NaN;
        if (double.IsFinite(lightRate) && lightRate > BenchmarkProtocol.MvsFprFail) robustResult = "fail";
        else if (double.IsFinite(heavyRate)) robustResult = heavyRate <= BenchmarkProtocol.MvsFprPass ? "pass" : "inconclusive";
        verdicts.Add(new HypothesisVerdict("D",
            "The error rate stays controlled when up to a tenth of the measurements are corrupted",
            "Доля ложных открытий остаётся под контролем, когда испорчено до десятой части измерений",
            "MVS <= 0.075 at 10% contamination; fail if it already exceeds 0.10 at 2%",
            "MVS <= 0,075 при 10% загрязнения; провал, если уже на 2% выше 0,10",
            "2% " + Pct(lightRate) + ", 10% " + Pct(heavyRate),
            robustResult));

        // E. Does the same seed give the same answer twice?
        bool identical = outcome.DeterminismFirst.Length > 0 &&
            string.Equals(outcome.DeterminismFirst, outcome.DeterminismSecond, StringComparison.Ordinal);
        verdicts.Add(new HypothesisVerdict("E",
            "The same seed reproduces the same result exactly",
            "Тот же seed даёт тот же результат бит в бит",
            "identical SHA-256 of the decision matrix",
            "совпадение SHA-256 матрицы решений",
            (outcome.DeterminismFirst.Length >= 16 ? outcome.DeterminismFirst.Substring(0, 16) : outcome.DeterminismFirst) +
            " vs " +
            (outcome.DeterminismSecond.Length >= 16 ? outcome.DeterminismSecond.Substring(0, 16) : outcome.DeterminismSecond),
            identical ? "pass" : "fail"));

        return verdicts;
    }

    private static string Overall(List<HypothesisVerdict> verdicts)
    {
        bool anyFail = false;
        bool anyUnclear = false;
        foreach (HypothesisVerdict verdict in verdicts)
        {
            if (verdict.Result == "fail") anyFail = true;
            else if (verdict.Result != "pass") anyUnclear = true;
        }
        if (anyFail) return "no-go";
        return anyUnclear ? "conditional" : "go";
    }

    public static string Pct(double value) =>
        double.IsFinite(value) ? (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%" : "n/a";

    public static string Points(double value) =>
        double.IsFinite(value) ? (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + " pts" : "n/a";

    public static string Num(double value) =>
        double.IsFinite(value) ? value.ToString("0.000", CultureInfo.InvariantCulture) : "n/a";
}
