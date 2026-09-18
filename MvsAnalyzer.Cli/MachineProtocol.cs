using System.Text.Json;

namespace MvsAnalyzer.Cli;

internal static class CliMachineContext
{
    private static readonly List<object> diagnostics = new();
    public static bool Enabled { get; set; }
    public static bool Quiet { get; set; }
    public static string? OutputDirectory { get; private set; }
    public static string? RunId { get; private set; }

    public static void Reset(bool enabled, bool quiet)
    {
        Enabled = enabled;
        Quiet = quiet || enabled;
        OutputDirectory = null;
        RunId = null;
        diagnostics.Clear();
    }

    public static void RecordOutput(string? directory, string? runId = null)
    {
        if (!string.IsNullOrWhiteSpace(directory)) OutputDirectory = Path.GetFullPath(directory);
        if (!string.IsNullOrWhiteSpace(runId)) RunId = runId;
    }

    public static void Diagnostic(string level, string code, string message) =>
        diagnostics.Add(new { level, code, message });

    public static IReadOnlyList<object> Diagnostics => diagnostics;
}

internal static class CliMachineProtocol
{
    public const string Schema = "mvs-cli-result/v1";

    public static void Write(TextWriter writer, string command, int exitCode, Exception? error = null)
    {
        string? folder = CliMachineContext.OutputDirectory;
        string? manifest = FindManifest(folder);
        string? runId = CliMachineContext.RunId ?? ReadRunId(manifest);
        object[] artifacts = EnumerateArtifacts(folder);
        string status = exitCode switch { 0 => "completed", 2 => "diagnostic", _ => "error" };
        object? errorPayload = error != null
            ? new { type = error.GetType().Name, message = error.Message }
            : exitCode == 1 ? new { type = "CommandFailure", message = "Command failed; see stderr for human-readable details." } : null;
        var payload = new
        {
            schemaVersion = Schema,
            status,
            command,
            exitCode,
            runId,
            outputDirectory = folder,
            appVersion = ReleaseInfo.Version,
            applicationVersion = ReleaseInfo.Version,
            engineVersion = ReleaseInfo.EngineVersion,
            stateSchema = ReleaseInfo.StateSchema,
            cliProtocol = new { name = "mvs-cli", major = 1, capabilities = new[] { "calibrate", "analyze", "state-check", "variance", "melsm", "estimation", "benchmark", "resume", "env", "version", "json-result-v1" } },
            transport = ColabCompatibility.Wire,
            formulaVersion = OutputExporter.FormulaVersion,
            formulaHash = OutputExporter.FormulaHash,
            executionEnvironment = new { description = Benchmarking.BenchmarkEnvironment.Describe(), fingerprint = Benchmarking.BenchmarkEnvironment.Hash, replayScope = Benchmarking.BenchmarkEnvironment.Scope },
            manifestPath = manifest,
            artifacts,
            diagnostics = CliMachineContext.Diagnostics,
            error = errorPayload
        };
        writer.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
        writer.Flush();
    }

    private static string? FindManifest(string? folder)
    {
        if (string.IsNullOrWhiteSpace(folder) || !Directory.Exists(folder)) return null;
        foreach (string name in new[] { "run_manifest.json", "benchmark_manifest.json" })
        {
            string path = Path.Combine(folder, name);
            if (File.Exists(path)) return Path.GetFullPath(path);
        }
        return null;
    }

    private static string? ReadRunId(string? manifest)
    {
        if (manifest == null) return null;
        try
        {
            using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(manifest));
            return doc.RootElement.TryGetProperty("runId", out JsonElement value) && value.ValueKind == JsonValueKind.String
                ? value.GetString()
                : null;
        }
        catch (JsonException) { return null; }
        catch (IOException) { return null; }
    }

    private static object[] EnumerateArtifacts(string? folder)
    {
        if (string.IsNullOrWhiteSpace(folder) || !Directory.Exists(folder)) return Array.Empty<object>();
        try
        {
            return Directory.EnumerateFiles(folder, "*", SearchOption.TopDirectoryOnly)
                .OrderBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase)
                .Select(path => (object)new
                {
                    name = Path.GetFileName(path),
                    path = Path.GetFullPath(path),
                    sizeBytes = new FileInfo(path).Length,
                    sha256 = OutputExporter.HashFile(path)
                }).ToArray();
        }
        catch (IOException) { return Array.Empty<object>(); }
        catch (UnauthorizedAccessException) { return Array.Empty<object>(); }
    }
}
