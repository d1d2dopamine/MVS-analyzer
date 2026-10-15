using System.IO.Compression;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

internal static class ApplicationDataChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("Appdata unset preserves each legacy folder option without writes", Legacy),
        ("Appdata override bounds journal plugins settings and backup paths", Override),
        ("Appdata invalid override rejects instead of falling back", Invalid),
        ("Explicit backup directory retains precedence over appdata override", BackupPrecedence)
    };

    private static void Assert(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Isolated(Action<string> action)
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-appdata-test-" + Guid.NewGuid().ToString("N"));
        string? originalRoot = Environment.GetEnvironmentVariable(ApplicationDataPaths.OverrideVariable);
        string? originalBackup = Environment.GetEnvironmentVariable("MVS_BACKUP_DIR");
        try
        {
            Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, root);
            Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", null);
            action(root);
        }
        finally
        {
            Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, originalRoot);
            Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", originalBackup);
            if (Directory.Exists(root)) Directory.Delete(root, true);
        }
    }

    private static void Legacy() => Isolated(_ =>
    {
        Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, null);
        // These are string lookups only: never load/save/list anything in real appdata.
        foreach (var option in new[] { Environment.SpecialFolderOption.None, Environment.SpecialFolderOption.DoNotVerify })
            Assert(ApplicationDataPaths.GetLocalApplicationData(option) ==
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData, option),
                "Unset override changed legacy folder resolution for " + option);
    });

    private static void Override() => Isolated(root =>
    {
        Assert(ApplicationDataPaths.GetLocalApplicationData() == root, "Explicit root was not selected.");
        Assert(ApplicationDataPaths.GetLocalApplicationData(Environment.SpecialFolderOption.DoNotVerify) == root,
            "Explicit root depended on legacy folder options.");
        string folder = Path.Combine(root, "MVS_Analyzer");
        string journal = Path.Combine(folder, "run_journal.jsonl");
        Assert(RunAuditor.JournalPath == journal, "Journal escaped the override.");
        Assert(BackupSession.Folder == Path.Combine(folder, "MVS_Backups"), "Default backup escaped the override.");
        Assert(!Directory.Exists(root), "Resolving paths created directories.");

        new AppSettings { CalibrationSeed = 1973 }.Save();
        Assert(File.Exists(Path.Combine(folder, "settings.txt")), "Settings were not saved inside the override.");
        Assert(AppSettings.Load().CalibrationSeed == 1973, "Settings were not loaded from the override.");
        new BenchmarkOptions { Seed = 1974 }.Save();
        Assert(File.Exists(Path.Combine(folder, "benchmark.txt")), "Benchmark settings escaped the override.");
        Assert(BenchmarkOptions.Load().Seed == 1974, "Benchmark settings were not loaded from the override.");

        RunAuditor.AppendJournal("bounded-native-test", folder, "synthetic", new AppSettings(), 100, "");
        Assert(File.ReadAllLines(journal).Length == 1, "Expected one bounded journal entry.");
        Assert(File.Exists(journal + ".lock"), "Journal lock escaped the override.");

        string archive = Path.Combine(root, "fixture.zip");
        using (var zip = ZipFile.Open(archive, ZipArchiveMode.Create))
        using (var writer = new StreamWriter(zip.CreateEntry("plugin.json").Open()))
            writer.Write("{\"id\":\"bounded-test\",\"name\":\"Bounded fixture\",\"type\":\"visualization\"}");
        PluginManifest plugin = PluginManager.Install(archive);
        Assert(plugin.Folder == Path.Combine(folder, "plugins", "bounded-test"), "Plugin install escaped the override.");
        Assert(File.Exists(Path.Combine(plugin.Folder, "plugin.json")), "Plugin manifest was not installed.");
        Assert(PluginManager.ListInstalled().Single().Id == "bounded-test", "Plugin list did not read the override.");
    });

    private static void Rejected(Action action)
    {
        try { action(); }
        catch (DirectoryNotFoundException) { return; }
        throw new Exception("Invalid appdata override was accepted.");
    }

    private static void Invalid() => Isolated(root =>
    {
        // .NET may map an empty environment value to unset; test explicit empty
        // input directly, and whitespace/relative values through the real environment.
        Rejected(() => ApplicationDataPaths.ResolveLocalApplicationData(""));
        foreach (string invalid in new[] { " ", ".", "relative-data", "../data" })
        {
            Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, invalid);
            Rejected(() => ApplicationDataPaths.GetLocalApplicationData());
            Rejected(() => { _ = RunAuditor.JournalPath; });
            Rejected(() => AppSettings.Load());
            Rejected(() => new AppSettings().Save());
            Rejected(() => PluginManager.ListInstalled());
            Rejected(() => { _ = BackupSession.Folder; });
        }
        if (OperatingSystem.IsWindows())
            foreach (string invalid in new[] { "C:relative", @"\root-relative" })
                Rejected(() => ApplicationDataPaths.ResolveLocalApplicationData(invalid));
        Assert(!Directory.Exists(root), "Invalid path checks wrote to the fixture root.");
    });

    private static void BackupPrecedence() => Isolated(root =>
    {
        string backup = Path.Combine(root, "explicit-backups");
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", backup);
        Environment.SetEnvironmentVariable(ApplicationDataPaths.OverrideVariable, "invalid-relative-root");
        Assert(BackupSession.Folder == backup, "Explicit MVS_BACKUP_DIR lost its existing precedence.");
        Assert(!Directory.Exists(root), "Backup path resolution created directories.");
    });
}
