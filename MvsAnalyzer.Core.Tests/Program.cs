using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

if (args.Length == 2 && args[0] == "--export-portability") { SerializationChecks.ExportFixtures(args[1]); return 0; }
if (args.Length == 2 && args[0] == "--verify-portability") { SerializationChecks.VerifyFixtures(args[1]); return 0; }
if (args.Length != 0) { Console.Error.WriteLine("Unknown test harness arguments."); return 2; }
var tests = new (string Name, Action Run)[]
{
    ("Processing limits are applied", ProcessingLimits),
    ("Two to ten groups are accepted", MultiGroupBuild),
    ("Mann-Whitney is symmetric", MannWhitneySymmetry),
    ("Kruskal-Wallis detects separated groups", KruskalWallisSeparation),
    ("Weak calibration produces an empty candidate set", CandidateThresholds),
    ("Run folders never overwrite", UniqueRunFolders),
    ("Formula hash is deterministic", FormulaHash),
    ("Legacy Cyrillic CSV is decoded", LegacyCyrillicDecode),
    ("Encodings are detected from their marks", EncodingDetection),
    ("Numbers survive locale noise", NumericNoiseParsing),
    ("Unknown simulation scenarios are rejected", ScenarioWhitelist),
    ("Scenario labels carry no lost glyphs", GlyphCoverage),
    ("Cliffs delta is antisymmetric and bounded", DeltaSymmetry),
    ("Equivalent groups are not reported as different", EquivalenceVerdict),
    ("A wide interval is reported as not enough data", InsufficientVerdict),
    ("MDE is interpolated from the power curve", MdeCurve),
    ("Split calibration keeps the halves disjoint", SplitHalves),
    ("Benchmark protocol text is unchanged", BenchmarkProtocolFrozen),
    ("Benchmark random stream is reproducible", BenchmarkRandomStream),
    ("Benchmark data generator has the planned shape", BenchmarkDatasetShape),
    ("Kendall tau and the Wilson interval behave", BenchmarkStatistics),
    ("The oracle is chosen on held-out replications", HeldOutOracle),
    ("The environment fingerprint is stable and honest", EnvironmentFingerprint),
    ("A remote job survives the round trip", RemoteJobRoundTrip),
    ("Command line options are read the same way twice", CliArgumentReading)
}.Concat(ScientificChecks.All).Concat(SerializationChecks.All).Concat(ColabChecks.All).Concat(ColabBridgeChecks.All).ToArray();
int failed=0;foreach(var test in tests){try{test.Run();Console.WriteLine($"PASS  {test.Name}");}catch(Exception ex){failed++;Console.WriteLine($"FAIL  {test.Name}: {ex.Message}");}}
Console.WriteLine($"{tests.Length-failed}/{tests.Length} tests passed");return failed==0?0:1;

