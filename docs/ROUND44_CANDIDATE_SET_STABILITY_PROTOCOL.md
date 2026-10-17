# Frozen Round44 protocol: fixed-recipe candidate-set stability diagnosis

Protocol ID: `mvs-r44-candidate-set-stability/v1`  
Prepared: 2026-10-16 UTC  
Status: frozen before retained recommendation outcomes are evaluated; implementation, synthetic tests and full binding must pass independent review before execution.

## 1. Question, scope, and interpretation boundary

Describe the split-half stability of the **existing, unchanged** `CalibrationRecommendations.MethodId == "family-power-ci-overlap-v1"` on the newly retained full CalibrationRow pairs from Round43, separately for location, variability, and heterogeneity. The fixed analysis population is the 120 requested split indices 0–119, with one retained left and right calibration each. These are same-recipe historical replays, not 120 newly designed experiments or new external validation data.

No regeneration, new calibration, resampling of measurements, additional seeds, selection of a favorable track, parameter search, new statistic activation, change in metric registry, change in inference/multiplicity policy, or source change is authorized by this protocol. Do not call AnalysisEngine.Calibrate, BenchmarkRunner.Calibrate, BenchmarkDatasets.Generate, or SplitEntities. Loading retained rows and evaluating the existing recommendation layer is the only scientific computation being diagnosed. Synthetic deterministic rows are allowed solely as software tests and must be unmistakably separated from retained evidence.

This is a **posthoc development diagnosis**, frozen before these recommendation outcomes are inspected. It is not prospective scientific evidence, a new confirmation of an old hypothesis, or a scientific go/no-go reversal. Prior historical stability results were already known; source discovery also exposed old historical manifest summaries. No Round43 retained CalibrationRow values or candidate recommendation outputs were read while drafting this protocol. Same-recipe matching of the old retained diagnostics does not prove identity to unavailable original historical score or calibration vectors.

The interval-overlap rule is a selection heuristic. Overlap of individual Wilson power intervals is not a test of equality, equivalence, noninferiority, or a confidence interval for a difference. Shared simulations, selection of the empirical best, and dependence between metrics are not accounted for by an overlap comparison. Do not repeat the production reason string “statistically competitive” as an established inferential claim; quote it only as a literal software label with this caveat.

## 2. Fixed source and native API contract

Read-only baseline: the delivered Round43 full source archive. Round44 uses a separate source copy with unchanged production code.

The separate Round44 working copy is `Round44 source copy`. All eight source pins below were verified byte-identical between the two copies during protocol preparation. Use the unchanged Core there if needed, while keeping all new work in a bounded validation harness/reference/report; do not modify the pinned implementation.

Use the original Core assembly, with verified provenance to this source, and invoke both original methods for every accepted half and track:

- `CalibrationRecommendations.Build(IReadOnlyList<CalibrationRow> rows, string track)`
- `CalibrationRecommendations.Summarize(IReadOnlyList<CalibrationRow> rows, string track)`

The optional multi-track overloads `Build(rows, IEnumerable<string>)` and `Summaries(rows, IEnumerable<string>)` may be checked against concatenated single-track calls; they must not replace the required direct API evidence. These classes are internal. The existing `InternalsVisibleTo("MvsAnalyzer.Core.Tests")` route or explicit reflection can provide access from a separate diagnostic harness without modifying source. Merely duplicating Build in a new executable does **not** satisfy native execution.

Relevant implementation locations:

- `Core/CalibrationRecommendations.cs`: Build, Summarize, MethodId, quality/status labels.
- `Core/Models.cs`: CalibrationRow fields, TrackIndex, PowerIn, and fallback behavior.
- `Core/MetricRegistry.cs`: LegacyKeys, family membership, FamilyForTrack, IsNaturalForTrack.
- `Core/ScientificInfrastructure.cs`: DecisionPolicy.FprLimit.
- `Core/AnalysisEngine.cs`: CandidateMinPower, MetricKeys, calibration missingness semantics.
- `validation/stability_replay/Program.cs`: Round43 schema, full row serialization, nonfinite_fields encoding and original replay settings. Read this source, not its generated outcomes, before freeze.

