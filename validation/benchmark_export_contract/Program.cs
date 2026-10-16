// Synthetic engineering fixture only. No statistical simulations or RNG work.
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
    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    static readonly string[] Tables = {"benchmark_report.md","benchmark_summary.csv","benchmark_replications.csv","benchmark_replication_procedures.csv","benchmark_replication_metrics.csv","benchmark_metrics.csv","benchmark_choices.csv","benchmark_stability.csv","benchmark_stability_replications.csv","benchmark_verdicts.csv","benchmark_protocol.txt"};
    static readonly string[] BenchmarkNames = Tables.Concat(new[]{"benchmark_manifest.json","SHA256SUMS.txt"}).ToArray();
    readonly string dll, root; readonly Api api; readonly List<object> results = new();
    readonly Dictionary<string,string> cleanFolders = new();
    string fixture = "", fixtureHash = "", outcomeHash = ""; int failures; readonly bool baseline;
    public Suite(string[] args)
    {
        if(args.Length<2)throw new ArgumentException("Usage: BenchmarkExportContract <mvs.dll> <new-evidence-root> [--baseline]");
        dll=Path.GetFullPath(args[0]);root=Path.GetFullPath(args[1]);baseline=args.Skip(2).Contains("--baseline");
        if(Directory.Exists(root)||File.Exists(root))throw new IOException("Use a new evidence directory; evidence is never overwritten.");
        Directory.CreateDirectory(root);api=new(dll);
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS",null);Environment.SetEnvironmentVariable("MVS_BACKUP_JOB",null);
        foreach(string n in new[]{"MVS_APPDATA_ROOT","XDG_DATA_HOME","XDG_CONFIG_HOME"})Environment.SetEnvironmentVariable(n,Path.Combine(root,"isolation",n));
    }
    static string Hash(string p)=>HashBytes(File.ReadAllBytes(p));
    static string HashBytes(byte[] b)=>Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
    static void Save(string d,string n,object o)=>File.WriteAllText(Path.Combine(d,n),JsonSerializer.Serialize(o,Json),new UTF8Encoding(false));
    static void Check(bool ok,string why){if(!ok)throw new InvalidOperationException(why);}
    void Isolate(string d)=>Environment.SetEnvironmentVariable("MVS_BACKUP_DIR",Path.Combine(d,"private-backups"));
    void Case(string n,Action<string> action)
    {
        string d=Path.Combine(root,n);Directory.CreateDirectory(d);Isolate(d);api.Context("Reset",true,true);
        try{action(d);results.Add(new{id=n,status="passed",evidenceDirectory=d});Console.WriteLine("PASS "+n);}
        catch(Exception e){failures++;Save(d,"failure.json",new{error=e.ToString()});results.Add(new{id=n,status="failed",evidenceDirectory=d,error=e.ToString()});Console.WriteLine("FAIL "+n+": "+e.Message);}
    }
    public int Run()
    {
        Save(root,"provenance.json",new{schema="mvs-benchmark-export-provenance/v1",purpose="Synthetic engineering fixtures only. No model, simulation, RNG, replication, or scientific validation.",binary=dll,binarySha256=Hash(dll),coreSha256=Hash(Path.Combine(Path.GetDirectoryName(dll)!,"MvsAnalyzer.Core.dll")),harnessSha256=Hash(Assembly.GetExecutingAssembly().Location),runtime=System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,baseline,backupDisabled=false,scientificReadiness="no_go",fixtureMethod="Real BackupSession Validate/Encode/Decode/Restore/Begin/Try and cached BenchmarkRunner result. No simulation branch is used.",limitations="Faults are synchronous test-owned filesystem collisions or callback exceptions in a newly allocated unique output directory. No ordinary --overwrite reuse, native Windows execution, UI rendering, or scientific readiness is established."});
        MakeFixture();
        foreach(string mode in new[]{"partial","foreign","clean","exit0"})Case("benchmark_main_"+mode,d=>MainBenchmark(d,mode));
        foreach(string mode in new[]{"partial","foreign","provenance","clean"})Case("resume_api_"+mode,d=>Observed(d,true,mode));
        Case("resume_main_clean",d=>ResumeMain(d,false));Case("resume_main_exit0",d=>ResumeMain(d,true));
        if(!baseline)
        {
            foreach(string mode in new[]{"first","manifest","checksum","before_throw","after_throw","start_throw","cancel_after_write"})Case("benchmark_api_"+mode,d=>Observed(d,false,mode));
            foreach(string mode in new[]{"manifest_rewrite","checksum_rewrite","manifest_read","start_throw","cancel_after_write"})Case("resume_api_"+mode,d=>Observed(d,true,mode));
            Case("benchmark_legacy_parity",d=>LegacyParity(d,false));Case("resume_legacy_parity",d=>LegacyParity(d,true));
            Case("preoutput_failure",Preoutput);Case("benchmark_figure_parity",FigureParity);
        }
        Check(Hash(fixture)==fixtureHash,"Input fixture changed.");
        Save(root,"report.json",new{schema="mvs-benchmark-export-tests/v1",baseline,evidenceRoot=root,passed=results.Count-failures,failed=failures,total=results.Count,cases=results,fixture,fixtureSha256Before=fixtureHash,fixtureSha256After=Hash(fixture),cachedOutcomeSha256=outcomeHash,scientificSimulations=0,scientificReadiness="no_go"});
        Console.WriteLine(File.ReadAllText(Path.Combine(root,"report.json")));return failures==0?0:1;
    }
    void MakeFixture()
    {
        string d=Path.Combine(root,"fixture");Directory.CreateDirectory(d);Isolate(d);
        object profile=api.Call(api.CoreType("Benchmarking.BenchmarkProtocol"),"ProfileById","quick")!;
        bool frozen=(bool)api.Property(api.CoreType("Benchmarking.BenchmarkProtocol"),"HashIsFrozen")!;
        var notes = frozen?Array.Empty<string>():new[]{"WARNING: the protocol text no longer matches the frozen hash. This run is not comparable with published runs."};
        var requestJson=JsonSerializer.Serialize(new{Kind="benchmark",Seed=20260904,Benchmark=JsonNode.Parse(api.Serialize(profile)),RealData=Array.Empty<object>(),RealDataNotes=notes});
        object request=api.Deserialize(requestJson,api.CoreType("BackupRequest"));
        var outcomeJson=JsonSerializer.Serialize(new{Profile=JsonNode.Parse(api.Serialize(profile)),Seed=20260904,RunId="synthetic_engineering_export_only",StartedUtc="2026-01-01T00:00:00Z",FinishedUtc="2026-01-01T00:00:00Z",Conditions=Array.Empty<object>(),Stability=new{Tau=Array.Empty<double>(),Repeats=0,TopOneMatches=0,TopMetricCounts=Array.Empty<int>(),Failed=0},DeterminismFirst="not_executed_synthetic",DeterminismSecond="not_executed_synthetic",LockedPilotMetric=new Dictionary<string,int>(),Threads=0,Notes=new[]{"SYNTHETIC ENGINEERING EXPORT FIXTURE. No model, simulation, RNG, replication, or scientific validation was executed. Empty fabricated cached outcome."},Verdicts=Array.Empty<object>(),Overall="no-go"});
        object outcome=api.Deserialize(outcomeJson,api.CoreType("Benchmarking.BenchmarkOutcome"));
        object doc=Activator.CreateInstance(api.CoreType("BackupDocument"))!;
        api.Set(doc,"Id","11111111111111111111111111111138");api.Set(doc,"SavedUtc",new DateTime(2026,1,1,0,0,0,DateTimeKind.Utc));api.Set(doc,"Request",request);
        api.Set(doc,"RequestHash",api.Call(api.CoreType("ScientificMath"),"Hash",api.Serialize(request)));
        api.Set(doc,"CalculationComplete",true);
        ((IList)api.Get(doc,"Environments")!).Add((string)api.Property(api.CoreType("Benchmarking.BenchmarkEnvironment"),"Hash")!);
        ((IDictionary)api.Get(doc,"Units")!).Add("result",JsonSerializer.SerializeToElement(outcome,outcome.GetType(),api.BackupJson));
        api.Call(api.CoreType("BackupSession"),"Validate",doc);
        fixture=Path.Combine(d,"synthetic-completed-benchmark.mvsbackup");File.WriteAllBytes(fixture,api.Encode(doc));fixtureHash=Hash(fixture);
        File.WriteAllText(Path.Combine(d,"backup.json"),api.Serialize(doc));
        object decoded=api.Decode(File.ReadAllBytes(fixture));
        var element=(JsonElement)((IDictionary)api.Get(decoded,"Units")!)["result"]!;outcomeHash=HashBytes(Encoding.UTF8.GetBytes(element.GetRawText()));
        // Real generic Try must accept the stored type before allowing the export tests.
        using((IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",decoded)!)
        using(var session=(IDisposable)api.Call(api.CoreType("BackupSession"),"Begin",request)!)
        {
            var method=api.CoreType("BackupSession").GetMethod("Try",BindingFlags.NonPublic|BindingFlags.Instance)!.MakeGenericMethod(api.CoreType("Benchmarking.BenchmarkOutcome"));
            object?[] a={"result",null};Check((bool)method.Invoke(session,a)!,"Synthetic cached result is unreadable.");Check((string)api.Get(a[1]!,"RunId")! == "synthetic_engineering_export_only","Wrong cached result.");
        }
        Save(d,"manifest.json",new{fixture,sha256=fixtureHash,outcomeSha256=outcomeHash,validation="Real BackupSession.Validate + Encode + Decode + Restore + Begin + Try<BenchmarkOutcome> all accepted the fixture.",scientificResults=false,plannedProfile="quick",actualSimulations=0});
    }
    object Doc()=>api.Decode(File.ReadAllBytes(fixture));

    object Document(bool exit0)
    {
        object doc=Doc();if(!exit0)return doc;
        var units=(IDictionary)api.Get(doc,"Units")!;var node=JsonNode.Parse(((JsonElement)units["result"]!).GetRawText())!;node["Overall"]="inconclusive";
        units["result"]=JsonSerializer.SerializeToElement(node);return doc;
    }
    void CheckDocument(object doc,bool exit0=false)
    {
        Check(((IDictionary)api.Get(doc,"Units")!).Count==1,"New computational units appeared.");
        var e=(JsonElement)((IDictionary)api.Get(doc,"Units")!)["result"]!;
        if(!exit0)Check(HashBytes(Encoding.UTF8.GetBytes(e.GetRawText()))==outcomeHash,"Cached outcome mutated.");
        Check(Hash(fixture)==fixtureHash,"Source checkpoint changed.");
    }
    void Inject(string folder,string mode)
    {
        Check(Directory.Exists(folder),"Export boundary occurred before folder allocation.");
        if(mode=="partial")Directory.CreateDirectory(Path.Combine(folder,"benchmark_summary.csv"));
        if(mode=="provenance")Directory.CreateDirectory(Path.Combine(folder,"backup_resume.json"));
        if(mode=="foreign")foreach(string n in new[]{"foreign-old-canary.txt","foreign-nested/foreign-old-nested.txt"})
        {string p=Path.Combine(folder,n);Directory.CreateDirectory(Path.GetDirectoryName(p)!);File.WriteAllText(p,"UNRELATED TEST-OWNED CONTENT; never written by benchmark exporter.\n",new UTF8Encoding(false));File.SetLastWriteTimeUtc(p,new DateTime(2000,1,1,0,0,0,DateTimeKind.Utc));}
    }
    void MainBenchmark(string dir,string mode)
    {
        string? folder=null;int boundaries=0;object doc=Document(mode=="exit0");
        string[] args={"benchmark","--profile","quick","--seed","20260904","--out",Path.Combine(dir,"output"),"--json"};
        using var restore=(IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",doc)!;
        var r=api.Main(args,line=>{if(!line.Contains("Saving the tables and the report  -  ",StringComparison.Ordinal))return;boundaries++;folder=line[(line.IndexOf("  -  ",StringComparison.Ordinal)+5)..];Inject(folder,mode);});
        File.WriteAllText(Path.Combine(dir,"stdout.json"),r.Stdout);File.WriteAllText(Path.Combine(dir,"stderr.txt"),r.Stderr);
        Check(boundaries==1&&folder!=null,"Actual CLI export boundary missing.");
        Verify(dir,folder!,mode,false,JsonNode.Parse(r.Stdout)!.AsObject(),r.Code);CheckDocument(doc,mode=="exit0");
        Save(dir,"boundary.json",new{actualCliMain=true,args,boundaries,injection="Synchronous real ConsoleProgress at .995 after unique output allocation; no model/writer substitution."});
        if(mode is "clean" or "exit0")cleanFolders["benchmark_"+mode]=folder!;
    }
    void ResumeMain(string dir,bool exit0)
    {
        object doc=Document(exit0);string input=fixture;
        if(exit0){input=Path.Combine(dir,"synthetic-inconclusive.mvsbackup");File.WriteAllBytes(input,api.Encode(doc));}
        string before=Hash(input);var r=api.Main(new[]{"resume","--in",input,"--out",Path.Combine(dir,"output"),"--json","--quiet"});
        File.WriteAllText(Path.Combine(dir,"stdout.json"),r.Stdout);File.WriteAllText(Path.Combine(dir,"stderr.txt"),r.Stderr);
        var p=JsonNode.Parse(r.Stdout)!.AsObject();string folder=p["outputDirectory"]!.GetValue<string>();
        Verify(dir,folder,exit0?"exit0":"clean",true,p,r.Code);CheckDocument(doc,exit0);Check(before==Hash(input),"Resume checkpoint mutated.");
        Save(dir,"boundary.json",new{actualCliMain=true,command="resume",sourceCheckpoint=input,sha256Before=before,sha256After=Hash(input)});
        cleanFolders["resume_"+(exit0?"exit0":"clean")]=folder;
    }
    void Observed(string dir,bool resume,string mode)
    {
        object doc=Doc();string? folder=null;int starts=0;var events=new List<object>();var counts=new Dictionary<string,int>();var progress=new List<object>();Exception? error=null;object? result=null;
        string? faultTarget=null;
        void Collision(string p){faultTarget=p;if(File.Exists(p)){string kept=Path.Combine(dir,"retained-before-fault-"+Path.GetFileName(p));File.Move(p,kept);Save(dir,"fault-fixture.json",new{target=p,retained=kept,sha256=Hash(kept)});}Directory.CreateDirectory(p);}
        Action<string> started=f=>{folder=f;starts++;api.Context("BeginOutput",f);events.Add(new{kind="start",path=f,completed=(bool?)null});if(mode=="start_throw")throw new IOException("TEST callback start failure");};
        Action<string,bool> observe=(p,done)=>{
            api.Context("ObserveOutput",p,done);events.Add(new{kind="write",path=p,completed=(bool?)done});
            string name=Path.GetFileName(p);if(!done)counts[name]=counts.GetValueOrDefault(name)+1;
            if(!done&&((mode=="first"&&name==Tables[0])||(mode=="manifest"&&name=="benchmark_manifest.json")||(mode=="checksum"&&name=="SHA256SUMS.txt")))Collision(p);
            if(!done&&mode=="manifest_rewrite"&&name=="benchmark_manifest.json"&&counts[name]==2)Collision(p);
            if(done&&mode=="checksum_rewrite"&&name=="benchmark_manifest.json"&&counts[name]==2)Collision(Path.Combine(Path.GetDirectoryName(p)!,"SHA256SUMS.txt"));
            if(done&&mode=="manifest_read"&&name=="backup_resume.json"){
                string manifest=Path.Combine(Path.GetDirectoryName(p)!,"benchmark_manifest.json");File.Copy(manifest,Path.Combine(dir,"retained-before-fault-benchmark_manifest.json"));File.WriteAllText(manifest,"{ MALFORMED TEST FIXTURE");faultTarget=manifest;
            }
            if(mode=="before_throw"&&!done&&name=="benchmark_summary.csv")throw new IOException("TEST callback before failure");
            if(mode=="after_throw"&&done&&name=="benchmark_report.md")throw new IOException("TEST callback after failure");
            if(mode=="cancel_after_write"&&done&&name=="benchmark_report.md")throw new OperationCanceledException("TEST cancellation after first completed write; not a token-latency claim");
        };
        object reporter=api.Progress(p=>{double f=(double)api.Get(p,"Fraction")!;progress.Add(new{fraction=f,action=api.Get(p,"Action"),details=api.Get(p,"Details")});Check(f==0||f==.99||f==.995,"Unexpected computational progress; cached-only guard.");if(f==.995){folder=(string)api.Get(p,"Details")!;Inject(folder,mode);}});
        using var restore=resume?null:(IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",doc)!;
        try{result=resume?api.Call(api.CoreType("BackupRunner"),"RunWithOutputObserver",doc,Path.Combine(dir,"output"),reporter,default(CancellationToken),started,observe):api.Call(api.CoreType("Benchmarking.BenchmarkReport"),"RunAndWriteWithOutputObserver",api.Get(api.Get(doc,"Request")!,"Benchmark"),20260904,Path.Combine(dir,"output"),"",false,reporter,default(CancellationToken),started,observe);}
        catch(Exception e){error=e;File.WriteAllText(Path.Combine(dir,"error.txt"),e.ToString());}
        int code=result==null?1:resume?(int)api.Get(result,"ExitCode")!:2;
        if(result!=null)api.Context("RecordOutput",api.Get(result,"Folder"));
        string raw=api.Payload(resume?"resume":"benchmark",code,error);File.WriteAllText(Path.Combine(dir,"stdout.json"),raw);
        Save(dir,"boundary.json",new{actualCliMain=false,api=resume?"BackupRunner.RunWithOutputObserver":"BenchmarkReport.RunAndWriteWithOutputObserver",starts,events,progress,faultTarget,errorType=error?.GetType().Name});
        Check(folder!=null,"Export folder boundary missing.");
        Verify(dir,folder!,mode,resume,JsonNode.Parse(raw)!.AsObject(),code);CheckDocument(doc);
        if(mode=="cancel_after_write")Check(error is OperationCanceledException,"Cancellation exception was lost.");
        Check(starts==(baseline?0:1),"Unexpected output-start count.");
        if(!baseline&&mode=="clean")Check(events.Count==(resume?34:27),"Unexpected clean observer event count: "+events.Count);
    }
    void Verify(string dir,string folder,string mode,bool resume,JsonObject payload,int code)
    {
        var disk=Directory.GetFiles(folder,"*",SearchOption.AllDirectories).OrderBy(p=>p,StringComparer.Ordinal).Select(p=>new{path=p,name=Path.GetRelativePath(folder,p).Replace('\\','/'),sha256=Hash(p),sizeBytes=new FileInfo(p).Length}).ToArray();Save(dir,"disk-files.json",disk);
        bool failed=mode is not("clean" or "foreign" or "exit0");int expectedCode=failed?1:mode=="exit0"?0:2;
        Check(code==expectedCode&&payload["exitCode"]!.GetValue<int>()==code,"Exit code changed.");
        Check(payload["execution"]!["completed"]!.GetValue<bool>()==!failed,"Execution completion changed.");
        Check(payload["scientificReadiness"]!["status"]!.GetValue<string>()=="no_go"&&!payload["scientificReadiness"]!["independentConfirmatoryValidation"]!.GetValue<bool>(),"Scientific readiness changed.");
        var artifacts=payload["artifacts"]!.AsArray();string[] names=artifacts.Select(a=>a!["name"]!.GetValue<string>()).OrderBy(n=>n,StringComparer.Ordinal).ToArray();
        string[] expected=mode switch{
            "first" or "start_throw"=>Array.Empty<string>(),
            "partial" or "before_throw" or "after_throw" or "cancel_after_write"=>new[]{"benchmark_report.md"},
            "manifest"=>Tables,
            "checksum" or "provenance"=>Tables.Concat(new[]{"benchmark_manifest.json"}).ToArray(),
            "manifest_rewrite" or "manifest_read"=>Tables.Concat(new[]{"backup_resume.json"}).ToArray(),
            "checksum_rewrite"=>Tables.Concat(new[]{"benchmark_manifest.json","backup_resume.json"}).ToArray(),
            _=>BenchmarkNames.Concat(resume?new[]{"backup_resume.json"}:Array.Empty<string>()).ToArray()};
        if(baseline&&failed)expected=Array.Empty<string>();
        if(baseline&&mode=="foreign")expected=expected.Append("foreign-old-canary.txt").ToArray();
        Check(names.SequenceEqual(expected.OrderBy(n=>n,StringComparer.Ordinal)),"Artifact membership differs: "+string.Join(",",names)+"; expected "+string.Join(",",expected));
        if(baseline&&failed)Check(payload["outputDirectory"]==null&&!payload.ContainsKey("partialOutput"),"Baseline no longer reproduces missing partial output.");
        else{
            Check(payload["outputDirectory"]!.GetValue<string>()==folder,"Wrong actual inner output directory.");
            Check(payload.ContainsKey("partialOutput")==failed,"Wrong partialOutput presence.");
            if(!baseline)Check(payload["artifactScope"]!.GetValue<string>()=="current_invocation_successful_writes","Missing invocation ownership scope.");
        }
        foreach(var a in artifacts){string p=a!["path"]!.GetValue<string>();Check(Path.GetDirectoryName(p)==folder,"Artifact outside output folder.");Check(Hash(p)==a["sha256"]!.GetValue<string>()&&new FileInfo(p).Length==a["sizeBytes"]!.GetValue<long>(),"Artifact bytes/hash/size disagree.");}
        bool hasManifest=names.Contains("benchmark_manifest.json");Check((payload["manifestPath"]!=null)==hasManifest,"Manifest path claims an unverified artifact.");
        if(failed&&!baseline){
            string? attempted=mode switch{"partial" or "before_throw"=>"benchmark_summary.csv","first"=>Tables[0],"manifest" or "manifest_rewrite"=>"benchmark_manifest.json","checksum" or "checksum_rewrite"=>"SHA256SUMS.txt","provenance"=>"backup_resume.json",_=>null};
            Check(payload["partialOutput"]!["status"]!.GetValue<string>()=="incomplete","Partial result is not incomplete.");
            if(attempted!=null)Check(payload["partialOutput"]!["attemptedPath"]?.GetValue<string>()==Path.Combine(folder,attempted),"Wrong attempted path for "+mode);
            if(mode=="manifest_read")Check(payload["partialOutput"]!["unverifiedPaths"]!.AsArray().Any(x=>x!.GetValue<string>()==Path.Combine(folder,"benchmark_manifest.json")),"Changed manifest not marked unverified.");
            if(resume&&mode is "provenance" or "manifest_rewrite" or "manifest_read")Check(File.Exists(Path.Combine(folder,"SHA256SUMS.txt"))&&!names.Contains("SHA256SUMS.txt"),"Initial checksum must be retained on disk but not claimed after resume publication starts.");
        }
        if(!failed){
            var manifest=JsonNode.Parse(File.ReadAllText(Path.Combine(folder,"benchmark_manifest.json")))!;
            string[] mf=manifest["files"]!.AsArray().Select(x=>x!.GetValue<string>()).ToArray();string[] expectedMf=Tables.Concat(resume?new[]{"backup_resume.json"}:Array.Empty<string>()).OrderBy(x=>x,StringComparer.Ordinal).ToArray();
            Check(mf.OrderBy(x=>x,StringComparer.Ordinal).SequenceEqual(expectedMf),"Manifest claims unexpected members.");
            string[] sums=File.ReadAllLines(Path.Combine(folder,"SHA256SUMS.txt"));var checks=new Dictionary<string,string>();foreach(string line in sums){Check(line.Length>66&&line.Substring(64,2)=="  ","Malformed checksum line.");checks.Add(line[66..],line[..64]);Check(Hash(Path.Combine(folder,line[66..]))==line[..64],"Checksum disagrees with bytes.");}
            var expectedSums=expected.Where(n=>n!="SHA256SUMS.txt");if(baseline&&mode=="foreign"&&!resume)expectedSums=expectedSums.Where(n=>!n.StartsWith("foreign-",StringComparison.Ordinal));if(baseline&&mode=="foreign"&&resume)expectedSums=expectedSums.Append("foreign-nested/foreign-old-nested.txt");
            Check(checks.Keys.OrderBy(n=>n,StringComparer.Ordinal).SequenceEqual(expectedSums.OrderBy(n=>n,StringComparer.Ordinal)),"Checksum member set differs.");
            Save(dir,"checksums.json",checks);
        }
        if(mode=="foreign")Check(disk.Any(f=>f.name=="foreign-old-canary.txt")&&disk.Any(f=>f.name=="foreign-nested/foreign-old-nested.txt"),"Test canaries missing from disk.");
        Save(dir,"details.json",new{mode,resume,folder,exitCode=code,expectedArtifacts=expected.OrderBy(x=>x,StringComparer.Ordinal),artifactNames=names,partialOutputPresent=payload.ContainsKey("partialOutput"),sourceFixtureUnchanged=Hash(fixture)==fixtureHash,actualSimulations=0});
    }
    void LegacyParity(string dir,bool resume)
    {
        object doc=Doc();object? result;using var restore=resume?null:(IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",doc)!;
        object progress=api.Progress(p=>{double f=(double)api.Get(p,"Fraction")!;Check(f==0||f==.99||f==.995,"Computational progress escaped cache.");});
        result=resume?api.Call(api.CoreType("BackupRunner"),"Run",doc,Path.Combine(dir,"output"),progress,default(CancellationToken)):api.Call(api.CoreType("Benchmarking.BenchmarkReport"),"RunAndWrite",api.Get(api.Get(doc,"Request")!,"Benchmark"),20260904,Path.Combine(dir,"output"),"",false,progress,default(CancellationToken));
        string folder=(string)api.Get(result!,"Folder")!;string other=cleanFolders[(resume?"resume":"benchmark")+"_clean"];
        string[] expected=BenchmarkNames.Concat(resume?new[]{"backup_resume.json"}:Array.Empty<string>()).ToArray();
        var files=expected.Select(n=>new{name=n,legacy=Path.Combine(folder,n),observed=Path.Combine(other,n),legacySha256=Hash(Path.Combine(folder,n)),observedSha256=Hash(Path.Combine(other,n))}).ToArray();Check(files.All(f=>f.legacySha256==f.observedSha256),"Legacy wrapper changed output bytes.");CheckDocument(doc);
        Save(dir,"parity.json",new{comparison="Exact bytes; no normalization or excluded files",files});
    }
    void FigureParity(string dir)
    {
        const string figureName="returned-fixture.svg";int starts=0;var events=new List<object>();
        object generator=api.FigureGenerator((outcome,folder,russian)=>{
            string path=Path.Combine(folder,figureName);File.WriteAllText(path,"<svg xmlns=\"http://www.w3.org/2000/svg\"><text>Synthetic export test</text></svg>\n",new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(folder,"unreturned-canary.txt"),"Not returned by renderer; not an exporter artifact.\n",new UTF8Encoding(false));return new List<string>{path};
        });
        object doc=Doc();object report;
        using((IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",doc)!)
            report=api.Call(api.CoreType("Benchmarking.BenchmarkReport"),"RunAndWriteWithOutputObserver",api.Get(api.Get(doc,"Request")!,"Benchmark"),20260904,Path.Combine(dir,"observed"),"",false,null,default(CancellationToken),
                (Action<string>)(f=>{starts++;api.Context("BeginOutput",f);}),
                (Action<string,bool>)((p,done)=>{events.Add(new{path=p,completed=done});api.Context("ObserveOutput",p,done);}),generator)!;
        string folder=(string)api.Get(report,"Folder")!;api.Context("RecordOutput",folder);
        string raw=api.Payload("benchmark",2,null);File.WriteAllText(Path.Combine(dir,"stdout.json"),raw);var payload=JsonNode.Parse(raw)!;
        Check(starts==1,"Figure export did not begin once.");var artifacts=payload["artifacts"]!.AsArray();
        string[] expected=BenchmarkNames.Append(figureName).OrderBy(n=>n,StringComparer.Ordinal).ToArray();
        Check(artifacts.Select(a=>a!["name"]!.GetValue<string>()).OrderBy(n=>n,StringComparer.Ordinal).SequenceEqual(expected),"Returned figure artifact set differs.");
        foreach(var a in artifacts){string p=a!["path"]!.GetValue<string>();Check(Hash(p)==a["sha256"]!.GetValue<string>()&&new FileInfo(p).Length==a["sizeBytes"]!.GetValue<long>(),"Figure artifact bytes differ.");}
        string[] returned=(string[])((IEnumerable)api.Get(report,"Figures")!).Cast<string>().ToArray();Check(returned.Length==1&&returned[0]==Path.Combine(folder,"figures",figureName),"Renderer return changed.");
        var manifest=JsonNode.Parse(File.ReadAllText(Path.Combine(folder,"benchmark_manifest.json")))!;
        Check(manifest["files"]!.AsArray().Select(x=>x!.GetValue<string>()).OrderBy(x=>x,StringComparer.Ordinal).SequenceEqual(Tables.Append("figures/"+figureName).OrderBy(x=>x,StringComparer.Ordinal)),"Figure manifest differs.");
        var checks=File.ReadAllLines(Path.Combine(folder,"SHA256SUMS.txt")).ToDictionary(line=>line[66..],line=>line[..64]);
        Check(checks.Keys.OrderBy(x=>x,StringComparer.Ordinal).SequenceEqual(BenchmarkNames.Where(n=>n!="SHA256SUMS.txt").Append("figures/"+figureName).OrderBy(x=>x,StringComparer.Ordinal)),"Figure checksum members differ.");
        foreach(var pair in checks)Check(Hash(Path.Combine(folder,pair.Key))==pair.Value,"Figure checksum bytes differ.");
        object legacy;
        using((IDisposable)api.Call(api.CoreType("BackupSession"),"Restore",Doc())!)
            legacy=api.Call(api.CoreType("Benchmarking.BenchmarkReport"),"RunAndWrite",api.Get(api.Get(Doc(),"Request")!,"Benchmark"),20260904,Path.Combine(dir,"legacy"),"",false,null,default(CancellationToken),generator)!;
        string old=(string)api.Get(legacy,"Folder")!;var files=BenchmarkNames.Append("figures/"+figureName).Select(n=>new{name=n,legacy=Path.Combine(old,n),observed=Path.Combine(folder,n),legacySha256=Hash(Path.Combine(old,n)),observedSha256=Hash(Path.Combine(folder,n))}).ToArray();
        Check(files.All(f=>f.legacySha256==f.observedSha256),"Figure wrapper bytes changed.");CheckDocument(doc);
        Save(dir,"parity.json",new{comparison="Exact bytes including deterministic returned SVG fixture; renderer itself is test code, not UI rendering validation",files});
        Save(dir,"details.json",new{folder,starts,events,actualSimulations=0,sourceFixtureUnchanged=true,scope="Returned-file observation only; renderer partial writes on thrown exceptions are outside this contract."});
    }
    void Preoutput(string dir)
    {
        int callbacks=0;Exception? error=null;
        try{api.Call(api.CoreType("Benchmarking.BenchmarkReport"),"RunAndWriteWithOutputObserver",api.Get(api.Get(Doc(),"Request")!,"Benchmark"),20260904,"","",false,null,default(CancellationToken),(Action<string>)(_=>callbacks++),(Action<string,bool>)((_,_)=>callbacks++));}catch(Exception e){error=e;}
        Check(error is InvalidDataException&&callbacks==0,"Pre-output validation invoked callbacks.");
        string raw=api.Payload("benchmark",1,error);File.WriteAllText(Path.Combine(dir,"stdout.json"),raw);var p=JsonNode.Parse(raw)!;Check(p["outputDirectory"]==null&&p["artifacts"]!.AsArray().Count==0&&p["partialOutput"]==null,"Pre-output failure claimed output.");
        Save(dir,"details.json",new{callbacks,actualSimulations=0,error=error!.GetType().Name});
    }
}
sealed class Api
{
    readonly Assembly core,cli;readonly Type machine,protocol;public JsonSerializerOptions BackupJson{get;}
    public Api(string path)
    {
        string folder=Path.GetDirectoryName(path)!;var c=new AssemblyLoadContext("benchmark-export-repro",true);
        c.Resolving+=(owner,name)=>{string p=Path.Combine(folder,name.Name+".dll");return File.Exists(p)?owner.LoadFromAssemblyPath(p):null;};
        cli=c.LoadFromAssemblyPath(path);core=c.LoadFromAssemblyPath(Path.Combine(folder,"MvsAnalyzer.Core.dll"));
        machine=cli.GetType("MvsAnalyzer.Cli.CliMachineContext",true)!;protocol=cli.GetType("MvsAnalyzer.Cli.CliMachineProtocol",true)!;
        BackupJson=(JsonSerializerOptions)CoreType("BackupSession").GetField("Json",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
    }
    public Type CoreType(string n)=>core.GetType("MvsAnalyzer."+n,true)!;
    public object? Property(Type t,string n)=>t.GetProperty(n,BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!.GetValue(null);
    public object? Get(object target,string n)=>target.GetType().GetProperty(n,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)!.GetValue(target);
    public void Set(object target,string n,object? value)=>target.GetType().GetProperty(n,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)!.SetValue(target,value);
    public object Deserialize(string json,Type t)=>JsonSerializer.Deserialize(json,t,BackupJson)!;
    public string Serialize(object value)=>JsonSerializer.Serialize(value,value.GetType(),BackupJson);
    public object Decode(byte[] b)=>Call(CoreType("BackupSession"),"Decode",b)!;
    public byte[] Encode(object d)=>(byte[])Call(CoreType("BackupSession"),"Encode",d)!;
    public object? Context(string name,params object?[] args)=>Call(machine,name,args);
    public object? Call(Type t,string n,params object?[] args)
    {
        MethodInfo m=t.GetMethod(n,BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!;
        var full=m.GetParameters().Select((p,i)=>i<args.Length?args[i]:p.HasDefaultValue?p.DefaultValue:throw new ArgumentException("Missing "+p.Name)).ToArray();
        try{return m.Invoke(null,full);}catch(TargetInvocationException e)when(e.InnerException!=null){ExceptionDispatchInfo.Capture(e.InnerException).Throw();throw;}
    }
    public object FigureGenerator(Func<object,string,bool,List<string>> a)=>typeof(FigureBridge).GetMethod("Create")!.MakeGenericMethod(CoreType("Benchmarking.BenchmarkOutcome")).Invoke(null,new object[]{a})!;
    public object Progress(Action<object> a)=>Activator.CreateInstance(typeof(ImmediateProgress<>).MakeGenericType(CoreType("ProgressInfo")),a)!;
    public string Payload(string command,int code,Exception? error){var w=new StringWriter(CultureInfo.InvariantCulture);Call(protocol,"Write",w,command,code,error);return w.ToString();}
    public (int Code,string Stdout,string Stderr) Main(string[] args,Action<string>? onLine=null)
    {
        Console.OutputEncoding=Encoding.UTF8;TextWriter oldOut=Console.Out,oldErr=Console.Error;var stdout=new StringWriter(CultureInfo.InvariantCulture);var stderr=new TappingWriter(onLine);
        try{Console.SetOut(stdout);Console.SetError(stderr);int code=(int)Call(cli.GetType("MvsAnalyzer.Cli.CliProgram",true)!,"Main",(object)args)!;return(code,stdout.ToString(),stderr.ToString());}
        finally{Console.SetOut(oldOut);Console.SetError(oldErr);}
    }
}
public sealed class ImmediateProgress<T>(Action<object> a):IProgress<T>{public void Report(T value)=>a(value!);}
sealed class TappingWriter(Action<string>? onLine):StringWriter(CultureInfo.InvariantCulture)
{public override void WriteLine(string? value){base.WriteLine(value);onLine?.Invoke(value??"");}}

public static class FigureBridge { public static Func<T,string,bool,List<string>> Create<T>(Func<object,string,bool,List<string>> f)=>(o,p,r)=>f(o!,p,r); }
