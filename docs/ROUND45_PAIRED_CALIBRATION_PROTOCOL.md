# Proposed Round45 protocol: paired calibration-dependence diagnosis

Protocol ID: `mvs-r45-paired-calibration-dependence/v1-proposed`  
Prepared: 2026-10-16 UTC  
Status: proposed; scientific review, exact implementation binding, and immutable freeze are required before retained-case execution or paired-outcome inspection.

## 1. Question and limits of interpretation

On the fixed 240 retained Round43 calibration halves, quantify the within-replication dependence between prespecified metric rejection indicators, and the resulting finite-replicate moment estimate for Monte Carlo uncertainty of each prespecified **power difference**. Compare that estimate with an independence counterfactual using exactly the same marginal rejection counts. Describe the common-null pairs separately.

Round44 found near-full-family candidate sets and exact left/right agreement of 114/120 for location, 96/120 for variability, and 120/120 for heterogeneity; agreement was at or below the empirical marginal baseline. Those results motivate a mechanism diagnosis. They neither establish global invalidity of the method nor provide scientific GO. The existing interval-overlap candidate rule is a heuristic, not a confidence interval or test for a difference.

This protocol does not select a winner, change candidate membership or thresholds, compare selected winners, claim statistical significance, or create p-values, new confidence intervals, superiority/equivalence claims, or scientific GO. No changes to calibration, random-number generation, the metric registry, inference/multiplicity, candidate selection, UI, or user defaults are authorized. Existing Wilson intervals are reconstructed solely to verify exact replay; they are not new inferential results for pair differences.

The data are reused synthetic development data. This is a posthoc diagnostic whose question and inputs were informed by prior development results. Round43 rows and Round44 results already exist; a Round43 case schema and its row contents were inspected during protocol preparation. No retained per-replication calibration-code vectors existed in Round43, and none have been generated or inspected in preparing this proposal. Do not present the analysis as prospective independent validation, a rescue of Round27/Round32, or a recovery of unavailable original historical vectors.

Why a replay is necessary: a pair of marginal rejection totals does not identify the joint count n11. Consequently the retained CalibrationRows cannot recover covariance or paired-difference variance. The rerun must obtain joint codes through the existing recording seam and then demonstrate exact equality to every retained Round43 CalibrationRow. Matching those rows binds the new traces to the same reproducible computation; it does not prove identity to unavailable original per-replication vectors.

## 2. Fixed source, inputs, and freeze boundary

Read-only implementation root: `/workspace/scratch/8105054a3211/mvs_round45/MVS-analyzer-main`, the unchanged Round44 copy when this proposal was prepared. New diagnostic code may subsequently be added only in bounded validation/test/report locations. No production source change is permitted. This proposal itself is outside that source root.

The complete input population is exactly:

- `/workspace/scratch/8105054a3211/mvs-r43-replay/case-NNN/native.json`, NNN = 000 through 119 inclusive.
- Both `data.left` and `data.right`, with `calibration_left` / `calibration_right` and the corresponding `nonfinite_fields` lists.
- The stored `seeds.calibration_left_seed` and `seeds.calibration_right_seed`, settings, metric order, identity, and canonical-data hashes from each input.
- The Round43 binding manifest and its checksum, and Round44 completion evidence, for provenance only.

There are 120 fixed case indices and 240 fixed halves. No missing case, failed half, metric, or pair may be replaced. Do not generate data, split entities again, recompute seeds from a replacement stream, add seeds, change the effect, or run extra repetitions. In particular, neither `BenchmarkDatasets.Generate`, `AnalysisEngine.Build`, nor `AnalysisEngine.SplitEntities` belongs in the retained replay path. Deserialize each stored full `AnalysisData` directly. Preserve observation/entity/group/metric order and every stored field, including derived-count consistency checks. Verify its `canonical_json` UTF-8 SHA-256 and equality to `values` before invoking the engine. The full R43 input file is the immutable authority.

Known source SHA-256 pins:

| File | SHA-256 |
|---|---|
| Core/AnalysisEngine.cs | bc4caa7600034781861784cedaf64cc19d22ecc5eb26841ada291c0c6d66bd05 |
| Core/Models.cs | d4f51d62c5972d866af3bf59a224b7a314df43c02d4475547ed83405a969d706 |
| Core/MetricRegistry.cs | 5a61012f1914f72850df690358a16c1fe162aa09ba5b2a1ce6e9f8f68d05fa04 |
| Core/RunRecording.cs | 5fb027bd2328dd9b5b7a9d3d0a4b8e1953715d6e1e227c34fccb54bb661ac5aa |
| Core/ScientificInfrastructure.cs | 7e2947c272e7f3aaecade2829367cf0cdfd3206c67006f6c163b826da3d60d1a |
| Core/SimulationScenarios.cs | ef6efee8232388c9ba450f6724f987e12269dbe4338ea262b23dae366e8d57b2 |
| Core/CalibrationRecommendations.cs | c1b5089a40ba56c5e1bba957216a019d01994bc18729b86afdbf862afe462c1c |
| SharedSources.props | a86d92f474867e834c2c7d6155122a709cae56394d6d4a5f6aa203b691881dd6 |
| MvsAnalyzer.Core/AssemblyInfo.cs | 76fd41a5433081215c3e89869931a0b9e098aef1a8abcb005c29824cb360a5fd |
| validation/stability_replay/Program.cs | 65851549a5c46a0bee0b812cbfd1ca4532b13b717c802e2212a5672300664297 |
| validation/stability-replay-protocol-v1.json | bb94422017c04e6b9229dd7cd0165ef751446cd957de437823f12b0dd13b938d |

Before retained execution, bind the final reviewed protocol hash, all 120 input byte hashes, each half's canonical-data hash and calibration seed, the complete allowed-source/baseline manifest, new harness/reference/test/driver hashes, loaded Core assembly hash and build provenance, executable identity, exact commands, runtime/environment fingerprint, fixed pair list, output schema, output paths, and resource limits. Require the Round43 runtime/probe identity and document any discrepancy as a blocker before execution. Record an immutable timestamped freeze manifest and its checksum. Synthetic hand fixtures and structural/schema checks are permitted before freeze; retained-case calibration is not. Freeze the equality rules in section 5 and estimator in section 7 before outcomes are opened. Changes after retained execution require an explicitly documented amendment and do not authorize a second run under this protocol.

## 3. Exactly one replay of each stored half

Invoke the existing native `AnalysisEngine.CalibrateWithRecording` with a test-only implementation of the existing `IRunRecordingFactory` / `IRunRecording` seam. Access may use the existing test friend assembly or reflection; do not edit Core to expose a new hook. The original calculation delegate must be executed exactly once per requested cache key, and its result returned unchanged.

Fixed settings for every half:

- Repetitions: 1,000; effect: 1.15; primary scenario: `location`.
- Tracks, in order: `location`, `variability`, `heterogeneity`.
- Outlier rate: 0.02; missing rate: 0; alpha: 0.05.
- Grid: [1.00, 1.02, 1.05, 1.10, 1.20], with point `rep % 5`; 200 replicates per point.
- Calibration seed: the exact stored side-specific Round43 seed.
- Stored AnalysisData preprocessing settings remain −1,000,000 / +1,000,000 / 6; they are loaded, not reapplied.

The recorder must disable restoration (`Try` returns false), never supply a cached result, never draw random numbers, never call a calculation delegate twice, and never mutate any `CalibrationStep` array or returned row. `Cached("simulation/" + rep, ...)` provides the existing `CalibrationStep.Null`, `.Power`, and `.Grid`. Native code constructs the same `drawSeed` for null, each track's power alternative, and its grid alternative. The recording seam observes this calculation without changing it. Diagnostic keys and `Finish` are passed through unchanged; unexpected simulation key/type/order/shape is a hard failure. Persistent production backups are disabled as in Round43.

Use one process per fixed case, replaying left then right, for 120 scheduled case processes and 240 half invocations. Record each half's started/completed/failed/not-started state separately. Any calibration or trace/identity/equality failure stops additional retained scheduling and preserves already-started work according to the watchdog policy. Do not rerun a failed case or fill unused budget with additional work.

## 4. Lossless per-replication trace and partial preservation

Retain all 84 signed codes per replication: 12 null, 3×12 power, 3×12 grid. Codes have their native meaning: −1 = nonfinite metric p-value; 0 = finite non-rejection; 1 = finite rejection. The Bonferroni decision remains the original engine's decision; do not reinterpret a code from a rounded p-value.

