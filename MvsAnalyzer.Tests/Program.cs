using MvsAnalyzer;

var tests = new (string Name, Action Run)[]
{
    ("Processing limits are applied", ProcessingLimits),
    ("Two to ten groups are accepted", MultiGroupBuild),
    ("Mann-Whitney is symmetric", MannWhitneySymmetry),
    ("Kruskal-Wallis detects separated groups", KruskalWallisSeparation),
    ("Weak calibration produces an empty candidate set", CandidateThresholds),
    ("Run folders never overwrite", UniqueRunFolders),
    ("Formula hash is deterministic", FormulaHash),
    ("Cliffs delta is antisymmetric and bounded", DeltaSymmetry),
    ("Equivalent groups are not reported as different", EquivalenceVerdict),
    ("A wide interval is reported as not enough data", InsufficientVerdict),
    ("MDE is interpolated from the power curve", MdeCurve),
    ("Split calibration keeps the halves disjoint", SplitHalves)
};
int failed=0;foreach(var test in tests){try{test.Run();Console.WriteLine($"PASS  {test.Name}");}catch(Exception ex){failed++;Console.WriteLine($"FAIL  {test.Name}: {ex.Message}");}}
Console.WriteLine($"{tests.Length-failed}/{tests.Length} tests passed");return failed==0?0:1;

static void ProcessingLimits(){var rows=Data(8,10,100,40).Concat(Data(8,10,250,40,"B")).ToList();var data=AnalysisEngine.Build(rows,150,5000,6);Assert(data.Observations.All(x=>x.Value>=150),"Configured minimum was ignored");Assert(data.MinValueApplied==150&&data.MinMeasurementsApplied==6,"Applied limits not recorded");}
static void MultiGroupBuild(){var rows=Data(6,10,100,2,"A").Concat(Data(6,10,120,2,"B")).Concat(Data(6,10,140,2,"C")).ToList();var data=AnalysisEngine.Build(rows);Assert(data.GroupNames.Length==3&&data.GroupCounts.All(x=>x==6),"Three-group data was not built");}
static void MannWhitneySymmetry(){double[] a={1,2,2,4,5},b={2,3,3,6,7};Near(AnalysisEngine.MannWhitneyP(a,b),AnalysisEngine.MannWhitneyP(b,a),1e-12);}
static void KruskalWallisSeparation(){double p=AnalysisEngine.KruskalWallisP(new[]{new double[]{1,2,3,4,5},new double[]{20,21,22,23,24},new double[]{40,41,42,43,44}});Assert(p<.01,$"Expected p < .01, got {p}");}
static void CandidateThresholds(){var data=AnalysisEngine.Build(Data(6,12,400,5).Concat(Data(6,12,450,5,"B")).ToList());var calibration=AnalysisEngine.MetricKeys.Select(m=>new CalibrationRow(m,.10,.20,30)).ToList();var rows=AnalysisEngine.Results(data,calibration,new ImmediateProgress(),CancellationToken.None);Assert(rows.All(x=>!x.Candidate),"Candidates were forced despite failing thresholds");}
static void UniqueRunFolders(){string root=Path.Combine(Path.GetTempPath(),"mvs-v1-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);try{var settings=new AppSettings{FigureOutputFolder=root,OutputPrefix="MVS"};string a=OutputExporter.PrepareRunFolder(settings,"same"),b=OutputExporter.PrepareRunFolder(settings,"same");Assert(a!=b,"Folder collision was not resolved");}finally{Directory.Delete(root,true);}}
static void FormulaHash()=>Assert(OutputExporter.FormulaHash=="70e1d57723df1ca2bbc1b7856357f04d844cd77f36a83ad5fefd02565e401e2f","Invalid formula hash");

static void DeltaSymmetry(){double[] a={1,2,3,4,5,6},b={4,5,6,7,8,9};double ab=AnalysisEngine.CliffsDelta(a,b),ba=AnalysisEngine.CliffsDelta(b,a);Near(ab,-ba,1e-12);Assert(Math.Abs(ab)<=1,"Delta out of range");Assert(AnalysisEngine.CliffsDelta(a,a)==0,"Identical groups must give zero");}
static void EquivalenceVerdict(){Assert(AnalysisEngine.Verdict(true,.6,.05,-.05,.05,.147)=="equivalent","A tight interval inside the margin is equivalence");}
static void InsufficientVerdict(){Assert(AnalysisEngine.Verdict(true,.30,.05,-.40,.55,.147)=="insufficient","A wide interval cannot decide");Assert(AnalysisEngine.Verdict(true,.001,.05,.20,.60,.147)=="difference","A significant interval away from zero is a difference");Assert(AnalysisEngine.Verdict(false,.001,.05,.20,.60,.147)=="not_applicable","An unusable metric stays not applicable");}
static void MdeCurve(){double[] effects={1.00,1.02,1.05,1.10,1.20},power={.05,.20,.60,1.00,1.00};double mde=AnalysisEngine.MdeFromCurve(effects,power,.80);Assert(mde>.05&&mde<.10,"MDE must fall between the bracketing grid points");Assert(!double.IsFinite(AnalysisEngine.MdeFromCurve(effects,new double[]{.01,.02,.03,.04,.05},.80)),"A flat curve has no MDE");}
static void SplitHalves(){var rows=Data(10,8,300,4).Concat(Data(10,8,340,4,"B")).ToList();var data=AnalysisEngine.Build(rows);var halves=AnalysisEngine.SplitEntities(data,20260719);var left=halves.Calibration.Entities.Select(x=>x.Group+"/"+x.Entity).ToHashSet();var right=halves.Analysis.Entities.Select(x=>x.Group+"/"+x.Entity).ToHashSet();Assert(!left.Overlaps(right),"The two halves must not share an entity");Assert(left.Count>0&&right.Count>0,"Both halves must hold entities");}
static IEnumerable<Observation> Data(int entities,int measurements,double baseline,double step,string group="A"){for(int e=1;e<=entities;e++)for(int m=1;m<=measurements;m++)yield return new Observation(group+e,group,baseline+e*step+m,m,"test","unit");}
static void Assert(bool condition,string message){if(!condition)throw new Exception(message);}static void Near(double a,double b,double tolerance)=>Assert(Math.Abs(a-b)<=tolerance,$"{a} != {b}");
sealed class ImmediateProgress:IProgress<ProgressInfo>{public void Report(ProgressInfo value){}}