static void ProcessingLimits(){var rows=Data(8,10,100,40).Concat(Data(8,10,250,40,"B")).ToList();var data=AnalysisEngine.Build(rows,150,5000,6);Assert(data.Observations.All(x=>x.Value>=150),"Configured minimum was ignored");Assert(data.MinValueApplied==150&&data.MinMeasurementsApplied==6,"Applied limits not recorded");}
static void MultiGroupBuild(){var rows=Data(6,10,100,2,"A").Concat(Data(6,10,120,2,"B")).Concat(Data(6,10,140,2,"C")).ToList();var data=AnalysisEngine.Build(rows);Assert(data.GroupNames.Length==3&&data.GroupCounts.All(x=>x==6),"Three-group data was not built");}
static void MannWhitneySymmetry(){double[] a={1,2,2,4,5},b={2,3,3,6,7};Near(AnalysisEngine.MannWhitneyP(a,b),AnalysisEngine.MannWhitneyP(b,a),1e-12);}
static void KruskalWallisSeparation(){double p=AnalysisEngine.KruskalWallisP(new[]{new double[]{1,2,3,4,5},new double[]{20,21,22,23,24},new double[]{40,41,42,43,44}});Assert(p<.01,$"Expected p < .01, got {p}");}
static void CandidateThresholds(){var data=AnalysisEngine.Build(Data(6,12,400,5).Concat(Data(6,12,450,5,"B")).ToList());var calibration=AnalysisEngine.MetricKeys.Select(m=>new CalibrationRow(m,.10,.20,30)).ToList();var rows=AnalysisEngine.Results(data,calibration,new ImmediateProgress(),CancellationToken.None);Assert(rows.All(x=>!x.Candidate),"Candidates were forced despite failing thresholds");}
static void UniqueRunFolders(){string root=Path.Combine(Path.GetTempPath(),"mvs-v1-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);try{var settings=new AppSettings{FigureOutputFolder=root,OutputPrefix="MVS"};string a=OutputExporter.PrepareRunFolder(settings,"same"),b=OutputExporter.PrepareRunFolder(settings,"same");Assert(a!=b,"Folder collision was not resolved");}finally{Directory.Delete(root,true);}}
static void FormulaHash()=>Assert(OutputExporter.FormulaHash=="10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c","Invalid formula hash");

static void DeltaSymmetry(){double[] a={1,2,3,4,5,6},b={4,5,6,7,8,9};double ab=AnalysisEngine.CliffsDelta(a,b),ba=AnalysisEngine.CliffsDelta(b,a);Near(ab,-ba,1e-12);Assert(Math.Abs(ab)<=1,"Delta out of range");Assert(AnalysisEngine.CliffsDelta(a,a)==0,"Identical groups must give zero");}
static void EquivalenceVerdict(){Assert(AnalysisEngine.Verdict(true,.6,.05,-.05,.05,.147)=="equivalent","A tight interval inside the margin is equivalence");}
static void InsufficientVerdict(){Assert(AnalysisEngine.Verdict(true,.30,.05,-.40,.55,.147)=="insufficient","A wide interval cannot decide");Assert(AnalysisEngine.Verdict(true,.001,.05,.20,.60,.147)=="difference","A significant interval away from zero is a difference");Assert(AnalysisEngine.Verdict(false,.001,.05,.20,.60,.147)=="not_applicable","An unusable metric stays not applicable");}
static void MdeCurve(){double[] effects={1.00,1.02,1.05,1.10,1.20},power={.05,.20,.60,1.00,1.00};double mde=AnalysisEngine.MdeFromCurve(effects,power,.80);Assert(mde>.05&&mde<.10,"MDE must fall between the bracketing grid points");Assert(!double.IsFinite(AnalysisEngine.MdeFromCurve(effects,new double[]{.01,.02,.03,.04,.05},.80)),"A flat curve has no MDE");}
static void SplitHalves(){var rows=Data(10,8,300,4).Concat(Data(10,8,340,4,"B")).ToList();var data=AnalysisEngine.Build(rows);var halves=AnalysisEngine.SplitEntities(data,20260719);var left=halves.Calibration.Entities.Select(x=>x.Group+"/"+x.Entity).ToHashSet();var right=halves.Analysis.Entities.Select(x=>x.Group+"/"+x.Entity).ToHashSet();Assert(!left.Overlaps(right),"The two halves must not share an entity");Assert(left.Count>0&&right.Count>0,"Both halves must hold entities");}
static void BenchmarkProtocolFrozen(){Assert(BenchmarkProtocol.HashIsFrozen,"The benchmark protocol text changed - already published runs are no longer comparable");Assert(BenchmarkProtocol.Hash.Length==64,"The protocol hash must be a SHA-256 digest");Assert(BenchmarkProtocol.ProfileById("full").PrimaryReplications>=BenchmarkProtocol.ProfileById("quick").PrimaryReplications,"A deeper profile must not run fewer repetitions");}
static void BenchmarkRandomStream(){var random=new BenchmarkRandom(20260904UL);ulong[] expected={8419501177352733710UL,9045835510591893074UL,9237519410920844811UL,9973926479834897958UL,14688187863013897198UL};for(int i=0;i<expected.Length;i++)Assert(random.NextUInt64()==expected[i],$"The benchmark random stream changed at draw {i+1}");Assert(BenchmarkRandom.Derive(7,1,2,3)==BenchmarkRandom.Derive(7,1,2,3),"A derived seed must depend only on its coordinates");Assert(BenchmarkRandom.Derive(7,1,2,3)!=BenchmarkRandom.Derive(7,1,2,4),"Neighbouring replications must not share a stream");}
static void BenchmarkDatasetShape(){var rows=BenchmarkDatasets.Generate(BenchmarkDatasets.Gait,InjectionMode.None,1,0,new BenchmarkRandom(11UL));var data=AnalysisEngine.Build(rows);Assert(data.GroupNames.Length==2,"A benchmark condition always has two groups");Assert(data.GroupCounts.All(x=>x==BenchmarkDatasets.Gait.EntitiesPerGroup),"Every group must hold the planned number of entities");Assert(rows.All(x=>x.Value>0),"Measurements of a positive quantity must stay positive");var shifted=BenchmarkDatasets.Generate(BenchmarkDatasets.Gait,InjectionMode.Location,1.20,0,new BenchmarkRandom(11UL));double before=rows.Where(x=>x.Group=="case").Average(x=>x.Value),after=shifted.Where(x=>x.Group=="case").Average(x=>x.Value);Assert(after>before,"A location effect must raise the treated group");Assert(Math.Abs(rows.Where(x=>x.Group=="control").Average(x=>x.Value)-shifted.Where(x=>x.Group=="control").Average(x=>x.Value))<1e-12,"The untreated group must be untouched by the injected effect");}
static void BenchmarkStatistics(){double[] a={1,2,3,4,5};Near(BenchmarkMath.KendallTau(a,a),1,1e-12);Near(BenchmarkMath.KendallTau(a,new double[]{5,4,3,2,1}),-1,1e-12);var interval=BenchmarkMath.WilsonInterval(5,100);Assert(interval.Low<.05&&interval.High>.05,"The Wilson interval must cover the observed rate");Assert(interval.Low>0&&interval.High<1,"The Wilson interval must stay inside the unit interval");}
static IEnumerable<Observation> Data(int entities,int measurements,double baseline,double step,string group="A"){for(int e=1;e<=entities;e++)for(int m=1;m<=measurements;m++)yield return new Observation(group+e,group,baseline+e*step+m,m,"test","unit");}
static void Assert(bool condition,string message){if(!condition)throw new Exception(message);}static void Near(double a,double b,double tolerance)=>Assert(Math.Abs(a-b)<=tolerance,$"{a} != {b}");
// A real Windows-1251 export, byte for byte. The expected text is written as escapes so
// that this test keeps working even if the test file itself is ever saved in a wrong encoding.
static void LegacyCyrillicDecode(){byte[] bytes={227,240,243,239,239,224,59,231,237,224,247,229,237,232,229,10,234,238,237,242,240,238,235,252,59,49,50,44,53,10};string expected="\u0433\u0440\u0443\u043F\u043F\u0430;\u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435\u000A\u043A\u043E\u043D\u0442\u0440\u043E\u043B\u044C;12,5\u000A";string text=CsvImporter.Decode(bytes,out string name);Assert(text==expected,"Windows-1251 Cyrillic must survive import unchanged");Assert(name=="windows-1251",$"The reported code page was {name}");Assert(!text.Contains('\uFFFD'),"A successful decode must leave no replacement characters");}
static void EncodingDetection(){
    byte[] utf8Bom={0xEF,0xBB,0xBF,0x61,0x2C,0x62};Assert(CsvImporter.Decode(utf8Bom,out string a)=="a,b"&&a=="utf-8-bom","A UTF-8 BOM must be consumed, not parsed as data");
    byte[] utf16Bom={0xFF,0xFE,0x61,0x00,0x2C,0x00,0x62,0x00};Assert(CsvImporter.Decode(utf16Bom,out string b)=="a,b"&&b=="utf-16le-bom","A UTF-16 BOM must be consumed");
    byte[] naked={0x61,0x00,0x2C,0x00,0x62,0x00,0x63,0x00};Assert(CsvImporter.Decode(naked,out string c)=="a,bc"&&c=="utf-16le","BOM-less UTF-16 must be recognised from its zero bytes");
    byte[] plain={0x61,0x2C,0x62};Assert(CsvImporter.Decode(plain,out string d)=="a,b"&&d=="utf-8","Plain ASCII must stay UTF-8");
}
// Spreadsheets export digit group separators as invisible spaces and minus as U+2212.
static void NumericNoiseParsing(){
    Assert(CsvImporter.TryDouble("1\u00A0234,5",true,out double a),"A non breaking space must not break a number");Near(a,1234.5,1e-9);
    Assert(CsvImporter.TryDouble("\u202F12,25",true,out double b),"A narrow non breaking space must not break a number");Near(b,12.25,1e-9);
    Assert(CsvImporter.TryDouble("1.234,56",true,out double c),"A thousands dot with a decimal comma must parse");Near(c,1234.56,1e-9);
    Assert(CsvImporter.TryDouble("\u22125,5",true,out double d),"A Unicode minus must parse as a negative number");Near(d,-5.5,1e-9);
    Assert(!CsvImporter.TryDouble("n/a",false,out _),"Text must not be read as a measurement");
}
static void ScenarioWhitelist(){
    Assert(SimulationScenarios.Canonicalize("scale")==SimulationScenarios.Variability,"docs/METHODS.md spells the dispersion scenario as scale");
    Assert(SimulationScenarios.Canonicalize("LOCATION_DOWN")==SimulationScenarios.Decrease,"Scenario names are case insensitive");
    bool threw=false;try{SimulationScenarios.Canonicalize("variabilty");}catch(ArgumentException){threw=true;}
    Assert(threw,"A misspelled scenario must fail loudly instead of silently running a location shift");
    threw=false;try{SimulationScenarios.Canonicalize(null);}catch(ArgumentException){threw=true;}Assert(threw,"A missing scenario must fail too");
}
static void GlyphCoverage(){
    foreach(string scenario in SimulationScenarios.All)
        foreach(bool russian in new[]{false,true}){string text=SimulationScenarios.Describe(scenario,russian);Assert(text.Length>0,"Every scenario needs a label");Assert(!text.Contains('\uFFFD'),"A label must not contain a replacement character");}
    Assert(SimulationScenarios.Describe(SimulationScenarios.Variability,true).Contains('\u0432'),"The Russian label must really be Cyrillic");
}
static void HeldOutOracle(){
    int metrics=AnalysisEngine.MetricKeys.Length;
    int procedures=BenchmarkProcedures.MvsTwoTrack+1;
    var choosing=new int[metrics]; choosing[0]=5; choosing[1]=4;
    var scoring=new int[metrics]; scoring[0]=1; scoring[1]=5;
    var summary=new ConditionSummary{
        Condition=new BenchmarkCondition("t","power","gait_stride_like","normal","dispersion",1.30,0,10,"synthetic"),
        Completed=10, Failed=0,
        Rejections=new int[procedures], Claims=new int[procedures],
        MetricRejections=Enumerable.Range(0,metrics).Select(m=>choosing[m]+scoring[m]).ToArray(),
        CompletedHalf=new[]{5,5},
        MetricRejectionsHalf=new[]{choosing,scoring},
        ChosenCounts=Enumerable.Range(0,procedures).Select(_=>new int[metrics]).ToArray(),
        DecisionDigest="", FirstError=""};
    Assert(summary.OracleMetricHeldOut()==0,"The oracle must be chosen on the half that does not score it");
    Near(summary.OraclePowerHeldOut(),.20,1e-9);
    Assert(summary.OracleMetric()==1,"The old oracle picks the winner over all replications at once");
    Near(summary.MetricRate(summary.OracleMetric()),.90,1e-9);
    Assert(summary.OraclePowerHeldOut()<summary.MetricRate(summary.OracleMetric()),"Choosing and scoring on the same replications inflates the oracle, and that inflation was charged to MVS");
}
static void EnvironmentFingerprint(){
    Assert(BenchmarkEnvironment.Scope=="withinEnvironment","The manifest has to say what replay guarantees");
    string first=BenchmarkEnvironment.Hash, second=BenchmarkEnvironment.Hash;
    Assert(first==second,"The environment id must not change between two reads on one machine");
    Assert(first.Length==64,"The environment id is a SHA-256 in hex");
    Assert(BenchmarkEnvironment.ShortHash.Length==16 && first.StartsWith(BenchmarkEnvironment.ShortHash),"The short id must be a prefix of the full one, or two reports cannot be compared");
    double[] probe=BenchmarkEnvironment.ProbeValues();
    Assert(probe.Length>=10,"The probe must cover the functions that are allowed to differ across platforms");
    foreach(double value in probe) Assert(double.IsFinite(value),"A probe value must be a real number");
    string fingerprint=BenchmarkEnvironment.Fingerprint();
    Assert(fingerprint.Contains("runtime=") && fingerprint.Contains("probe="),"The fingerprint must be readable enough to diff");
    Assert(!fingerprint.Contains(Environment.OSVersion.VersionString),"The operating system build string must stay out of the hash: a patch changes it without changing any arithmetic");
    Assert(BenchmarkEnvironment.Describe().Length>0,"A report needs the environment in words too");
}
static void RemoteJobRoundTrip(){
    var settings=new AppSettings{CalibrationSeed=4242,CalibrationEffect=1.22,Alpha=.01,SplitCalibration=true,MinMeasurements=9};
    var job=RemoteJob.Describe("calibrate_analyze","data/measurements.csv","abc123","Project","Notes",settings,777);
    string path=Path.Combine(Path.GetTempPath(),"mvs_job_"+Guid.NewGuid().ToString("N")+".json");
    File.WriteAllText(path,RemoteJob.Serialize(job));
    RemoteJobFile read=RemoteJob.Read(path);
    File.Delete(path);
    Assert(read.Dataset=="measurements.csv","Only the file name travels, never the local path");
    Assert(read.Seed==4242 && read.Repetitions==777,"A remote run must use the seed it was given, not a default");
    Near(read.Effect,1.22,1e-12); Near(read.Alpha,.01,1e-12);
    Assert(read.SplitCalibration,"Split calibration has to survive the trip or the remote run answers a different question");
    Assert(read.FormulaHash==OutputExporter.FormulaHash,"The job records which formula it was built for");
    var target=new AppSettings();
    RemoteJob.Apply(read,target);
    Assert(target.CalibrationSeed==4242 && target.MinMeasurements==9,"Applying a job must overwrite the local settings");
    Near(target.CalibrationEffect,1.22,1e-12);
    string url=RemoteJob.ColabUrl("analysis");
    Assert(url.Contains(RemoteJob.Repository) && url.Contains("/blob/"+RemoteJob.Branch+"/") && url.EndsWith(".ipynb"),"The notebook link is the only one-click route into Colab, so its shape is load bearing");
    Assert(RemoteJob.ColabUrl("benchmark")!=url,"The benchmark and the analysis are different notebooks");
}
static void CliArgumentReading(){
    var args=new CliArguments(new[]{"calibrate","--in","data.csv","--out=folder","--split","--effect","1.15"});
    Assert(args.Command=="calibrate","The first token is the command");
    Assert(args.Value("--in")=="data.csv","--name value has to work");
    Assert(args.Value("--out")=="folder","--name=value has to work too, because that is what gets typed into notebook cells");
    Assert(args.Flag("--split"),"A switch with no value is still a switch");
    Near(args.Number("--effect",1),1.15,1e-12);
    Assert(args.Int("--seed",7)==7,"A missing option falls back instead of throwing");
    bool threw=false; try{args.Require("--missing");}catch(ArgumentException){threw=true;}
    Assert(threw,"A required option that is absent must fail loudly");
    var greedy=new CliArguments(new[]{"--in","--out","folder"});
    Assert(greedy.Value("--in")==null,"An option must not swallow the next option as its value");
    Assert(greedy.Command=="","Options alone mean no command was given");
}
sealed class ImmediateProgress:IProgress<ProgressInfo>{public void Report(ProgressInfo value){}}