Current source SHA-256 pins, to verify again at freeze and after execution:

| File | SHA-256 |
|---|---|
| Core/CalibrationRecommendations.cs | c1b5089a40ba56c5e1bba957216a019d01994bc18729b86afdbf862afe462c1c |
| Core/Models.cs | d4f51d62c5972d866af3bf59a224b7a314df43c02d4475547ed83405a969d706 |
| Core/MetricRegistry.cs | 5a61012f1914f72850df690358a16c1fe162aa09ba5b2a1ce6e9f8f68d05fa04 |
| Core/ScientificInfrastructure.cs | 7e2947c272e7f3aaecade2829367cf0cdfd3206c67006f6c163b826da3d60d1a |
| Core/SimulationScenarios.cs | ef6efee8232388c9ba450f6724f987e12269dbe4338ea262b23dae366e8d57b2 |
| Core/AnalysisEngine.cs | bc4caa7600034781861784cedaf64cc19d22ecc5eb26841ada291c0c6d66bd05 |
| SharedSources.props | a86d92f474867e834c2c7d6155122a709cae56394d6d4a5f6aa203b691881dd6 |
| MvsAnalyzer.Core/AssemblyInfo.cs | 76fd41a5433081215c3e89869931a0b9e098aef1a8abcb005c29824cb360a5fd |

Before outcome access, add exact input paths and byte hashes, harness/reference/test hashes, original loaded assembly hash and source/build provenance, executable/runtime identity, protocol hash, timestamp, command, expected artifact list and output directory to an immutable binding manifest. Hashing data bytes before freeze is permitted; parsing values to learn results is not. The parent must resolve and freeze any binding or schema issue before running outcomes. Preserve input bytes. Outputs must be separate and create-new; never overwrite Round43 evidence or source. Verify all input/source pins after the run.

## 3. Fixed tracks, universe, and selector semantics

Track order is exactly `location`, `variability`, `heterogeneity`. Legacy metric order is exactly:

`median, standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, mean, rms, range, geometric_mean, trimmed_mean_20`.

Natural-family universe F(t):

- Location: `{median, mean, geometric_mean, trimmed_mean_20}`; size 4.
- Variability: `{standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, range}`; size 7.
- Heterogeneity: the same location-family universe of size 4. This is the current generator/registry mapping, not an assertion that the final heterogeneity inferential method is settled.
- `rms` is magnitude-family and outside all three natural-family candidate sets. No staged 1.5 metric is activated.

For one accepted retained half and track, the original method computes:

1. `alpha` from the first calibration row, with all rows required by this protocol to have the same retained alpha .05.
2. `limit = min(1, max(1.5 * (alpha / 12), alpha / 12 + .02))`. The divisor remains all 12 active metrics; do not replace it with family size.
3. For each row, track power P, lower L, and upper U from that row’s matching track arrays; applicable iff row.Applicable and P/L/U are finite.
4. Null-controlled iff applicable, `!FprInflated`, finite retained FprHigh, and `FprHigh <= limit`. The production fallback to Fpr is not allowed to rescue structurally missing/invalid bounds in this study.
5. Pool E = natural-family AND null-controlled rows. If E is empty, the candidate set and single-best comparator are empty/none.
6. Anchor b is maximum P in E; exact ties use the earliest legacy metric index. No tolerance or rounding is applied to selection comparisons.
7. Candidate set C = `{m in E : U_m >= L_b}`. The inclusive boundary is preserved. Valid interval ordering guarantees b belongs to C.
8. Qualified subset Q = `{m in C : L_m >= .70}`. The .70 condition is a quality label, not a candidate-set membership gate.
9. Status is qualified if Q nonempty, uncertain if C nonempty and Q empty, otherwise unavailable.

Keep native output row order and strings for audit. Canonicalize candidate and qualified sets into legacy-order keys only for stable storage and equality checks; equality means set equality, not incidental array ordering. Do not collapse a native unexpected duplicate into a valid set.

