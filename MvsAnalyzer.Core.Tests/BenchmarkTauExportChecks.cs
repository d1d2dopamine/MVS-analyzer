using System.Reflection;
using System.Text;
using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

// Fabricated export fixtures only: these checks never run calibration or simulation.
internal static class BenchmarkTauExportChecks
{
    public static readonly (string Name, Action Run)[] All =
    {
        ("Benchmark tau exports append identity to logical CSV rows without changing values", CsvIdentity),
        ("Benchmark tau exports preserve legacy values and identify unknown provenance", Legacy),
        ("Benchmark undefined tau exports JSON null and diagnostic CSV reason", Undefined),
        ("Benchmark tau export surfaces reject mismatched identity", Mismatch)
    };
    private static void Assert(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }
    private static BenchmarkOutcome Fixture(string? method, bool undefined = false) => new()
    {
        Profile = new("export-only", "Test", "Test", "", "", 2, 1, 100, 1, 2),
        Seed = 54, RunId = "synthetic_export_only", StartedUtc = DateTime.UnixEpoch, FinishedUtc = DateTime.UnixEpoch,
        Conditions = new(), DeterminismFirst = "retained-first", DeterminismSecond = "retained-second",
        LockedPilotMetric = new(), Threads = 0, Notes = new(), Overall = "no-go", StabilityMethod = method,
        Verdicts = new() { new("C", "Question, \"quoted\"\r\nsecond line", "", "retained threshold", "", "0.5", "fail") },
        Stability = new()
        {
            Tau = undefined ? Array.Empty<double>() : new[] { .5 }, Repeats = undefined ? 0 : 1,
            TopOneMatches = undefined ? 0 : 1, Failed = undefined ? 1 : 0, TopMetricCounts = new int[12],
            ReplicationRecords = new[] { new BenchmarkRunner.StabilityCheckpoint(undefined ? double.NaN : .5,
                !undefined, undefined ? -1 : 0, undefined,
                undefined ? "undefined tau: zero denominator, \"ties\"\r\nretained reason" : "", null, true, method) }
        }
    };
    // Independent RFC-style logical-record parser, deliberately not Split('\n')/Split(',').
    private static List<string[]> Rows(string text)
    {
        var rows = new List<string[]>(); var cells = new List<string>(); var cell = new StringBuilder(); bool quoted = false;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            if (c == '"')
            {
                if (quoted && i + 1 < text.Length && text[i + 1] == '"') { cell.Append('"'); i++; }
                else quoted = !quoted;
            }
            else if (c == ',' && !quoted) { cells.Add(cell.ToString()); cell.Clear(); }
            else if ((c == '\n' || c == '\r') && !quoted)
            {
                if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                cells.Add(cell.ToString()); cell.Clear(); rows.Add(cells.ToArray()); cells.Clear();
            }
            else cell.Append(c);
        }
        Assert(!quoted, "Unterminated CSV fixture/output.");
        if (cell.Length != 0 || cells.Count != 0) { cells.Add(cell.ToString()); rows.Add(cells.ToArray()); }
        return rows;
    }
    private static void CheckCsv(string raw, BenchmarkOutcome outcome)
    {
        string wrapped = BenchmarkReport.WithStabilityIdentity(raw, outcome);
        var before = Rows(raw); var after = Rows(wrapped);
        Assert(before.Count == after.Count, "Identity changed logical row count.");
        for (int i = 0; i < before.Count; i++)
        {
            Assert(after[i].Length == before[i].Length + 3, "Identity column count differs.");
            Assert(after[i].Take(before[i].Length).SequenceEqual(before[i]), "An original CSV field changed.");
            string[] expected = i == 0 ? new[] { "stability_method", "stability_method_hash", "comparability_key" }
                : new[] { outcome.StabilityMethod == null ? "kendall-legacy-v1" : "kendall-tau-b-v2",
                    BenchmarkStabilityMethod.HashFor(outcome.StabilityMethod), BenchmarkStabilityMethod.ComparisonKey(outcome.StabilityMethod) };
            Assert(after[i].TakeLast(3).SequenceEqual(expected), "Missing or wrong identity on a logical row.");
        }
    }
    private static void CsvIdentity()
    {
        foreach (string? marker in new[] { (string?)null, "kendall-tau-b-v2" })
        {
            var outcome = Fixture(marker);
            foreach (string name in new[] { "SummaryCsv", "ReplicationsCsv", "ReplicationProceduresCsv", "ReplicationMetricsCsv", "MetricsCsv", "ChoicesCsv", "StabilityCsv", "StabilityReplicationsCsv", "VerdictsCsv" })
            {
                var method = typeof(BenchmarkReport).GetMethod(name, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!;
                CheckCsv((string)method.Invoke(null, new object[] { outcome })!, outcome);
            }
            CheckCsv("value,error\r\n0.012345678901234567,\"a,\"\"quoted\"\"\r\nb\"\r\n-2,plain", outcome);
            CheckCsv("value,error\n", outcome);
            Assert(BenchmarkReport.WithStabilityIdentity("", outcome) == "", "Empty CSV fabricated a row.");
        }
    }
    private static void Legacy()
    {
        var outcome = Fixture(null);
        string before = JsonSerializer.Serialize(outcome, BackupSession.Json);
        using var manifest = JsonDocument.Parse(BenchmarkReport.Manifest(outcome, new(), new()));
        var root = manifest.RootElement;
        Assert(root.GetProperty("stabilityMethod").GetString() == "kendall-legacy-v1", "Unmarked result relabeled as corrected.");
        Assert(root.GetProperty("stabilityMethodProvenance").GetString() == "legacy_unversioned", "Unknown original provenance hidden.");
        Assert(root.GetProperty("overall").GetString() == "no-go", "Historical overall changed.");
        Assert(root.GetProperty("stability").GetProperty("medianTau").GetDouble() == .5, "Historical tau recalculated.");
        Assert(BenchmarkReport.StabilityIdentityText(outcome).Contains("original executable identity was not recorded"), "Sidecar claims original identity.");
        Assert(JsonSerializer.Serialize(outcome, BackupSession.Json) == before && outcome.Verdicts[0].Result == "fail", "Export mutated historical outcome/verdict.");
        using var current = JsonDocument.Parse(BenchmarkReport.Manifest(Fixture("kendall-tau-b-v2"), new(), new()));
        Assert(root.GetProperty("comparabilityKey").GetString() != current.RootElement.GetProperty("comparabilityKey").GetString(), "Legacy/current comparison keys collide.");
    }
    private static void Undefined()
    {
        var outcome = Fixture("kendall-tau-b-v2", true);
        using var manifest = JsonDocument.Parse(BenchmarkReport.Manifest(outcome, new(), new()));
        Assert(manifest.RootElement.GetProperty("stability").GetProperty("medianTau").ValueKind == JsonValueKind.Null, "Undefined tau is not JSON null.");
        var rows = Rows(BenchmarkReport.WithStabilityIdentity(BenchmarkReport.StabilityReplicationsCsv(outcome), outcome));
        Assert(rows.Count == 2 && rows[1][1] == "failed" && rows[1][4] == "", "Undefined tau fabricated a value or lost failed row.");
        Assert(rows[1][3] == "undefined tau: zero denominator, \"ties\"\r\nretained reason", "Undefined tau lost its exact reason.");
        Assert(rows[1].Skip(5).Take(3).All(string.IsNullOrEmpty), "Failed stability contributed top-one data.");
    }
    private static void Mismatch()
    {
        var outcome = Fixture("kendall-tau-b-v2");
        outcome.Stability.ReplicationRecords![0] = outcome.Stability.ReplicationRecords[0] with { StabilityMethod = null };
        foreach (Action export in new Action[] { () => BenchmarkReport.Manifest(outcome, new(), new()), () => BenchmarkReport.WithStabilityIdentity("value\n1\n", outcome), () => BenchmarkReport.StabilityIdentityText(outcome) })
        {
            bool rejected = false; try { export(); } catch (InvalidDataException) { rejected = true; }
            Assert(rejected, "Mixed provenance reached an export surface.");
        }
    }
}
