using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using MvsAnalyzer.Benchmarking;
namespace MvsAnalyzer;

// Data only. No executable commands, connection credentials or input file paths.
internal sealed record BackupContext(AnalysisData? FullData = null, CalibrationState? Calibration = null,
    string DatasetName = "Restored data", string DatasetHash = "", string Project = "Restored project", string Description = "",
    ProcessingSnapshot? Processing = null, bool Split = false, double Margin = .147);
internal sealed record BackupRequest
{
    public string Kind { get; init; } = "";
    public AnalysisData? Data { get; init; }
    public List<Observation>? Observations { get; init; }
    public List<CalibrationRow>? Calibration { get; init; }
    public int Repetitions { get; init; }
    public int ReferenceReplications { get; init; }
    public int Seed { get; init; }
    public double Effect { get; init; } = 1.15;
    public double SecondEffect { get; init; } = 1.3;
    public double Alpha { get; init; } = .05;
    public double Margin { get; init; } = .147;
    public double Outliers { get; init; } = .02;
    public double Missing { get; init; }
    public string Scenario { get; init; } = "location";
    public string[]? Tracks { get; init; }
    public EstimationOptions? Estimation { get; init; }
    public MelsmOptions? Melsm { get; init; }
    public BenchmarkProfile? Benchmark { get; init; }
    public List<RealDataset>? RealData { get; init; }
    public List<string>? RealDataNotes { get; init; }
    public BackupContext? Context { get; init; }
}
internal sealed record BackupDocument
{
    public int Schema { get; init; } = 1;
    public string Implementation { get; init; } = "portable-checkpoints-1";
    public string Application { get; init; } = ReleaseInfo.Version;
    public string Engine { get; init; } = ReleaseInfo.EngineVersion;
    public string Formula { get; init; } = OutputExporter.FormulaHash;
    public string Protocol { get; init; } = BenchmarkProtocol.Hash;
    public string OriginJob { get; init; } = Environment.GetEnvironmentVariable("MVS_BACKUP_JOB") ?? "";
    public string Id { get; init; } = Guid.NewGuid().ToString("N");
    public DateTime SavedUtc { get; set; } = DateTime.UtcNow;
    public BackupRequest Request { get; init; } = new();
    public string RequestHash { get; init; } = "";
    public List<string> Environments { get; init; } = new();
    public Dictionary<string, JsonElement> Units { get; init; } = new(StringComparer.Ordinal);
    public bool CalculationComplete { get; set; }
}
internal sealed class BackupSession : IDisposable
{
    internal const int MaxBytes = 64 * 1024 * 1024;
    internal static readonly JsonSerializerOptions Json = new()
    { IncludeFields = true, IgnoreReadOnlyProperties = true, NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals, MaxDepth = 64 };
    private static readonly AsyncLocal<BackupSession?> active = new();
    private static readonly AsyncLocal<BackupDocument?> pending = new();
    private static readonly AsyncLocal<BackupContext?> context = new();
    private static readonly object archiveGate = new();
    internal static readonly BackupSession Disabled = new();
    private readonly object gate = new();
    private BackupDocument? document;
    private DateTime lastSave = DateTime.MinValue;
    private bool dirty, disposed;
    internal bool EnvironmentChanged { get; private set; }
    internal bool WasRestored { get; private set; }
    internal static string Folder => Path.GetFullPath(Environment.GetEnvironmentVariable("MVS_BACKUP_DIR") ??
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "MVS_Backups"));
    internal static string Pack<T>(T value) => JsonSerializer.Serialize(value, Json);
    internal static BackupDocument? Pending => pending.Value;
    private sealed class Scope(Action restore) : IDisposable { public void Dispose() => restore(); }
    internal static IDisposable SetContext(BackupContext value)
    { var old = context.Value; context.Value = value; return new Scope(() => context.Value = old); }
    internal static IDisposable Restore(BackupDocument value)
    {
        Validate(value);
        if (active.Value != null || pending.Value != null) throw new InvalidOperationException("Another restore is active.");
        pending.Value = value; return new Scope(() => pending.Value = null);
    }
    internal static BackupSession Begin(BackupRequest request)
    {
        // Nested scientific work belongs to its outer operation; do not create thousands of child backups.
        if (active.Value != null || Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1") return Disabled;
        BackupDocument? saved = pending.Value;
        request = request with { Context = context.Value ?? saved?.Request.Context };
        string hash = ScientificMath.Hash(Pack(request));
        if (saved != null && saved.RequestHash != hash) throw new InvalidDataException("Backup inputs/settings do not match this calculation.");
        var session = new BackupSession { document = saved ?? new BackupDocument { Request = request, RequestHash = hash }, WasRestored = saved != null };
        pending.Value = null;
        session.EnvironmentChanged = session.document.Environments.Count > 0 && session.document.Environments[^1] != BenchmarkEnvironment.Hash;
        if (session.document.Environments.Count == 0 || session.document.Environments[^1] != BenchmarkEnvironment.Hash) session.document.Environments.Add(BenchmarkEnvironment.Hash);
        active.Value = session; session.dirty = true;
        try { session.Flush(true); } catch { active.Value = null; throw; }
        return session;
    }
    internal bool Try<T>(string key, out T value)
    {
        lock (gate)
            if (document != null && document.Units.TryGetValue(key, out var stored))
            { value = stored.Deserialize<T>(Json)!; if (value is null) throw new InvalidDataException("Invalid saved unit: " + key); return true; }
        value = default!; return false;
    }
    internal T Cached<T>(string key, Func<T> calculate)
    { if (Try<T>(key, out var value)) return value; value = calculate(); Put(key, value); return value; }
    internal void Put<T>(string key, T value)
    {
        if (document == null) return;
        lock (gate) { document.Units[key] = JsonSerializer.SerializeToElement(value, Json); dirty = true; Flush(false); }
    }
    internal T Finish<T>(T value)
    {
        if (document != null) lock (gate)
        { document.Units["result"] = JsonSerializer.SerializeToElement(value, Json); document.CalculationComplete = true; dirty = true; Flush(true); }
        return value;
    }
    private void Flush(bool force)
    {
        if (document == null || !dirty || (!force && DateTime.UtcNow - lastSave < TimeSpan.FromSeconds(15))) return;
        document.SavedUtc = DateTime.UtcNow; Store(Encode(document), document, Folder); lastSave = DateTime.UtcNow; dirty = false;
    }
    public void Dispose()
    {
        if (document == null || disposed) return; disposed = true;
        try { lock (gate) Flush(true); } finally { if (active.Value == this) active.Value = null; }
    }
    internal static void Validate(BackupDocument d)
    {
        if (d.Schema != 1 || d.Implementation != "portable-checkpoints-1" || d.Application != ReleaseInfo.Version || d.Engine != ReleaseInfo.EngineVersion || d.Formula != OutputExporter.FormulaHash || d.Protocol != BenchmarkProtocol.Hash)
            throw new InvalidDataException("Incompatible backup or scientific implementation. Use the matching MVS build.");
        if (d.OriginJob == null || (d.OriginJob.Length != 0 && !ColabSessionStore.HexKey(d.OriginJob)) || d.Id == null || d.Id.Length != 32 || d.Id.Any(c => !char.IsAsciiHexDigit(c)) ||
            d.Request == null || d.Units == null || d.Environments == null || !new[] { "benchmark", "calibrate", "analyze", "variance", "estimation", "melsm" }.Contains(d.Request.Kind))
            throw new InvalidDataException("Invalid backup identity or operation.");
        if (d.RequestHash != ScientificMath.Hash(Pack(d.Request))) throw new InvalidDataException("Backup settings/input checksum mismatch.");
        if (d.Units.Count > 250000 || d.Units.Any(x => x.Key.Length > 200) || d.Environments.Count > 100) throw new InvalidDataException("Backup exceeds safe limits.");
    }
    internal static byte[] Encode(BackupDocument document)
    {
        byte[] json = Encoding.UTF8.GetBytes(Pack(document));
        if (json.Length > MaxBytes) throw new InvalidDataException("Backup exceeds 64 MiB. The last complete snapshot remains available.");
        using var buffer = new MemoryStream();
        using (var zip = new ZipArchive(buffer, ZipArchiveMode.Create, true))
        {
            using (var output = zip.CreateEntry("backup.json", CompressionLevel.Fastest).Open()) output.Write(json);
            using var sums = new StreamWriter(zip.CreateEntry("SHA256SUMS.txt").Open(), new UTF8Encoding(false));
            sums.Write(Convert.ToHexString(SHA256.HashData(json)).ToLowerInvariant() + "  backup.json\n");
        }
        return buffer.ToArray();
    }
    private static byte[] ReadEntry(ZipArchiveEntry entry, int limit)
    {
        if (entry.Length < 0 || entry.Length > limit) throw new InvalidDataException("Backup entry exceeds safe limits.");
        using var input = entry.Open(); using var output = new MemoryStream(); byte[] block = new byte[65536]; int count;
        while ((count = input.Read(block, 0, block.Length)) != 0)
        { if (output.Length + count > limit) throw new InvalidDataException("Backup expansion limit exceeded."); output.Write(block, 0, count); }
        if (output.Length != entry.Length) throw new InvalidDataException("Truncated backup entry."); return output.ToArray();
    }
    internal static BackupDocument Decode(byte[] bytes)
    {
        if (bytes.Length > MaxBytes) throw new InvalidDataException("Backup archive too large.");
        using var stream = new MemoryStream(bytes, false); using var zip = new ZipArchive(stream, ZipArchiveMode.Read);
        if (zip.Entries.Count != 2 || zip.Entries.Count(x => x.FullName == "backup.json") != 1 || zip.Entries.Count(x => x.FullName == "SHA256SUMS.txt") != 1)
            throw new InvalidDataException("Unexpected backup archive structure.");
        byte[] json = ReadEntry(zip.GetEntry("backup.json")!, MaxBytes);
        string sum = Encoding.UTF8.GetString(ReadEntry(zip.GetEntry("SHA256SUMS.txt")!, 256)).Trim();
        if (sum != Convert.ToHexString(SHA256.HashData(json)).ToLowerInvariant() + "  backup.json") throw new InvalidDataException("Damaged backup checksum.");
        BackupDocument result = JsonSerializer.Deserialize<BackupDocument>(json, Json) ?? throw new InvalidDataException("Empty backup."); Validate(result); return result;
    }
    internal static List<BackupDocument> ReadArchive(string path)
    {
        const long totalLimit = 512L * 1024 * 1024;
        if (new FileInfo(path).Length > totalLimit) throw new InvalidDataException("Backup collection exceeds 512 MiB.");
        using var zip = ZipFile.OpenRead(path);
        if (zip.GetEntry("backup.json") != null)
        { if (new FileInfo(path).Length > MaxBytes) throw new InvalidDataException("Backup too large."); return new() { Decode(File.ReadAllBytes(path)) }; }
        if (zip.Entries.Count is < 1 or > 512) throw new InvalidDataException("Invalid backup collection size.");
        var found = new List<BackupDocument>(); long expanded = 0;
        foreach (var entry in zip.Entries)
        {
            if (entry.FullName != Path.GetFileName(entry.FullName) || entry.FullName.Contains('\\') || !entry.FullName.EndsWith(".mvsbackup", StringComparison.Ordinal)) throw new InvalidDataException("Unsafe backup entry.");
            byte[] bytes = ReadEntry(entry, MaxBytes);
            using var inner = new ZipArchive(new MemoryStream(bytes, false), ZipArchiveMode.Read);
            expanded += inner.GetEntry("backup.json")?.Length ?? MaxBytes;
            if (expanded > totalLimit) throw new InvalidDataException("Expanded backup collection exceeds 512 MiB.");
            found.Add(Decode(bytes));
        }
        return found.OrderByDescending(d => d.SavedUtc).ToList();
    }
    internal static void Receive(byte[] bytes) { var d = Decode(bytes); Store(bytes, d, Folder); }
    private static void AtomicBytes(string path, byte[] bytes)
    {
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { output.Write(bytes); output.Flush(true); } File.Move(temp, path, true); }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    private static void Store(byte[] bytes, BackupDocument doc, string folder)
    {
        lock (archiveGate)
        {
            Directory.CreateDirectory(folder); string current = Path.Combine(folder, doc.Id + ".mvsbackup");
            if (File.Exists(current))
            {
                byte[] oldBytes = File.ReadAllBytes(current); var old = Decode(oldBytes);
                if (old.SavedUtc >= doc.SavedUtc) return;
                AtomicBytes(Path.Combine(folder, doc.Id + ".previous.mvsbackup"), oldBytes);
            }
            AtomicBytes(current, bytes); ExportAll(Path.Combine(folder, "MVS_Backups.zip"), folder);
        }
    }
    internal static void ExportAll(string destination, string? folder = null)
    {
        lock (archiveGate)
        {
            folder ??= Folder; Directory.CreateDirectory(folder);
            string[] files = Directory.GetFiles(folder, "*.mvsbackup").OrderBy(x => x, StringComparer.Ordinal).ToArray();
            if (files.Length > 512 || files.Sum(f => new FileInfo(f).Length) > 512L * 1024 * 1024) throw new InvalidDataException("Backup collection is full. Move older backups elsewhere.");
            long expanded = 0;
            foreach (string file in files)
            {
                using var check = ZipFile.OpenRead(file);
                expanded += check.GetEntry("backup.json")?.Length ?? MaxBytes;
                if (expanded > 512L * 1024 * 1024) throw new InvalidDataException("Expanded backup collection is full. Move older backups elsewhere.");
            }
            string temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try { using (var zip = ZipFile.Open(temporary, ZipArchiveMode.Create)) foreach (string file in files) zip.CreateEntryFromFile(file, Path.GetFileName(file), CompressionLevel.NoCompression); File.Move(temporary, destination, true); }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
    }
}