Metric order is fixed:

`median, standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, mean, rms, range, geometric_mean, trimmed_mean_20`.

Binary schema `mvs-calibration-codes-2bit/v1`:

1. Within each replication, flatten `Null[0..11]`, then `Power[track=0..2][metric=0..11]`, then `Grid[track=0..2][metric=0..11]`.
2. Map −1→00, 0→01, 1→10. Bit pattern 11 is reserved and invalid, never missing, padding, or a replacement value.
3. Place four symbols per byte, first symbol in the least-significant two bits, then shifts 2, 4, 6. Bytes concatenate in ascending replication order, 0 through 999.
4. Each complete replication is exactly 21 bytes; a complete half is 21,000 bytes, 84,000 symbols, and 168,000 significant bits. Across 240 complete halves there are 20,160,000 symbols and 5,040,000 raw trace bytes.
5. Metadata declares schema, source-input/hash, case, side, seed, settings, metric/track/grid order, code mapping, flattening/bit order, expected and observed replication/symbol/byte counts, significant bits, terminal status, and SHA-256 over the exact raw bytes. It also binds the replayed rows, source/runtime identity, and freeze manifest. Full traces have zero trailing padding bits. A generic decoder must reject nonzero padding if used for shorter synthetic fixtures, extra symbols/bytes, reserved 11 codes, and inconsistent lengths.

Reserve create-new output files before work. Append each complete 21-byte step and flush the application buffer to the operating system before returning that step to the engine. Per-frame fsync and power-loss durability are not required or claimed. Do not buffer an entire half in memory until success. Preserve the entire physical trace, including any torn suffix on forced termination or I/O failure, with its byte length and hash. Record complete prefix records and any residual-byte count separately; never decode a torn record as complete. Any computed step whose recording fails makes that half unsuccessful. Partial or unstarted replications are **unobserved**, not −1 codes, zero rejections, or filler. A failed/partial trace is retained for audit but cannot contribute a primary moment estimate. No partial evidence is deleted during cleanup.

Finalization, including a post-exit driver pass if the child was killed, must enumerate and hash all files and account for every scheduled case/half and every retained prefix. Record stdout, stderr, exception/status, exit code/signal, watchdog events, timings, resource observations, started records, and exact commands. Keep successful and failed artifacts alike. No selected subset or compressed summary substitutes for full traces.

## 5. Mandatory replay identity and all-field equality gate

No paired-moment interpretation is allowed until **all 240 halves** pass input/identity/trace integrity, marginal reconstruction, and equality to **all** saved CalibrationRows. If any gate fails, report an incomplete or mismatched diagnostic with the full failure inventory and raw evidence; do not interpret surviving pairs as the planned result.

Compare the ordered twelve replayed rows with the ordered twelve saved rows. Require exactly these 25 serialized properties, with no absent, additional, or duplicate property:

`metric, fpr, power, score, robustness, repeatability, coverage, applicable, mde, fpr_inflated, power_curve, tracks, track_powers, track_scores, track_mdes, track_curves, repetitions, fpr_low, fpr_high, track_power_low, track_power_high, track_failures, track_mde_status, alpha, null_failures`.

Equality is recursive and type-aware:

- Object property order may differ; key sets may not. Array order, length, and null-vs-array must match exactly.
- Strings are exact ordinal values, including curve strings and status labels; no normalization or numeric reparsing replaces string equality.
- Integers and booleans are exact and type-distinct. Do not accept bool-as-int, rounded integer conversion, or coercion from strings.
- Finite numbers representing doubles must deserialize to the same binary64 bits, including the sign of zero. No tolerance, rounding, display-string comparison, or JSON-text numeric spelling requirement substitutes for finite binary64 identity.
- Round43 encodes nonfinite doubles as JSON null with a separate path/class label. Require the same complete set of nonfinite paths, each exactly once, with the same `NaN`, `Infinity`, or `-Infinity` class. Null without the required label, a label on a finite number, an unknown path, duplicate labels, or an extra label is a failure. NaN payload-bit identity is not claimed because the input preserved only its class.
- Array/string nulls, if any, remain ordinary structural nulls, not nonfinite numbers. The frozen property schema determines the distinction.

