using System.Security.Cryptography;
using System.Text.Json;

namespace MvsAnalyzer;

internal sealed record ColabSession(string Key, string Token, string Kind, string NotebookUrl = "",
    string Epoch = "", string Phase = "new", DateTime LastSeenUtc = default, DateTime LaunchedUtc = default,
    string RequestedAction = "calibrate", string CommandId = "", string AcknowledgedCommandId = "",
    int? Percent = null, string ProgressMessage = "", string RuntimeLabel = "", bool ControlsReady = false,
    long Sequence = 0);
internal sealed record ColabRunPlan(string Key, string Kind, string RequestedAction, string DatasetHash,
    string SettingsHash, int Repetitions, string[] Arguments, string AppVersion = ReleaseInfo.Version,
    string EngineVersion = ReleaseInfo.EngineVersion, string Revision = ColabSessionStore.Protocol,
    string CommandId = "");

/// <summary>
/// Notebook identity, connection lease and verified outputs are separate. A closed tab cannot
/// reliably announce its closure: only fresh runtime messages extend the short lease. Disconnect
/// revokes the token, not the saved calibration, and never claims to stop Google's runtime.
/// </summary>
internal sealed class ColabSessionStore
{
    public const string Protocol = "ui-colab-3";
    public const int LeaseSeconds = 45;
    public const int PendingSeconds = 45;
    private readonly object gate = new();
    private readonly Dictionary<string, ColabSession> sessions = new(StringComparer.Ordinal);
    private readonly Func<DateTime> clock;
    public string Folder { get; }
    private static string NewToken() => Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
    public ColabSessionStore(string folder, Func<DateTime>? utcNow = null)
    {
        clock = utcNow ?? (() => DateTime.UtcNow);
        Folder = Path.GetFullPath(folder); Directory.CreateDirectory(Folder);
        try
        {
            string path = Path.Combine(Folder, "sessions.json");
            if (File.Exists(path) && new FileInfo(path).Length <= 2 * 1024 * 1024)
                foreach (ColabSession? session in ScientificJson.Read<ColabSession?[]>(path))
                    if (session != null && HexKey(session.Key) && HexKey(session.Token) &&
                        (string.IsNullOrEmpty(session.NotebookUrl) || ValidNotebookUrl(session.NotebookUrl)))
                        // A different desktop process has a different listener. Never restore a live lease.
                        sessions[session.Key] = session with { Token = NewToken(), Epoch = "", Phase = "disconnected",
                            LastSeenUtc = default, ControlsReady = false, CommandId = "", AcknowledgedCommandId = "",
                            Percent = null, ProgressMessage = "", Sequence = 0 };
        }
        catch (Exception error) when (error is IOException or JsonException or InvalidDataException or ArgumentException) { }
    }
    public static bool HexKey(string? text) => text is { Length: 64 } && text.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    public static string KeyFor(string datasetHash, string settingsHash, int repetitions, string kind, string[]? arguments = null) =>
        // Transport updates must not orphan compatible 1.4.0 calibration directories.
        ScientificMath.Hash(ScientificJson.Serialize(new { datasetHash, settingsHash, repetitions, kind, arguments = arguments ?? Array.Empty<string>(), revision = "ui-colab-2" }));
    public static bool ValidNotebookUrl(string? value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? url) || url.Scheme != "https" ||
            !url.Host.Equals("colab.research.google.com", StringComparison.OrdinalIgnoreCase) ||
            url.UserInfo.Length != 0 || !url.IsDefaultPort) return false;
        string path = url.AbsolutePath;
        if (path.StartsWith("/drive/", StringComparison.Ordinal))
            return path[7..].Length >= 10 && path[7..].All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-');
        return new[] { "analysis", "benchmark" }.Any(kind => path.Equals(new Uri(RemoteJob.ColabUrl(kind)).AbsolutePath, StringComparison.OrdinalIgnoreCase));
    }
    public static string NormalizeNotebookUrl(string value)
    {
        if (!ValidNotebookUrl(value)) throw new InvalidDataException("Use this project's Colab notebook or a saved Colab /drive/ notebook address.");
        return new Uri(value).GetLeftPart(UriPartial.Path); // Strip old #copy=true, query parameters and stale cell anchors.
    }
    public string DirectoryFor(string key)
    {
        if (!HexKey(key)) throw new InvalidDataException("Invalid Colab job identity.");
        return Path.Combine(Folder, key);
    }
    public string CalibrationPath(string key) => Path.Combine(DirectoryFor(key), CalibrationPersistence.FileName);
    public string ArchivePath(string key) => Path.Combine(DirectoryFor(key), "job.zip");
    public ColabSession GetOrCreate(string key, string kind, string action)
    {
        _ = DirectoryFor(key);
        lock (gate)
        {
            if (!sessions.TryGetValue(key, out ColabSession? session))
            { session = new(key, NewToken(), kind, RequestedAction: action); sessions[key] = session; Save(); }
            return session;
        }
    }
    public ColabSession? Find(string key) { lock (gate) return sessions.GetValueOrDefault(key); }
    public ColabSession? ByToken(string token) { lock (gate) return sessions.Values.FirstOrDefault(x => x.Token == token); }
    public ColabSession? Latest() { lock (gate) return sessions.Values.OrderByDescending(s => s.LaunchedUtc).FirstOrDefault(); }
    public bool Live(ColabSession? session, DateTime now) => session != null && session.Epoch.Length > 0 &&
        session.Phase is not ("disconnected" or "offline") && session.LastSeenUtc > now.AddSeconds(-LeaseSeconds) && session.LastSeenUtc <= now.AddSeconds(5);
    public bool Pending(ColabSession? session, DateTime now) => session != null &&
        (session.Phase == "opening" || session.CommandId.Length > 0 && session.CommandId != session.AcknowledgedCommandId) &&
        session.LaunchedUtc > now.AddSeconds(-PendingSeconds) && session.LaunchedUtc <= now.AddSeconds(5);
    public static bool Working(string phase) => phase is "preparing" or "calibrating" or "analyzing" or "running" or "downloading" or "cancelling";
    public bool Busy(ColabSession? session, DateTime now) => Live(session, now) && Working(session!.Phase);
    public string NotebookFor(string? key = null)
    {
        lock (gate)
        {
            if (key != null && sessions.TryGetValue(key, out var own) && ValidNotebookUrl(own.NotebookUrl)) return NormalizeNotebookUrl(own.NotebookUrl);
            ColabSession? last = sessions.Values.Where(s => ValidNotebookUrl(s.NotebookUrl)).OrderByDescending(s => s.LaunchedUtc).FirstOrDefault();
            return last == null ? RemoteJob.ColabUrl("analysis") : NormalizeNotebookUrl(last.NotebookUrl);
        }
    }
    public void LinkNotebook(string key, string url)
    {
        string normalized = NormalizeNotebookUrl(url);
        lock (gate) { sessions[key] = sessions[key] with { NotebookUrl = normalized }; Save(); }
    }
    public string Launch(string key, string action)
    {
        ValidateAction(action);
        lock (gate)
        {
            string url = NotebookFor(key);
            ColabSession session = sessions[key];
            sessions[key] = session with { Token = NewToken(), Phase = "opening", LaunchedUtc = clock(), RequestedAction = action,
                NotebookUrl = url, Epoch = "", LastSeenUtc = default, ControlsReady = false, CommandId = NewToken(),
                AcknowledgedCommandId = "", Percent = null, ProgressMessage = "", Sequence = 0 };
            Save();
            // Opening an existing notebook is independent of whether its runtime is still alive.
            return url + "#scrollTo=mvs-calibrate";
        }
    }
    public ColabSession QueueAction(string key, string action)
    {
        ValidateAction(action);
        lock (gate)
        {
            ColabSession current = sessions[key];
            if (!Live(current, clock()) || !current.ControlsReady) throw new InvalidOperationException("Reconnect the notebook's first cell before sending commands.");
            if (action != "cancel" && (Busy(current, clock()) || Pending(current, clock())))
                throw new InvalidOperationException("An MVS command is already pending or running.");
            if (action == "cancel" && !Busy(current, clock()) && !Pending(current, clock()))
                throw new InvalidOperationException("There is no pending or running command to cancel.");
            current = current with { CommandId = NewToken(), RequestedAction = action, LaunchedUtc = clock(),
                Percent = action == "cancel" ? current.Percent : null, ProgressMessage = "" };
            sessions[key] = current; Save(); return current;
        }
    }
    private static void ValidateAction(string action)
    {
        if (action is not ("prepare" or "calibrate" or "analyze" or "download" or "cancel")) throw new InvalidDataException("Unknown Colab command.");
    }
    public void Disconnect(string key)
    {
        lock (gate)
        {
            if (!sessions.TryGetValue(key, out var session)) return;
            sessions[key] = session with { Token = NewToken(), Epoch = "", Phase = "disconnected", LastSeenUtc = default,
                ControlsReady = false, CommandId = "", AcknowledgedCommandId = "", Percent = null, ProgressMessage = "", Sequence = 0 };
            Save();
        }
    }
    public void CheckObservation(string token, string key, string epoch, string commandId, long sequence)
    {
        if (epoch.Length is < 8 or > 100 || !epoch.All(c => char.IsAsciiLetterOrDigit(c) || c == '-')) throw new InvalidDataException("Invalid runtime generation.");
        lock (gate)
        {
            if (!sessions.TryGetValue(key, out var current) || current.Token != token || current.Phase == "disconnected")
                throw new InvalidDataException("This connection was revoked. Copy a new code from MVS.");
            if (current.Epoch.Length > 0 && current.Epoch != epoch)
                throw new InvalidDataException("A different runtime owns this connection. Reconnect explicitly; do not start a notebook copy.");
            if (sequence <= current.Sequence || sequence < 1) throw new InvalidDataException("Stale Colab status packet.");
            if (commandId.Length > 0 && commandId != current.CommandId && commandId != current.AcknowledgedCommandId)
                throw new InvalidDataException("Stale Colab command acknowledgement.");
        }
    }
    public ColabSession Observe(string token, string key, string notebookUrl, string epoch, string phase,
        string commandId, long sequence, int? percent = null, string message = "", string runtime = "", bool controlsReady = false)
    {
        if (notebookUrl.Length != 0 && !ValidNotebookUrl(notebookUrl)) throw new InvalidDataException("Invalid Colab notebook address.");
        if (!new[] { "preparing", "ready", "calibrating", "analyzing", "running", "calibrated", "complete", "failed", "cancelled", "downloading", "cancelling", "offline" }.Contains(phase))
            throw new InvalidDataException("Unknown Colab phase.");
        if (percent is < 0 or > 100 || message.Length > 500 || runtime.Length > 200) throw new InvalidDataException("Invalid Colab progress.");
        lock (gate)
        {
            CheckObservation(token, key, epoch, commandId, sequence);
            ColabSession current = sessions[key];
            current = current with { NotebookUrl = notebookUrl.Length == 0 ? current.NotebookUrl : NormalizeNotebookUrl(notebookUrl),
                Epoch = epoch, Phase = phase, LastSeenUtc = clock(), ControlsReady = controlsReady, Sequence = sequence,
                AcknowledgedCommandId = commandId == current.CommandId ? commandId : current.AcknowledgedCommandId,
                Percent = percent, ProgressMessage = message, RuntimeLabel = runtime };
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
