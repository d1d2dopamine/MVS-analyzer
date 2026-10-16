// Synthetic engineering fixtures only. Minimum CLI budgets do not validate numerical science.
// Explicit invocation: dotnet OverwriteOutputHarness.dll --candidate /path/mvs.dll --out NEW_DIRECTORY [--baseline /old/mvs.dll]
using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

return new Suite(args).Run();

sealed class Suite
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    private readonly string root, candidatePath;
    private readonly string? baselinePath;
    private readonly List<object> cases = new();
    private int passed, failed;
    private CliApi candidate = null!;
    private static readonly string[] Canaries = { "stale_previous_report.txt", "old_scientific_result.csv", "benchmark_manifest.json", "nested/keep.txt" };
    private static readonly Dictionary<string, string[]> ScientificFiles = new() {
        ["estimation"] = new[] { "estimation_report.json", "estimation_performance.csv", "estimation_draws.csv" },
        ["variance"] = new[] { "variance_report.json", "variance_components.csv", "variance_tests.csv" },
        ["melsm"] = new[] { "melsm_report.json", "melsm_parameters.csv", "melsm_random_effects.csv" }
    };
    public Suite(string[] args)
    {
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i += 2)
            if (i + 1 == args.Length || args[i] is not ("--candidate" or "--baseline" or "--out") || !options.TryAdd(args[i], args[i + 1]))
                throw new ArgumentException("Use --candidate CLI_DLL --out NEW_DIRECTORY [--baseline OLD_CLI_DLL].");
        candidatePath = Path.GetFullPath(options["--candidate"]);
        baselinePath = options.TryGetValue("--baseline", out string? old) ? Path.GetFullPath(old) : null;
        root = Path.GetFullPath(options["--out"]);
        if (!File.Exists(candidatePath) || (baselinePath != null && !File.Exists(baselinePath))) throw new FileNotFoundException("An explicitly supplied CLI does not exist.");
        if (Directory.Exists(root) || File.Exists(root)) throw new IOException("Use a new evidence directory; existing evidence is never overwritten.");
        Directory.CreateDirectory(root);
    }
    public int Run()
    {
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1");
        Environment.SetEnvironmentVariable("MVS_DEBUG", "1");
        foreach (string variable in new[] { "MVS_APPDATA_ROOT", "MVS_BACKUP_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME" })
            Environment.SetEnvironmentVariable(variable, Path.Combine(root, "isolated", variable));
        candidate = new CliApi(candidatePath);
        Save(root, "provenance.json", new {
            schema = "mvs-overwrite-output-provenance/v1",
            purpose = "Synthetic engineering fixtures only; no numerical or independent scientific validation.",
            candidate = Binary(candidatePath), baseline = baselinePath == null ? null : Binary(baselinePath),
            harnessSha256 = Hash(Assembly.GetExecutingAssembly().Location), backupDisabled = true,
            benchmarkModelExecuted = false, runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            os = System.Runtime.InteropServices.RuntimeInformation.OSDescription, startedUtc = DateTimeOffset.UtcNow
        });
        if (baselinePath != null) Case("baseline_estimation_counterexample", dir => ScientificPair(dir, "estimation", baselinePath, expectBug: true));
        foreach (string kind in ScientificFiles.Keys) Case("candidate_" + kind + "_overwrite", dir => ScientificPair(dir, kind, candidatePath, expectBug: false));
        Case("human_estimation_manifest", Human);
        Case("tracked_success_stale_no_manifest", dir => Stale(dir, 0));
        Case("tracked_diagnostic_stale_no_manifest", dir => Stale(dir, 2));
        Case("tracked_partial_stale_no_manifest", dir => Stale(dir, 1));
        Case("tracked_current_manifest_run_id", dir => CurrentManifest(dir, explicitRunId: false));
        Case("tracked_explicit_run_id", dir => CurrentManifest(dir, explicitRunId: true));
        Case("tracked_empty_success", Empty);
        Case("tracked_changed_file", dir => Changed(dir, "change", "bad.csv"));
        Case("tracked_deleted_file", dir => Changed(dir, "delete", "bad.csv"));
        Case("tracked_unreadable_file", dir => Changed(dir, "lock", "bad.csv"));
        Case("tracked_changed_manifest", dir => Changed(dir, "change", "run_manifest.json"));
        Case("tracked_deleted_manifest", dir => Changed(dir, "delete", "run_manifest.json"));
        Case("tracked_failed_rewrite", FailedRewrite);
        Case("reset_clears_tracked_context", Reset);
        Case("untracked_legacy_benchmark_success", dir => LegacyBenchmark(dir, 0));
        Case("untracked_legacy_benchmark_diagnostic", dir => LegacyBenchmark(dir, 2));
        if (baselinePath != null) Case("baseline_tracked_stale_manifest_counterexample", BaselineStale);
        var report = new { schema = "mvs-overwrite-output-tests/v1", passed, failed, total = passed + failed,
            baselineIncluded = baselinePath != null, evidenceRoot = root, cases, finishedUtc = DateTimeOffset.UtcNow };
        Save(root, "report.json", report); Console.WriteLine(JsonSerializer.Serialize(report, Json));
        return failed == 0 ? 0 : 1;
    }
    private static object Binary(string path) => new { path, sha256 = Hash(path), coreSha256 = Hash(Path.Combine(Path.GetDirectoryName(path)!, "MvsAnalyzer.Core.dll")) };
    private void Case(string id, Action<string> run)
    {
        string dir = Path.Combine(root, id); Directory.CreateDirectory(dir);
        var watch = Stopwatch.StartNew();
        try { run(dir); passed++; cases.Add(new { id, status = "passed", evidenceDirectory = dir, elapsedSeconds = watch.Elapsed.TotalSeconds }); Console.WriteLine("PASS " + id); }
        catch (Exception error) { failed++; File.WriteAllText(Path.Combine(dir, "failure.txt"), error.ToString()); cases.Add(new { id, status = "failed", error = error.ToString(), evidenceDirectory = dir, elapsedSeconds = watch.Elapsed.TotalSeconds }); Console.WriteLine("FAIL " + id + ": " + error.Message); }
    }
    private static void Assert(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static void Save(string dir, string name, object value) => File.WriteAllText(Path.Combine(dir, name), JsonSerializer.Serialize(value, Json), new UTF8Encoding(false));
    private static void Text(string path, string value) { Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, value, new UTF8Encoding(false)); }
    private static JsonObject Read(string path) => JsonNode.Parse(File.ReadAllText(path))!.AsObject();
    private static string[] Names(JsonObject payload) => payload["artifacts"]!.AsArray().Select(x => x!["name"]!.GetValue<string>()).ToArray();
    private static string[] ManifestNames(JsonObject manifest) => manifest["files"]!.AsArray().Select(x => x!["FileName"]!.GetValue<string>()).ToArray();
    private static bool SameNames(IEnumerable<string> a, IEnumerable<string> b) => a.Order(StringComparer.Ordinal).SequenceEqual(b.Order(StringComparer.Ordinal));
    private static JsonObject NormalManifest(JsonObject value) { var copy = value.DeepClone().AsObject(); copy.Remove("created"); copy.Remove("runId"); return copy; }
    private static string Fixture(string dir)
    {
        var text = new StringBuilder("entity,group,value,sequence\n");
        for (int group = 0; group < 2; group++) for (int entity = 1; entity <= 4; entity++) for (int measurement = 1; measurement <= 3; measurement++)
        {
            double value = 100 + 3 * group + .7 * entity + .6 * measurement + ((entity * measurement) % 5) * .11;
            string label = group == 0 ? "A" : "B";
            text.Append(FormattableString.Invariant($"{label}{entity},{label},{value:R},{measurement}\n"));
        }
        string path = Path.Combine(dir, "input.csv"); Text(path, text.ToString()); return path;
    }
    private static Dictionary<string, string> Seed(string output)
    {
        Directory.CreateDirectory(output);
        foreach (string name in Canaries) Text(Path.Combine(output, name), name == "benchmark_manifest.json" ? "{\"runId\":\"stale-benchmark-run\"}\n" : "Old untouched canary: " + name + "\n");
        Text(Path.Combine(output, "run_manifest.json"), "{\"runId\":\"stale-run\",\"files\":[{\"FileName\":\"stale_previous_report.txt\"}]}\n");
        return Canaries.ToDictionary(name => name, name => Hash(Path.Combine(output, name)), StringComparer.Ordinal);
    }
    private static object[] CheckCanaries(string output, Dictionary<string, string> before) => before.Select(pair => {
        string path = Path.Combine(output, pair.Key), after = Hash(path);
        Assert(after == pair.Value, "An unrelated old file was altered or deleted: " + pair.Key);
        return (object)new { path, beforeSha256 = pair.Value, afterSha256 = after, sizeBytes = new FileInfo(path).Length };
    }).ToArray();
    private static string[] Arguments(string kind, string output, string input, bool machine)
    {
        var args = new List<string> { kind, "--out", output, "--overwrite", "--quiet" };
        if (machine) args.Add("--json");
        if (kind == "estimation") args.AddRange(new[] { "--target", "mean", "--shape", "normal", "--entities", "4", "--measurements", "3", "--repetitions", "100", "--bootstrap", "99", "--seed", "20260719" });
        else if (kind == "variance") args.AddRange(new[] { "--in", input, "--repetitions", "100", "--bootstrap", "99", "--seed", "20260719", "--min-measurements", "3" });
        else args.AddRange(new[] { "--in", input, "--mean-time", "--scale-time", "--correlate", "--quadrature", "7", "--max-iterations", "100" });
        return args.ToArray();
    }
    private static (int Code, JsonObject? Payload) Invoke(string dll, string dir, string[] args, bool machine)
    {
        Directory.CreateDirectory(dir);
        var start = new ProcessStartInfo { FileName = Environment.GetEnvironmentVariable("DOTNET_HOST_PATH") ?? "dotnet", RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        start.ArgumentList.Add(dll); foreach (string arg in args) start.ArgumentList.Add(arg);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Could not start CLI.");
        Task<string> stdout = process.StandardOutput.ReadToEndAsync(), stderr = process.StandardError.ReadToEndAsync();
        bool finished = process.WaitForExit(120_000);
        if (!finished) { process.Kill(entireProcessTree: true); process.WaitForExit(); }
        string outText = stdout.GetAwaiter().GetResult(), errText = stderr.GetAwaiter().GetResult();
        Text(Path.Combine(dir, machine ? "stdout.json" : "human-stdout.txt"), outText); Text(Path.Combine(dir, "stderr.log"), errText);
        Save(dir, "invocation.json", new { arguments = args, exitCode = process.ExitCode, actualProcess = true, timedOut = !finished, timeoutSeconds = 120, machine });
        Assert(finished, "Bounded CLI fixture timed out; no result was accepted.");
        Assert(process.ExitCode is 0 or 2, "CLI failed with native exit " + process.ExitCode + ": " + errText);
        JsonObject? payload = machine ? JsonNode.Parse(outText)!.AsObject() : null;
        if (payload != null) Status(payload, process.ExitCode);
        return (process.ExitCode, payload);
    }
    private void ScientificPair(string dir, string kind, string dll, bool expectBug)
    {
        string input = Fixture(dir), inputHash = Hash(input);
        string clean = Path.Combine(dir, "clean", "output"), dirty = Path.Combine(dir, "contaminated", "output");
        Dictionary<string, string> before = Seed(dirty);
        string oldManifestHash = Hash(Path.Combine(dirty, "run_manifest.json"));
        var left = Invoke(dll, Path.GetDirectoryName(clean)!, Arguments(kind, clean, input, true), true);
        var right = Invoke(dll, Path.GetDirectoryName(dirty)!, Arguments(kind, dirty, input, true), true);
        string[] expected = ScientificFiles[kind];
        Assert(left.Code == right.Code, "Overwrite changed the actual native exit status.");
        if (!expectBug) foreach (JsonObject payload in new[] { left.Payload!, right.Payload! }) Assert(payload["artifactScope"]?.GetValue<string>() == "current_invocation_successful_writes", "Current-invocation artifact marker missing.");
        Artifacts(left.Payload!, clean, expected.Append("run_manifest.json"));
        string[] oldTopLevel = Canaries.Where(name => !name.Contains('/')).ToArray();
        Artifacts(right.Payload!, dirty, expected.Append("run_manifest.json").Concat(expectBug ? oldTopLevel : Array.Empty<string>()));
        JsonObject cleanManifest = Manifest(clean, expected), dirtyManifest = Manifest(dirty, expected.Concat(expectBug ? oldTopLevel : Array.Empty<string>()));
        Assert(left.Payload!["runId"]!.GetValue<string>() == cleanManifest["runId"]!.GetValue<string>() && right.Payload!["runId"]!.GetValue<string>() == dirtyManifest["runId"]!.GetValue<string>(), "Machine run ID is not bound to the current manifest.");
        Assert(Hash(Path.Combine(dirty, "run_manifest.json")) != oldManifestHash, "Old manifest was not replaced.");
        Assert(dirtyManifest["runId"]!.GetValue<string>() != "stale-run", "Stale run ID survived.");
        var parity = expected.Select(name => {
            string cleanHash = Hash(Path.Combine(clean, name)), dirtyHash = Hash(Path.Combine(dirty, name));
            Assert(cleanHash == dirtyHash, "Scientific output bytes changed in dirty folder: " + name);
            return new { name, cleanSha256 = cleanHash, contaminatedSha256 = dirtyHash };
        }).ToArray();
        if (!expectBug) Assert(JsonNode.DeepEquals(NormalManifest(cleanManifest), NormalManifest(dirtyManifest)), "Manifest differs beyond created/runId or contains stale provenance.");
        Assert(Hash(input) == inputHash, "Input CSV changed.");
        Save(dir, "details.json", new { kind, expectBug, clean, contaminated = dirty, nativeExitCode = left.Code, actualProcesses = true,
            expectedScientificFiles = expected, canaries = CheckCanaries(dirty, before), scientificParity = parity,
            input = new { path = input, beforeSha256 = inputHash, afterSha256 = Hash(input) }, oldManifestSha256 = oldManifestHash,
            manifestNormalizedEqual = JsonNode.DeepEquals(NormalManifest(cleanManifest), NormalManifest(dirtyManifest)) });
    }
    private void Human(string dir)
    {
        string input = Fixture(dir), output = Path.Combine(dir, "output"); var before = Seed(output);
        var result = Invoke(candidatePath, dir, Arguments("estimation", output, input, false), false);
        Manifest(output, ScientificFiles["estimation"]);
        string clean = Path.Combine(root, "candidate_estimation_overwrite", "clean", "output");
        foreach (string name in ScientificFiles["estimation"]) Assert(Hash(Path.Combine(output, name)) == Hash(Path.Combine(clean, name)), "Human-mode scientific bytes changed.");
        string text = File.ReadAllText(Path.Combine(dir, "human-stdout.txt"));
        Assert(text.Contains("Known-truth estimation report saved: " + output) && !text.Contains("mvs-cli-result/v1"), "Human stdout contract changed.");
        Save(dir, "details.json", new { nativeExitCode = result.Code, actualProcess = true, machine = false, canaries = CheckCanaries(output, before), scientificParityWith = clean });
    }
    private static JsonObject Manifest(string output, IEnumerable<string> expected)
    {
        JsonObject manifest = Read(Path.Combine(output, "run_manifest.json"));
        Assert(SameNames(ManifestNames(manifest), expected), "Manifest files do not match this invocation's expected writes.");
        foreach (JsonNode? file in manifest["files"]!.AsArray())
        {
            string path = Path.Combine(output, file!["FileName"]!.GetValue<string>());
            Assert(Hash(path) == file["sha256"]!.GetValue<string>() && new FileInfo(path).Length == file["SizeBytes"]!.GetValue<long>(), "Manifest hash/size differs from retained bytes.");
        }
        return manifest;
    }
    private static void Status(JsonObject payload, int code)
    {
        Assert(payload["schemaVersion"]!.GetValue<string>() == "mvs-cli-result/v1", "Machine schema changed.");
        Assert(payload["exitCode"]!.GetValue<int>() == code && payload["status"]!.GetValue<string>() == (code == 0 ? "completed" : code == 2 ? "diagnostic" : "error"), "Native and machine exit/status disagree.");
        Assert(payload["execution"]!["completed"]!.GetValue<bool>() == (code is 0 or 2), "Completion flag changed.");
        Assert(payload["execution"]!["outcome"]!.GetValue<string>() == (code == 0 ? "completed" : code == 2 ? "completed_with_diagnostic" : "failed"), "Outcome changed.");
        Assert(payload["scientificReadiness"]!["status"]!.GetValue<string>() == "no_go", "Engineering fixtures must retain no_go scientific status.");
        if (code is 0 or 2) Assert(payload["error"] == null && !payload.ContainsKey("partialOutput"), "Completed/diagnostic result changed shape.");
    }
    private static void Artifacts(JsonObject payload, string output, IEnumerable<string> expected)
    {
        Assert(payload["outputDirectory"]!.GetValue<string>() == output && SameNames(Names(payload), expected), "Machine artifact scope contains stale or missing files.");
        foreach (JsonNode? artifact in payload["artifacts"]!.AsArray())
        {
            string name = artifact!["name"]!.GetValue<string>(), path = artifact["path"]!.GetValue<string>();
            Assert(Path.Combine(output, name) == path && Path.GetFileName(path) == name, "Artifact escaped output directory.");
            Assert(File.Exists(path) && new FileInfo(path).Length == artifact["sizeBytes"]!.GetValue<long>() && Hash(path) == artifact["sha256"]!.GetValue<string>(), "Artifact hash or size differs from current bytes.");
        }
        string? manifest = payload["manifestPath"]?.GetValue<string>();
        Assert(manifest == null || payload["artifacts"]!.AsArray().Any(a => a!["path"]!.GetValue<string>() == manifest), "Manifest path is not a verified artifact.");
    }
    private string Begin(string dir, string? runId = null)
    {
        string output = Path.Combine(dir, "output"); Directory.CreateDirectory(output);
        candidate.Context("Reset", true, false); candidate.Context("BeginOutput", output, runId); return output;
    }
    private void Write(string path, string text = "current fixture bytes\n") => candidate.Context("WriteOutput", path, (Action)(() => Text(path, text)));
    private JsonObject Payload(string dir, int code = 0, string command = "estimation")
    {
        JsonObject result = candidate.Payload(command, code, code == 1 ? new IOException("Injected fixture failure.") : null);
        Save(dir, "stdout.json", result); Status(result, code);
        if (result["outputDirectory"] != null && command != "benchmark") Assert(result["artifactScope"]?.GetValue<string>() == "current_invocation_successful_writes", "Tracked scope marker missing.");
        return result;
    }
    private void Stale(string dir, int code)
    {
        string output = Begin(dir); var before = Seed(output); string staleManifest = Hash(Path.Combine(output, "run_manifest.json"));
        Write(Path.Combine(output, "good.csv")); if (code != 1) candidate.Context("RecordOutput", output);
        if (code == 2) candidate.Context("Diagnostic", "warning", "fixture_diagnostic", "Synthetic diagnostic fixture.");
        JsonObject payload = Payload(dir, code); Artifacts(payload, output, new[] { "good.csv" });
        Assert(payload["manifestPath"] == null && payload["runId"] == null, "Stale manifest/run ID leaked into tracked output.");
        Assert(Hash(Path.Combine(output, "run_manifest.json")) == staleManifest, "Ignored old manifest was altered.");
        if (code == 1) Assert(payload["partialOutput"]!["scope"]!.GetValue<string>() == "current_invocation_successful_writes", "Partial contract changed.");
        Save(dir, "details.json", new { nativeProtocolExitCode = code, canaries = CheckCanaries(output, before), ignoredManifestSha256 = staleManifest });
    }
    private void CurrentManifest(string dir, bool explicitRunId)
    {
        string output = Begin(dir, explicitRunId ? "explicit-current-run" : null); Seed(output);
        Write(Path.Combine(output, "good.csv")); Write(Path.Combine(output, "run_manifest.json"), "{\"runId\":\"current-manifest-run\"}\n");
        candidate.Context("RecordOutput", output, explicitRunId ? "explicit-current-run" : null);
        JsonObject payload = Payload(dir); Artifacts(payload, output, new[] { "good.csv", "run_manifest.json" });
        Assert(payload["manifestPath"]!.GetValue<string>() == Path.Combine(output, "run_manifest.json") && payload["runId"]!.GetValue<string>() == (explicitRunId ? "explicit-current-run" : "current-manifest-run"), "Current run binding/explicit precedence failed.");
    }
    private void Empty(string dir)
    {
        string output = Begin(dir); Seed(output); candidate.Context("RecordOutput", output);
        JsonObject payload = Payload(dir); Artifacts(payload, output, Array.Empty<string>());
        Assert(payload["manifestPath"] == null && payload["runId"] == null, "No current writes must not claim stale completion artifacts.");
    }
    private void Changed(string dir, string action, string name)
    {
        string output = Begin(dir), bad = Path.Combine(output, name); Seed(output);
        Write(Path.Combine(output, "good.csv")); Write(bad, name.EndsWith(".json") ? "{\"runId\":\"current-manifest-run\"}" : "ABCD");
        string before = Hash(bad); FileStream? held = null;
        try
        {
            if (action == "change") Text(bad, name.EndsWith(".json") ? "{\"runId\":\"outside-manifest-run\"}" : "WXYZ");
            else if (action == "delete") File.Delete(bad);
            else { held = new FileStream(bad, FileMode.Open, FileAccess.ReadWrite, FileShare.None); AssertUnreadable(bad); }
            candidate.Context("RecordOutput", output);
            JsonObject payload = Payload(dir); Artifacts(payload, output, new[] { "good.csv" });
            Assert(payload["manifestPath"] == null && payload["runId"] == null, "Invalidated or stale manifest still supplied identity.");
        }
        finally { held?.Dispose(); }
        Save(dir, "details.json", new { action, path = bad, beforeSha256 = before, existsAfter = File.Exists(bad), afterSha256 = File.Exists(bad) ? Hash(bad) : null, mutationWasFixtureInjected = true });
    }
    private static void AssertUnreadable(string path)
    {
        try { using var read = File.OpenRead(path); } catch (IOException) { return; } catch (UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("Platform did not enforce FileShare.None; unreadable fixture cannot pass.");
    }
    private void FailedRewrite(string dir)
    {
        string output = Begin(dir), bad = Path.Combine(output, "rewrite.csv"); Seed(output); Write(Path.Combine(output, "good.csv")); Write(bad);
        try { candidate.Context("WriteOutput", bad, (Action)(() => throw new IOException("Injected failed rewrite."))); throw new InvalidOperationException("Fixture did not fail."); } catch (IOException) { }
        candidate.Context("RecordOutput", output); JsonObject payload = Payload(dir); Artifacts(payload, output, new[] { "good.csv" });
        Assert(File.Exists(bad), "Failed-rewrite fixture unexpectedly deleted prior bytes.");
    }
    private void Reset(string dir)
    {
        string output = Begin(dir, "old-emission"); Write(Path.Combine(output, "old.csv"));
        candidate.Context("Reset", true, false); JsonObject payload = Payload(dir);
        Assert(!payload.ContainsKey("artifactScope") && payload["outputDirectory"] == null && payload["manifestPath"] == null && payload["runId"] == null && Names(payload).Length == 0, "Reset retained tracked output context.");
    }
    private void LegacyBenchmark(string dir, int code)
    {
        string output = Path.Combine(dir, "output"); Text(Path.Combine(output, "benchmark.csv"), "legacy benchmark fixture\n");
        Text(Path.Combine(output, "benchmark_manifest.json"), "{\"runId\":\"legacy-benchmark-run\"}\n");
        Text(Path.Combine(output, "old.csv"), "legacy folder-enumeration fixture\n");
        candidate.Context("Reset", true, false); candidate.Context("RecordOutput", output);
        JsonObject payload = Payload(dir, code, "benchmark"); Assert(!payload.ContainsKey("artifactScope"), "Untracked benchmark falsely claims tracked scope."); Artifacts(payload, output, new[] { "benchmark.csv", "benchmark_manifest.json", "old.csv" });
        Assert(payload["runId"]!.GetValue<string>() == "legacy-benchmark-run", "Untracked legacy manifest identity changed.");
        bool? parity = null;
        if (baselinePath != null)
        {
            var old = new CliApi(baselinePath); old.Context("Reset", true, false); old.Context("RecordOutput", output);
            JsonObject baseline = old.Payload("benchmark", code, null); Save(dir, "baseline-stdout.json", baseline);
            parity = JsonNode.DeepEquals(payload, baseline); Assert(parity.Value, "Untracked legacy benchmark protocol changed.");
        }
        Save(dir, "details.json", new { benchmarkModelExecuted = false, writeTrackingStarted = false, scope = "Protocol-only legacy folder-enumeration compatibility; no benchmark model or partial-output support claim.", baselinePayloadEqual = parity });
    }
    private void BaselineStale(string dir)
    {
        var old = new CliApi(baselinePath!); string output = Path.Combine(dir, "output"); Seed(output);
        old.Context("Reset", true, false); old.Context("BeginOutput", output);
        old.Context("WriteOutput", Path.Combine(output, "good.csv"), (Action)(() => Text(Path.Combine(output, "good.csv"), "current\n")));
        old.Context("RecordOutput", output); JsonObject payload = old.Payload("estimation", 0, null); Save(dir, "stdout.json", payload);
        Assert(payload["runId"]!.GetValue<string>() == "stale-run" && payload["manifestPath"]!.GetValue<string>() == Path.Combine(output, "run_manifest.json") && Names(payload).Contains("stale_previous_report.txt"), "Baseline stale identity counterexample did not reproduce.");
    }
}

sealed class CliApi
{
    private readonly AssemblyLoadContext context;
    private readonly Type machine, protocol;
    public CliApi(string path)
    {
        string folder = Path.GetDirectoryName(path)!;
        context = new AssemblyLoadContext("overwrite-output-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        context.Resolving += (owner, name) => { string dependency = Path.Combine(folder, name.Name + ".dll"); return File.Exists(dependency) ? owner.LoadFromAssemblyPath(dependency) : null; };
        Assembly cli = context.LoadFromAssemblyPath(path);
        machine = cli.GetType("MvsAnalyzer.Cli.CliMachineContext", true)!; protocol = cli.GetType("MvsAnalyzer.Cli.CliMachineProtocol", true)!;
    }
    public object? Context(string name, params object?[] args) => Call(machine, name, args);
    private static object? Call(Type type, string name, params object?[] args)
    {
        MethodInfo method = type.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) ?? throw new MissingMethodException(type.FullName, name);
        object?[] full = method.GetParameters().Select((p, i) => i < args.Length ? args[i] : p.HasDefaultValue ? p.DefaultValue : throw new ArgumentException("Missing " + p.Name)).ToArray();
        try { return method.Invoke(null, full); }
        catch (TargetInvocationException error) when (error.InnerException != null) { ExceptionDispatchInfo.Capture(error.InnerException).Throw(); throw; }
    }
    public JsonObject Payload(string command, int code, Exception? error)
    {
        var writer = new StringWriter(CultureInfo.InvariantCulture); Call(protocol, "Write", writer, command, code, error);
        return JsonNode.Parse(writer.ToString())!.AsObject();
    }
}