Retain path-by-path mismatch diagnostics, expected/actual types, finite binary64 hex representations where relevant, and nonfinite classes. Source/runtime/seed/input mismatches are failures even if displayed row values happen to agree. All-row equality includes robustness, repeatability and coverage; code counts alone cannot reconstruct these diagnostics, so the native returned values themselves must match the saved values.

### Independent reconstruction from decoded codes

A separate reference reader must recover exact per-metric rejection, valid, and missing counts for null, all three power tracks, and all fifteen track/grid-point cells. With N=1,000 and N_grid=200:

- Null failures = N − count(code≥0); track failures use the corresponding power codes.
- Rejection-rate denominators are **all** N or all N_grid, never just valid or complete-pair codes. This is the existing native behavior.
- Applicability includes the observed-data group/metric length requirement and null validity ≥0.9N. Track power requires applicability and track validity ≥0.9N; otherwise it is NaN. A grid cell similarly requires applicability and validity ≥0.9N_grid.
- Reconstruct FPR, all TrackPowers, FPR Wilson endpoints, every TrackPowerLow/High endpoint, all grid rates, curves, track failure totals, repetitions, alpha, nominal alpha/12, FPR inflation, MDE/status, and primary-track projection. Use the original operation ordering and Wilson constant z=1.959963984540054 when exact binary64 comparison is required. Retain rational count/n identities as an independent arithmetic check.
- Grid MDE reconstruction preserves the native first upward crossing and lack of monotonicity repair. Do not smooth, pool grid points, add monotonicity, or change the 0.80 target or native applicability/inflation requirements.
- Derived score reconstruction may use the unchanged composite/penalty recipe and the replayed diagnostic values, with its dependencies disclosed. It does not independently reconstruct robustness, repeatability, or coverage from codes.

All decoded counts must agree with native recorder count checks and the corresponding saved rows' consequences. Require full native-row equality independently of reconstruction. A count agreement alone is insufficient; a row agreement alone is insufficient without trace structure/count validation.

## 6. Prespecified pair universe and missingness

Include every unordered pair within the natural metric family for each alternative track, regardless of candidate membership, quality flags, empirical power, or which metric is best:

- Location: `{median, mean, geometric_mean, trimmed_mean_20}`; 6 pairs per half, 1,440 pair-half rows.
- Variability: `{standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, range}`; 21 pairs per half, 5,040 rows.
- Heterogeneity: the same four-metric location family; 6 pairs per half, 1,440 rows. This is the current generator/registry mapping, not a new scientific endorsement of a heterogeneity method.
- Common null: all unordered pairs of the full 12-metric registry, including rms; 66 pairs per half, 15,840 rows.

Thus the alternative-power population is exactly 7,920 pair-half rows, with 15,840 null rows kept separate, for 23,760 total rows. Pairs are oriented only for naming the difference: earlier registry index i minus later registry index j. Each unordered pair occurs once. Output ordering is case, side, stratum, then i,j registry order. Do not rank pairs by observed results.

Grid traces are fully retained and reconstructed as required in section 5, but grid-pair uncertainty summaries and cross-track/null-versus-power pair statistics are outside the primary estimand. No result-dependent choice to add those analyses is allowed under this frozen protocol.

For each pair retain the full 3×3 joint count matrix with row/column order [−1,0,1], plus n_observed, expected N, each metric's missing total, jointly-valid total, missing-only-left, missing-only-right, and both-missing counts. The nine cells sum to N for a complete trace. Nonfinite codes and unobserved replications are different categories and must never be merged.

The strict primary-moment rule is fixed before execution: if either metric has even one −1 code, covariance, marginal sample variances, paired-difference variance, independence-counterfactual variance, correlation, and variance ratio are **undefined**, with reason `nonfinite_code_present`. Preserve the complete nine-cell table and count/N rejection rates for native-reconstruction purposes. Do not silently drop failed replicates, substitute −1→0 for moment estimation, change to a complete-case denominator, or impute missing codes. If the trace is partial or invalid, all primary rate/moment outputs are undefined with the appropriate distinct reason; retain observed counts solely as partial audit data.

