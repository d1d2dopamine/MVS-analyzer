using System.Globalization;
using System.Reflection;

namespace MvsAnalyzer;

internal static class ScientificTables
{
    public static string Csv<T>(IEnumerable<T> rows)
    {
        PropertyInfo[] columns = typeof(T).GetProperties().Where(p => p.PropertyType == typeof(string) || p.PropertyType.IsPrimitive).ToArray();
        string Value(object? value) => value switch {
            null => "", double d => double.IsFinite(d) ? d.ToString("R", CultureInfo.InvariantCulture) : "",
            string s => "\"" + ((s.Length > 0 && "=+-@\t\r".Contains(s[0])) ? "'" + s : s).Replace("\"", "\"\"") + "\"",
            IFormattable f => f.ToString(null, CultureInfo.InvariantCulture), _ => value.ToString() ?? "" };
        return string.Join(",", columns.Select(p => p.Name)) + "\n" + string.Join("\n", rows.Select(r => string.Join(",", columns.Select(p => Value(p.GetValue(r)))))) + "\n";
    }
    public static void WriteManifest<T>(string folder, string kind, T settings, string inputHash)
    {
        var files = Directory.GetFiles(folder).Where(p => Path.GetFileName(p) != "run_manifest.json")
            .Select(p => new { FileName = Path.GetFileName(p), SizeBytes = new FileInfo(p).Length, sha256 = OutputExporter.HashFile(p) }).ToArray();
        ScientificJson.Write(Path.Combine(folder, "run_manifest.json"), new { schemaVersion = 2, executionEnvironment = new { description = Benchmarking.BenchmarkEnvironment.Describe(), fingerprint = Benchmarking.BenchmarkEnvironment.Hash, replayScope = Benchmarking.BenchmarkEnvironment.Scope }, application = "MVS Analyzer", version = ReleaseInfo.Version,
            engineVersion = ReleaseInfo.EngineVersion, kind, created = DateTimeOffset.UtcNow, runId = kind + "_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture),
            configuration = settings, inputData = new { sha256 = inputHash }, files,
            warning = "Model-specific report. Consult its convergence, assumptions and uncertainty; completion is not scientific certification." });
    }
}
