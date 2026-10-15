using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MvsAnalyzer;

internal static class RunAuditorChecks
{
    internal static IEnumerable<(string Name, Action Run)> All
    {
        get
        {
            yield return ("Journal rejects empty or relative application-data roots", RejectRelative);
            yield return ("Journal absolute path resolution is read-only", ResolveAbsolute);
            if (OperatingSystem.IsLinux())
            {
                yield return ("Journal creates nonexistent absolute XDG data directory", NewDataDirectory);
                yield return ("Journal appends without changing existing chain bytes", ExistingChain);
                yield return ("Journal obstruction does not fall back to working directory", ObstructedDirectory);
                yield return ("Journal read does not create nonexistent data directory", ReadOnlyLookup);
                yield return ("Journal file lock excludes same-process threads", SameProcessFileLock);
                yield return ("Journal lock file persists empty after release", PersistentLockFile);
                yield return ("Journal lock obstruction fails without fallback", LockObstruction);
            }
        }
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void RejectRelative()
    {
        foreach (string root in new[] { "", " ", ".", "relative-data", "../data" })
        {
            try { RunAuditor.ResolveJournalFolder(root); }
            catch (DirectoryNotFoundException) { continue; }
            throw new Exception("Unsafe journal root accepted: " + root);
        }
    }

    private static void ResolveAbsolute()
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-journal-lookup-" + Guid.NewGuid().ToString("N"));
        Assert(RunAuditor.ResolveJournalFolder(root) == Path.Combine(root, "MVS_Analyzer"), "Absolute root changed.");
        Assert(!Directory.Exists(root), "Resolving the journal path created a directory.");
    }