Row applicability flags are recorded separately. Complete finite binary codes permit descriptive indicator moments even if a row's separate observed-data applicability gate makes a reported CalibrationRow power NaN; flag this explicitly and do not relabel such an indicator rate as a finite reported power. This protocol never conditions inclusion on candidate status or empirical winners.

## 7. Fixed moment estimator and independence counterfactual

The following definitions apply only to a complete, valid, no-missing pair with N=1,000. They are finite-replicate sample-moment estimates conditional on one fixed stored half, its simulation recipe, and its seeds. The usual interpretation as Monte Carlo mean variance uses the across-replication Monte Carlo sampling assumption; this single deterministic replay does not independently establish the actual repeated-calibration variance, PRNG independence, or interval coverage.

Let n_ab count X_i=a and X_j=b for a,b∈{0,1}; X is the native rejection indicator. Let:

- a = n10+n11; b = n01+n11; c = n11; q = n10+n01.
- p_i = a/N; p_j = b/N; d = (a−b)/N.
- D_r = X_ir−X_jr, so its observed mean is d.

Use unbiased sample moments (N−1 denominator), not a mixture of unbiased paired and plug-in marginal estimates:

- s_i² = a(N−a)/[N(N−1)]; s_j² = b(N−b)/[N(N−1)].
- s_ij = (Nc−ab)/[N(N−1)].
- V_paired = s_D²/N = [Nq−(a−b)²]/[N²(N−1)].
- V_independent = (s_i²+s_j²)/N = [a(N−a)+b(N−b)]/[N²(N−1)].
- V_independent−V_paired = 2s_ij/N. This is a descriptive difference of the two moment calculations.

The independence counterfactual keeps the **same a, b, N**, setting only within-replication covariance to zero. It is not a newly simulated independent experiment or an estimate from a second set of marginal rates. Positive covariance lowers the moment estimate for a difference, negative covariance raises it, and zero covariance leaves it unchanged.

Optional derived fields are prespecified here and may be reported for every row:

- Estimated MC standard deviations sqrt(V_paired), sqrt(V_independent), labeled as descriptive conditional Monte Carlo moment estimates, not confidence intervals.
- Empirical sample correlation rho=s_ij/sqrt(s_i²s_j²), undefined when either marginal variance is zero.
- Ratio R=V_paired/V_independent, undefined when V_independent=0. A ratio above 1 is valid and must be retained. Negative covariance is also valid and must be retained. Zero estimated variances and zero covariance remain defined when the denominator conditions allow them; an undefined ratio must not turn them into missing values.

Store integer counts and exact integer numerators/denominators for all rational moments; convert to binary64 only for presentation or square roots. Determine covariance sign by Nc−ab, not a rounded float or tolerance. Validate nonnegative variance numerators rather than silently clamp a negative value. Large-count arithmetic must not overflow. No p-value, confidence interval, significance threshold, winner selection, effective-replication claim, or outcome-dependent subgroup is permitted.

## 8. Fixed descriptive summaries and denominators

Publish the full 23,760-row pair file with every finite/undefined state. Provide one summary for each alternative track and a separate common-null summary. All pair-half rows receive equal weight within that stratum; this describes the frozen population of computations, not independent biological observations. Metrics share draws, pairs share metrics, and left/right halves share a source case. Never use the row count as an independent statistical sample size or attach standard errors/intervals to these aggregate summaries.

For each field report its planned count, observed valid count, finite count, undefined count by reason, and the denominator of every fraction. Summarize finite values by minimum, median, and maximum; the median of an even finite count is the arithmetic mean of the two central ordered values. No finite values means undefined summary, not zero.

For covariance report exact counts negative/zero/positive among defined rows. Report positive-covariance fraction among defined covariances and the separate defined/planned fraction, so the denominator is visible. Apply the same explicit defined/undefined accounting to correlation and variance ratio. Do not calculate an average of pair correlations and call it a global common-draw correlation. Do not pool null and power, pool tracks, or convert these summaries into rankings, candidates, or selected winners. Report full marginal-rate ranges only as context with the same fixed-pair weighting disclosed.

If the all-240-half gate fails, publish coverage/failure counts, mismatch details, and raw audit artifacts only; planned descriptive scientific summaries remain withheld. Report that the planned diagnostic did not complete, rather than shrinking its population after observing failures.

## 9. Exact synthetic fixtures and validation gates