### Single-metric comparator, explicitly bounded

The apples-to-apples single-metric comparator is **Build’s own maximum-power, natural-family, null-controlled anchor b**, with the same eligible pool and legacy-order tie break. It is not global primary-score top-1 and not the old >=.70 gated score rule. Obtain b independently from the accepted raw rows and verify it equals native Summarize.BestMetric. Enforce original legacy row order on input so Summarize’s stable input-order tie break agrees with Build’s registry-order tie break. Never reorder input to repair an invalid record.

Define singleton recommendation T = `{b}` if b exists and empty otherwise. Candidate C and singleton T are evaluated on the exact same split/track population, with identical empty conventions and matching descriptive chance baselines. As these are different recommendation targets, differences in agreement do not establish the superiority or scientific validity of either method. The previously known historical global-score agreement may appear only as clearly labeled context, with its own method and denominator, never as the direct comparator.

## 4. Fail-closed input handling

The primary analysis requires all 120 complete pairs on all three tracks. Validate the entire frozen input set before publishing any aggregate. Every index and side must be present once, correct, completed, retained, bound to the expected Round43 recipe and authorized input hash. Reject partial files, synthesized replacements, missing pairs, unexpected extra cases, duplicate JSON object members, unknown schema/version, incorrect index/side association, mismatched settings, corrupted hash, or method/source drift. Do not filter to a favorable subset or silently shrink N.

Each half must contain exactly 12 distinct known metric rows in the exact frozen order. Required fields must be explicitly present with the correct type; do not rely on CalibrationRow constructor defaults. Require alpha=.05 and repetitions=1000 on every row. Require the full three-track arrays in exact canonical track order, with matching lengths and unique track names. In particular Tracks, TrackPowers, TrackPowerLow, TrackPowerHigh, TrackScores, TrackFailures must be non-null complete arrays. Require retained Fpr, FprLow, FprHigh, Applicable, FprInflated, NullFailures and all other serialized CalibrationRow fields to be present. The loader restores the full original row, not a hand-selected partial row.

Round43 uses JSON null for every nonfinite double and a `nonfinite_fields` list specifying its exact property/array path and NaN/Infinity/-Infinity label. Require a one-to-one match: every null in a double field needs one matching sidecar label; no label may point to a finite value, wrong row, unknown field, duplicate path, or out-of-range index. Restore the documented nonfinite value. Never convert null to zero, infer NaN from absence, or equate NaN and infinity. Nullable arrays are different from tagged nonfinite elements and are rejected when required. Infinity in selector-required FPR/power/bound fields is malformed, not ordinary unavailability. This study does not reconstruct NaN payload bits; finite doubles must survive exact round-trip.

Accept legitimate calibration unavailability **as a recorded outcome**, not as malformed input, only when its semantics match original AnalysisEngine generation:

- NullFailures and all TrackFailures must be integers in [0, Repetitions].
- If Applicable=true, the retained FPR and its two bounds must all be finite probabilities with `0 <= FprLow <= FprHigh <= 1` and Fpr in [0,1], with the endpoint arithmetic rule below; null-valid count must meet the original >=.9*Repetitions requirement.
- If Applicable=false, the corresponding unavailable FPR/power/bound fields must have explicit NaN provenance consistent with original serialization. Finite optional diagnostics are not silently promoted into applicability. A complete non-applicable row remains a valid row and cannot be a candidate.
- A track is power-available only when Applicable=true and its retained valid count, Repetitions−TrackFailures, meets the original >=.9*Repetitions rule. Such a track must have finite `0 <= L <= U <= 1` and P in [0,1], with the endpoint arithmetic rule below and finite TrackScore.
- Otherwise its P/L/U/TrackScore must all be explicitly recorded NaNs, and it remains a valid unavailable track outcome. A mixed finite/nonfinite triplet, an absent field/bound, or unexplained NaN is malformed. No fallback to primary Power, Fpr, point bounds, or another track is allowed.
- Verify FprInflated against the original finite Fpr comparison and fixed limit; do not recompute or replace it in the row. A mismatch blocks analysis. Primary scalar Power and Score must match the first track under the original finite/nonfinite encoding.

