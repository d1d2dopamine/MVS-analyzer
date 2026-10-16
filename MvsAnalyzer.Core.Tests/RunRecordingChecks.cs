using System.Text.Json;
using MvsAnalyzer;

// These are ownership/control-flow tests, not independent numerical validation.
// Preloaded unavailable fits deliberately exercise cheap report branches.
internal static class RunRecordingChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[] {
        ("Per-run recording: validation precedes acquisition", Validation),
        ("Per-run recording: five acquisition/cache/error ownership paths", Ownership),
        ("Per-run recording: five seeded traversals and Finish failures", Traversals),
        ("Per-run recording: Put, cancellation and delegate failures", Failures),
        ("Per-run recording: interleaved calls remain independent", Independence),
        ("Borrowed optimizer recording: snapshots, replay and environment", Optimizer)
    };
    private static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    private sealed class Fault(string message) : Exception(message) { }
    private static void ThrowsSame(Action action, Exception expected)
    {
        try { action(); } catch (Exception actual) { Assert(ReferenceEquals(actual, expected), "Wrong exception: " + actual); return; }
        throw new Exception("Expected exception was swallowed: " + expected.Message);
    }
    private static void Order(IEnumerable<string> actual, params string[] expected) => Assert(actual.SequenceEqual(expected),
        "Recording order differs. Expected " + string.Join(",", expected) + "; actual " + string.Join(",", actual));
    private sealed class Reporter(Action<ProgressInfo>? action = null) : IProgress<ProgressInfo>
    { public void Report(ProgressInfo value) => action?.Invoke(value); }
    private sealed class Recording : IRunRecording
    {
        internal readonly List<string> Events = new();
        internal readonly Dictionary<string, JsonElement> Units = new();
        internal Exception? TryError, PutError, FinishError, DisposeError;
        internal Action<string>? OnTry;
        internal bool Completed;
        internal int Disposals;
        public bool EnvironmentChanged { get; set; }
        internal void Seed<T>(string key, T value) => Units[key] = JsonSerializer.SerializeToElement(value, BackupSession.Json);
        public bool Try<T>(string key, out T value)
        {
            Events.Add("Try:" + key); OnTry?.Invoke(key);
            if (TryError != null) throw TryError;
            if (Units.TryGetValue(key, out var stored)) { value = stored.Deserialize<T>(BackupSession.Json)!; return true; }
            value = default!; return false;
        }
        public T Cached<T>(string key, Func<T> calculate)
        {
            Events.Add("Cached:" + key);
            if (Try<T>(key, out var value)) return value;
            value = calculate(); Put(key, value); return value;
        }
        public void Put<T>(string key, T value)
        { Events.Add("Put:" + key); if (PutError != null) throw PutError; Seed(key, value); }
        public T Finish<T>(T value)
        { Events.Add("Finish"); if (FinishError != null) throw FinishError; Seed("result", value); Completed = true; return value; }
        public void Dispose() { Events.Add("Dispose"); Disposals++; if (DisposeError != null) throw DisposeError; }
    }
    private sealed class Factory(Recording recording) : IRunRecordingFactory
    {
        internal Exception? Error;
        internal BackupRequest? Request;
        internal int Acquisitions;
        public IRunRecording Begin(BackupRequest request)
        {
            Acquisitions++; Request = request; recording.Events.Add("Begin:" + request.Kind);
            if (Error != null) throw Error;
            return recording;
        }
    }
    private sealed record Case(string Kind, Func<Factory, IProgress<ProgressInfo>, CancellationToken, object> Run,
        Action<Recording> SeedResult, Func<Recording, List<string>> SeedUnits);
    private static AnalysisData Data() => AnalysisEngine.Build(Enumerable.Range(0, 2).SelectMany(g => Enumerable.Range(0, 4)
        .SelectMany(e => Enumerable.Range(0, 3).Select(i => new Observation($"G{g}E{e}", "G" + g, 100 + g * 3 + e * .7 + Math.Sin(i + e), i)))).ToList(), minMeasurements: 3);
    private static List<CalibrationRow> Calibration() => AnalysisEngine.MetricKeys.Select(k => new CalibrationRow(k, .01, .8, 80)).ToList();
    private static ResultRow Result(string key) => new(key, 1, 2, 1, .5, .01, .8, 80, false,
        Tracks: new[] { "location" }, TrackPowers: new[] { .8 }, TrackScores: new[] { 80d }, TrackMdes: new[] { 1.2 }, TrackCandidates: new[] { false });
    private static Case[] Cases()
    {
        var data = Data(); var cal = Calibration();
        var estimation = new EstimationOptions(Entities: 4, Measurements: 3, Repetitions: 100, BootstrapReplications: 99);
        var melsm = new MelsmOptions(RandomScale: false, QuadraturePoints: 7, MaxIterations: 100);
        return new[] {
            new Case("calibrate", (f,p,t) => AnalysisEngine.CalibrateWithRecording(f, data, 100, 1.15, 54, p, t),
                r => r.Seed("result", cal), r => {
                    var keys = new List<string>(); int n = AnalysisEngine.MetricKeys.Length;
                    for (int i = 0; i < 100; i++) { string k = "simulation/" + i; keys.Add(k); r.Seed(k, new AnalysisEngine.CalibrationStep(new int[n], new[] { new int[n] }, new[] { new int[n] })); }
                    for (int i = 0; i < n; i++) { string k = "diagnostic/" + i; keys.Add(k); r.Seed(k, cal[i]); } return keys;
                }),
            new Case("analyze", (f,p,t) => AnalysisEngine.ResultsWithRecording(f, data, cal, p, t),
                r => r.Seed("result", AnalysisEngine.MetricKeys.Select(Result).ToList()), r => {
                    var keys = new List<string>(); for (int i = 0; i < cal.Count; i++) { string k = "metric/" + i; keys.Add(k); r.Seed(k, Result(cal[i].Metric)); } return keys;
                }),
            new Case("variance", (f,p,t) => VarianceAnalysis.RunWithRecording(f, data, 100, 99, 1.3, 1.3, 54, .05, p, t),
                r => r.Seed("result", new VarianceReport("test", "cached", "two", 54, .05, Array.Empty<VarianceGroup>(), Array.Empty<VarianceTrack>(), Array.Empty<string>())), r => {
                    var fit = new VarianceFit(new[] { 100d, 103d }, new[] { 1d, 1d }, new[] { 1d, 1d }, 0, false, false, "REML", 0);
                    r.Seed("initial-fit", fit); var keys = new List<string> { "initial-fit" };
                    foreach (string track in new[] { "within", "between" }) { r.Seed(track + "/null-fit", fit); r.Seed(track + "/observed", double.NaN); keys.Add(track + "/null-fit"); keys.Add(track + "/observed"); } return keys;
                }),
            new Case("estimation", (f,p,t) => EstimationStudy.RunWithRecording(f, estimation, p, t),
                r => r.Seed("result", new EstimationReport("test", "cached", estimation, 100, Array.Empty<EstimationPerformance>(), Array.Empty<EstimationDraw>(), Array.Empty<string>())), r => {
                    var keys = new List<string>(); for (int i = 0; i < 100; i++) { string k = "replication/" + i; keys.Add(k); r.Seed(k, new[] { new EstimationDraw(i, "arithmetic_mean", 100 + i % 2, 99, 102, "ok") }); } return keys;
                }),
            new Case("melsm", (f,p,t) => MelsmAnalysis.RunWithRecording(f, data.Observations, melsm, p, t),
                r => r.Seed("result", new MelsmReport("test", "cached", "cached", false, 0, 0, 0, 7, 8, 24, 0, 1, melsm, Array.Empty<ModelParameter>(), Array.Empty<MelsmEntity>(), Array.Empty<string>())), r => {
                    // Explicit unavailable-fit fixture: NaN prevents a refinement pass; no scientific assertion is made.
                    r.Seed("fit/first", new OptimizationResult(new double[5], double.NaN, false, 0, false)); return new List<string> { "fit/first" };
                })
        };
    }
    private static string[] TraversalOrder(Case c, IEnumerable<string> keys) => new[] { "Begin:" + c.Kind, "Try:result" }
        .Concat(keys.SelectMany(k => new[] { "Cached:" + k, "Try:" + k })).Concat(new[] { "Finish", "Dispose" }).ToArray();
    private static void Validation()
    {
        var data = Data();
        Action<Factory>[] invalid = {
            f => AnalysisEngine.CalibrateWithRecording(f, data, 99, 1.15, 54, new Reporter(), default),
            f => AnalysisEngine.ResultsWithRecording(f, data, new List<CalibrationRow>(), new Reporter(), default),
            f => VarianceAnalysis.RunWithRecording(f, data, 99, 99, 1.3, 1.3, 54, .05),
            f => EstimationStudy.RunWithRecording(f, new EstimationOptions(Repetitions: 99)),
            f => MelsmAnalysis.RunWithRecording(f, data.Observations, new MelsmOptions(MaxIterations: 99))
        };
        foreach (var run in invalid) {
            var r = new Recording(); var f = new Factory(r); bool rejected = false;
            try { run(f); } catch (Exception e) when (e is ArgumentException or InvalidDataException) { rejected = true; }
            Assert(rejected && f.Acquisitions == 0 && r.Disposals == 0 && r.Events.Count == 0, "Validation acquired recording or invalid input was accepted.");
        }
    }
    private static void Ownership()
    {
        foreach (var c in Cases()) {
            var acquisition = new Fault("acquire " + c.Kind); var r = new Recording(); var f = new Factory(r) { Error = acquisition };
            ThrowsSame(() => c.Run(f, new Reporter(), default), acquisition); Order(r.Events, "Begin:" + c.Kind);
            Assert(r.Disposals == 0 && f.Acquisitions == 1, "Unacquired session was disposed/retried.");
            r = new Recording(); c.SeedResult(r); f = new Factory(r); string expected = r.Units["result"].GetRawText();
            object value = c.Run(f, new Reporter(), default);
            Assert(JsonSerializer.Serialize(value, value.GetType(), BackupSession.Json) == expected, "Wrong typed cached result.");
            Order(r.Events, "Begin:" + c.Kind, "Try:result", "Dispose"); Assert(r.Disposals == 1 && !r.Completed, "Cache hit ownership/completion changed.");
            var read = new Fault("try " + c.Kind); r = new Recording { TryError = read }; f = new Factory(r);
            ThrowsSame(() => c.Run(f, new Reporter(), default), read); Order(r.Events, "Begin:" + c.Kind, "Try:result", "Dispose");
            Assert(r.Disposals == 1 && !r.Completed, "Failed read was completed or disposed twice.");
            // Preserve ordinary C# using behavior: a Dispose exception masks an in-flight error.
            var dispose = new Fault("dispose " + c.Kind); r = new Recording { TryError = read, DisposeError = dispose }; f = new Factory(r);
            ThrowsSame(() => c.Run(f, new Reporter(), default), dispose); Order(r.Events, "Begin:" + c.Kind, "Try:result", "Dispose");
            Assert(r.Disposals == 1 && !r.Completed, "Exceptional disposal ownership changed.");
        }
    }
    private static void Traversals()
    {
        foreach (var c in Cases()) foreach (bool fail in new[] { false, true }) {
            var r = new Recording(); var keys = c.SeedUnits(r); var f = new Factory(r); var error = new Fault("finish " + c.Kind);
            if (fail) { r.FinishError = error; ThrowsSame(() => c.Run(f, new Reporter(), default), error); }
            else { var result = c.Run(f, new Reporter(), default); Assert(result != null, "No completed report."); }
            Order(r.Events, TraversalOrder(c, keys)); Assert(r.Completed == !fail && r.Disposals == 1 && f.Acquisitions == 1, "Finish/disposal contract changed.");
            Assert(r.Units.ContainsKey("result") == !fail, "Failed Finish published a result.");
        }
    }
    private static void Failures()
    {
        foreach (var c in Cases()) {
            var r = new Recording { PutError = new Fault("put " + c.Kind) }; var f = new Factory(r);
            ThrowsSame(() => c.Run(f, new Reporter(), default), r.PutError);
            string first = c.Kind switch { "calibrate" => "simulation/0", "analyze" => "metric/0", "variance" => "initial-fit", "estimation" => "replication/0", _ => "fit/first" };
            string put = c.Kind == "melsm" ? "simplex/first" : first;
            var expected = new List<string> { "Begin:" + c.Kind, "Try:result", "Cached:" + first, "Try:" + first };
            if (c.Kind == "melsm") expected.Add("Try:simplex/first"); expected.Add("Put:" + put); expected.Add("Dispose");
            Order(r.Events, expected.ToArray()); Assert(!r.Completed && r.Disposals == 1, "Put failure completed or leaked.");
            r = new Recording(); f = new Factory(r); using var stop = new CancellationTokenSource(); stop.Cancel();
            try { c.Run(f, new Reporter(), stop.Token); throw new Exception("Cancellation ignored."); } catch (OperationCanceledException) { }
            expected = new List<string> { "Begin:" + c.Kind, "Try:result" };
            if (c.Kind is "variance" or "melsm") { expected.Add("Cached:" + first); expected.Add("Try:" + first); }
            if (c.Kind == "melsm") expected.Add("Try:simplex/first"); expected.Add("Dispose");
            Order(r.Events, expected.ToArray()); Assert(!r.Completed && r.Disposals == 1, "Cancellation completed or leaked.");
        }
        // A real caller delegate throws after the first cached unit; no Finish is allowed.
        var analysis = Cases().Single(c => c.Kind == "analyze"); var recording = new Recording(); analysis.SeedUnits(recording);
        var failure = new Fault("progress delegate"); ThrowsSame(() => analysis.Run(new Factory(recording), new Reporter(_ => throw failure), default), failure);
        Order(recording.Events, "Begin:analyze", "Try:result", "Cached:metric/0", "Try:metric/0", "Dispose");
        Assert(!recording.Completed && recording.Disposals == 1, "Delegate failure completed or leaked.");
    }
    private static void Independence()
    {
        foreach (var c in Cases()) {
            var outer = new Recording(); var inner = new Recording(); c.SeedResult(outer); c.SeedResult(inner);
            var f1 = new Factory(outer); var f2 = new Factory(inner); bool entered = false;
            outer.OnTry = key => { if (key != "result" || entered) return; entered = true; c.Run(f2, new Reporter(), default); Assert(outer.Disposals == 0, "Inner call disposed outer session."); };
            c.Run(f1, new Reporter(), default);
            Order(outer.Events, "Begin:" + c.Kind, "Try:result", "Dispose"); Order(inner.Events, "Begin:" + c.Kind, "Try:result", "Dispose");
            Assert(entered && f1.Acquisitions == 1 && f2.Acquisitions == 1 && outer.Disposals == 1 && inner.Disposals == 1, "Per-call factories cross-contaminated.");
            // Failure in one invocation must not change another explicit factory's behavior.
            var failed = new Recording { TryError = new Fault("isolated") };
            ThrowsSame(() => c.Run(new Factory(failed), new Reporter(), default), failed.TryError);
            var later = new Recording(); c.SeedResult(later); c.Run(new Factory(later), new Reporter(), default);
            Order(later.Events, "Begin:" + c.Kind, "Try:result", "Dispose");
        }
    }
    private static OptimizationResult Minimize(Recording r, Func<double[], double> f, int iterations = 0, CancellationToken token = default) =>
        NumericalMethods.MinimizeWithRecording(f, new[] { 1d }, new[] { -10d }, new[] { 10d }, maximumIterations: iterations, token: token, backup: r, checkpointKey: "simplex");
    private static void Optimizer()
    {
        foreach (bool changed in new[] { false, true }) {
            var r = new Recording { EnvironmentChanged = changed }; var points = new[] { new[] { 1d }, new[] { 2d } }; var values = new[] { -999d, -998d };
            r.Seed("simplex", new NumericalMethods.SimplexCheckpoint(points, values, 0)); string snapshot = r.Units["simplex"].GetRawText();
            points[0][0] = 9; values[0] = 999; int calls = 0;
            var result = Minimize(r, p => { calls++; return p[0] * p[0]; });
            Assert(calls == (changed ? 2 : 0) && result.Parameters[0] == 1 && result.Value == (changed ? 1 : -999), "Optimizer restore/environment contract changed.");
            result.Parameters[0] = 7; Assert(r.Units["simplex"].GetRawText() == snapshot, "Mutable optimizer arrays escaped snapshot boundary.");
            Order(r.Events, "Try:simplex"); Assert(r.Disposals == 0 && !r.Completed, "Optimizer disposed/completed borrowed recording.");
        }
        var snapshots = new Recording(); var mutable = new[] { new[] { 3d }, new[] { 4d } };
        snapshots.Put("simplex", new NumericalMethods.SimplexCheckpoint(mutable, new[] { 9d, 16d }, 0));
        mutable[0][0] = 99; snapshots.Try<NumericalMethods.SimplexCheckpoint>("simplex", out var firstRead);
        Assert(firstRead.Points[0][0] == 3, "Put retained caller-owned arrays."); firstRead.Points[0][0] = 77;
        snapshots.Try<NumericalMethods.SimplexCheckpoint>("simplex", out var secondRead);
        Assert(secondRead.Points[0][0] == 3, "Try exposed stored mutable arrays.");
        Order(snapshots.Events, "Put:simplex", "Try:simplex", "Try:simplex");
        var fresh = new Recording(); Minimize(fresh, p => p[0] * p[0], 2);
        Order(fresh.Events, "Try:simplex", "Put:simplex", "Put:simplex"); Assert(fresh.Disposals == 0, "Fresh optimizer disposed borrowed recording.");
        var fault = new Fault("objective"); var failed = new Recording();
        ThrowsSame(() => Minimize(failed, _ => throw fault, 2), fault); Order(failed.Events, "Try:simplex"); Assert(failed.Disposals == 0, "Failed objective disposed borrowed recording.");
        var put = new Recording { PutError = new Fault("optimizer put") };
        ThrowsSame(() => Minimize(put, p => p[0] * p[0], 2), put.PutError); Order(put.Events, "Try:simplex", "Put:simplex"); Assert(put.Disposals == 0, "Failed optimizer Put disposed borrowed recording.");
        using var stop = new CancellationTokenSource(); stop.Cancel(); var canceled = new Recording();
        try { Minimize(canceled, p => p[0] * p[0], 2, stop.Token); throw new Exception("Optimizer cancellation ignored."); } catch (OperationCanceledException) { }
        Order(canceled.Events, "Try:simplex", "Put:simplex"); Assert(canceled.Disposals == 0 && !canceled.Completed, "Canceled optimizer disposed/completed borrowed recording.");
    }
}
