# Round 49 frozen protocol: generator and variance-report integration contract

Frozen before candidate execution, 2026-10-17. No numerical executions, code changes, seed searches, fits, or optimization performed in preparing this document. Source: Round48 `Core/VarianceAnalysis.cs`, `Core/ScientificInfrastructure.cs`, `Core/AnalysisEngine.cs`, `Core/RunRecording.cs`, `MvsAnalyzer.Core.Tests/RunRecordingChecks.cs`, `ScientificChecks.cs`, and `docs/METHODS.md` section6. Freeze this protocol, implementation, and literal manifest before execution. Identifier: round49-variance-bootstrap-contract-v1.

## Purpose and exact scope

Integrate the already separately checked estimator with actual production generator/report-control-flow contracts. Test the existing Generate method against independent hand algebra and execute actual RunWithRecording to prove the published report contains correct bootstrap p values, fixed-family adjustment, denominator/failure accounting, MDE gates and boundary suppression. This closes a real integration gap: existing recording tests seed unavailable fits and never traverse usable variance-test reports. It does NOT establish bootstrap calibration, power accuracy, coverage, seed-stream independence, optimizer reliability, or end-to-end simulated refit correctness. Scientific activation/NO-GO and all production thresholds/models stay unchanged.

Exactly six direct Generate cases and fourteen successful RunWithRecording scenarios. Scientific Fit calls=0, Statistic calls=0, optimizer calls=0; no reference optimizer or external package is needed. All Run cases deliberately use a nonconverged initial estimate to bypass interval generation. Actual seeded interval generation and interval aggregation are deferred: Generate occurs before the interval cache lookup and cannot honestly be called cache-only. Six scripted generator checks are the only random-number consumption in this protocol.

## A. Scripted normal-transform/generator oracle: six calls

Override Random.NextDouble with a finite literal queue. Every unexpected draw throws; require exact exhaustion after each call. Do not call ScientificMath.Gaussian or Generate in the expectation builder. Derive a=sqrt(2 ln2), so uniforms (0.5,0) yield +a and (0.5,0.5) yield -a using radial/angle Box–Muller algebra. Independent expectation may evaluate ln/sqrt; do not repeat production cosine code for these angles.

Five calls share design, in this exact order: (Entity E0,Group0,Count2,Mean101,WSS7), (E1,Group1,Count3,Mean102,WSS8), (E2,Group2,Count2,Mean103,WSS9). Model Means=[10,20,30], Within=[4,9,16], Between=[1,4,9]. Other fit metadata: NLL0, Converged=true, AtBoundary=false, Method=ML, Iterations0. Input summaries' Mean/WSS deliberately differ from generated results. Every output preserves Entity,Group,Count and order; input arrays/records remain unchanged.

Literal uniform sequence, reset for each call:
[0.5,0, 0.5,0.5, 0.5,0, 0.5,0.5, 0.5,0, 0.5,0.5, 0.5,0, 0.5,0, 0.5,0.5, 0.5,0].
Normal sequence: [+a,-a,+a, -a,+a,-a,+a, +a,-a,+a]. Exactly20 uniforms/10 normals per call, since each cluster consumes n+1 normals. Never infer one normal per pair with a cached sine partner.

G01 track=none,effect1. Means=[10+(1-sqrt2)a,20+(-2+sqrt3)a,30+(3-sqrt8)a]; WSS=[4a²,18a²,16a²].
G02 track=within,effect2. First two outputs equal G01; last mean=30+(3-2sqrt8)a and WSS=64a².
G03 track=between,effect2. First two outputs equal G01; last mean=30+(6-sqrt8)a and WSS=16a².
G04 track=within,effect1: all outputs equal G01.
G05 track=between,effect1: all outputs equal G01.
These separate mean noise, random-intercept noise and residual chi-square algebra, demonstrate variance scales by effect², preserve unbalanced n, and demonstrate only the last model group changes.

G06 clamp: one cluster(EZ,Group0,Count2,Mean101,WSS7); model Means=[0],Within=[1],Between=[1]; track=none,effect1. Literal uniforms=[0,0,0.5,0,0.5,0.5]. Expected mean=sqrt(30 ln10)+a/sqrt2, WSS=a². Exactly6 uniforms/3 normals. This tests the zero-uniform floor without seed search. Total direct calls consume106 uniforms/53 normals.