    private static void Isolated(Action<string, string> action)
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-journal-test-" + Guid.NewGuid().ToString("N"));
        string cwd = Path.Combine(root, "cwd"), data = Path.Combine(root, "new-data");
        string originalCwd = Environment.CurrentDirectory;
        string? originalXdg = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
        string? originalAppdata = Environment.GetEnvironmentVariable(ApplicationDataPaths.OverrideVariable);
        Directory.CreateDirectory(cwd);
        Directory.CreateDirectory(Path.Combine(cwd, "MVS_Analyzer"));
        string sentinel = Path.Combine(cwd, "MVS_Analyzer", "run_journal.jsonl");
        File.WriteAllText(sentinel, "unrelated working-directory journal; preserve exactly\n");
        byte[] before = File.ReadAllBytes(sentinel);
        try
        {
            Environment.CurrentDirectory = cwd;
            Environment.SetEnvironmentVariable("XDG_DATA_HOME", data);
            Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, null);
            action(root, data);
            Assert(before.SequenceEqual(File.ReadAllBytes(sentinel)), "Working-directory journal was changed.");
        }
        finally
        {
            Environment.CurrentDirectory = originalCwd;
            Environment.SetEnvironmentVariable("XDG_DATA_HOME", originalXdg);
            Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, originalAppdata);
            Directory.Delete(root, true);
        }
    }

    private static void Append(string id) => RunAuditor.AppendJournal(id, "/synthetic/output", "synthetic-hash", new AppSettings(), 100, "");

    private static void NewDataDirectory() => Isolated((_, data) =>
    {
        Assert(!Directory.Exists(data), "Fixture data directory already exists.");
        Assert(RunAuditor.JournalPath == Path.Combine(data, "MVS_Analyzer", "run_journal.jsonl"), "Missing XDG root was not resolved absolutely.");
        Assert(!Directory.Exists(data), "Path getter unexpectedly created the directory.");
        Append("new");
        string[] lines = File.ReadAllLines(RunAuditor.JournalPath);
        Assert(lines.Length == 1, "Expected one entry in the application-data journal.");
        using JsonDocument doc = JsonDocument.Parse(lines[0]);
        Assert(doc.RootElement.GetProperty("previous").GetString() == "genesis", "New chain must start with genesis.");
    });

    private static void ExistingChain() => Isolated((_, data) =>
    {
        Directory.CreateDirectory(data);
        Append("first");
        byte[] before = File.ReadAllBytes(RunAuditor.JournalPath);
        string first = File.ReadAllLines(RunAuditor.JournalPath).Single();
        Append("second");
        byte[] after = File.ReadAllBytes(RunAuditor.JournalPath);
        Assert(after.Take(before.Length).SequenceEqual(before), "Existing journal prefix was rewritten.");
        string[] lines = File.ReadAllLines(RunAuditor.JournalPath);
        Assert(lines.Length == 2, "Append did not retain both entries.");
        using JsonDocument doc = JsonDocument.Parse(lines[1]);
        string expected = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(first))).ToLowerInvariant();
        Assert(doc.RootElement.GetProperty("previous").GetString() == expected, "Append broke the existing hash chain.");
    });

    private static void ObstructedDirectory() => Isolated((_, data) =>
    {
        File.WriteAllText(data, "preserve obstruction");
        bool failed = false;
        try { Append("blocked"); }
        catch (IOException) { failed = true; }
        Assert(failed, "Obstructed application-data path silently succeeded.");
        Assert(File.ReadAllText(data) == "preserve obstruction", "Obstruction file changed.");
    });

    private static void ReadOnlyLookup() => Isolated((root, data) =>
    {
        string reportRoot = Path.Combine(root, "empty-reports");
        Directory.CreateDirectory(reportRoot);
        RunAuditor.Audit(reportRoot);
        Assert(!Directory.Exists(data), "Reading an absent journal created application-data directories.");
    });
    private static void SameProcessFileLock() => Isolated((_, data) =>
    {
        Directory.CreateDirectory(Path.Combine(data, "MVS_Analyzer"));
        string journal = RunAuditor.JournalPath;
        using var held = new FileStream(journal + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var started = new ManualResetEventSlim();
        using var acquired = new ManualResetEventSlim();
        var worker = Task.Run(() =>
        {
            started.Set();
            using var guard = RunAuditor.AcquireJournalLock(journal);
            acquired.Set();
        });
        bool began = started.Wait(TimeSpan.FromSeconds(5));
        bool premature = acquired.Wait(TimeSpan.FromMilliseconds(200));
        held.Dispose();
        Assert(worker.Wait(TimeSpan.FromSeconds(12)), "File-lock waiter did not finish after release.");
        Assert(began && !premature && acquired.IsSet, "FileShare.None did not exclude the other thread.");
    });

    private static void PersistentLockFile() => Isolated((_, data) =>
    {
        Append("lock-test");
        string path = RunAuditor.JournalPath + ".lock";
        Assert(File.Exists(path) && new FileInfo(path).Length == 0, "Released lock file must persist empty.");
        byte[] before = File.ReadAllBytes(RunAuditor.JournalPath);
        RunAuditor.Audit(data);
        Assert(File.Exists(path) && new FileInfo(path).Length == 0, "Read removed/replaced lock state.");
        Assert(before.SequenceEqual(File.ReadAllBytes(RunAuditor.JournalPath)), "Audit changed journal bytes.");
    });

    private static void LockObstruction() => Isolated((_, data) =>
    {
        string lockPath = Path.Combine(data, "MVS_Analyzer", "run_journal.jsonl.lock");
        Directory.CreateDirectory(lockPath);
        File.WriteAllText(Path.Combine(lockPath, "preserve.txt"), "preserve");
        bool failed = false;
        try { Append("blocked-lock"); }
        catch (IOException) { failed = true; }
        catch (UnauthorizedAccessException) { failed = true; }
        Assert(failed, "Lock obstruction silently succeeded.");
        Assert(!File.Exists(RunAuditor.JournalPath), "Append bypassed the unavailable lock.");
        Assert(File.ReadAllText(Path.Combine(lockPath, "preserve.txt")) == "preserve", "Lock obstruction changed.");
    });

}