Before retained execution, validate a native/reference implementation against hand-computable binary examples, retained as synthetic software tests with no claims about the real calibration traces. Required exact examples (i,j vectors; N; expected s_ij, V_paired, V_independent, rho, R):

1. Identical mixed vectors [0,0,1,1], [0,0,1,1]; N=4: 1/3, 0, 1/6, 1, 0.
2. Complementary vectors [0,0,1,1], [1,1,0,0]; N=4: −1/3, 1/3, 1/6, −1, 2.
3. Balanced empirically uncorrelated vectors [0,0,1,1], [0,1,0,1]; N=4: 0, 1/6, 1/6, 0, 1.
4. Constant offset [1,1,1,1], [0,0,0,0]; N=4: d=1, s_ij=0, both variances=0, rho and R undefined. Include all-zero identical vectors too, with d=0 and the same zero/undefined distinction. Also include one constant member [0,0,0,0] against [0,0,1,1]: s_ij=0, both MC variances=1/12, R=1, rho undefined.
5. Asymmetric vectors [1,1,1,0,0], [1,0,0,1,0]; N=5: a=3,b=2,c=1,q=3,d=1/5; s_ij=−1/20, V_paired=7/50, V_independent=3/25, rho=−1/6, R=7/6. Reversing the pair changes only the sign of d; moments and ratio are unchanged.
6. One-missing example [−1,0,1,1], [0,0,1,0]: retain cells (−1,0)=1,(0,0)=1,(1,1)=1,(1,0)=1; every primary moment is undefined, while reconstruction rejection totals are 2 and 1 out of 4. Include only-left, only-right, and both-missing examples and a fixture exercising all nine cells.
7. N<2, invalid symbol, incomplete replication, unexpected extra replication, and unobserved tail: defined failure states, never a numeric moment.

Required additional checks:

- Exhaustive paired binary vectors for small N (at least N=2..6) against direct rational sample moments, with symmetry, all marginal counts, and V_independent−V_paired=2s_ij/N identities.
- Exact codec fixture [−1,0,1,−1]→byte 0x24; [1,0,−1,1]→0x86. Roundtrip every symbol and all nine joint cells. Cover symbol 11 rejection, padding corruption, hash/length changes, truncated byte/record tails, wrong order/shape, duplicate/skipped replication keys, and cross-track/grid offset mistakes.
- All 84 code positions must have a distinct deterministic synthetic pattern so Null/Power/Grid and metric/track transpose errors are detected. Verify rep%5 allocation and exactly 200 points per complete 1,000-rep trace.
- Native-row equality fixtures mutate each of the 25 fields, array order/length, one finite double by one ULP, +0/−0, an integer, boolean, curve string, track label, and each nonfinite class/path. Every change must fail; object-property reorder alone must pass. Duplicate/missing JSON keys and unlabeled numeric nulls must fail.
- Synthetic reconstruction fixtures cover 899/900/901 validity of 1,000, observed group length 3/4, 179/180/181 grid validity of 200, FPR inflation boundaries, zero/full rejection counts, Wilson endpoints, noisy/nonmonotone grid curves, insufficient grid count, and MDE first crossing/status. Use exact native operation ordering for finite binary64 identity and a separately expressed count-based reference for arithmetic checks.
- Recorder pass-through tests prove no restoration, single delegate invocation, unchanged returned object contents, complete prefix persistence on forced failure, and no RNG usage by the recorder. Resource-driver tests cover stop-before-launch races, launch failure, watchdog stop, descendants, incomplete traces, and cleanup accounting.

Preflight must prove that all tests are independent of retained paired outcomes. Then freeze hashes and run the fixed retained population once. After execution require every gate in sections 4–5, input/source hash verification, separate reference analysis, and reviewer confirmation before interpreting the summaries.

## 10. Resource, stopping, and evidence contract

The resource envelope is inherited from Round43, unchanged:

- At most 8 concurrently active case processes; DOTNET_PROCESSOR_COUNT=1.
- Whole retained-run wall budget 900 seconds, measured from the driver before the first launch; no per-half restart of the budget.
- At most 10 additional seconds for termination/cleanup, with no scientific computation launched after the deadline.
- 4 GiB aggregate resident-memory ceiling across driver and active launched process groups, including descendants; measure RSS, not only managed heaps.
- 384 MiB .NET GC heap hard limit per child (`DOTNET_GCHeapHardLimit=0x18000000`), `MVS_DISABLE_BACKUPS=1`, exact runtime with roll-forward disabled.
- Zero retries, replacement seeds, replacement halves, resumed science, extra repetitions, or favorable-subset reruns. Timeout, memory exceedance, infrastructure error, mismatch, or invalid trace is a retained terminal failure for this protocol.

Failure handling must stop new launches, cancel/terminate active children, preserve their physical output files, collect process-group completion within the cleanup deadline, and list any still-running/unknown states explicitly. Do not delete failure traces to obtain a clean package. The final driver manifest includes requested, started, completed, matched, failed, killed, and not-started counts with fixed denominators 120 cases / 240 halves; states are mutually coherent and audited against process records.

Required deliverables after an authorized run:

1. Frozen protocol, immutable input/source/harness/runtime bindings, final boundary check, and all synthetic test logs.
2. Per-half metadata, complete or partial lossless raw trace, replayed full CalibrationRows with nonfinite labels, all-field comparison result, marginal/grid reconstruction report, and native/driver logs.
3. All scheduled attempts, including failures/not-started halves, resource/watchdog/cleanup records, file inventory, byte sizes, and SHA-256 values.
4. Full fixed-universe joint-count/pair-moment file and fixed descriptive summaries only after all acceptance gates pass; otherwise an explicit no-interpretation status with audit evidence.
5. A short report stating the conditional, reused-synthetic-data scope, exact completion and gate counts, dependence findings without pair rankings or winners, and unchanged scientific NO-GO. Do not infer that covariance alone explains all Round44 candidate-set behavior or validates a replacement selector.
6. Independently openable raw ZIP parts, each strictly below 20,000,000 bytes, with a part manifest and checksum. Include every generated evidence file and all failures, never just aggregate tables. Retain the original R43 input bytes in the evidence package or include the exact corresponding already-retained raw-input archive parts with verified hashes and explicit retrieval references; unavailable inputs make the package incomplete. No private local path alone substitutes for delivered evidence.

No actual calibration replay, code-outcome retention, production edit, or scientific result is asserted by this proposed document. It defines the bounded diagnostic for implementation review and a later single authorized execution.


## Implementation freeze clarification, before any Round45 replay

Original proposed document SHA-256: 87dbded20d78c413b5534c47ab56f3e367be2289887e0288dd11ec568f981af1. The original text above is retained unchanged. This clarification resolves implementation details before any paired outcome acquisition.

The codec is headerless: exactly 21 payload bytes per complete replication and 21,000 bytes per complete half. All identities, dimensions and hashes belong in separate strict metadata. No binary header or implicit padding is used. A multi-frame synthetic pattern distinguishes all 84 positions; a single frame cannot give 84 unique values from a three-symbol alphabet.

All 25 native CalibrationRow fields must match Round43 exactly, including binary64 signed zero, array order, strings and nonfinite classes. This gate has no tolerance. Independent Python reconstruction has a separate numerical cross-runtime check: counts, rates, validity, failures, flags and parsed curve coordinates/rates are exact; Wilson endpoints use absolute tolerance 1e-15 and composite score uses absolute tolerance 1e-12 because sqrt/exp implementations can round differently. Retain every reconstruction difference and maximum absolute difference. MDE remains bit-exact with the native elementary-operation ordering, crossing index/status and nonfinite classification. No reconstruction tolerance changes a crossing, flag, eligibility, denominator or pair moment. Native curve strings remain exact against Round43.

The native command accepts --input PATH --index N --sha256 HASH --out DIR --freeze-sha256 HASH. The output directory must be new or empty; logs are outside it. Reserved CreateNew files are reservation.json, left.started.json/right.started.json, left.codes.bin/right.codes.bin, left.rows.json/right.rows.json, left.meta.json/right.meta.json and result.json. A killed process may leave empty reserved metadata or a partial physical trace. The driver preserves these bytes and writes its own terminal inventory separately, never fabricating successful native metadata.

Independent scientific review approved the original estimand and this arithmetic clarification before execution. This freeze is a development diagnostic on already seen synthetic data, not prospective research registration.