Compare finite numerical values with abs(actual-expected)<=2e-12*max(1,abs(expected)); metadata and consumed counts exact. Classification must be finite. No moment/distribution assertions from six deterministic samples.

## B. Cache-only execution harness

Use a new dedicated typed in-memory IRunRecording test double, not the existing permissive Cached implementation. Try(result) returns false; Cached<T> looks up the exact key and compatible type. Missing key/type throws a dedicated exception BEFORE touching calculate. It never invokes calculate under any circumstances. Put is forbidden; Finish records exactly one report and returns it; Dispose exactly once. Assert all supplied entries were read exactly once, no unexpected key, Begin once with exact request fields, Finish once and Dispose once. The full lookup order is initial-fit, optional interval/0..N-1, then within/null-fit,within/observed,within/reference/0..R-1, interleaved within/null/i,alternative/i,grid/i if usable, then the corresponding between keys. No final-result shortcut.

Independent harness self-checks, not extra scientific Run scenarios: exercise missing key and wrong type against the fake directly, supplying a callback that would increment then throw; it must remain uncalled. These prove the fake fails closed. Static/source review verifies all Fit/Statistic entry points in Run are confined to Cached callbacks; the only Generate outside callbacks is the interval branch. Report zero callback invocations as an architectural guarantee, not a profiler measurement. Never fall back to a real calculation to fill a missing cache item.

Literal common observed data, four clusters with two repeats each: G0/E0=[-1,1], G0/E1=[1,3], G1/E2=[9,11], G1/E3=[11,13]. Construct AnalysisData directly for this internal Run seam, with group order G0,G1 and minMeasurements2 metadata; do not call AnalysisEngine.Build, whose public data-processing gate requires at least four entities per group. These two-entity-per-group scripted report fixtures do not validate CLI/import acceptance. Exact summaries: means0,2,10,12; WSS2 each; n2 each. Per-group observed center sample variance2, withinMoment2, betweenMoment1; entities2,measurements4. Use seed54, withinEffect2,betweenEffect3. No seed search or fixture selection.

Unless overridden: N=100,R=99,alpha=.05; initial-fit Means=[1,11],Within=[2,2],Between=[1,1],NLL0,Converged=false,AtBoundary=false,Method=REML,Iterations0. Thus group Status=not_converged_or_degenerate, within/between/ICC=NaN; intervals remain not_computed with count0. Means and moment diagnostics still match above. Null fits for each track: Means=[1,11],Within=[1,1],Between=[1,1],NLL0,Converged=true,AtBoundary=false,Method=ML,Iterations0. All synthetic fits are scripted seam inputs, not estimated from observations.

Default track reference statistics: R zeros; observed=1; p=1/(R+1), adjusted=min(1,2p). Default evaluation: null statistic1 for i<10 else0; alternative1 for i<80 else0; grid1 throughout. Null/alternative failures0, FPR=.1,Power=.8. Default grid curve all1; N100 gives20 per point and Mde=NaN,MdeStatus=insufficient_simulations. Each successful usable track Status=conditional_plugin_bootstrap and Verdict=difference unless overridden. ReferenceReplications counts FINITE values; ReferenceFailures=R-that count. EvaluationReplications=N always. EffectGrid exactly[1,1.02,1.05,1.10,1.20]. EffectSdMultiplier is2/3 respectively.

### Fourteen fixed Run scenarios

R01 inclusive tie and strict alpha: alpha=.04. Both reference lists: indices0..97=0,index98=2; observed2, giving p=2/100=.02,AdjustedP=.04,Verdict=insufficient exactly at alpha. Null statistics3 for i<10 else2; alternative3 for i<80 else2; grid3. Strict p<alpha/2 yields FPR=.1,Power=.8: tied2 is not rejected,3 is. Both statuses conditional_plugin_bootstrap, ref99/fail0. Cache reads803.

R02 plus-one and full family despite unavailable peer: alpha=.015. Within reference all0,observed1; null/alternative/grid all1. p=.01,AdjustedP=.02,Verdict=insufficient,FPR=Power=0,curve all0. Between null-fit Converged=false,observed=NaN; no between reference/evaluation cache entries. Between ref0/fail99,NullFailures=AlternativeFailures=100,all rates/p/curve=NaN,Status=bootstrap_or_fit_failure,Verdict=insufficient,MdeStatus=insufficient_simulations. Family size remains2 even though one track unavailable. Cache reads404.

