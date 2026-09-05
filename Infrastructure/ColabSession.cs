using System.Security.Cryptography;
using System.Text.Json;

namespace MvsAnalyzer;

internal sealed record ColabSession(string Key, string Token, string Kind, string NotebookUrl = "",
    string Epoch = "", string Phase = "new", DateTime LastSeenUtc = default, DateTime LaunchedUtc = default,
    string RequestedAction = "calibrate");
internal sealed record ColabRunPlan(string Key, string Kind, string RequestedAction, string DatasetHash,
    string SettingsHash, int Repetitions, string[] Arguments, string AppVersion = ReleaseInfo.Version,
    string EngineVersion = ReleaseInfo.EngineVersion, string Revision = "ui-colab-1");

// A completion flag is never enough: a validated calibration file is required before disabling a button.
internal sealed class ColabSessionStore
{
    private readonly object gate = new();
    private readonly Dictionary<string, ColabSession> sessions = new(StringComparer.Ordinal);
    public string Folder { get; }
    public ColabSessionStore(string folder)
    {
        Folder = Path.GetFullPath(folder); Directory.CreateDirectory(Folder);
        try
        {
            string path = Path.Combine(Folder, "sessions.json");
            if (File.Exists(path) && new FileInfo(path).Length <= 2 * 1024 * 1024) foreach (ColabSession? session in ScientificJson.Read<ColabSession?[]>(path))
                if (session != null && HexKey(session.Key) && HexKey(session.Token) && (string.IsNullOrEmpty(session.NotebookUrl) || ValidNotebookUrl(session.NotebookUrl))) sessions[session.Key] = session;
        }
        catch (Exception error) when (error is IOException or JsonException or InvalidDataException) { }
    }
    public static bool HexKey(string? text) => text is { Length: 64 } && text.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    public static string KeyFor(string datasetHash, string settingsHash, int repetitions, string kind, string[]? arguments = null) =>
        ScientificMath.Hash(ScientificJson.Serialize(new { datasetHash, settingsHash, repetitions, kind, arguments = arguments ?? Array.Empty<string>(), revision = "ui-colab-1" }));
    public static bool ValidNotebookUrl(string value) => Uri.TryCreate(value, UriKind.Absolute, out Uri? url) && url.Scheme == "https" &&
        url.Host.Equals("colab.research.google.com", StringComparison.OrdinalIgnoreCase) && url.UserInfo.Length == 0 && url.IsDefaultPort &&
        url.AbsolutePath.StartsWith("/drive/", StringComparison.Ordinal) && url.AbsolutePath[7..].Length >= 10 &&
        url.AbsolutePath[7..].All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-');
    public string DirectoryFor(string key)
    {
        if (!HexKey(key)) throw new InvalidDataException("Invalid Colab job identity.");
        return Path.Combine(Folder, key);
    }
    public string CalibrationPath(string key) => Path.Combine(DirectoryFor(key), CalibrationPersistence.FileName);
    public string ArchivePath(string key) => Path.Combine(DirectoryFor(key), "job.zip");
    public ColabSession GetOrCreate(string key, string kind, string action)
    {
        lock (gate)
        {
            if (!sessions.TryGetValue(key, out ColabSession? session))
                session = new(key, Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant(), kind);
            session = session with { RequestedAction = action };
            sessions[key] = session; Save(); return session;
        }
    }
    public ColabSession? Find(string key) { lock (gate) return sessions.GetValueOrDefault(key); }
    public ColabSession? ByToken(string token) { lock (gate) return sessions.Values.FirstOrDefault(x => x.Token == token); }
    public bool Live(ColabSession? session, DateTime now) => session != null && !string.IsNullOrEmpty(session.Epoch) && session.LastSeenUtc > now.AddSeconds(-100) && session.LastSeenUtc <= now.AddSeconds(5);
    public bool Pending(ColabSession? session, DateTime now) => session != null && session.Phase == "opening" && session.LaunchedUtc > now.AddMinutes(-3);
    public ColabSession? Reusable()
    {
        lock (gate) return sessions.Values.Where(s => Live(s, DateTime.UtcNow) && ValidNotebookUrl(s.NotebookUrl) && s.Phase is not ("preparing" or "calibrating" or "analyzing" or "running"))
            .OrderByDescending(s => s.LastSeenUtc).FirstOrDefault();
    }
    public string Launch(string key, string action, ColabSession? reusable = null)
    {
        lock (gate)
        {
            ColabSession session = sessions[key];
            // Reuse only a notebook that actually reported a live MVS kernel, never an invented active flag.
            ColabSession? active = reusable != null && Live(reusable, DateTime.UtcNow) && ValidNotebookUrl(reusable.NotebookUrl) ? reusable : null;
            string url = active?.NotebookUrl ?? RemoteJob.ColabUrl("analysis");
            sessions[key] = session with { Phase = "opening", LaunchedUtc = DateTime.UtcNow, RequestedAction = action,
                NotebookUrl = active?.NotebookUrl ?? "", Epoch = active?.Epoch ?? "", LastSeenUtc = active?.LastSeenUtc ?? default };
            Save();
            return active == null ? url + "#copy=true" : url + "#scrollTo=" + (action == "calibrate" || active.Key != key ? "mvs-calibrate" : "mvs-analyze");
        }
    }
    public ColabSession Observe(string key, string notebookUrl, string epoch, string phase)
    {
        if (epoch.Length is < 8 or > 100 || !epoch.All(c => char.IsAsciiLetterOrDigit(c) || c == '-')) throw new InvalidDataException("Invalid runtime generation.");
        if (notebookUrl.Length != 0 && !ValidNotebookUrl(notebookUrl)) throw new InvalidDataException("Expected a saved Colab notebook URL.");
        if (!new[] { "preparing", "ready", "calibrating", "analyzing", "running", "calibrated", "complete", "failed", "cancelled" }.Contains(phase)) throw new InvalidDataException("Unknown Colab phase.");
        lock (gate)
        {
            foreach (ColabSession previous in sessions.Values.Where(s => s.Key != key && s.Epoch == epoch).ToArray())
                sessions[previous.Key] = previous with { LastSeenUtc = default, Epoch = "", Phase = "idle" };
            ColabSession current = sessions[key];
            current = current with { NotebookUrl = notebookUrl.Length == 0 ? current.NotebookUrl : new Uri(notebookUrl).GetLeftPart(UriPartial.Path),
                Epoch = epoch, Phase = phase, LastSeenUtc = DateTime.UtcNow };
            sessions[key] = current; Save(); return current;
        }
    }
    public bool HasCalibration(string key, string datasetHash, string settingsHash, int repetitions)
    {
        string path = CalibrationPath(key);
        if (!File.Exists(path)) return false;
        try { CalibrationState state = CalibrationPersistence.Read(path); return state.DatasetHash == datasetHash && state.SettingsHash == settingsHash && state.Repetitions == repetitions; }
        catch (Exception error) when (error is IOException or JsonException or InvalidDataException or ArgumentException) { return false; }
    }
    private void Save() => ScientificJson.Write(Path.Combine(Folder, "sessions.json"), sessions.Values.OrderBy(x => x.Key).ToArray());
}
