// Engineering regression fixtures only. No numerical validation or experiment.
// Run explicitly: dotnet PartialOutputHarness.dll --candidate /path/mvs.dll --out /new/evidence [--baseline /old/mvs.dll]
using System.Collections;
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
    private CliApi? baseline;
    private string? baselineCalibrationHash;
    public Suite(string[] args)
    {
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i += 2)
        {
            if (i + 1 == args.Length || args[i] is not ("--candidate" or "--baseline" or "--out") || !options.TryAdd(args[i], args[i + 1]))
                throw new ArgumentException("Use --candidate CLI_DLL --out NEW_DIRECTORY [--baseline OLD_CLI_DLL].");
        }
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
        foreach (string variable in new[] { "MVS_APPDATA_ROOT", "MVS_BACKUP_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME" })
            Environment.SetEnvironmentVariable(variable, Path.Combine(root, "isolated", variable));
        Environment.SetEnvironmentVariable("MVS_DEBUG", "1");
        candidate = new CliApi(candidatePath);
        if (baselinePath != null) baseline = new CliApi(baselinePath);
        Save("provenance.json", new {
            schema = "mvs-partial-output-provenance/v1", purpose = "Synthetic engineering fixtures only; no numerical experiment or scientific validation.",
            candidate = Binary(candidatePath), baseline = baselinePath == null ? null : Binary(baselinePath),
            harnessSha256 = Hash(Assembly.GetExecutingAssembly().Location), backupDisabled = true,
            runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            os = System.Runtime.InteropServices.RuntimeInformation.OSDescription, startedUtc = DateTimeOffset.UtcNow
        });
        if (baseline != null) Case("baseline_late_calibration_counterexample", dir => Calibration(baseline, dir, expectBug: true));
        Case("candidate_late_calibration", dir => Calibration(candidate, dir, expectBug: false));
        Case("current_files_only", CurrentFilesOnly);
        Case("failed_rewrite_invalidates_previous_success", FailedRewrite);
        Case("mutation_omits_changed_file", dir => ChangedFile(dir, "mutation"));
        Case("deletion_omits_deleted_file", dir => ChangedFile(dir, "deletion"));
        Case("unreadable_omits_locked_file", dir => ChangedFile(dir, "unreadable"));
        Case("unreadable_at_capture_is_unverified", UnreadableAtCapture);
        Case("reset_clears_partial_state", Reset);
        Case("disabled_tracking_has_no_emission", Disabled);
        Case("cancellation_retains_successful_files", Cancellation);
        Case("preflight_failure_has_no_output_context", Preflight);
        Case("success_payload_contract", Success);
        Case("diagnostic_payload_has_no_partial_output", Diagnostic);
        Case("exporter_manifest_write_failure", ManifestFailure);
        if (baseline != null) Case("success_payload_matches_baseline", SuccessParity);
        var report = new { schema = "mvs-partial-output-tests/v1", passed, failed, total = passed + failed,
            baselineIncluded = baseline != null, evidenceRoot = root, cases, finishedUtc = DateTimeOffset.UtcNow };
        Save("report.json", report);
        Console.WriteLine(JsonSerializer.Serialize(report, Json));
        return failed == 0 ? 0 : 1;
    }
    private object Binary(string path) => new { path, sha256 = Hash(path), coreSha256 = Hash(Path.Combine(Path.GetDirectoryName(path)!, "MvsAnalyzer.Core.dll")) };
    private void Case(string id, Action<string> run)
    {
        string dir = Path.Combine(root, id); Directory.CreateDirectory(dir);
        try { run(dir); passed++; cases.Add(new { id, status = "passed", evidenceDirectory = dir }); Console.WriteLine("PASS " + id); }
        catch (Exception error) { failed++; File.WriteAllText(Path.Combine(dir, "failure.txt"), error.ToString()); cases.Add(new { id, status = "failed", error = error.ToString(), evidenceDirectory = dir }); Console.WriteLine("FAIL " + id + ": " + error.Message); }
    }
    private static void Assert(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private void Save(string name, object value) => File.WriteAllText(Path.Combine(root, name), JsonSerializer.Serialize(value, Json), new UTF8Encoding(false));
    private static void SaveAt(string dir, string name, object value) => File.WriteAllText(Path.Combine(dir, name), JsonSerializer.Serialize(value, Json), new UTF8Encoding(false));
    private static string Fixture(string dir)
    {
        var text = new StringBuilder("entity,group,value,sequence\n");
        for (int group = 0; group < 2; group++) for (int entity = 1; entity <= 6; entity++) for (int measurement = 1; measurement <= 6; measurement++)
        {
            double value = 100 + 3 * group + .7 * entity + .6 * measurement + ((entity * measurement) % 5) * .11;
            string label = group == 0 ? "A" : "B";
            text.Append(FormattableString.Invariant($"{label}{entity},{label},{value:R},{measurement}\n"));
        }
        string path = Path.Combine(dir, "input.csv"); File.WriteAllText(path, text.ToString(), new UTF8Encoding(false)); return path;
    }
    private JsonObject InvokeCli(CliApi api, string dir, string[] arguments, Action<string>? onLine = null)
    {
        TextWriter oldOut = Console.Out, oldError = Console.Error;
        var stdout = new StringWriter(CultureInfo.InvariantCulture); var stderr = new StringWriter(CultureInfo.InvariantCulture);
        int exitCode;
        try
        {
            Console.SetOut(new LineWriter(stdout, onLine)); Console.SetError(new LineWriter(stderr, onLine));
            exitCode = (int)api.Call(api.Program, "Main", new object?[] { arguments })!;
        }
        finally
        {
            Console.SetOut(oldOut); Console.SetError(oldError);
            File.WriteAllText(Path.Combine(dir, "stdout.json"), stdout.ToString(), new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(dir, "stderr.log"), stderr.ToString(), new UTF8Encoding(false));
        }
        JsonObject payload = JsonNode.Parse(stdout.ToString())!.AsObject();
        SaveAt(dir, "invocation.json", new { arguments, exitCode });
        Assert(payload["exitCode"]!.GetValue<int>() == exitCode, "Actual Main return differs from machine exitCode.");
        return payload;
    }
    private static JsonArray Artifacts(JsonObject payload) => payload["artifacts"]!.AsArray();
    private static string[] Names(JsonObject payload) => Artifacts(payload).Select(x => x!["name"]!.GetValue<string>()).ToArray();
    private static void Partial(JsonObject payload, string folder, params string[] names)
    {
        Assert(payload["schemaVersion"]!.GetValue<string>() == "mvs-cli-result/v1", "Protocol schema changed.");
        Assert(payload["status"]!.GetValue<string>() == "error" && payload["exitCode"]!.GetValue<int>() == 1, "Partial output must remain an error.");
        Assert(!payload["execution"]!["completed"]!.GetValue<bool>() && payload["execution"]!["outcome"]!.GetValue<string>() == "failed", "Partial output falsely claims completion.");
        Assert(payload["outputDirectory"]!.GetValue<string>() == Path.GetFullPath(folder), "Missing actual output directory.");
        Assert(payload["partialOutput"]!["status"]!.GetValue<string>() == "incomplete", "Partial status missing.");
        Assert(payload["partialOutput"]!["scope"]!.GetValue<string>() == "current_invocation_successful_writes", "Partial scope changed.");
        Assert(Names(payload).Order().SequenceEqual(names.Order()), "Artifact names do not equal verified current writes.");
        foreach (JsonNode? artifact in Artifacts(payload))
        {
            string path = artifact!["path"]!.GetValue<string>();
            Assert(Path.GetDirectoryName(path) == Path.GetFullPath(folder), "Artifact escaped output directory.");
            Assert(File.Exists(path), "Reported artifact is absent.");
            Assert(new FileInfo(path).Length == artifact["sizeBytes"]!.GetValue<long>(), "Artifact size differs from retained file.");
            Assert(Hash(path) == artifact["sha256"]!.GetValue<string>(), "Artifact hash differs from retained file.");
        }
    }
    private void Calibration(CliApi api, string dir, bool expectBug)
    {
        string input = Fixture(dir), output = Path.Combine(dir, "output"), blocked = Path.Combine(output, "calibration_tracks.csv");
        int triggerCount = 0;
        JsonObject payload = InvokeCli(api, dir, new[] { "calibrate", "--in", input, "--out", output, "--repetitions", "100", "--seed", "20260719", "--json", "--quiet" }, line => {
            if (line != "MVS calibration") return;
            triggerCount++; Assert(triggerCount == 1 && !Directory.Exists(output), "Trigger must occur exactly once after read-only preflight.");
            Directory.CreateDirectory(blocked); SaveAt(dir, "trigger.json", new { line, createdOwnedDirectory = blocked, triggerCount });
        });
        Assert(triggerCount == 1, "Post-preflight trigger was not reached.");
        string retained = Path.Combine(output, "calibration.csv");
        Assert(File.Exists(retained), "First export did not survive second export failure.");
        Assert(payload["exitCode"]!.GetValue<int>() == 1 && payload["error"]!["type"]!.GetValue<string>() == "IOException", "Expected actual export IOException.");
        SaveAt(dir, "retained.json", new { inputSha256 = Hash(input), path = retained, sizeBytes = new FileInfo(retained).Length, sha256 = Hash(retained) });
        if (expectBug)
        {
            Assert(payload["outputDirectory"] == null && Artifacts(payload).Count == 0, "Baseline no longer reproduces the historical defect.");
            baselineCalibrationHash = Hash(retained);
        }
        else
        {
            Partial(payload, output, "calibration.csv");
            Assert(payload["partialOutput"]!["attemptedPath"]!.GetValue<string>() == blocked, "Failed write target missing.");
            Assert(payload["manifestPath"] == null, "Failed calibration must not claim a manifest.");
            if (baselineCalibrationHash != null) Assert(Hash(retained) == baselineCalibrationHash, "Retained numerical output differs from baseline fixture bytes.");
        }
    }
    private string Begin(string dir, string? runId = null)
    {
        string output = Path.Combine(dir, "output"); Directory.CreateDirectory(output);
        candidate.Context("Reset", true, false); candidate.Context("BeginOutput", output, runId); return output;
    }
    private void Write(string path, string text = "current fixture bytes\n") => candidate.Context("WriteOutput", path, (Action)(() => File.WriteAllText(path, text, new UTF8Encoding(false))));
    private JsonObject Payload(string dir, Exception? error = null, int code = 1, string command = "calibrate")
    {
        JsonObject payload = candidate.Payload(command, code, error ?? (code == 1 ? new IOException("Injected engineering fixture failure.") : null));
        File.WriteAllText(Path.Combine(dir, "stdout.json"), payload.ToJsonString(Json)); return payload;
    }
    private void CurrentFilesOnly(string dir)
    {
        string output = Begin(dir), good = Path.Combine(output, "good.csv");
        File.WriteAllText(Path.Combine(output, "stale.csv"), "untouched prior invocation");
        File.WriteAllText(Path.Combine(output, "run_manifest.json"), "{\"runId\":\"old-run\"}");
        Write(good); JsonObject payload = Payload(dir); Partial(payload, output, "good.csv");
        Assert(payload["manifestPath"] == null && payload["runId"] == null, "Stale manifest or run ID leaked into failure response.");
    }
    private void FailedRewrite(string dir)
    {
        string output = Begin(dir), good = Path.Combine(output, "good.csv"), rewritten = Path.Combine(output, "rewrite.csv");
        Write(good); Write(rewritten);
        try { candidate.Context("WriteOutput", rewritten, (Action)(() => throw new IOException("Injected rewrite failure."))); throw new InvalidOperationException("Injected write did not fail."); } catch (IOException) { }
        JsonObject payload = Payload(dir); Partial(payload, output, "good.csv");
        Assert(File.Exists(rewritten), "Prior successful bytes must remain to make invalidation meaningful.");
        Assert(payload["partialOutput"]!["attemptedPath"]!.GetValue<string>() == rewritten, "Rewrite target missing.");
    }
    private void ChangedFile(string dir, string mutation)
    {
        string output = Begin(dir), good = Path.Combine(output, "good.csv"), bad = Path.Combine(output, "changed.csv");
        Write(good); Write(bad, "ABCD");
        FileStream? held = null;
        try
        {
            if (mutation == "mutation") File.WriteAllText(bad, "WXYZ");
            else if (mutation == "deletion") File.Delete(bad);
            else { held = new FileStream(bad, FileMode.Open, FileAccess.ReadWrite, FileShare.None); AssertUnreadable(bad); }
            JsonObject payload = Payload(dir); Partial(payload, output, "good.csv");
            Assert(payload["partialOutput"]!["unverifiedPaths"]!.AsArray().Select(x => x!.GetValue<string>()).Contains(bad), "Invalidated captured path not disclosed.");
        }
        finally { held?.Dispose(); }
    }
    private static void AssertUnreadable(string path)
    {
        try { using var read = File.OpenRead(path); } catch (IOException) { return; } catch (UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("Platform did not enforce FileShare.None; unreadable fixture cannot be claimed as passed.");
    }
    private void UnreadableAtCapture(string dir)
    {
        string output = Begin(dir), bad = Path.Combine(output, "uncaptured.csv"); Write(Path.Combine(output, "good.csv")); File.WriteAllText(bad, "locked");
        using var held = new FileStream(bad, FileMode.Open, FileAccess.ReadWrite, FileShare.None); AssertUnreadable(bad);
        candidate.Context("ObserveOutput", bad, true); JsonObject payload = Payload(dir); Partial(payload, output, "good.csv");
        Assert(payload["partialOutput"]!["unverifiedPaths"]!.AsArray().Any(x => x!.GetValue<string>() == bad), "Failed capture must be disclosed.");
    }
    private void Reset(string dir)
    {
        string output = Begin(dir, "old-run"); Write(Path.Combine(output, "old.csv"));
        candidate.Context("ObserveOutput", Path.Combine(output, "attempted.csv"), false); candidate.Context("Reset", true, false);
        JsonObject payload = Payload(dir); Assert(payload["outputDirectory"] == null && payload["runId"] == null && payload["manifestPath"] == null && Artifacts(payload).Count == 0 && !payload.ContainsKey("partialOutput"), "Reset leaked prior invocation context.");
    }
    private void Disabled(string dir)
    {
        string output = Path.Combine(dir, "output"); Directory.CreateDirectory(output);
        candidate.Context("Reset", false, true); candidate.Context("BeginOutput", output, "ignored-run");
        Write(Path.Combine(output, "good.csv")); JsonObject payload = Payload(dir);
        Assert(File.Exists(Path.Combine(output, "good.csv")), "Disabling tracking must not prevent writes.");
        Assert(payload["outputDirectory"] == null && Artifacts(payload).Count == 0 && !payload.ContainsKey("partialOutput"), "Human-only execution unexpectedly tracked output emission.");
    }
    private void Cancellation(string dir)
    {
        string output = Begin(dir), stopped = Path.Combine(output, "cancelled.csv"); Write(Path.Combine(output, "good.csv"));
        OperationCanceledException? cancelled = null;
        try { candidate.Context("WriteOutput", stopped, (Action)(() => throw new OperationCanceledException("Injected cancellation."))); } catch (OperationCanceledException error) { cancelled = error; }
        Assert(cancelled != null, "Cancellation did not propagate from actual write wrapper.");
        JsonObject payload = Payload(dir, cancelled); Partial(payload, output, "good.csv");
        Assert(payload["error"]!["type"]!.GetValue<string>() == "OperationCanceledException" && payload["partialOutput"]!["attemptedPath"]!.GetValue<string>() == stopped, "Cancellation type or attempted path lost.");
    }
    private void Preflight(string dir)
    {
        string input = Fixture(dir), output = Path.Combine(dir, "output"); Directory.CreateDirectory(Path.Combine(output, "calibration_tracks.csv"));
        JsonObject payload = InvokeCli(candidate, dir, new[] { "calibrate", "--in", input, "--out", output, "--repetitions", "100", "--json" });
        Assert(payload["exitCode"]!.GetValue<int>() == 1 && payload["error"]!["type"]!.GetValue<string>() == "InvalidDataException", "Preflight must reject conflicting target.");
        Assert(payload["outputDirectory"] == null && Artifacts(payload).Count == 0 && !payload.ContainsKey("partialOutput"), "Preflight incorrectly claims output emission.");
        Assert(!File.ReadAllText(Path.Combine(dir, "stderr.log")).Contains("MVS calibration"), "Preflight failure reached calibration banner.");
    }
    private void Success(string dir)
    {
        string output = Begin(dir, "current-run"); Write(Path.Combine(output, "good.csv")); candidate.Context("RecordOutput", output, "current-run");
        JsonObject payload = Payload(dir, code: 0); AssertSuccess(payload, "completed", 0);
        Assert(Names(payload).SequenceEqual(new[] { "good.csv" }) && payload["runId"]!.GetValue<string>() == "current-run", "Success artifact/run metadata changed.");
    }
    private static void AssertSuccess(JsonObject payload, string status, int code)
    {
        Assert(!payload.ContainsKey("partialOutput"), "Success/diagnostic payload unexpectedly has partialOutput.");
        Assert(payload["status"]!.GetValue<string>() == status && payload["exitCode"]!.GetValue<int>() == code && payload["execution"]!["completed"]!.GetValue<bool>() && payload["error"] == null, "Success/diagnostic execution fields changed.");
        Assert(payload["scientificReadiness"]!["status"]!.GetValue<string>() == "no_go", "Engineering output changed scientific readiness.");
    }
    private void Diagnostic(string dir)
    {
        string output = Begin(dir); Write(Path.Combine(output, "good.csv")); candidate.Context("RecordOutput", output, null);
        AssertSuccess(Payload(dir, code: 2), "diagnostic", 2);
    }
    private void SuccessParity(string dir)
    {
        string output = Begin(dir, "same-run"); Write(Path.Combine(output, "good.csv"));
        File.WriteAllText(Path.Combine(output, "run_manifest.json"), "{\"runId\":\"same-run\"}");
        candidate.Context("RecordOutput", output, "same-run"); baseline!.Context("Reset", true, false); baseline.Context("RecordOutput", output, "same-run");
        JsonObject current = Payload(dir, code: 0), old = baseline.Payload("calibrate", 0, null);
        File.WriteAllText(Path.Combine(dir, "baseline-stdout.json"), old.ToJsonString(Json));
        Assert(JsonNode.DeepEquals(old, current), "Successful machine payload changed compared with baseline.");
    }
    private void ManifestFailure(string dir)
    {
        string output = Begin(dir, "manifest-fixture"), input = Fixture(dir), manifest = Path.Combine(output, "run_manifest.json");
        object imported = candidate.Call(candidate.CoreType("CsvImporter"), "Import", input, -1000000, 1000000)!;
        object observations = imported.GetType().GetProperty("Observations")!.GetValue(imported)!;
        object data = candidate.Call(candidate.CoreType("AnalysisEngine"), "Build", observations, -1000000, 1000000, 6)!;
        object settings = Activator.CreateInstance(candidate.CoreType("AppSettings"), nonPublic: true)!;
        settings.GetType().GetProperty("AutoExportCalibration")!.SetValue(settings, false);
        object EmptyList(string type) => Activator.CreateInstance(typeof(List<>).MakeGenericType(candidate.CoreType(type)))!;
        bool injected = false;
        Action<string, bool> observer = (path, completed) => {
            candidate.Context("ObserveOutput", path, completed);
            if (!completed && path == manifest) { injected = true; Directory.CreateDirectory(manifest); }
        };
        IOException? failure = null;
        try { candidate.Call(candidate.CoreType("OutputExporter"), "Export", output, "manifest-fixture", "Engineering fixture", "", "fixture", "input.csv", Hash(input), data,
            EmptyList("CalibrationRow"), EmptyList("ResultRow"), settings, 100, EmptyList("OutputArtifact"), "same_dataset", null, false, observer); }
        catch (IOException error) { failure = error; }
        Assert(injected && failure != null, "Actual exporter manifest write did not encounter injected directory collision.");
        JsonObject payload = Payload(dir, failure, command: "analyze"); Partial(payload, output, "results.csv", "metric_availability.csv", "results.json", "data_quality.csv");
        Assert(payload["manifestPath"] == null && payload["partialOutput"]!["attemptedPath"]!.GetValue<string>() == manifest, "Failed manifest was reported as completed.");
        Assert(payload["runId"]!.GetValue<string>() == "manifest-fixture", "Current invocation run ID was lost.");
        SaveAt(dir, "exporter-injection.json", new { actualMethod = "OutputExporter.Export", injected, failedPath = manifest, error = failure!.ToString() });
    }
}

sealed class CliApi
{
    private readonly AssemblyLoadContext context;
    private readonly Assembly core;
    public Type Program { get; }
    private Type MachineContext { get; }
    private Type Protocol { get; }
    public CliApi(string path)
    {
        string folder = Path.GetDirectoryName(path)!;
        context = new AssemblyLoadContext("partial-output-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        context.Resolving += (owner, name) => { string dependency = Path.Combine(folder, name.Name + ".dll"); return File.Exists(dependency) ? owner.LoadFromAssemblyPath(dependency) : null; };
        Assembly cli = context.LoadFromAssemblyPath(path); core = context.LoadFromAssemblyPath(Path.Combine(folder, "MvsAnalyzer.Core.dll"));
        Program = cli.GetType("MvsAnalyzer.Cli.CliProgram", true)!;
        MachineContext = cli.GetType("MvsAnalyzer.Cli.CliMachineContext", true)!;
        Protocol = cli.GetType("MvsAnalyzer.Cli.CliMachineProtocol", true)!;
    }
    public Type CoreType(string name) => core.GetType("MvsAnalyzer." + name, true)!;
    public object? Context(string name, params object?[] args) => Call(MachineContext, name, args);
    public object? Call(Type type, string name, params object?[] args)
    {
        MethodInfo method = type.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) ?? throw new MissingMethodException(type.FullName, name);
        ParameterInfo[] parameters = method.GetParameters();
        object?[] full = parameters.Select((p, i) => i < args.Length ? args[i] : p.HasDefaultValue ? p.DefaultValue : throw new ArgumentException("Missing " + p.Name)).ToArray();
        try { return method.Invoke(null, full); }
        catch (TargetInvocationException error) when (error.InnerException != null) { ExceptionDispatchInfo.Capture(error.InnerException).Throw(); throw; }
    }
    public JsonObject Payload(string command, int code, Exception? error)
    {
        var writer = new StringWriter(CultureInfo.InvariantCulture); Call(Protocol, "Write", writer, command, code, error);
        return JsonNode.Parse(writer.ToString())!.AsObject();
    }
}

sealed class LineWriter(TextWriter target, Action<string>? onLine) : TextWriter
{
    private readonly StringBuilder pending = new();
    public override Encoding Encoding => Encoding.UTF8;
    public override void Write(char value)
    {
        target.Write(value);
        if (value == '\n') { string line = pending.ToString().TrimEnd('\r'); pending.Clear(); onLine?.Invoke(line); }
        else pending.Append(value);
    }
    public override void Write(string? value) { if (value != null) foreach (char character in value) Write(character); }
    public override void WriteLine(string? value) { Write(value); Write(NewLine); }
    public override void Flush() => target.Flush();
}