R03 exactly90% reference acceptance: R100; both references indices0..89=0,90..99=NaN. Other defaults. Both ref90/fail10,p=1/91,AdjustedP=2/91,Verdict=difference,failures0,FPR=.1,Power=.8,status conditional_plugin_bootstrap. Cache reads805.

R04 below90% reference rejection: R100; indices0..88=0,89..99=NaN. Both observed1 retained but p/adjusted/rates/curve=NaN,ref89/fail11,NullFailures=AlternativeFailures=100,Status=bootstrap_or_fit_failure,Verdict=insufficient,MdeStatus=insufficient_simulations. No evaluation keys allowed. Cache reads205.

R05 exactly10% evaluation/grid failures: defaults except both null and alternative indices90..99=NaN (other defaults retained); grid indices0..89=1,90..99=NaN. Both NullFailures=AlternativeFailures=10; FPR=10/100=.1,Power=80/100=.8,curve five values18/20=.9. Finite rates use requested denominator100, not90; status remains conditional_plugin_bootstrap. Cache reads803.

R06 null failures above10%: defaults except null indices89..99=NaN,alternative90..99=NaN. NullFailures11,AlternativeFailures10. Both rates and both Wilson intervals NaN, Status=excess_simulation_failures; p=.01,AdjustedP=.02,Verdict=difference still retained; grid default all1 remains finite, MDE insufficient_simulations. Cache reads803.

R07 alternative failures above10%: converse of R06: null90..99=NaN,alternative89..99=NaN. Failure counts10,11; other R06 expectations identical. Cache reads803.

R08 grid minimum below cutoff: N499; default reference/observed and evaluation definitions still yield FPR10/499,Power80/499. For grid let point=i%5,j=floor(i/5), thresholds=[0,50,90,70,95]; statistic1 iff j<threshold[point],else0. Per-point totals[100,100,100,100,99]; curve[0,.5,.9,.7,95/99]. MDE NaN,insufficient_simulations despite a crossing. Cache reads3197.

R09 grid minimum attained/no forced monotonicity: N500, same thresholds. FPR=.02,Power=.16; curve[0,.5,.9,.7,.95], MDE=.0425,estimated_on_grid. First upward crossing interpolates between1.02 at.5 and1.05 at.9; noisy decrease at1.10 is preserved. Cache reads3203.

R10 exactly10% grid failures: N500; thresholds=[0,50,80,70,95]. Point2,j90..99=NaN; its j80..89=0; others as R09. Curve[0,.5,.8,.7,.95],MDE=.05,estimated_on_grid. Point2 denominator100,not90. FPR=.02,Power=.16,Status=conditional_plugin_bootstrap. Cache reads3203.

R11 above10% grid failures: N500; as R10 but point2,j89..99=NaN (j80..88=0). Curve[0,.5,NaN,.7,.95],MDE=NaN,target_not_reached_or_invalid_curve. Evaluation rates/status stay finite/conditional_plugin_bootstrap; grid failures do not change main NullFailures/AlternativeFailures (both0). Cache reads3203.

R12 tested near-zero versus nuisance near-zero: defaults except BOTH null fits Within=[1e-8,1e-8],Between=[1,1],AtBoundary=false. Within tested component lies exactly at inclusive1e-8*max threshold: Status=boundary_baseline_power_not_identifiable,Power/PowerLow/PowerHigh/entire curve/MDE=NaN,MdeStatus=zero_baseline. Its p=.01,AdjustedP=.02,Verdict=difference,FPR=.1 and FPR Wilson remain. Between has only nuisance within tiny: Status=conditional_plugin_bootstrap,Power=.8,curve all1,MdeStatus=insufficient_simulations. Cache reads803.

R13 above near-zero threshold and geometric flag independence: as R12 but Within=[2e-8,2e-8],AtBoundary=true. Both tracks Status=conditional_plugin_bootstrap,Power=.8,curve all1,MdeStatus=insufficient_simulations despite AtBoundary=true. Tests source relative-component criterion, not optimizer geometric flag. Cache reads803.

R14 observed statistic unavailable with valid null/reference: both null fits converge, references99 zeros,observed=NaN. Neither track has evaluation cache keys. Both ref99/fail0,NullFailures=AlternativeFailures=100,p/adjusted/rates/curve=NaN,Status=bootstrap_or_fit_failure,Verdict=insufficient,MdeStatus=insufficient_simulations. This isolates the finite-observed usable gate from reference/convergence failure. Cache reads203.

