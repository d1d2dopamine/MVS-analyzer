using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace MvsAnalyzer;

/// <summary>
/// Verifies saved runs. Hashes prove integrity (nothing was edited after the run);
/// the append-only journal is what makes hidden or deleted runs visible, which is
/// the part that actually exposes result shopping.
/// </summary>
internal static class RunAuditor
{
    public const string Fail = "fail";
    public const string Warn = "warn";
    public const string Ok = "ok";

    private static string Folder => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer");
    public static string JournalPath => Path.Combine(Folder, "run_journal.jsonl");

    private static string HashText(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    private static string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    // ---------- append-only journal ----------

    /// <summary>
    /// Appends one tamper-evident line. Every entry stores the SHA-256 of the previous
    /// line, so deleting or rewriting an inconvenient run breaks the chain.
    /// </summary>
    public static void AppendJournal(string runId, string folder, string datasetHash, AppSettings settings, int repetitions, string candidateSet)
    {
        using var mutex = new Mutex(false, "MVSAnalyzerJournalV2");
        bool acquired;
        try { acquired = mutex.WaitOne(TimeSpan.FromSeconds(10)); } catch (AbandonedMutexException) { acquired = true; }
        if (!acquired) throw new IOException("The run journal is busy.");
        try
        {
            Directory.CreateDirectory(Folder);
            string previous = "genesis";
            if (File.Exists(JournalPath))
            {
                string[] lines = File.ReadAllLines(JournalPath).Where(line => line.Trim().Length > 0).ToArray();
                if (lines.Length > 0) previous = HashText(lines[^1]);
            }
            var entry = new
            {
                runId,
                created = DateTimeOffset.Now,
                folder,
                datasetHash,
                seed = settings.CalibrationSeed,
                effect = settings.CalibrationEffect,
                scenario = settings.SimulationScenario,
                repetitions,
                alpha = settings.Alpha,
                outlierRate = settings.OutlierRate,
                missingRate = settings.MissingRate,
                minMeasurements = settings.MinMeasurements,
                candidateSet,
                engineVersion = AnalysisEngine.EngineVersion,
                formulaHash = OutputExporter.FormulaHash,
                previous
            };
            File.AppendAllText(JournalPath, JsonSerializer.Serialize(entry) + "\n", new UTF8Encoding(false));
        }
        finally { mutex.ReleaseMutex(); }
    }

    private static List<JournalEntry> ReadJournal(List<AuditFinding> findings)
    {
        var entries = new List<JournalEntry>();
        if (!File.Exists(JournalPath)) return entries;
        string[] lines = File.ReadAllLines(JournalPath).Where(line => line.Trim().Length > 0).ToArray();
        string expected = "genesis";
        for (int i = 0; i < lines.Length; i++)
        {
            JsonElement root;
            try { root = JsonDocument.Parse(lines[i]).RootElement; }
            catch
            {
                findings.Add(new AuditFinding(Fail, "JOURNAL_UNREADABLE", $"Journal line {i + 1} is not valid JSON.", $"Строка журнала {i + 1} повреждена."));
                return entries;
            }
            string previous = Text(root, "previous");
            if (previous != expected)
                findings.Add(new AuditFinding(Fail, "JOURNAL_BROKEN", $"Journal chain breaks at line {i + 1}: an earlier run was deleted or edited.", $"Цепочка журнала обрывается на строке {i + 1}: более ранний прогон удалён или изменён."));
            expected = HashText(lines[i]);
            entries.Add(new JournalEntry(Text(root, "runId"), Text(root, "folder"), Text(root, "datasetHash"), Text(root, "candidateSet"),
                Number(root, "seed"), Number(root, "effect"), Text(root, "scenario"), Number(root, "alpha")));
        }
        return entries;
    }

    // ---------- folder audit ----------

    public static AuditReport Audit(string root)
    {
        if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root)) throw new DirectoryNotFoundException("Folder was not found: " + root);
        var runs = new List<RunAudit>();
        var global = new List<AuditFinding>();

        foreach (string manifestPath in Directory.EnumerateFiles(root, "run_manifest.json", SearchOption.AllDirectories).OrderBy(x => x))
            runs.Add(AuditRun(manifestPath));

