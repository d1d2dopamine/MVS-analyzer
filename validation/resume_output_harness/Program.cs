// Explicit engineering regression harness. No experiment or scientific validation.
// dotnet ResumeOutputHarness.dll --candidate /path/mvs.dll --out /new/evidence [--baseline /old/mvs.dll] [--fixtures /frozen/checkpoint/directory]
using System.Collections;
using System.Globalization;
using System.IO.Compression;
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
    private readonly string? baselinePath, fixtureDirectory;
    private readonly List<object> cases = new();
    private readonly Dictionary<string, string> inputHashes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> completed = new(StringComparer.Ordinal);
    private int passed, failed;
    private Api api = null!;
    private string partial = "";
    public Suite(string[] args)
    {
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i += 2)
            if (i + 1 >= args.Length || args[i] is not ("--candidate" or "--baseline" or "--out" or "--fixtures") || !options.TryAdd(args[i], args[i + 1]))
                throw new ArgumentException("Use --candidate CLI_DLL --out NEW_DIRECTORY [--baseline CLI_DLL] [--fixtures DIRECTORY].");
        candidatePath = Path.GetFullPath(options["--candidate"]);
        baselinePath = options.TryGetValue("--baseline", out string? baseline) ? Path.GetFullPath(baseline) : null;
        fixtureDirectory = options.TryGetValue("--fixtures", out string? fixtures) ? Path.GetFullPath(fixtures) : null;
        root = Path.GetFullPath(options["--out"]);
        if (!File.Exists(candidatePath) || baselinePath != null && !File.Exists(baselinePath)) throw new FileNotFoundException("Pass an existing explicit CLI binary.");
        if (Directory.Exists(root) || File.Exists(root)) throw new IOException("Use a fresh evidence directory; retained evidence is never overwritten.");
        if (fixtureDirectory != null && !Directory.Exists(fixtureDirectory)) throw new DirectoryNotFoundException(fixtureDirectory);
        Directory.CreateDirectory(root);
    }
    public int Run()
    {
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null);
        foreach (string variable in new[] { "MVS_APPDATA_ROOT", "XDG_DATA_HOME", "XDG_CONFIG_HOME" })
            Environment.SetEnvironmentVariable(variable, Path.Combine(root, "isolated", variable));
        api = new(candidatePath);
        Save(root, "provenance.json", new { schema = "mvs-resume-output-provenance/v1", purpose = "Synthetic engineering fixtures only; no numerical experiment or scientific validation.",
            candidate = Binary(candidatePath), baseline = baselinePath == null ? null : Binary(baselinePath), backupDisabled = false,
            harnessSha256 = Hash(Assembly.GetExecutingAssembly().Location), runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            os = System.Runtime.InteropServices.RuntimeInformation.OSDescription, startedUtc = DateTimeOffset.UtcNow,
            faultBoundary = "Actual BackupRunner.RunWithOutputObserver plus CliMachineProtocol.Write; actual Main exercised separately in successful human and JSON cases.",
            benchmarkScope = "Only pre-model missing-profile branch is tested; no benchmark write observer coverage or benchmark changes are claimed." });
        Fixtures();
        Case("late_calibration", dir => Collision(dir, "calibration_tracks.csv", new[] { "calibration_state.json", "calibration.csv" }, usePartial: true));
        Case("first_write_failure", dir => Collision(dir, "calibration_state.json", Array.Empty<string>()));
        Case("second_write_failure", dir => Collision(dir, "calibration.csv", new[] { "calibration_state.json" }));
        Case("state_reread_failure", StateReread);
        Case("provenance_write_failure", dir => Collision(dir, "backup_resume.json", new[] { "calibration_state.json", "calibration.csv", "calibration_tracks.csv" }));
        Case("preoutput_validation_failure", InvalidBeforeOutput);
        foreach (string stage in new[] { "start", "before", "after" }) Case("observer_" + stage + "_throw_retry", dir => ObserverRetry(dir, stage));
        Case("cancellation_before_output", CancelBefore);
        Case("cancellation_after_write", CancelAfter);
        foreach (string history in new[] { "empty", "foreign", "current" }) Case("history_" + history, dir => History(dir, history));
        Case("legacy_observer_disabled_parity", dir => Parity(dir, "calibrate"));
        Case("human_cli_success", dir => MainSuccess(dir, machine: false));
        Case("machine_cli_success", dir => MainSuccess(dir, machine: true));
        Case("benchmark_validation_callbacks_absent", BenchmarkExcluded);
        foreach (string kind in completed.Keys.Where(k => k != "calibrate").OrderBy(k => k, StringComparer.Ordinal))
        {
            Case("exporter_manifest_" + kind, dir => ManifestFailure(dir, kind));
            Case("legacy_disabled_" + kind, dir => Parity(dir, kind));
        }
        if (baselinePath != null) Case("baseline_late_calibration", BaselineFailure);
        var fixtureChecks = inputHashes.Select(item => new { path = item.Key, beforeSha256 = item.Value, afterSha256 = Hash(item.Key) }).ToArray();
        if (fixtureChecks.Any(item => item.beforeSha256 != item.afterSha256)) { failed++; cases.Add(new { id = "source_fixture_immutability", status = "failed", evidenceDirectory = root, error = "An immutable input checkpoint changed." }); }
        var report = new { schema = "mvs-resume-output-tests/v1", passed, failed, total = passed + failed, baselineIncluded = baselinePath != null,
            evidenceRoot = root, fixtureKinds = completed.Keys.OrderBy(k => k).ToArray(), fixtureChecks, cases, finishedUtc = DateTimeOffset.UtcNow };
        Save(root, "report.json", report); Console.WriteLine(JsonSerializer.Serialize(report, Json)); return failed == 0 ? 0 : 1;
    }
    private object Binary(string path) => new { path, sha256 = Hash(path), coreSha256 = Hash(Path.Combine(Path.GetDirectoryName(path)!, "MvsAnalyzer.Core.dll")) };
    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static void Save(string dir, string name, object value) => File.WriteAllText(Path.Combine(dir, name), JsonSerializer.Serialize(value, Json), new UTF8Encoding(false));
    private static void Assert(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    private void Track(string path) { inputHashes.TryAdd(path, Hash(path)); }
    private void Isolate(string dir) => Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", Path.Combine(dir, "private-backups"));
    private void Case(string id, Action<string> action)
    {
        string dir = Path.Combine(root, id); Directory.CreateDirectory(dir); Isolate(dir); api.Context("Reset", true, true);
        try { action(dir); passed++; cases.Add(new { id, status = "passed", evidenceDirectory = dir }); Console.WriteLine("PASS " + id); }
        catch (Exception e) { failed++; Save(dir, "failure.json", new { error = e.ToString() }); cases.Add(new { id, status = "failed", evidenceDirectory = dir, error = e.ToString() }); Console.WriteLine("FAIL " + id + ": " + e.Message); }
    }
    private void Fixtures()
    {
        string dir = Path.Combine(root, "fixtures"); Directory.CreateDirectory(dir); Isolate(dir);
        string inputDirectory = fixtureDirectory ?? Path.Combine(dir, "bundled");
        if (fixtureDirectory == null)
        {
            Directory.CreateDirectory(inputDirectory);
            string bundle = Path.Combine(AppContext.BaseDirectory, "resume-output-fixtures-v1.zip");
            using var archive = ZipFile.OpenRead(bundle);
            var manifestEntry = archive.GetEntry("manifest.json") ?? throw new InvalidDataException("Missing bundled fixture manifest.");
            using var reader = new StreamReader(manifestEntry.Open());
            JsonObject manifest = JsonNode.Parse(reader.ReadToEnd())!.AsObject();
            foreach (JsonNode? item in manifest["fixtures"]!.AsArray())
            {
                string name = item!["file"]!.GetValue<string>();
                Assert(name == Path.GetFileName(name) && name.EndsWith(".mvsbackup", StringComparison.Ordinal), "Unsafe bundled fixture name.");
                var entry = archive.GetEntry(name) ?? throw new InvalidDataException("Missing fixture " + name);
                Assert(entry.Length <= 64 * 1024 * 1024, "Oversized fixture.");
                string path = Path.Combine(inputDirectory, name); using (var input = entry.Open()) using (var output = File.Create(path)) input.CopyTo(output);
                Assert(Hash(path) == item["sha256"]!.GetValue<string>(), "Bundled fixture checksum differs: " + name);
            }
            Save(dir, "bundled-source-manifest.json", manifest);
        }
        foreach (string path in Directory.GetFiles(inputDirectory, "*.mvsbackup", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal))
            {
                object doc = api.Decode(File.ReadAllBytes(path)); string kind = (string)api.Get(api.Get(doc, "Request")!, "Kind")!;
                if (kind is "calibrate" or "analyze" or "variance" or "estimation" or "melsm" && (bool)api.Get(doc, "CalculationComplete")!)
                { if (!completed.ContainsKey(kind)) { completed.Add(kind, path); Track(path); } }
            }
        if (fixtureDirectory == null) Assert(completed.Keys.OrderBy(x => x).SequenceEqual(new[] { "analyze", "calibrate", "estimation", "melsm", "variance" }), "Bundled five-kind coverage is incomplete.");
        // Only one minimal incomplete calibration is needed by candidate-only CI.
        var observations = Enumerable.Range(0, 2).SelectMany(g => Enumerable.Range(0, 6).SelectMany(e => Enumerable.Range(0, 6).Select(i => new { Entity = "G" + g + "E" + e, Group = "G" + g, Value = 100 + g * 3 + e * .7 + Math.Sin(i + e), Sequence = i, Variable = "measurement", Unit = "" }))).ToArray();
        object rows = api.Deserialize(JsonSerializer.Serialize(observations), typeof(List<>).MakeGenericType(api.CoreType("Observation")));
        object data = api.Call(api.CoreType("AnalysisEngine"), "Build", rows)!;
        using var stop = new CancellationTokenSource(); bool cancelled = false;
        try { api.Call(api.CoreType("AnalysisEngine"), "Calibrate", data, 100, 1.15, 54, api.Progress(_ => stop.Cancel()), stop.Token, "location", .02, 0d, .05, api.Field(api.CoreType("AnalysisEngine"), "DefaultTracks")); }
        catch (OperationCanceledException) { cancelled = true; }
        Assert(cancelled, "Partial fixture generation failed to cancel.");
        string generated = Directory.GetFiles(Path.Combine(dir, "private-backups"), "*.mvsbackup").Single(p => !p.Contains(".previous."));
        partial = Path.Combine(dir, "calibrate-unfinished.mvsbackup"); File.Copy(generated, partial); Track(partial);
        object partialDoc = api.Decode(File.ReadAllBytes(partial));
        Assert(!(bool)api.Get(partialDoc, "CalculationComplete")! && ((IDictionary)api.Get(partialDoc, "Units")!).Count == 1, "Expected one genuine cached simulation unit.");
        if (!completed.ContainsKey("calibrate"))
        {
            string completeDir = Path.Combine(dir, "complete-generation"); Directory.CreateDirectory(completeDir); Isolate(completeDir);
            api.Run(partialDoc, Path.Combine(completeDir, "output"), api.Progress(_ => { }), default, null, null, legacy: true);
            string source = Directory.GetFiles(Path.Combine(completeDir, "private-backups"), "*.mvsbackup").Single(p => !p.Contains(".previous."));
            string frozen = Path.Combine(dir, "calibrate-completed.mvsbackup"); File.Copy(source, frozen);
            Assert((bool)api.Get(api.Decode(File.ReadAllBytes(frozen)), "CalculationComplete")!, "Completed fixture missing result."); completed.Add("calibrate", frozen); Track(frozen);
        }
        Save(dir, "manifest.json", new { purpose = "Synthetic engineering fixture sources; input archives are immutable.", partial, completed, minimalFixture = new { groups = 2, entitiesPerGroup = 6, measurementsPerEntity = 6, repetitions = 100, seed = 54 }, externalFixtureDirectory = fixtureDirectory });
    }
    private sealed record Execution(object? Result, Exception? Error, string? Folder, List<object> Events, DateTime SavedUtc, int RetainedUnits, string[] BeforeHistory);
    private Execution Execute(string dir, string fixture, Action<string>? started = null, Action<string, bool>? observed = null,
        Action<object>? progress = null, CancellationToken token = default, bool legacy = false, bool disabled = false, Api? alternate = null, object? document = null)
    {
        Api selected = alternate ?? api; object doc = document ?? selected.Decode(File.ReadAllBytes(fixture));
        DateTime saved = (DateTime)selected.Get(doc, "SavedUtc")!; int units = ((IDictionary)selected.Get(doc, "Units")!).Count;
        string[] history = ((IEnumerable)selected.Get(doc, "Environments")!).Cast<string>().ToArray();
        string parent = Path.Combine(dir, "output"); string? folder = null; var events = new List<object>();
        Action<string> start = path => { folder = path; events.Add(new { kind = "start", path }); if (!disabled) selected.Context("BeginOutput", path); started?.Invoke(path); };
        Action<string, bool> observe = (path, done) => { events.Add(new { kind = done ? "after" : "before", path }); if (!disabled) selected.Context("ObserveOutput", path, done); observed?.Invoke(path, done); };
        object? result = null; Exception? error = null;
        try { result = selected.Run(doc, parent, selected.Progress(progress ?? (_ => { })), token, disabled ? null : start, disabled ? null : observe, legacy); }
        catch (Exception e) { error = e; }
        if (result != null) folder = (string)selected.Get(result, "Folder")!;
        if (folder == null && Directory.Exists(parent)) folder = Directory.GetDirectories(parent, "MVS_restored_*").SingleOrDefault();
        Save(dir, "events.json", events); if (error != null) File.WriteAllText(Path.Combine(dir, "error.txt"), error.ToString());
        return new(result, error, folder, events, saved, units, history);
    }
    private JsonObject Payload(string dir, Exception? error, int code = 1, Api? alternate = null)
    {
        JsonObject payload = (alternate ?? api).Payload("resume", code, error);
        File.WriteAllText(Path.Combine(dir, "stdout.json"), payload.ToJsonString(Json)); return payload;
    }
    private static void Partial(JsonObject payload, string? folder, params string[] expected)
    {
        Assert(payload["status"]!.GetValue<string>() == "error" && payload["exitCode"]!.GetValue<int>() == 1 && !payload["execution"]!["completed"]!.GetValue<bool>(), "Partial output claimed completion.");
        Assert(payload["outputDirectory"]?.GetValue<string>() == folder, "Partial output folder lost.");
        Assert(payload["partialOutput"]?["status"]?.GetValue<string>() == "incomplete" && payload["partialOutput"]?["scope"]?.GetValue<string>() == "current_invocation_successful_writes", "Partial scope lost.");
        Assert(payload["artifacts"]!.AsArray().Select(a => a!["name"]!.GetValue<string>()).OrderBy(x => x).SequenceEqual(expected.OrderBy(x => x)), "Retained file set differs.");
        foreach (JsonNode? artifact in payload["artifacts"]!.AsArray())
        { string path = artifact!["path"]!.GetValue<string>(); Assert(new FileInfo(path).Length == artifact["sizeBytes"]!.GetValue<long>() && Hash(path) == artifact["sha256"]!.GetValue<string>(), "Retained bytes/hash differ."); }
        Assert(payload["scientificReadiness"]!["status"]!.GetValue<string>() == "no_go", "Scientific readiness changed.");
    }
    private static void NoPartial(JsonObject payload)
    { Assert(payload["outputDirectory"] == null && payload["artifacts"]!.AsArray().Count == 0 && !payload.ContainsKey("partialOutput"), "Pre-output failure acquired output metadata."); }
    private void Collision(string dir, string name, string[] expected, bool usePartial = false)
    {
        bool injected = false; bool wasRestored = false; bool originalCachedUnit = false;
        string fixture = usePartial ? partial : completed["calibrate"];
        Execution execution = Execute(dir, fixture, observed: (path, done) => { if (!usePartial && !done && Path.GetFileName(path) == name) { Directory.CreateDirectory(path); injected = true; } },
            progress: p => { object? active = api.ActiveSession(); if (active != null) { wasRestored |= (bool)api.Get(active, "WasRestored")!; originalCachedUnit |= api.HasUnit(active, "simulation/0"); }
                if (usePartial && !injected && (double)api.Get(p, "Fraction")! >= 1)
                { string folder = Directory.GetDirectories(Path.Combine(dir, "output"), "MVS_restored_*").Single(); Directory.CreateDirectory(Path.Combine(folder, name)); injected = true; }
            });
        Assert(injected && execution.Error is IOException, "Actual resumed writer did not hit collision.");
        if (usePartial) Assert(wasRestored && originalCachedUnit, "Incomplete checkpoint was not genuinely restored.");
        JsonObject payload = Payload(dir, execution.Error); Partial(payload, execution.Folder, expected);
        Assert(Path.GetFileName(payload["partialOutput"]!["attemptedPath"]!.GetValue<string>()) == name, "Failed destination differs.");
        Assert(execution.Events.Count(x => ((JsonObject)JsonSerializer.SerializeToNode(x)!) ["kind"]!.GetValue<string>() == "start") == 1, "Observer began more than once.");
        Save(dir, "details.json", new { injected, target = name, boundary = "BackupRunner.RunWithOutputObserver and normal machine serializer", wasRestored, originalCachedUnit, injection = usePartial ? "Final synchronous progress callback, matching frozen baseline repro" : "Before target write observer callback", expectedArtifacts = expected });
    }
    private void StateReread(string dir)
    {
        bool corrupted = false; Execution execution = Execute(dir, completed["calibrate"], observed: (path, done) => { if (done && Path.GetFileName(path) == "calibration_state.json") { File.WriteAllText(path, "{}"); corrupted = true; } });
        Assert(corrupted && execution.Error is InvalidDataException, "Actual calibration state reread did not reject corruption.");
        JsonObject payload = Payload(dir, execution.Error); Partial(payload, execution.Folder);
        Assert(payload["partialOutput"]!["attemptedPath"] == null && payload["partialOutput"]!["unverifiedPaths"]!.AsArray().Single()!.GetValue<string>() == Path.Combine(execution.Folder!, "calibration_state.json"), "Mutated completed state not disclosed.");
        Save(dir, "details.json", new { corrupted, actualReread = true, verifiedArtifacts = 0 });
    }
    private void InvalidBeforeOutput(string dir)
    {
        object doc = api.Decode(File.ReadAllBytes(completed["calibrate"])); api.Set(doc, "Engine", "intentionally-incompatible-engine");
        Execution e = Execute(dir, completed["calibrate"], document: doc);
        Assert(e.Error is InvalidDataException && e.Events.Count == 0 && e.Folder == null, "Invalid checkpoint entered output scope."); NoPartial(Payload(dir, e.Error));
        Save(dir, "details.json", new { validationRejected = true, observerCalls = 0, outputFolderCreated = false });
    }
    private void ObserverRetry(string dir, string stage)
    {
        var original = new IOException("Intentional synchronous observer " + stage + " failure."); bool injected = false;
        Action Throw() => () => { if (!injected) { injected = true; throw original; } };
        Action throwOnce = Throw();
        Execution e = Execute(dir, completed["calibrate"], started: stage == "start" ? _ => throwOnce() : null,
            observed: (path, done) => { if ((stage == "before" && !done) || (stage == "after" && done)) throwOnce(); });
        Assert(ReferenceEquals(e.Error, original) && injected, "Observer exception was replaced or swallowed.");
        Payload(dir, e.Error);
        string retry = Path.Combine(dir, "retry"); Directory.CreateDirectory(retry); Isolate(retry); api.Context("Reset", true, true);
        Execution resumed = Execute(retry, completed["calibrate"]);
        Assert(resumed.Error == null && resumed.Result != null, "Restore scope was not released for retry.");
        Save(dir, "details.json", new { stage, originalExceptionPreserved = true, retrySucceeded = true, completedFilesBeforeFailure = Directory.GetFiles(e.Folder!).Select(Path.GetFileName).OrderBy(x => x).ToArray() });
    }
    private void CancelBefore(string dir)
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        Execution e = Execute(dir, partial, token: stop.Token);
        Assert(e.Error is OperationCanceledException && e.Events.Count == 0, "Cancellation semantics changed before export."); NoPartial(Payload(dir, e.Error));
        string retry = Path.Combine(dir, "retry"); Directory.CreateDirectory(retry); Isolate(retry); api.Context("Reset", true, true);
        Assert(Execute(retry, completed["calibrate"]).Error == null, "Cancelled restore scope leaked.");
        Save(dir, "details.json", new { cancellationPropagated = true, observerCalls = 0, retrySucceeded = true });
    }
    private void CancelAfter(string dir)
    {
        Execution e = Execute(dir, completed["calibrate"], observed: (_, done) => { if (done) throw new OperationCanceledException("Injected after completed first write."); });
        Assert(e.Error is OperationCanceledException, "Cancellation was replaced."); Partial(Payload(dir, e.Error), e.Folder, "calibration_state.json");
        Save(dir, "details.json", new { cancellationPropagated = true, injection = "after first completed export", retainedState = true });
    }
    private void History(string dir, string variant)
    {
        object doc = api.Decode(File.ReadAllBytes(completed["calibrate"])); var history = (IList)api.Get(doc, "Environments")!; history.Clear();
        string current = (string)api.CoreType("Benchmarking.BenchmarkEnvironment").GetProperty("Hash", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(null)!;
        if (variant == "foreign") history.Add(new string('a', 64)); if (variant == "current") history.Add(current);
        string frozen = Path.Combine(dir, "source.mvsbackup"); File.WriteAllBytes(frozen, api.Encode(doc)); Track(frozen);
        Execution e = Execute(dir, frozen); Assert(e.Error == null, "History variant failed to resume.");
        JsonObject provenance = JsonNode.Parse(File.ReadAllText(Path.Combine(e.Folder!, "backup_resume.json")))!.AsObject();
        Assert(provenance["retainedUnits"]!.GetValue<int>() == e.RetainedUnits && DateTime.Parse(provenance["resumedFromUtc"]!.GetValue<string>(), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind) == e.SavedUtc, "Pre-resume provenance changed.");
        string[] expected = variant == "empty" ? Array.Empty<string>() : variant == "foreign" ? new[] { new string('a', 64), current } : new[] { current };
        Assert(provenance["environments"]!.AsArray().Select(x => x!.GetValue<string>()).SequenceEqual(expected), "Environment history semantics changed.");
        JsonObject state = JsonNode.Parse(File.ReadAllText(Path.Combine(e.Folder!, "calibration_state.json")))!.AsObject();
        string expectedStateEnvironment = expected.Length == 1 ? expected[0] : (string)api.Call(api.CoreType("ScientificMath"), "Hash", "mixed-resume:" + string.Join(";", expected))!;
        Assert(state["EnvironmentHash"]!.GetValue<string>() == expectedStateEnvironment, "State environment derivation changed.");
        Save(dir, "details.json", new { variant, sourceUnchanged = inputHashes[frozen] == Hash(frozen), beforeHistory = e.BeforeHistory, afterHistory = expected, stateEnvironmentHash = expectedStateEnvironment, retainedUnits = e.RetainedUnits, resumedFromUtc = e.SavedUtc });
    }
    private static JsonNode Normalize(string name, JsonNode input)
    {
        JsonNode node = input.DeepClone();
        if (name == "calibration_state.json") { node.AsObject().Remove("CreatedUtc"); node.AsObject().Remove("PayloadHash"); }
        if (name == "run_manifest.json")
        {
            node.AsObject().Remove("created"); node.AsObject().Remove("runId");
            foreach (JsonNode? f in node["files"]?.AsArray() ?? new JsonArray())
                if (f?["FileName"]?.GetValue<string>() == "calibration_state.json") { f.AsObject().Remove("sha256"); f.AsObject().Remove("SizeBytes"); }
        }
        return node;
    }
    private void Parity(string dir, string kind)
    {
        string first = Path.Combine(dir, "legacy"), second = Path.Combine(dir, "disabled"); Directory.CreateDirectory(first); Directory.CreateDirectory(second);
        Isolate(first); Execution legacy = Execute(first, completed[kind], legacy: true, disabled: true);
        Isolate(second); Execution disabled = Execute(second, completed[kind], disabled: true);
        Assert(legacy.Error == null && disabled.Error == null, "Legacy or disabled-observer resume failed.");
        string[] names = Directory.GetFiles(legacy.Folder!).Select(Path.GetFileName).OrderBy(x => x).ToArray()!;
        Assert(names.SequenceEqual(Directory.GetFiles(disabled.Folder!).Select(Path.GetFileName).OrderBy(x => x)), "Disabled observer changed artifact names.");
        foreach (string name in names)
        {
            string left = File.ReadAllText(Path.Combine(legacy.Folder!, name)), right = File.ReadAllText(Path.Combine(disabled.Folder!, name));
            if (name is "calibration_state.json" or "run_manifest.json")
                Assert(JsonNode.DeepEquals(Normalize(name, JsonNode.Parse(left)!), Normalize(name, JsonNode.Parse(right)!)), "Disabled observer changed normalized " + name);
            else Assert(left == right, "Disabled observer changed bytes: " + name);
        }
        Assert((int)api.Get(legacy.Result!, "ExitCode")! == (int)api.Get(disabled.Result!, "ExitCode")!, "Disabled observer changed diagnostic exit.");
        Save(dir, "details.json", new { kind, legacySucceeded = true, disabledSucceeded = true, artifacts = names, exitCode = api.Get(legacy.Result!, "ExitCode"),
            normalization = "Only calibration_state.CreatedUtc and its derived PayloadHash; run_manifest.created/runId and corresponding calibration_state file size/hash. All other JSON values and all CSV/report bytes are equal." });
    }
    private void MainSuccess(string dir, bool machine)
    {
        string[] args = machine ? new[] { "resume", "--in", completed["calibrate"], "--out", Path.Combine(dir, "output"), "--json", "--quiet" } : new[] { "resume", "--in", completed["calibrate"], "--out", Path.Combine(dir, "output"), "--quiet" };
        var (code, stdout, stderr) = api.Main(args);
        File.WriteAllText(Path.Combine(dir, machine ? "stdout.json" : "human-stdout.txt"), stdout); File.WriteAllText(Path.Combine(dir, "stderr.txt"), stderr);
        Assert(code == 0, "Actual Main resume failed.");
        if (machine)
        {
            JsonObject payload = JsonNode.Parse(stdout)!.AsObject(); Assert(payload["status"]!.GetValue<string>() == "completed" && !payload.ContainsKey("partialOutput") && payload["artifacts"]!.AsArray().Count == 4 && payload["scientificReadiness"]!["status"]!.GetValue<string>() == "no_go", "Success machine contract changed.");
        }
        else
        {
            string folder = Directory.GetDirectories(Path.Combine(dir, "output"), "MVS_restored_*").Single();
            Assert(stdout == "Resumed result saved: " + folder + Environment.NewLine && stderr.Length == 0, "Human success text or stderr changed.");
        }
        Save(dir, "details.json", new { actualMainInvoked = true, machine, exitCode = code, backupsEnabled = true });
    }
    private void BenchmarkExcluded(string dir)
    {
        object doc = api.Decode(File.ReadAllBytes(completed["calibrate"])); object request = api.Get(doc, "Request")!; api.Set(request, "Kind", "benchmark"); api.Set(request, "Benchmark", null);
        api.Set(doc, "RequestHash", api.Call(api.CoreType("ScientificMath"), "Hash", api.SerializeBackup(request)));
        Execution e = Execute(dir, completed["calibrate"], document: doc);
        Assert(e.Error is InvalidDataException && e.Error.Message == "Missing benchmark profile." && e.Events.Count == 0, "Benchmark pre-model path acquired observers."); NoPartial(Payload(dir, e.Error));
        Save(dir, "details.json", new { observerCalls = 0, benchmarkModelExecuted = false, scope = "Missing-profile pre-model branch only. Full benchmark behavior remains outside this observer seam." });
    }
    private void ManifestFailure(string dir, string kind)
    {
        bool injected = false; Execution e = Execute(dir, completed[kind], observed: (path, done) => { if (!done && Path.GetFileName(path) == "run_manifest.json") { Directory.CreateDirectory(path); injected = true; } });
        Assert(injected && e.Error is IOException, "Actual resumed exporter manifest did not fail.");
        string[] expected = Directory.GetFiles(e.Folder!).Select(Path.GetFileName).ToArray()!; JsonObject payload = Payload(dir, e.Error); Partial(payload, e.Folder, expected);
        Assert(payload["manifestPath"] == null && Path.GetFileName(payload["partialOutput"]!["attemptedPath"]!.GetValue<string>()) == "run_manifest.json", "Failed manifest was reported complete.");
        Save(dir, "details.json", new { kind, injected, expectedArtifacts = expected, actualMethod = kind == "analyze" ? "OutputExporter.Export" : "ScientificTables.WriteManifest" });
    }
    private void BaselineFailure(string dir)
    {
        var baseline = new Api(baselinePath!); baseline.Context("Reset", true, true); bool injected = false;
        Execution e = Execute(dir, partial, legacy: true, alternate: baseline, progress: p => {
            if ((double)baseline.Get(p, "Fraction")! < 1 || injected) return;
            string folder = Directory.GetDirectories(Path.Combine(dir, "output"), "MVS_restored_*").Single(); Directory.CreateDirectory(Path.Combine(folder, "calibration_tracks.csv")); injected = true;
        });
        Assert(injected && e.Error is IOException && File.Exists(Path.Combine(e.Folder!, "calibration_state.json")) && File.Exists(Path.Combine(e.Folder!, "calibration.csv")), "Baseline counterexample did not reproduce.");
        NoPartial(Payload(dir, e.Error, alternate: baseline));
        Save(dir, "details.json", new { injected, retained = Directory.GetFiles(e.Folder!).Select(p => new { path = p, sha256 = Hash(p), sizeBytes = new FileInfo(p).Length }), boundary = "Unmodified legacy BackupRunner.Run and machine serializer; not actual Main for fault injection." });
    }
}