Malformed structure, loader error, native exception, unexpected output, parity mismatch, or missing comparator is an **analysis failure**. It must not be encoded as empty C, unavailable status, disagreement, or zero Jaccard. Report indices/sides/tracks and precise failure reasons, and stop the primary aggregate publication. There is no automatic reduced-N rescue, recalibration, or exclusion amendment after outcomes are seen. Complete-case exploratory follow-up would require a separately identified amendment and report all omissions; it is not part of this bounded protocol.

Valid empty C means E is genuinely empty under unchanged software on fully validated input. Report the reasons (no applicable natural-family rows versus applicable rows failing null control, allowing counts for both), without changing eligibility. Both-empty is valid shared abstention, not evidence of a stable useful metric recommendation.

## 5. Per-track outputs and fixed denominators

On successful validation, N=120 paired cases, 120 left halves and 120 right halves per track, 240 halves per track, 360 pair-track observations and 720 half-track evaluations in total. The 360/720 counts are bookkeeping, not independent scientific sample sizes. Do not pool tracks into a single scientific headline.

Retain one per-case/per-track record with left/right C and Q, their sizes, statuses, single best b, pool sizes, native Build fields, exact match flags, intersection/union sizes, Jaccard values, and eligibility/exclusion reasons. Preserve full native Build/Summarize outputs. There are 720 required direct Build invocations and 720 required direct Summarize invocations; Summarize internally calls Build again.

For each track, report:

1. Left and right histograms of |C| over 0..|F|, each denominator 120; mean, median, min/max and quartiles using documented type-7 quantiles; |Q| separately, using the same side denominators. Report size-pair cross-tab counts, mean absolute size difference /120, and full-family frequency /120 per side. Size summaries include zeros. Optional 240-half pooled summaries must be labeled and cannot replace side summaries.
2. Candidate inclusion count and frequency for each of the 12 original keys per side, denominator 120. Outside-family zeros are useful invariant checks. Qualified inclusion frequencies are separate.
3. Counts of qualified/uncertain/unavailable native statuses per side, denominator 120. Count empty-left, empty-right, both-empty, left-only-empty, right-only-empty, and both-nonempty. The four disjoint pair categories sum to 120.
4. Exact candidate set agreement A_C = sum_i 1(C_Li=C_Ri) /120. Both-empty contributes 1, and its contribution must be shown separately.
5. Jaccard J(C,D) = |C∩D|/|C∪D| when union nonempty; **J(empty,empty)=1**; J(one empty,other nonempty)=0. Mean J_C is sum_i J/120. Report the mean/median/quartiles and each empty contribution. Do not replace empty/empty with missing or zero after seeing results.
6. Informative companion summaries: exact agreement and mean J over both-nonempty pairs B, denominator n_B; mean J over union-nonempty pairs U, denominator n_U. If a denominator is zero report undefined with count zero, never 0 or 1. Also report nonempty exact-match count /120 and real-single-best match count /120 so shared abstention cannot masquerade as usable stability.
7. For T singleton-or-empty, exact agreement A_T and mean J_T use the same 120 pairs and empty policy. They must coincide mathematically. Show both-empty contribution, real-best match count, marginal winner frequencies (including a separate none category), and both-nonempty conditional agreement /n_B.
8. Descriptive paired differences: A_C−A_T and mean(J_C)−A_T on all 120 pairs; corresponding both-nonempty differences on the same B if n_B>0. Label exact-set agreement versus singleton agreement and set-overlap versus singleton agreement explicitly; do not call one a strictly harder or better scientific criterion without justification.

All rates retain integer numerator and denominator. Mean J retains the sum of per-pair rational overlap contributions plus denominator. Summaries must be reproducible from the per-case table without rounding input. Print rounding is presentation only.