        if (runs.Count == 0)
            global.Add(new AuditFinding(Warn, "NO_RUNS", "No run_manifest.json was found in this folder.", "В этой папке не найдено ни одного run_manifest.json."));

        // Results written without a manifest cannot be verified at all.
        foreach (string csv in Directory.EnumerateFiles(root, "results.csv", SearchOption.AllDirectories))
            if (!File.Exists(Path.Combine(Path.GetDirectoryName(csv)!, "run_manifest.json")))
                global.Add(new AuditFinding(Warn, "ORPHAN_RESULTS", "results.csv without a manifest: " + csv, "results.csv без манифеста: " + csv));

        CompareRunsOnSameData(runs, global);

        List<JournalEntry> journal = ReadJournal(global);
        CompareWithJournal(runs, journal, global);

        string verdict = global.Concat(runs.SelectMany(r => r.Findings)).Any(f => f.Severity == Fail) ? Fail
            : global.Concat(runs.SelectMany(r => r.Findings)).Any(f => f.Severity == Warn) ? Warn : Ok;
        return new AuditReport(runs, global, verdict, journal.Count);
    }

    private static RunAudit AuditRun(string manifestPath)
    {
        string folder = Path.GetDirectoryName(manifestPath)!;
        var findings = new List<AuditFinding>();
        JsonElement root;
        try { using JsonDocument document = JsonDocument.Parse(File.ReadAllText(manifestPath)); root = document.RootElement.Clone(); }
        catch
        {
            findings.Add(new AuditFinding(Fail, "MANIFEST_UNREADABLE", "run_manifest.json is damaged.", "Файл run_manifest.json повреждён."));
            return new RunAudit(folder, Path.GetFileName(folder), "", "", "", "", "", 0, 0, "", 0, "", findings);
        }

        string runId = Text(root, "runId");
        string engineVersion = Text(root, "engineVersion");
        JsonElement project = Child(root, "project"), formula = Child(root, "formula"), calibration = Child(root, "calibration"), input = Child(root, "inputData");
        string datasetHash = Text(input, "sha256");
        string formulaHash = Text(formula, "hash");
        string candidateSet = root.TryGetProperty("candidateSet", out JsonElement set) && set.ValueKind == JsonValueKind.Array
            ? string.Join(", ", set.EnumerateArray().Select(x => x.GetString())) : "";

        // 1. Was any recorded file changed after the run?
        if (root.TryGetProperty("files", out JsonElement files) && files.ValueKind == JsonValueKind.Array)
            foreach (JsonElement file in files.EnumerateArray())
            {
                string name = Text(file, "FileName"), recorded = Text(file, "sha256");
                if (string.IsNullOrWhiteSpace(name) || name != Path.GetFileName(name) || name.Contains('\\'))
                { findings.Add(new AuditFinding(Fail, "UNSAFE_FILE_PATH", "Unsafe path in manifest.", "Небезопасный путь в манифесте.")); continue; }
                string path = Path.Combine(folder, name);
                if (!File.Exists(path)) { findings.Add(new AuditFinding(Fail, "FILE_MISSING", "Recorded file is missing: " + name, "Записанный файл отсутствует: " + name)); continue; }
                string actual = HashFile(path);
                if (!string.Equals(actual, recorded, StringComparison.OrdinalIgnoreCase))
                    findings.Add(new AuditFinding(Fail, "FILE_MODIFIED", "File was edited after the run: " + name, "Файл изменён после прогона: " + name));
            }
        else findings.Add(new AuditFinding(Warn, "NO_FILE_LIST", "The manifest contains no file hashes.", "В манифесте нет хешей файлов."));

        // 2. Was the scoring formula itself altered?
        if (formulaHash.Length > 0 && !string.Equals(formulaHash, OutputExporter.FormulaHash, StringComparison.OrdinalIgnoreCase))
            findings.Add(new AuditFinding(Warn, "FORMULA_CHANGED", "Historical result: the formula differs from this release; this is not by itself evidence of tampering.", "Исторический результат: другая версия формулы сама по себе не доказывает подмену."));

        // 3. Can the run be tied to specific input data?
        if (datasetHash.Length == 0)
            findings.Add(new AuditFinding(Warn, "NO_INPUT_HASH", "This run has no input-data hash and cannot be tied to a dataset.", "У прогона нет хеша входных данных, привязать его к датасету нельзя."));

        if (engineVersion.Length > 0 && engineVersion != AnalysisEngine.EngineVersion)
            findings.Add(new AuditFinding(Warn, "ENGINE_DIFFERS", $"Produced by engine {engineVersion}, current engine is {AnalysisEngine.EngineVersion}.", $"Создан движком {engineVersion}, текущий движок {AnalysisEngine.EngineVersion}."));

        if (findings.Count == 0) findings.Add(new AuditFinding(Ok, "RUN_INTACT", "All recorded files match their hashes.", "Все записанные файлы совпадают со своими хешами."));

        return new RunAudit(folder, runId, Text(project, "name"), Text(root, "dataset"), datasetHash, engineVersion, formulaHash,
            (int)Number(calibration, "seed"), Number(calibration, "effectMultiplier"), Text(calibration, "scenario"),
            (int)Number(calibration, "repetitions"), candidateSet, findings);
    }

    /// <summary>Several runs on identical input data: this is where result shopping shows up.</summary>
    private static void CompareRunsOnSameData(List<RunAudit> runs, List<AuditFinding> global)
    {
        foreach (var group in runs.Where(r => r.DatasetHash.Length > 0).GroupBy(r => r.DatasetHash))
        {
            var list = group.ToList();
            if (list.Count < 2) continue;
            global.Add(new AuditFinding(Ok, "SAME_DATA_RUNS", $"{list.Count} runs use the same input data.", $"{list.Count} прогонов выполнены на одних и тех же входных данных."));

            var settings = list.Select(r => $"seed={r.Seed}; effect={r.Effect:0.###}; scenario={r.Scenario}; repetitions={r.Repetitions}").Distinct().ToList();
            if (settings.Count > 1)
                global.Add(new AuditFinding(Warn, "SETTINGS_VARIED",
                    "Calibration settings were changed between runs on the same data: " + string.Join(" | ", settings),
                    "Настройки калибровки менялись между прогонами на одних данных: " + string.Join(" | ", settings)));

            var sets = list.Select(r => r.CandidateSet).Distinct().ToList();
            if (sets.Count > 1)
                global.Add(new AuditFinding(Fail, "CANDIDATE_SET_UNSTABLE",
                    "The same data produced different Candidate Sets: " + string.Join(" | ", sets.Select(s => s.Length == 0 ? "(empty)" : s)),
                    "Одни и те же данные дали разные наборы кандидатов: " + string.Join(" | ", sets.Select(s => s.Length == 0 ? "(пусто)" : s))));
        }
    }

    /// <summary>Runs that the journal remembers but that are no longer on disk.</summary>
    private static void CompareWithJournal(List<RunAudit> runs, List<JournalEntry> journal, List<AuditFinding> global)
    {
        if (journal.Count == 0) return;
        var present = runs.Select(r => r.RunId).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var datasets = runs.Select(r => r.DatasetHash).Where(x => x.Length > 0).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var hidden = journal.Where(e => e.DatasetHash.Length > 0 && datasets.Contains(e.DatasetHash) && !present.Contains(e.RunId)).ToList();
        if (hidden.Count > 0)
            global.Add(new AuditFinding(Fail, "RUN_HIDDEN",
                $"The journal records {hidden.Count} run(s) on this data that are absent from the folder: " + string.Join(", ", hidden.Select(e => e.RunId)),
                $"Журнал содержит {hidden.Count} прогон(ов) на этих данных, которых нет в папке: " + string.Join(", ", hidden.Select(e => e.RunId))));
    }

    // ---------- small JSON helpers ----------

    private static JsonElement Child(JsonElement parent, string name) => parent.ValueKind == JsonValueKind.Object && parent.TryGetProperty(name, out JsonElement value) ? value : default;
    private static string Text(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out JsonElement value)) return "";
        return value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : value.ValueKind == JsonValueKind.Number ? value.ToString() : "";
    }
    private static double Number(JsonElement parent, string name)
        => parent.ValueKind == JsonValueKind.Object && parent.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.Number ? value.GetDouble() : 0;
}

internal sealed record JournalEntry(string RunId, string Folder, string DatasetHash, string CandidateSet, double Seed, double Effect, string Scenario, double Alpha);
