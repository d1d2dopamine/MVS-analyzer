using MvsAnalyzer;

internal static class ColabChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("Colab opens the same notebook without forced copies", NoForcedCopy),
        ("Colab notebook identity survives an expired lease", StaleNotebookRetained),
        ("Colab busy and pending leases expire", LeasesExpire),
        ("Colab reconnect revokes stale runtime tokens", ReconnectRevokes),
        ("Colab disconnect retains saved artifacts", DisconnectRetains),
        ("Colab restart does not restore runtime liveness", RestartIsOffline),
        ("Colab rejects duplicate runtime generations", EpochOwnership),
        ("Colab rejects replayed status sequences", SequenceOrdering),
        ("Colab commands are single-flight with explicit cancellation", Commands),
        ("Colab validates notebook URL boundaries", UrlBoundary),
        ("Colab validates progress payloads", ProgressBounds),
        ("Colab transport revision preserves calibration keys", CalibrationKeyCompatible),
    };
    private sealed class Fixture : IDisposable
    {
        public readonly string Root = Path.Combine(Path.GetTempPath(), "mvs-colab-check-" + Guid.NewGuid().ToString("N"));
        public DateTime Now = new(2026, 9, 5, 12, 0, 0, DateTimeKind.Utc);
        public readonly ColabSessionStore Store;
        public readonly string Key = new('a', 64);
        public ColabSession Current => Store.Find(Key)!;
        public Fixture()
        {
            Store = new ColabSessionStore(Root, () => Now);
            Store.GetOrCreate(Key, "standard", "calibrate"); Store.Launch(Key, "calibrate");
        }
        public ColabSession Ping(string phase = "ready", string? command = null, long? sequence = null) =>
            Store.Observe(Current.Token, Key, "", "epoch-12345", phase, command ?? Current.CommandId,
                sequence ?? Current.Sequence + 1, controlsReady: true);
        public void Dispose() { if (Directory.Exists(Root)) Directory.Delete(Root, true); }
    }
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static void Reject(Action action)
    {
        try { action(); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { return; }
        throw new Exception("The invalid operation was accepted.");
    }
    private static void NoForcedCopy()
    {
        using var f = new Fixture();
        string notebook = "https://colab.research.google.com/drive/abcdefghij012345";
        f.Store.LinkNotebook(f.Key, notebook + "?copy=true#copy=true");
        string url = f.Store.Launch(f.Key, "prepare");
        Check(url == notebook + "#scrollTo=mvs-calibrate", "A forced copy or stale anchor remained.");
    }
    private static void StaleNotebookRetained()
    {
        using var f = new Fixture();
        string notebook = "https://colab.research.google.com/drive/abcdefghij012345";
        f.Store.LinkNotebook(f.Key, notebook); f.Ping("calibrating"); f.Now = f.Now.AddMinutes(5);
        Check(!f.Store.Busy(f.Current, f.Now), "An expired runtime still blocks the app.");
        Check(f.Store.Launch(f.Key, "prepare").StartsWith(notebook, StringComparison.Ordinal), "Reconnection forgot the notebook.");
    }
    private static void LeasesExpire()
    {
        using var f = new Fixture();
        Check(f.Store.Pending(f.Current, f.Now), "Launch was not pending.");
        f.Now = f.Now.AddSeconds(ColabSessionStore.PendingSeconds + 1);
        Check(!f.Store.Pending(f.Current, f.Now), "Pending launch never expired.");
        f.Ping("calibrating"); Check(f.Store.Busy(f.Current, f.Now), "A confirmed job is not busy.");
        f.Now = f.Now.AddSeconds(ColabSessionStore.LeaseSeconds + 1);
        Check(!f.Store.Busy(f.Current, f.Now), "The old cell kept a permanent busy state.");
        Check(!f.Store.Live(f.Current with { LastSeenUtc = f.Now.AddHours(1) }, f.Now), "A future timestamp extended liveness.");
        Check(!f.Store.Pending(f.Current with { Phase = "opening", LaunchedUtc = f.Now.AddHours(1) }, f.Now), "A future timestamp extended pending status.");
    }
    private static void ReconnectRevokes()
    {
        using var f = new Fixture(); f.Ping(); string token = f.Current.Token;
        f.Store.Launch(f.Key, "prepare");
        Check(f.Store.ByToken(token) == null, "The old code survived reconnect.");
        Reject(() => f.Store.CheckObservation(token, f.Key, "epoch-12345", "", 20));
        Check(f.Current.RequestedAction == "prepare", "Reconnect silently scheduled calculation.");
        Check(!f.Store.Live(f.Current, f.Now), "Reconnect inherited the previous runtime lease.");
    }
    private static void DisconnectRetains()
    {
        using var f = new Fixture();
        string output = f.Store.CalibrationPath(f.Key); Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        File.WriteAllText(output, "sentinel: retained file, not a valid calibration");
        f.Ping("calibrating"); string token = f.Current.Token; f.Store.Disconnect(f.Key);
        Check(File.ReadAllText(output).StartsWith("sentinel", StringComparison.Ordinal), "Disconnect deleted outputs.");
        Check(!f.Store.Busy(f.Current, f.Now) && f.Store.ByToken(token) == null, "Disconnect did not revoke ownership.");
    }
    private static void RestartIsOffline()
    {
        using var f = new Fixture(); f.Ping("calibrating"); string token = f.Current.Token;
        var reopened = new ColabSessionStore(f.Root, () => f.Now);
        Check(!reopened.Live(reopened.Find(f.Key), f.Now), "A new desktop process inherited a lease.");
        Check(reopened.ByToken(token) == null, "A restarted desktop accepts the old code.");
        Check(reopened.NotebookFor(f.Key) == f.Store.NotebookFor(f.Key), "Restart lost notebook identity.");
    }
    private static void EpochOwnership()
    {
        using var f = new Fixture(); f.Ping();
        Reject(() => f.Store.CheckObservation(f.Current.Token, f.Key, "another-runtime", f.Current.CommandId, 2));
        f.Store.Launch(f.Key, "prepare");
        f.Store.Observe(f.Current.Token, f.Key, "", "another-runtime", "ready", f.Current.CommandId, 1, controlsReady: true);
        Check(f.Current.Epoch == "another-runtime", "Explicit reconnection did not admit a new runtime.");
    }
    private static void SequenceOrdering()
    {
        using var f = new Fixture(); f.Ping(sequence: 2);
        Reject(() => f.Ping("calibrating", sequence: 1));
        Reject(() => f.Ping("calibrating", sequence: 2));
        Check(f.Current.Phase == "ready", "A delayed packet resurrected a running phase.");
    }
    private static void Commands()
    {
        using var f = new Fixture(); f.Ping();
        var first = f.Store.QueueAction(f.Key, "calibrate");
        Reject(() => f.Store.QueueAction(f.Key, "analyze"));
        f.Ping("calibrating");
        var cancel = f.Store.QueueAction(f.Key, "cancel");
        Check(cancel.CommandId != first.CommandId, "Cancellation reused a command identity.");
        Reject(() => f.Store.QueueAction(f.Key, "analyze"));
        f.Ping("cancelled");
        f.Store.QueueAction(f.Key, "analyze");
        Reject(() => f.Ping(command: new string('f', 64)));
    }
    private static void UrlBoundary()
    {
        Check(ColabSessionStore.ValidNotebookUrl(RemoteJob.ColabUrl("analysis")), "The canonical source notebook is not reusable.");
        foreach (string url in new[] { "https://evil.example/drive/abcdefghijk", "https://colab.research.google.com.evil.example/drive/abcdefghijk",
            "http://colab.research.google.com/drive/abcdefghijk", "https://user@colab.research.google.com/drive/abcdefghijk",
            "https://colab.research.google.com/drive/short", "https://colab.research.google.com/github/other/repo/blob/main/notebook.ipynb" })
            Check(!ColabSessionStore.ValidNotebookUrl(url), "Unsafe notebook URL accepted: " + url);
    }
    private static void ProgressBounds()
    {
        using var f = new Fixture();
        Reject(() => f.Store.Observe(f.Current.Token, f.Key, "", "epoch-12345", "ready", f.Current.CommandId, 1, percent: 101));
        Reject(() => f.Store.Observe(f.Current.Token, f.Key, "", "epoch-12345", "made-up", f.Current.CommandId, 1));
        Reject(() => f.Store.Observe(f.Current.Token, f.Key, "", "epoch-12345", "ready", f.Current.CommandId, 1, message: new string('x', 501)));
        f.Store.Observe(f.Current.Token, f.Key, "", "epoch-12345", "calibrating", f.Current.CommandId, 1, percent: 37, message: "simulation", controlsReady: true);
        Check(f.Current.Percent == 37 && f.Current.ProgressMessage == "simulation", "Reported progress was not preserved.");
    }
    private static void CalibrationKeyCompatible()
    {
        string datasetHash = new('b', 64), settingsHash = new('c', 64); int repetitions = 2000; string kind = "standard";
        string legacy = ScientificMath.Hash(ScientificJson.Serialize(new { datasetHash, settingsHash, repetitions, kind,
            arguments = Array.Empty<string>(), revision = "ui-colab-2" }));
        Check(ColabSessionStore.KeyFor(datasetHash, settingsHash, repetitions, kind) == legacy, "UI update orphaned a compatible calibration directory.");
    }
}