### Explicitly deferred interval branch

No interval cases are authorized or included. A later interval contract can use a converged initial fit with90/89 cached converged refits to check percentile/status gates, but it necessarily performs actual seeded Generate before each interval cache lookup. That requires a separately bounded protocol. The current nonconverged initial fit is a transparent branch-isolation mechanism, not a statement that initial REML failure normally coexists with usable ML tests. Round48 separately checks Fit; this round independently checks downstream reporting.

## Independent expected formulas, tolerances, budget and gates

Reference p=(1+k)/(m+1), k=count of finite scripted references >= scripted observed; family adjustment=min(1,2p). Null/alternative successes use strict p<alpha/2. Rate successes/N, including failed draws in N. Count finite reference values independently of production.

For every finite FPR/Power, independently compute Wilson using z=1.959963984540054, p=k/N,D=1+z²/N,center=(p+z²/(2N))/D,halfwidth=z*sqrt(p(1-p)/N+z²/(4N²))/D, limits clipped to[0,1]. Check all numeric report fields, including intervals and moment rows, with2e-12*max(1,abs(expected)); status/verdict/counts/metadata exact and all expected NaNs explicitly classified. MDE tolerance2e-12 absolute. Never replace NaN by zero or compare it with an ordinary numeric tolerance. Exact-threshold branch decisions are prescribed by input literals and expected statuses, not softened by comparison tolerances.

Budget: six direct scripted Generate calls; fourteen Run calls; exactly19,241 Cached reads across successful scenarios; zero production calculation-callback invocations; zero Fit/Statistic/optimizer calls. Total actual Gaussian evaluations53/uniform draws106. Run scenarios instantiate PRNGs for reference/evaluation callbacks but consume no draws because callbacks are not invoked. Do not claim statistical independence from observing no callbacks. All Run initial estimates are nonconverged and therefore skip the uncacheable interval Generate branch entirely.

Whole dedicated contract execution cap30 seconds, no retries/seeds/extensions. Build/restore time separate. Stop immediately on unexpected cache miss, extra call, exception, timeout or failed assertion, preserve partial results and classify failed/inconclusive rather than substituting a scenario. Exactly the14 scenario reports must be retained for a complete pass. If needed, an amended protocol requires review before execution; never loosen tolerances after observing outcomes.

Deliver a machine-readable record with hashes, case IDs, input scripts, actual/expected numeric classes, statuses, count/order evidence, callback/Generate budget, runtime versions and per-scenario results, plus a short integration report. Harness implementation/expectation review occurs before run. Separate already-established regression runs are engineering checks, not new Round49 scientific evidence, and must be labelled/budgeted separately.

## Truthful label after a pass

Recommended release/evidence description: “Deterministic Gaussian variance generator and report-contract integration checks passed (scripted cached fit/statistic inputs; zero optimizer calls).” Fit evidence remains separately “20-case numerical fit reference check.” Do not relabel either as “bootstrap scientifically validated,” “calibrated variance inference,” or “end-to-end bootstrap validation.” The existing report status conditional_plugin_bootstrap describes assumptions/calculation type; it does not mean externally calibrated. A documentation/UI explanation may state that distinction without changing thresholds, status enums, or model behavior. Any production-label change needs its own approved scope; this protocol authorizes none.

## Literal fixture schema

External prepared input: mvs-r49-fixtures-proposed.json. Root fields exactly schemaVersion=1,protocolId=round49-variance-bootstrap-contract-v1,status=frozen,budgets,generatorCases,runCases. Exact budgets: {generateCalls:6,runCalls:14,cachedReads:19241,uniformDraws:106,gaussianDraws:53,fitCalls:0,statisticCalls:0,optimizerCalls:0,calculationCallbacks:0,intervalGenerateCalls:0}. Generator fields id,design,model,uniformTape,track,effect,expectedException. Design fields entity,group,count,mean,withinSumSquares. Model/cache-fit field names use the native Pascal-case VarianceFit properties. Run fields id,data,repetitions,referenceReplications,withinEffect,betweenEffect,seed,alpha,cache,expectedException. Data fields groupNames,observations,warnings; observation fields entity,group,value,sequence. NaN doubles are serialized as the named-value string "NaN", never invalid JSON nonfinite numbers. expectedException=null for every main case. Expected answers are frozen in this protocol and independent oracle, not produced by the candidate. Order G01–G06/R01–R14.