## 6. Empirical marginal-frequency chance comparison

For each track, enumerate **all ordered 120×120 = 14,400** left–right pairings, including the original 120 diagonal pairs. Do not use only off-diagonal pairs, Monte Carlo pairing, permutation tests, or independence assumptions between metric inclusions. The reference is the product of the two observed empirical marginal distributions over whole candidate sets. It preserves set sizes and metric co-occurrence inside each side’s set.

Let p_L(S)=count_i(C_Li=S)/120 and p_R(S)=count_j(C_Rj=S)/120. Then:

- Exact-set reference B_A = sum_S p_L(S)p_R(S) = sum_ij 1(C_Li=C_Rj)/14,400.
- Jaccard reference B_J = sum_ij J(C_Li,C_Rj)/14,400, using exactly the frozen empty policy.
- Singleton reference B_T = sum_k p_L^T(k)p_R^T(k), with k covering family metric keys and explicit none. This equals all-cross-pair singleton exact/Jaccard mean.

Compute the category-frequency and explicit-cross-pair exact baselines independently and require equality. Per-metric inclusion frequencies may be reported alongside them; multiplying independent Bernoulli metric probabilities is **not** the set-match reference. A ratio of expected intersection to expected union is **not** expected Jaccard and must not substitute for B_J.

Report raw observed value O, reference B, excess O−B, and descriptive chance-adjusted `(O−B)/(1−B)` separately for exact C, mean J_C and singleton agreement. Do not clip negative adjusted values. When B=1, adjusted value is undefined with reason `degenerate_marginals`; report O and B unchanged. Use exact count/rational representation where practical to distinguish B=1 from floating-point near-1; do not introduce an arbitrary epsilon rule. If adjusted values are undefined, do not rank methods by them.

For the both-nonempty companion comparison only, repeat the same procedure restricted to original pair indices B: empirical left/right marginals from those n_B matched indices and all n_B² cross-pairs; report the changed denominator and conditioning explicitly. If n_B=0, all conditional baselines/adjustments are undefined. The union-nonempty descriptive mean has no additional chance-adjusted headline in this protocol.

These baselines are empirical chance-overlap **descriptions**, not an identified randomization null or corrected causal/clinical effect. The 14,400 cross-pair contributions reuse 240 halves; they are not 14,400 independent observations. Inclusion of the diagonal is intentional. No p-values, significance assertions, standard errors, bootstrap/permutation intervals, or newly invented stability pass threshold are authorized. Existing Wilson bounds are selector inputs, not uncertainty intervals for agreement.

## 7. Independent reference and test requirements

Before retained outcomes are opened, freeze a simple independent reference implementation plus hand-constructed tests. The native harness must call the original assembly APIs; the independent reference must read validated raw retained fields directly, use an explicit family-key map and simple maximum/filter/set operations, and must not call Build, consume native candidate flags as input, copy production selector code wholesale, or share its selection helper. It can be a small Python script. It must independently verify the top tie-break, candidate and qualified sets, status, set arithmetic, marginal baselines, empty policies, and all summary denominators.

Require exact parity of discrete selection outputs on every accepted half/track. Compare finite output fields to source inputs/expected expressions without decimal rounding; compare nonfinite classes explicitly. Summary arithmetic must agree as exact counts/rationals where possible; any unavoidable floating-only comparison must use a pre-frozen absolute tolerance no greater than 1e−12 and include raw deltas. Such a tolerance never changes selection or exact-equality decisions.

Pre-outcome synthetic fixtures must cover at least:

- Correct 4/7/4 family maps and magnitude exclusion.
- Unique best, power ties resolved by registry order, and native Build/Summarize tied-best agreement with canonical input order.
- Inclusive interval touch U=L_best, interval separation, full-family sets, and a case in which a weaker-point-power metric joins through the overlap heuristic.
- Null upper bound exactly at limit and immediately above it (adjacent representable doubles); inflated flag exclusion even where otherwise applicable.
- L=.70 versus immediately below; candidate stays included while qualified label changes.
- Genuine no-applicable and no-null-controlled empties; both-empty, one-empty, equal/disjoint/partially overlapping sets.
- Legitimate nonfinite unavailable track versus malformed missing bounds; nonfinite sidecar round-trip including rejection of malformed paths, duplicate paths and unexpected Infinity in selector inputs.
- Duplicate/missing/unknown/reordered metrics, duplicate/missing tracks, mismatched array lengths, conflicting alpha/repetitions, invalid probabilities or interval order, inconsistent failure counts, duplicate JSON keys, case pairing mismatch, input hash mutation and missing cases.
- Small hand-computable set distributions with skewed marginal frequencies showing that high raw agreement can arise without paired information; explicit cross-pair exact baseline equals category-frequency product; mean J differs from ratio of expected intersection/union.
- Both nondegenerate and B=1 degenerate marginals; negative adjusted agreement retained; conditional n_B=0 behavior.
- No dependency on globally projected scores, no .70 membership gate, and no source invocation that can recalibrate or generate new data.

Native output may be computed twice on the same retained inputs as a deterministic software check; this creates no additional observations and must not inflate any denominator. Expected repeated native outputs must be bit/discrete identical under the documented runtime.

## 8. Deliverables, acceptance, and stop conditions

Required outputs, in a separate Round44 analysis directory:

1. Frozen protocol and SHA-256, bindings/provenance manifest and exact commands.
2. External native harness, independent reference, synthetic fixtures/tests, build/runtime identity and logs.
3. Input validation results listing all 120 pairs and all required structural/semantic checks, without rewriting inputs.
4. Native full Build/Summarize results, per-case/per-track metrics, side size/status/inclusion distributions, exact/Jaccard/single-best summaries, all-cross-pair and category-frequency baseline audit evidence, and parity report.
5. Short interpretation note stating all three tracks, all denominators, empty conventions, set-size tradeoff, known heuristic/inference limitations and scientific no-go status unchanged.
6. Post-run hash verification and a machine-readable statement that no source/statistic activation, regeneration or calibration was performed.

Technical acceptance requires: correct frozen provenance; 120/120 complete valid pairs; 3/3 tracks; 720/720 half-track native evaluations from each required API; no silent fallbacks; zero native/reference discrete mismatches; zero Build/Summarize comparator mismatches; exact denominator reconciliation; correct 14,400 cross-pair count per track; all synthetic tests pass; input/source hashes unchanged. Technical acceptance does not require high agreement and does not constitute scientific acceptance.

Report whatever stability, size, emptiness and chance-description results the fixed procedure produces, including unfavorable or degenerate results. Stop once the complete validated outputs, independent check and bounded interpretation are delivered. Do not continue searching metrics, thresholds, data designs or follow-up experiments under this protocol. Any malformed-input, provenance, source-change or parity failure blocks completion and must be escalated with its precise evidence. No observed agreement threshold was frozen because this is diagnosis, not a new confirmatory test.

## Pre-execution amendment: binary64 Wilson endpoints and resource bound

Before any retained recommendation outcomes were opened, source-only evaluation of the unchanged Wilson formula at k=0,n=1000 found lower bound 2.168404344971009e-19 while p=0. Strict containment would reject legitimate stored arithmetic. For FPR and track power, permit containment residue at most 1e-15; require independently count-derived Wilson endpoints to agree within1e-15. Reconstruct k=round(p*1000), require exact binary64 p==k/1000 and 0<=k<=1000-failures. Require finite ordered bounds within[0,1]. Include k=0 and k=1000 synthetic tests. This tolerance validates serialization/arithmetic only: every original raw p/bound remains unchanged in all native and reference selector comparisons. No selection tolerance is introduced.

The retained-input audit uses one native process at a time, DOTNET_PROCESSOR_COUNT=1, a global120-second execution budget,512MiB childRSS limit and at most5seconds owned cleanup. No retry, selected subset or calibration is permitted. Every launch and failure is retained. Resource cost is descriptive for this audit, not a performance comparison to calibration.
