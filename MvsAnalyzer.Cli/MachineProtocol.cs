using System.Text.Json;

namespace MvsAnalyzer.Cli;

internal static class CliMachineContext
{
    private static readonly List<object> diagnostics = new();
    public static bool Enabled { get; set; }
    public static bool Quiet { get; set; }
    public static string? OutputDirectory { get; private set; }
    public static string? RunId { get; private set; }
    internal sealed record WrittenArtifact(string name, string path, long sizeBytes, string sha256);
    private static readonly List<WrittenArtifact> written = new();
    private static readonly List<string> unverified = new();
    internal static string? EmissionDirectory { get; private set; }
    internal static string? AttemptedPath { get; private set; }
    internal static string? EmissionRunId { get; private set; }

    // This records successful individual writes, not an atomic multi-file commit.
    internal static void BeginOutput(string directory, string? runId = null)
    {
        if (!Enabled) return;
        EmissionDirectory = Path.GetFullPath(directory);
        EmissionRunId = runId;
        AttemptedPath = null;
        written.Clear(); unverified.Clear();
    }
    internal static void ObserveOutput(string path, bool completed)
    {
        if (!Enabled) return;
        path = Path.GetFullPath(path);
        if (!completed) { written.RemoveAll(a => a.path == path); unverified.RemoveAll(p => p == path); AttemptedPath = path; return; }
        written.RemoveAll(a => a.path == path);
        unverified.RemoveAll(p => p == path);
        try
        {
            written.Add(new(Path.GetFileName(path), path, new FileInfo(path).Length, OutputExporter.HashFile(path)));
        }
        catch (IOException) { unverified.Add(path); }
        catch (UnauthorizedAccessException) { unverified.Add(path); }
        AttemptedPath = null;
    }
    internal static void WriteOutput(string path, Action write)
    {
        ObserveOutput(path, false); write(); ObserveOutput(path, true);
    }
    internal static WrittenArtifact[] VerifiedPartialArtifacts()
    {
        var valid = new List<WrittenArtifact>();
        foreach (WrittenArtifact item in written)
        {
            try
            {
                if (new FileInfo(item.path).Length == item.sizeBytes && OutputExporter.HashFile(item.path) == item.sha256)
                { valid.Add(item); continue; }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            unverified.Add(item.path);
        }
        return valid.OrderBy(a => a.name, StringComparer.OrdinalIgnoreCase).ToArray();
    }
    internal static string[] UnverifiedPaths => unverified.Distinct(StringComparer.Ordinal).ToArray();

    public static void Reset(bool enabled, bool quiet)
    {
        Enabled = enabled;
        Quiet = quiet || enabled;
        OutputDirectory = null;
        RunId = null;
        diagnostics.Clear();
        EmissionDirectory = null; EmissionRunId = null; AttemptedPath = null;
        written.Clear(); unverified.Clear();
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
        bool partial = exitCode == 1 && CliMachineContext.EmissionDirectory != null;
        // Observed commands own only their successful writes, even on success.
        // Untracked legacy commands retain their existing directory-listing contract.
        bool tracked = CliMachineContext.EmissionDirectory != null;
        string? folder = tracked ? CliMachineContext.EmissionDirectory : CliMachineContext.OutputDirectory;
        object[] artifacts = tracked ? CliMachineContext.VerifiedPartialArtifacts().Cast<object>().ToArray() : EnumerateArtifacts(folder);
        string? manifest = tracked
            ? artifacts.Cast<CliMachineContext.WrittenArtifact>().FirstOrDefault(a => a.name is "run_manifest.json" or "benchmark_manifest.json")?.path
            : FindManifest(folder);
        string? runId = partial ? CliMachineContext.EmissionRunId : CliMachineContext.RunId ?? ReadRunId(manifest);
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
            execution = new { completed = exitCode is 0 or 2, outcome = exitCode switch { 0 => "completed", 2 => "completed_with_diagnostic", _ => "failed" } },
            scientificReadiness = new { scope = "project_release_readiness", status = "no_go", basis = "MVS-BENCH-1.2.0 development", independentConfirmatoryValidation = false },
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
        var options = new JsonSerializerOptions { WriteIndented = true };
        if (partial)
        {
            var partialPayload = JsonSerializer.SerializeToNode(payload)!;
            partialPayload["artifactScope"] = "current_invocation_successful_writes";
            partialPayload["partialOutput"] = JsonSerializer.SerializeToNode(new {
                status = "incomplete", scope = "current_invocation_successful_writes",
                attemptedPath = CliMachineContext.AttemptedPath, unverifiedPaths = CliMachineContext.UnverifiedPaths
            });
            writer.WriteLine(partialPayload.ToJsonString(options));
        }
        else if (tracked)
        {
            var trackedPayload = JsonSerializer.SerializeToNode(payload)!;
            trackedPayload["artifactScope"] = "current_invocation_successful_writes";
            writer.WriteLine(trackedPayload.ToJsonString(options));
        }
        else if (command == "version")
        {
            // Capability handshake is read-only; older backends must not be used
            // for bounded Windows workflow state until they advertise this support.
            var versionPayload = JsonSerializer.SerializeToNode(payload)!;
            versionPayload["localAppDataOverride"] = "MVS_APPDATA_ROOT/v1";
            writer.WriteLine(versionPayload.ToJsonString(options));
        }
        else writer.WriteLine(JsonSerializer.Serialize(payload, options));
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
