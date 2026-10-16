using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

internal static class BackupRetryChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[] {
        ("Failed restore publication preserves retry identity and units", Retry),
        ("Failed restore publication preserves environment reevaluation", EnvironmentRetry),
        ("Late archive publication failure preserves retriable checkpoint", LateFailure),
        ("Failed restore scope exits without leaking pending state", ScopeExit),
        ("Fresh publication failure does not create restore state", FreshFailure),
        ("Request mismatch and disabled begin preserve pending restore", MismatchAndDisabled)
    }.Concat(BackupPublicationFault.All);
    private static void Assert(bool value, string message) { if (!value) throw new Exception(message); }
    private static BackupRequest Request() => new() { Kind = "estimation", Estimation = new() };
    private static BackupDocument Saved(BackupRequest request)
    {
        var document = new BackupDocument { Request = request, RequestHash = ScientificMath.Hash(BackupSession.Pack(request)), SavedUtc = new DateTime(2020, 1, 2, 3, 4, 5, DateTimeKind.Utc) };
        document.Units["retained"] = JsonSerializer.SerializeToElement(new[] { 7, 11, 19 });
        return document;
    }
    private static void Isolated(Action<string, string> test)
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-retry-check-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string blocker = Path.Combine(root, "blocked"); File.WriteAllText(blocker, "owned fixture");
        string? oldDir = Environment.GetEnvironmentVariable("MVS_BACKUP_DIR"), oldDisabled = Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS");
        try { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", blocker); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null); test(blocker, Path.Combine(root, "repaired")); }
        finally { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", oldDir); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", oldDisabled); Directory.Delete(root, true); }
    }
    private static void Fails(BackupRequest request)
    {
        try { using var ignored = BackupSession.Begin(request); }
        catch (IOException) { return; }
        throw new Exception("Owned file obstruction did not reject backup publication.");
    }
    private static void Retry() => Isolated((blocked, repaired) => {
        var request = Request(); var saved = Saved(request); string original = BackupSession.Pack(saved);
        using (BackupSession.Restore(saved)) {
            Fails(request); Fails(request);
            Assert(ReferenceEquals(BackupSession.Pending, saved), "Failed Begin consumed pending restore.");
            Assert(BackupSession.Pack(saved) == original, "Failed Begin mutated saved metadata or units.");
            Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
            using (var retry = BackupSession.Begin(request)) {
                Assert(retry.WasRestored, "Retry silently started fresh.");
                Assert(BackupSession.Pending == null, "Successful Begin did not consume pending restore.");
                Assert(retry.Try<int[]>("retained", out var values) && values.SequenceEqual(new[] { 7, 11, 19 }), "Retry lost saved unit.");
                using var nested = BackupSession.Begin(request);
                Assert(ReferenceEquals(nested, BackupSession.Disabled), "Nested default behavior changed.");
            }
            Assert(Directory.GetFiles(repaired, "*.mvsbackup").Select(p => BackupSession.Decode(File.ReadAllBytes(p))).All(d => d.Id == saved.Id), "Retry changed document identity.");
        }
        Assert(BackupSession.Pending == null, "Restore scope leaked.");
    });
    private static void EnvironmentRetry() => Isolated((blocked, repaired) => {
        var request = Request(); var saved = Saved(request); saved.Environments.Add("older-runtime");
        saved.Units["simplex"] = JsonSerializer.SerializeToElement(new NumericalMethods.SimplexCheckpoint(new[] { new[] { 1d }, new[] { 2d } }, new[] { -999d, -998d }, 0), BackupSession.Json);
        string original = BackupSession.Pack(saved);
        using (BackupSession.Restore(saved)) {
            Fails(request);
            Assert(BackupSession.Pack(saved) == original, "Failed publication consumed environment transition.");
            Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
            using var retry = BackupSession.Begin(request);
            Assert(retry.EnvironmentChanged, "Retry lost environment-change flag.");
            int evaluations = 0;
            var result = NumericalMethods.Minimize(x => { evaluations++; return x[0] * x[0]; }, new[] { 1d }, new[] { -10d }, new[] { 10d }, maximumIterations: 0, backup: retry, checkpointKey: "simplex");
            Assert(evaluations == 2 && result.Value == 1, "Restored simplex objective values were not reevaluated.");
            Assert(saved.Environments.SequenceEqual(new[] { "older-runtime", BenchmarkEnvironment.Hash }), "Environment history appended more than once.");
        }
    });
    private static void LateFailure() => Isolated((blocked, repaired) => {
        var request = Request(); var saved = Saved(request); saved.Environments.Add("older-runtime");
        string original = BackupSession.Pack(saved);
        Directory.CreateDirectory(repaired);
        string obstruction = Path.Combine(repaired, "MVS_Backups.zip"); Directory.CreateDirectory(obstruction);
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
        using (BackupSession.Restore(saved)) {
            BackupPublicationFault.ExpectDirectoryCollision(() => { using var ignored = BackupSession.Begin(request); }, obstruction);
            Assert(ReferenceEquals(BackupSession.Pending, saved) && BackupSession.Pack(saved) == original, "Late failure consumed restore metadata.");
            string[] installed = Directory.GetFiles(repaired, "*.mvsbackup");
            Assert(installed.Length > 0, "Fixture did not reach partial disk publication.");
            Assert(installed.Select(p => BackupSession.Decode(File.ReadAllBytes(p))).All(d => d.Id == saved.Id && d.Units.ContainsKey("retained")), "Installed checkpoint lost identity or units.");
            Directory.Delete(obstruction); // Empty directory created only by this test.
            using var retry = BackupSession.Begin(request);
            Assert(retry.WasRestored && retry.EnvironmentChanged && retry.Try<int[]>("retained", out _), "Retry after partial publication lost restored state.");
        }
        Assert(File.Exists(obstruction), "Retry did not publish collection archive.");
    });
    private static void ScopeExit() => Isolated((blocked, repaired) => {
        var request = Request(); var saved = Saved(request);
        using (BackupSession.Restore(saved)) Fails(request);
        Assert(BackupSession.Pending == null, "Failed restore scope leaked pending selection.");
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
        using var fresh = BackupSession.Begin(request);
        Assert(!fresh.WasRestored && !fresh.Try<int[]>("retained", out _), "Unrelated run inherited failed restore.");
    });
    private static void FreshFailure() => Isolated((blocked, repaired) => {
        var request = Request(); Fails(request);
        Assert(BackupSession.Pending == null, "Fresh failure invented pending restore.");
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
        using var fresh = BackupSession.Begin(request);
        Assert(!fresh.WasRestored && !ReferenceEquals(fresh, BackupSession.Disabled), "Fresh failure leaked active session.");
    });
    private static void MismatchAndDisabled() => Isolated((blocked, repaired) => {
        var request = Request(); var saved = Saved(request);
        using (BackupSession.Restore(saved)) {
            bool mismatch = false; try { using var ignored = BackupSession.Begin(request with { Seed = 99 }); } catch (InvalidDataException) { mismatch = true; }
            Assert(mismatch && ReferenceEquals(BackupSession.Pending, saved), "Request mismatch consumed restore.");
            Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1");
            using (var disabled = BackupSession.Begin(request)) Assert(ReferenceEquals(disabled, BackupSession.Disabled), "Disabled behavior changed.");
            Assert(ReferenceEquals(BackupSession.Pending, saved), "Disabled Begin consumed restore.");
            Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null); Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", repaired);
            using var retry = BackupSession.Begin(request); Assert(retry.WasRestored, "Retry after mismatch/disabled lost restore.");
        }
    });
}