sealed class Api
{
    private readonly Assembly core, cli;
    private readonly Type machine, protocol;
    private readonly JsonSerializerOptions backupJson;
    public Api(string path)
    {
        string folder = Path.GetDirectoryName(path)!; var context = new AssemblyLoadContext("resume-output-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        context.Resolving += (owner, name) => { string dependency = Path.Combine(folder, name.Name + ".dll"); return File.Exists(dependency) ? owner.LoadFromAssemblyPath(dependency) : null; };
        cli = context.LoadFromAssemblyPath(path); core = context.LoadFromAssemblyPath(Path.Combine(folder, "MvsAnalyzer.Core.dll"));
        machine = cli.GetType("MvsAnalyzer.Cli.CliMachineContext", true)!; protocol = cli.GetType("MvsAnalyzer.Cli.CliMachineProtocol", true)!;
        backupJson = (JsonSerializerOptions)Field(CoreType("BackupSession"), "Json")!;
    }
    public Type CoreType(string name) => core.GetType("MvsAnalyzer." + name, true)!;
    public object? Get(object target, string name) => target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(target);
    public void Set(object target, string name, object? value) => target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)!.SetValue(target, value);
    public object? Field(Type type, string name) => type.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null);
    public object Deserialize(string json, Type type) => JsonSerializer.Deserialize(json, type, backupJson)!;
    public string SerializeBackup(object value) => JsonSerializer.Serialize(value, value.GetType(), backupJson);
    public object Decode(byte[] bytes) => Call(CoreType("BackupSession"), "Decode", bytes)!;
    public byte[] Encode(object doc) => (byte[])Call(CoreType("BackupSession"), "Encode", doc)!;
    public object? Context(string name, params object?[] args) => Call(machine, name, args);
    public object? Call(Type type, string name, params object?[] args)
    {
        MethodInfo method = type.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) ?? throw new MissingMethodException(type.FullName, name);
        var full = method.GetParameters().Select((p, i) => i < args.Length ? args[i] : p.HasDefaultValue ? p.DefaultValue : throw new ArgumentException("Missing " + p.Name)).ToArray();
        try { return method.Invoke(null, full); } catch (TargetInvocationException e) when (e.InnerException != null) { ExceptionDispatchInfo.Capture(e.InnerException).Throw(); throw; }
    }
    public object Progress(Action<object> action) => Activator.CreateInstance(typeof(ImmediateProgress<>).MakeGenericType(CoreType("ProgressInfo")), action)!;
    public object? Run(object doc, string parent, object progress, CancellationToken token, Action<string>? started, Action<string, bool>? observed, bool legacy)
        => legacy ? Call(CoreType("BackupRunner"), "Run", doc, parent, progress, token) : Call(CoreType("BackupRunner"), "RunWithOutputObserver", doc, parent, progress, token, started, observed);
    public object? ActiveSession() { object local = Field(CoreType("BackupSession"), "active")!; return local.GetType().GetProperty("Value")!.GetValue(local); }
    public bool HasUnit(object session, string key)
    { object doc = session.GetType().GetField("document", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(session)!; return ((IDictionary)Get(doc, "Units")!).Contains(key); }
    public JsonObject Payload(string command, int code, Exception? error)
    { var writer = new StringWriter(CultureInfo.InvariantCulture); Call(protocol, "Write", writer, command, code, error); return JsonNode.Parse(writer.ToString())!.AsObject(); }
    public (int Code, string Stdout, string Stderr) Main(string[] args)
    {
        // Initialize encoding before capture: Main sets UTF8 too and must not replace our test writers.
        Console.OutputEncoding = Encoding.UTF8; TextWriter savedOut = Console.Out, savedError = Console.Error;
        var stdout = new StringWriter(CultureInfo.InvariantCulture); var stderr = new StringWriter(CultureInfo.InvariantCulture);
        try { Console.SetOut(stdout); Console.SetError(stderr); int code = (int)Call(cli.GetType("MvsAnalyzer.Cli.CliProgram", true)!, "Main", (object)args)!; return (code, stdout.ToString(), stderr.ToString()); }
        finally { Console.SetOut(savedOut); Console.SetError(savedError); }
    }
}
public sealed class ImmediateProgress<T>(Action<object> action) : IProgress<T> { public void Report(T value) => action(value!); }
