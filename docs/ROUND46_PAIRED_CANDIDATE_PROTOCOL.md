# Proposed Round46 protocol: exact paired-comparison candidate-set diagnosis

Protocol ID: `mvs-r46-exact-paired-candidate-comparison/v1-proposed`  
Prepared: 2026-10-16 UTC  
Status: proposal only. Independent scientific review, implementation review, synthetic tests, and an immutable implementation/input freeze are required before ANY new calculation on retained codes, rows, or candidate outcomes.

## 1. Question, authorization boundary, and known context

Compare one fixed experimental candidate-set rule with the unchanged `family-power-ci-overlap-v1` rule on exactly the same 120 retained left/right pairs, 240 halves, and three natural families. The experimental rule removes an eligible target only when at least one eligible competitor has greater conditional Monte Carlo power by a prespecified exact one-sided paired test with full-family Holm adjustment. The comparison concerns set size, identity, split-half stability, marginal-frequency chance descriptions, availability, and the retained absolute power context together.

This is explicitly a posthoc development experiment on reused synthetic data. Round44 candidate results and Round45 dependence summaries were known before choosing this rule. In particular, Round45 reported median paired/independent variance ratios approximately 0.056943 for location, 0.803780 for variability, and zero for heterogeneity among defined ratios; variability powers did not exceed 0.018 and heterogeneity powers did not exceed 0.009. Those results motivate this bounded comparison; they are not newly discovered Round46 results. A small set, a low Monte Carlo p-value, or a high stability figure cannot repair low absolute power or establish scientific validity.

No new calibration, new synthetic input, seed, bootstrap, permutation sample, measurement resampling, entity split, effect setting, parameter search, metric activation, inference policy, UI behavior, or production recommendation change is authorized. Do not call `AnalysisEngine.Calibrate`, `CalibrateWithRecording`, `BenchmarkRunner.Calibrate`, `BenchmarkDatasets.Generate`, `AnalysisEngine.Build`, or `SplitEntities`. Round46 only reads already retained codes/rows and evaluates fixed diagnostic rules. It introduces no test of real-data FWER and cannot reverse scientific NO-GO or the negative Round27/Round32 decisions.

All fresh implementation belongs in bounded validation/test/report files in the separate Round46 source copy. Production source and the Round43–45 inputs/results remain byte-unchanged. This proposed document is outside the source copies. During its preparation only source, protocols, metadata/checksums, existing published summary results, and file names were inspected; no retained code decoding, new discordance counts, p-values, recommendations, or stability calculations were performed.

## 2. Fixed sources, population, and binding

Read-only original source: `/workspace/scratch/8105054a3211/mvs_round45/MVS-analyzer-main`.

Separate working source: `/workspace/scratch/8105054a3211/mvs_round46/MVS-analyzer-main`; its pre-edit guard is `/workspace/scratch/8105054a3211/mvs-r46-before.json`. New source/test/report changes must be explicitly allowlisted. The guard is not itself proof that the subsequent implementation is unchanged or reviewed.

Required retained authorities:

1. Round45 raw evidence: `/workspace/scratch/8105054a3211/mvs-r45-replay/case-NNN/native/{left,right}.codes.bin`, matching `{left,right}.meta.json`, `{left,right}.rows.json`, `result.json`, case validation/attempt records, and the complete binding/run/completion inventories; NNN is exactly 000–119.
2. Round43 original rows and case identities: `/workspace/scratch/8105054a3211/mvs-r43-replay/case-NNN/native.json`, both retained calibration arrays and their exact nonfinite sidecars. No observations need to be regenerated or analyzed.
3. Round44 original native recommendations: `/workspace/scratch/8105054a3211/mvs-r44-analysis/case-NNN/native.json`, its `per-case.json`, report, binding, and completion evidence. These are the exact old-selector comparison authority, not a re-created approximate baseline.
4. Prior source protocols and results: `docs/ROUND44_CANDIDATE_SET_STABILITY_PROTOCOL.md`, `docs/ROUND45_PAIRED_CALIBRATION_PROTOCOL.md`, and the source-only files `validation/round44-results.json`, `validation/round45-results.json`, `validation/candidate-set-stability-protocol-v1.json`, and `validation/paired-calibration-trace-protocol-v1.json`.

Previously recorded binding SHA-256 values, to verify before using them:

- Round43 `bind.json`: `36912dcc45f2d2d1d27c0ace940ed2c63125b892088455f9f3d420cca6182eea`
- Round44 `bind.json`: `726c83813b1d1382a6a7fb08ad44b79e522bddaead7c333eb6587b633c9c7948`
- Round45 `bind.json`: `5189f7d718c8ae74861b31ee0ce1244c68c5e93719f7ea88fd9a50534de23144`

Unchanged production source pins inherited from the reviewed Round45 protocol:

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

The full pre-execution manifest must bind the final reviewed protocol, every exact input path/byte hash, prior binding and result files, the allowed source baseline, new harness/reference/test/driver code, synthetic logs, loaded original Core assembly and build provenance, executable/runtime identities, exact commands, output schema and paths, ordered hypothesis lists, limits, and approval timestamp. Include the complete input inventories rather than trusting only an aggregate report. Record each half's case/side, original input hash and calibration seed association; no seed is executed. Require expected `.NET 8.0.31` identity for any original native API replay and disable runtime roll-forward. Python standard-library exact arithmetic needs no package installation; freeze its version/executable too.

Before the freeze, hashing bytes and inspecting schemas/source are permitted, but no new retained-data calculation is permitted. Synthetic tests must use independently constructed literals, never extracted retained outcomes. The independent reviewer must approve the actual implementation and complete manifest before the parent authorizes its hash. Freeze files are write-once. Any unresolved pin, identity, schema, or resource issue blocks execution; it is not permission to relax the contract. Verify input and source hashes again after analysis and independent audit.

## 3. Fixed families, order, and unchanged eligibility

Tracks are exactly `location`, `variability`, `heterogeneity`, in that order. Legacy metric order is exactly:

`median, standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, mean, rms, range, geometric_mean, trimmed_mean_20`.

Natural universes, preserving this order:

- Location: median, mean, geometric_mean, trimmed_mean_20; K=4.
- Variability: standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, range; K=7.
- Heterogeneity: median, mean, geometric_mean, trimmed_mean_20; K=4.

The heterogeneity mapping is the existing registry mapping, not acceptance of a final scientific method. `rms` remains outside all three families.

For each validated half and track, eligibility is exactly the Round44/Core contract. Let P, L, U be the original matching track power and Wilson bounds, without re-rounding or substitution. A row is applicable iff its original `Applicable` is true and P/L/U are finite. It is null-controlled iff applicable, original `FprInflated` is false, original `FprHigh` is finite, and `FprHigh <= min(1, max(1.5*(.05/12), .05/12+.02))`. The divisor remains all twelve active metrics. The eligible set E comprises natural-family, null-controlled metrics. Retain native booleans and source inputs for audit. Missing fields, invalid intervals, or unexplained nonfinites may not invoke a fallback to Fpr, primary power, point intervals, or another track.

Use all original Round44 structural/nonfinite/validity checks, including the pre-frozen 1e-15 validation-only Wilson endpoint tolerance. Selection comparisons always use the original binary64 values with no tolerance. Preserve exact 25-field row equality to Round43/Round45, arrays/order, signed zero, and nonfinite classes. The quality threshold stays `L >= .70`, inclusive, and is only a quality label. It does not filter E, hypotheses, or candidate membership.

The old set is C_old={m in E: U_m >= L_b}, where b is E's maximum original P with the first legacy metric breaking ties. Invoke original `CalibrationRecommendations.Build(rows, track)` and `Summarize(rows, track)` for all 720 half-tracks and compare their complete outputs with the corresponding Round44 native records. Require exact discrete/string/finite-binary64/nonfinite-class parity, including all twelve Build rows, BestMetric, Candidates, QualifiedCandidates, and status. Also verify against a separately expressed old-rule reference. A missing baseline or any mismatch blocks the paired-method comparison. Round44 aggregate agreement alone is not a parity check.

Reuse the already-built Round44 `candidate_set_stability` native harness identified by the verified Round44 binding, with its pinned original assembly and exact runtime. Run 120 sequential read-only case processes, each evaluating the two halves on three tracks: 720 explicit Build invocations and 720 explicit Summarize invocations in total (Summarize also calls Build internally). This requires no new native harness or production-code modification and never calibrates. Pin the external independent verifier before execution as well. Both native parity and that verifier's computational pass are supervised within the same global 300-second deadline.

## 4. Exact paired rule, fixed before eligibility/selection

Experimental method ID: `family-power-exact-mcnemar-holm-v1-test-only`.

### 4.1 Code coordinates and availability

Read the fixed Round45 two-bit schema `mvs-calibration-codes-2bit/v1`: −1→00, 0→01, 1→10, 11 invalid; first symbol is the least-significant two bits. Every complete half is 1,000 frames × 21 bytes = 21,000 bytes. Each frame is twelve Null codes, then three tracks × twelve Power codes, then three tracks × twelve Grid codes. Power coordinate for track index t and legacy metric index j is `12+12*t+j`. Replication order is 0–999. Do not use Grid or Null codes as alternative Power evidence.

Verify full trace length, symbol legality, hashes, metadata, identity, all 84 coordinate mappings, and retained row consistency before any inference. Complete traces, not aggregate Round45 pair moments, are the count authority; the latter may serve only as an additional reconstruction check after freeze. Retain all four binary cells for each tested pair, the two marginal rejection totals, and N=1000.

Any legitimate −1 at any natural-family Power coordinate in any replication makes that entire half-track candidate family unavailable, including when that metric would fail eligibility. Record `analysis_availability=unavailable_missing_power_code`, exact positions/counts, C_new=null, size=null, and p-values=null. Do not delete incomplete pairs, shrink N or the metric family, substitute p=1, impute 0, reuse another track, or manufacture an empty candidate set. Codes outside that track's natural Power family do not trigger this specific rule; they remain fully inventoried and subject to original row validation. A malformed code, partial trace, missing file, or metadata mismatch is technical failure, not legitimate unavailability.

All 720 half-track families must be fully available for primary set-comparison acceptance. If any is unavailable, retain the availability/failure inventory but all planned all-120 primary set-comparison aggregates are undefined/blocked. There is no complete-case or reduced-N rescue. Zero missing codes in the existing Round45 report is context to verify, not a reason to omit handling. Observing no failures does not prove that the simulation kernel always has binary outcomes or justify a guarantee conditional on passing this gate.

### 4.2 Ordered hypotheses and exact tail

For each full natural family F, form every ordered pair (c,t), c≠t, with c the competitor and t the target. The fixed counts M=K(K−1) are 12,42,12. Generate competitor-major then target-major legacy order; this is the canonical tie order. Neither eligibility nor an empirical best may reduce or select the hypothesis family.

Let W_ct=count(c=1,t=0), L_ct=count(c=0,t=1), q=W_ct+L_ct. Test H_ct: π_c <= π_t against π_c > π_t, where π is rejection probability under the fixed half's calibration simulation kernel. The exact raw p-value is:

`p_ct = Fraction(sum(comb(q,k) for k=W_ct..q), 2**q)`.

When q=0, define p=1 exactly. This is the upper binomial tail including the observed count. Use arbitrary-precision integers and reduced exact fractions; the raw integer tail numerator and 2**q denominator must also be recoverable. No normal/chi-square approximation, continuity correction, mid-p, randomized test, two-sided p-value, clipped variance, asymptotic covariance shortcut, or floating p-value comparison is permitted. Caching exact integer binomial rows/tails is allowed and must not change results.

The reverse ordered test is computed explicitly with W and L swapped. Reverse tails obey the exact audit identity `p(W,L)+p(L,W)=1+comb(q,W)/2**q`; they are not complements and must not be assigned `1-p`. No smallest-effect margin is introduced; significance here can concern a practically tiny conditional power difference.

### 4.3 Full-family Holm and simultaneous selection

Set alpha=Fraction(1,20). Sort all M hypotheses by exact raw p, then the canonical ordered-pair position. For ranks r=1..M, the threshold is alpha/(M−r+1). Reject the consecutive initial sequence for which `p_(r) < alpha/(M-r+1)`, strictly. Stop at the first failure and reject no later hypothesis. Never restart, retest, or drop ineligible hypotheses. The strict boundary is intentionally conservative and fully frozen.

Also retain exact Holm-adjusted values:

`p_adj_(r) = min(1, max_{s<=r} ((M-s+1)*p_(s)))`.

Require equivalence of the frozen step-down decision and `p_adj < 1/20`. An independent integer check for a reached rank is `20*(M-r+1)*tail_numerator < 2**q`, also strictly. Store raw/adjusted numerator and denominator, canonical position, sorted rank, exact threshold, passed-prefix state, and reject flag for every hypothesis. Decimal values are display-only. Canonical tie order determines audit ranks but must not change the rejected hypothesis set.

Only after this full family is evaluated, construct:

`C_new = {t in E : there is no c in E, c != t, with rejected H_ct}`.

All originally eligible competitors participate simultaneously, including competitors that are themselves eliminated. No sequential pruning, eligibility-dependent multiplicity, winner-first comparison, transitive extra rejection, tie-winning metric, or iterative rerun is permitted. A rejected edge from an ineligible competitor remains in the audit but cannot eliminate an eligible target. E empty gives the genuine empty set []. E nonempty must give a nonempty candidate set.

Qualified candidates are Q_new={m in C_new: original L_m>=.70}. Status is qualified if Q_new nonempty, uncertain if C_new nonempty with Q_new empty, and unavailable_no_eligible if E empty. Keep `analysis_availability` separate from this recommendation status, and retain the original old-rule native labels rather than rewriting them.

Mandatory algebraic invariants: every rejection has W>L and competitor total>target total; no pair is rejected in both directions; the directed graph of rejections is acyclic; every empirical maximum in E survives; C_new is contained in E; and C_new is empty iff E is empty. Because all accepted powers use the same full N, a rejected edge strictly descends empirical counts. Any violation is a bug/analysis failure, never a reason to choose a fallback vertex or remove a cycle. These are implementation invariants, not evidence of useful power or scientific validity. Old and new sets need not be nested, and pairing need not improve stability or shrink a set.

An additional comparison invariant follows from the same-N, count-consistent monotone Wilson lower bounds: both methods retain a maximum-observed-power eligible metric, so `Q_old is nonempty` iff `Q_new is nonempty`. The number and identity of qualified candidates may change, but a half-track cannot newly become qualified or lose qualified status in this accepted complete-code setting. Verify that property and Wilson monotonicity in synthetic tests; an empirical violation is a bug or failed input contract, not a qualification gain. Inherited Wilson bounds and .70 labels keep their old meaning; paired Holm does not make them simultaneous bounds or validate them conditional on selection.

## 5. Mathematical justification and exact scope

For iid binary paired simulation draws given one fixed empirical half and its fixed calibration kernel, let π10 and π01 be the two discordance probabilities. Then π_c−π_t=π10−π01. Conditional on this pair's discordance count q, W is binomial(q,θ), where θ=π10/(π10+π01). The composite null implies θ<=1/2; its largest upper-tail probability is at θ=1/2. The inclusive exact tail is therefore super-uniform under that null; q=0 supplies no directional evidence. This standard conditional construction and its one-sided extension are described by [Fay (2010), sections 2 and 7](https://journal.r-project.org/articles/RJ-2010-008/index.html). The strict rejection boundary remains conservative.

With valid marginal p-values, Holm's step-down argument does not require independence between tests: if m0 nulls are true, the first rejected true null has p<=alpha/m0, so a union bound over those true nulls bounds any false rejection by alpha. See [Holm (1979), Theorem 1](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf), with the implementation convention also documented by [R's official p.adjust reference](https://search.r-project.org/R/refmans/stats/html/p.adjust.html). Testing the full family before eligibility avoids shrinking that family after observing outcomes.

Thus the nominal mathematical error-control statement is local: at most .05 FWER for one fixed half×track ordered-hypothesis family under the assumed iid binary simulation-vector model, unconditional over its Monte Carlo outputs and any output-dependent eligibility. It is NOT a claim conditional on observed winners, realized eligibility, all realized discordance totals, passing the no-missingness gate, or this adaptively chosen development protocol. Each exact tail conditions on its own pair's q; those individual statements do not establish joint control conditional on the vector of all q values.

Do not claim .05 control across 720 half-track families, all 15,840 ordered tests, three tracks jointly, repeated rounds, or posthoc method selection. Choosing this diagnostic after viewing Round44/45 does not establish a 5% post-selection or campaign error guarantee for the adaptive development workflow. These computations share metrics, draws, halves and source data; their bookkeeping totals are not independent research sample sizes. Fixed pseudorandom seeds make this realized audit deterministic, not a repeated-simulation calibration study. The inferential model describes hypothetical repetitions of a valid independent simulation kernel; the protocol does not prove that model from the observed trace. No theorem about simultaneous no-false-elimination, optimal-metric coverage, entity/sampling uncertainty, generalization, equivalence, minimum useful effect, or research validity may be advertised beyond the explicitly stated assumptions and scope. Failure to reject a dominance null does not show equal or adequate power.

## 6. Frozen outputs and complete comparison

Primary population: exactly 120 matched case indices per track, 120 left and 120 right halves, 240 half-tracks per track, 360 pair-track records and 720 half-track records overall. Total ordered hypothesis records are 240*(12+42+12)=15,840. Require all records, including nonsignificant tests, full-family/empty sets, unfavorable comparisons and technical failures. Never pool tracks into a single scientific headline.

### 6.1 Per-half and per-pair evidence

For every half-track retain E, all old native outputs, C_old/Q_old, C_new/Q_new, original P/L/U and null-control inputs for every natural metric, availability/reasons, all hypothesis audit records and directed edges. Store sets in canonical legacy order without discarding unexpected duplicates. For the old/new relationship report equal/proper-subset/proper-superset/incomparable set categories, independent cardinality decrease/equal/increase, intersection/union and Jaccard. Do not presume smaller cardinality implies subset. Empty status must agree between old and new on complete inputs because eligibility is identical and a nonempty E has a surviving empirical maximum.

For every matched case-track retain left/right sets, sizes, qualified sets, statuses, exact agreement indicators, rational Jaccard values, empty categories, and the new-minus-old differences in exact indicator and Jaccard. Freeze exact-match transition counts (old yes/new yes, old yes/new no, old no/new yes, old no/new no) and Jaccard increased/equal/decreased counts. Report both losses and gains.

### 6.2 Within-method size, availability, stability, and power

For each method and track, separately for left and right with denominator 120:

- Full |C| and |Q| histograms over 0..K; mean, median, min/max and type-7 quartiles. Zeros are included. Null unavailable sizes are not zeros and block the planned complete-population result.
- Size-pair cross-tab, mean absolute left/right size difference, full-family frequency, per-metric candidate and qualified inclusion frequencies, and qualified/uncertain/unavailable_no_eligible status counts.
- Counts of empty-left/right, both-empty, left-only-empty, right-only-empty, and both-nonempty; the four disjoint pair categories sum to 120. Separately show input-family unavailable counts/reasons even if zero.
- Absolute power context: retain per-metric P/L/U, side-wise min/median/max P and L for all natural metrics and all eligible metrics, and per-half minimum/maximum candidate P and L. Such descriptive summaries use finite values only, always with displayed finite/total counts; preserve legitimate unavailable row NaNs in the original per-row sidecars and never coerce them to zero. No finite values gives null with `no_finite_power_context`; empty eligible/candidate groups give null with `no_eligible_metrics`/`no_candidate_metrics`. This handling of descriptive field availability is not permission to reduce the fixed primary stability population. Report candidate-weighted summaries only if explicitly labeled with their metric-half denominator. Report Q counts, number of halves with no candidate meeting the .70 lower-bound target, and selected metrics' ranges together with set-size results. No raw calibration power changes in Round46; changes in the composition of a selected set are not improvement in a metric's power.

For any two available sets C,D, define exact agreement as 1(C=D), including both empty. Define J(C,D)=|intersection|/|union| when union is nonempty, J(empty,empty)=1, and J(one empty)=0. Exact agreement A is its indicator total/120; mean J is the exact sum of rational overlaps/120. Report mean/median/type-7 quartiles and the both-empty contribution separately, plus nonempty exact-match count/120. Both-empty agreement is abstention, not a usable recommendation.

The predefined informative companions use B, the original matched indices with both halves nonempty, and U, those with nonempty union. Report exact agreement and mean J on B and mean J on U, with explicit denominators. Zero denominator means undefined, never 0 or 1. E is unchanged and both selectors are nonempty iff E is nonempty, so B and U must be the same across methods; fail on a disagreement instead of choosing method-specific favorable subsets.

Report new-minus-old exact agreement and mean J on all 120, and the same comparisons on the shared B when defined, without significance tests, bootstrap intervals or a superiority decision. Every rate retains integer numerator/denominator; all overlap means and differences retain reduced fractions. Numerical display rounding never affects sets, tests, equality or denominator accounting.

### 6.3 Empirical marginal-frequency reference and degeneracy

For each method separately and each track, enumerate all ordered 120×120=14,400 left/right cross-pairs, including the 120 original diagonal pairs, using the same empty policy. Define B_A as cross-pair exact matches/14,400 and B_J as the sum of all cross-pair rational Jaccards/14,400. Independently verify B_A=sum_S p_left(S)*p_right(S) using whole-set category frequencies. This reference preserves within-set co-occurrence; it is not a product of per-metric Bernoulli inclusion probabilities. The ratio of expected intersection and expected union is not mean Jaccard.

Report O, B, O−B, and (O−B)/(1−B) for exact agreement and mean J of each method. Negative excess and adjusted values remain negative. If exact B=1, adjustment is null with reason `degenerate_marginals`; preserve raw O and B and do not rank by that undefined value. No epsilon or clipping rule is allowed. This is a descriptive product-of-observed-marginals baseline, not a null randomization distribution, p-value, chance-corrected scientific validity measure, or claim of independent splits.

Repeat the same calculations for the shared B companion using the original n_B matched indices and all n_B² cross-pairs. When n_B=0 all companion baselines/adjustments are undefined. Report changed denominators; do not substitute the all-120 baseline. Compare the two methods' adjusted values only where both are defined, as a descriptive difference. Do not call a method useful on the basis of raw agreement alone, especially when family size, abstention, degenerate marginals, or weak absolute power explain it.

### 6.4 Minimum machine-readable evidence contract

Freeze the complete JSON schema and file inventory with the implementation before execution. The following semantic fields and counts are mandatory; an implementer may not replace them with a favorable summary. Integers representing ordinary counts are JSON integers. Every exact fraction is an object with decimal-string `numerator` and positive decimal-string `denominator`, reduced to lowest terms; this preserves integers beyond binary64/JavaScript precision. A separate optional decimal display field is never authoritative. Undefined numeric results use null plus a machine-readable reason, never NaN, Infinity, zero, or an empty string.

- `ordered-tests.jsonl.gz`: exactly 15,840 records on accepted input. Required keys: `case_index`, `side`, `track`, `competitor`, `target`, `family_size`, `hypothesis_count`, `canonical_pair_position`, `n`, `n00`, `n01`, `n10`, `n11`, `competitor_rejections`, `target_rejections`, `discordances`, `competitor_only`, `target_only`, `power_difference`, `tail_numerator`, `tail_denominator_power_of_two`, `raw_p`, `holm_rank`, `holm_threshold`, `passes_own_rank_threshold`, `prefix_passes`, `adjusted_p`, `rejected`, `competitor_eligible`, `target_eligible`, `eligible_elimination_edge`, and `analysis_availability`. `n01` means competitor=0,target=1 and `n10` competitor=1,target=0. Unreduced `tail_numerator` is a decimal string; `tail_denominator_power_of_two` is q, making 2**q recoverable. A missing-family failure inventory records null test results separately, never as successful hypotheses.
- `half-tracks.jsonl.gz`: exactly 720 records on accepted input. Required keys: `case_index`, `side`, `track`, `input_binding`, `analysis_availability`, `unavailable_reason`, `family`, `eligible`, `metric_context`, `old_native_output_reference`, `old_candidates`, `old_qualified`, `old_native_status`, `new_candidates`, `new_qualified`, `new_status`, `old_size`, `new_size`, `old_qualified_size`, `new_qualified_size`, `rejected_edges`, `eligible_elimination_edges`, `surviving_empirical_maxima`, `set_relation`, `cardinality_change`, `old_new_jaccard`, `candidate_power_context`, and `invariant_checks`. `metric_context` includes original applicable/null-controlled flags and exact-round-trip original P/L/U/FPR fields. Store the complete native Build/Summarize payloads and nonfinite labels in the referenced retained native output, with a verified file hash.
- `pair-tracks.jsonl.gz`: exactly 360 records on accepted input. Required keys: `case_index`, `track`, references to both complete half records, both methods' sets/qualified sets/sizes/statuses, `old_empty_category`, `new_empty_category`, `old_exact`, `new_exact`, `old_intersection_size`, `old_union_size`, `new_intersection_size`, `new_union_size`, `old_jaccard`, `new_jaccard`, `exact_difference`, `jaccard_difference`, `exact_transition`, `jaccard_change`, and `shared_nonempty_conditioning_flags`.
- `summaries.json`: separate ordered track objects and separate old/new method objects, with the full side histograms, inclusion/status/availability counts, size cross-tabs, original-power context and per-half power summaries, all-120 exact/Jaccard numerators/denominators, B/U companions and reasons, every cross-pair count, whole-set category frequencies, exact/Jaccard baseline fractions, excess and adjusted values/reasons, and new-minus-old comparisons. Include set-relation/cardinality distributions, exact transition tables, Jaccard increase/equal/decrease counts, qualification-status invariant counts, and planned/observed denominators for every section. Retain any type-7 quantile as an exact fraction when its source values are integer/rational; native floating power contexts retain their original binary64 representation.
- Required supporting artifacts: frozen protocol and `bind.json`/`bind.sha256`; synthetic test/oracle logs; `run.json` with exact commands/times/state; `input-validation.json`; complete native baseline outputs and `native-baseline-parity.json`; `independent-audit.json`; `post-run-pins.json`; `resources.json`; failure/cleanup inventories if any; a human-readable report; and `file-manifest.json` listing artifact byte sizes and hashes. The manifest binds the exact paths/filenames before the run; unplanned new result summaries need a documented amendment.

The independent audit must compare semantic values and exact fractions, not compressed-file byte identity or JSON property order. Duplicate keys, reordered metric/track arrays, changed method identities, omitted required records or altered fraction signs/denominators are failures. All retained-data decoding, tests, native parity, aggregation, independent quantitative verification and quantitative report calculations occur inside the single 300-second retained-analysis budget. Later human review and prose drafting may use the finalized artifacts but may not add retained-data calculations. The separate packaging allowance performs only packaging/checksum/inventory work.

## 7. Independent pre-outcome tests and retained-result audit

Two separately expressed implementations are required. The main analyzer may reuse reviewed strict I/O infrastructure, but the independent reference must not import its exact-tail, Holm, eligibility, selection, graph, set-summary, or chance-baseline helpers. It must independently decode raw symbols, reconstruct all natural-family counts, calculate exact tails and adjustments, and compare every discrete/rational output. Use straightforward exact integer summation in one implementation and an independently expressed Pascal-row or binomial-recurrence calculation in the other. A second call to the same helper is not an oracle.

Synthetic tests precede the retained freeze and must include these literal hand expectations:

1. Exact tails: (W,L)=(0,0)→1; (1,0)→1/2; (0,1)→1; (2,0)→1/4; (1,1)→3/4; (2,1)→1/2; (3,0)→1/8; (3,1)→5/16; (4,0)→1/16; (4,1)→3/16. Reversing (4,1) gives (1,4)→31/32, not 13/16. Identical all-zero, identical all-one and mixed identical vectors all have q=0,p=1. Exact q=1000 end cases W=0 and W=q must yield 1 and 1/2**1000 without underflow.
2. At a fixed M=12 first Holm rank, all eight discordances in the competitor direction give 1/256<1/240 and pass, while seven give 1/128>1/240 and fail. For M=42, ten give 1/1024<1/840 and pass, while nine give 1/512>1/840 and fail. Do not reduce M for two eligible metrics.
3. Artificial p-vector Holm fixture, M=12: ordered values [1/480,1/220,1/210,1,1,1,1,1,1,1,1,1]. Reject only the first. Rank two exactly meets 1/220 and fails the strict rule; rank three would pass its own 1/200 threshold but remains unrejected after stopping. Adjusted first/second/third values are 1/40,1/20,1/20. A two-entry tie at 1/256 with the remaining ten values 1 follows canonical pair order, rejects both, and gives both adjusted values 3/64. Arbitrary rational vectors here test Holm machinery only; they are not claims that every vector is attainable by paired binary traces. In fact every genuine exact tail is dyadic while a threshold 1/(20*(M-r+1)) has a denominator with factor 5, so they cannot be exactly equal; the strict boundary is nevertheless an explicit implementation contract.
4. Full-family direction/selection fixture: K=4, N=8, A=[1,1,1,1,1,1,1,1], B=C=D=[0,0,0,0,0,0,0,0], all eligible. The three A→other tests have p=1/256, their reverse tests p=1, and other tests q=0,p=1. The three low tests all reject, their adjusted p-values equal 3/64, and C_new={A}. Direction reversal of the edge would be a failure. Making A ineligible leaves all three low tests in Holm but makes C_new={B,C,D}; it does not shrink M or let A eliminate eligible metrics.
   A second realizable multilevel fixture uses K=4,N=16: A is sixteen ones, B is eight ones followed by eight zeros, and C=D are sixteen zeros, all eligible. A→C and A→D have p=1/65536; A→B, B→C and B→D have p=1/256; all other directions have p=1. Holm rejects these five tests; the two smallest have adjusted p=3/16384 and the other three have adjusted p=5/128. C_new={A}. This exercises nontrivial count-descending chains with genuine code vectors.
5. Low-power version of fixture 4: N=1000, A has exactly eight initial ones and 992 zeros, all other vectors are zero, and all are otherwise eligible with count-consistent rows. The three directional tails are unchanged and C_new={A}, but P_A=.008 and Q_new is empty under the retained .70 criterion. This literal case must be reported as uncertain, never useful high power.
6. Graph-selection unit fixture with fixed E={A,B,C,D} and injected edges A→B,B→C yields C_new={A,D}; B's own elimination does not disable B→C. Edges are inputs to this isolated graph unit test, not asserted to be an actual McNemar result. An injected A→B,B→C,C→A cycle is rejected as an invalid analysis graph, never repaired. Full end-to-end binary fixtures must independently establish edge-count descent and absence of cycles.
7. E empty gives C_new=[],Q_new=[],status unavailable_no_eligible; a singleton E survives regardless of ineligible incoming edges. Equal observed maximum-power eligible metrics all survive; the selector must not break this tie by choosing one. A family of identical binary vectors has all p=1 and retains all eligible metrics. In an isolated label test, quality L=.70 versus the immediately smaller binary64 value changes Q/status only, never C or Holm; no unattainable interval is claimed to be a count-consistent end-to-end trace. Independently check native Wilson lower-bound monotonicity over all k=0..1000 at N=1000, and on full count-consistent selection fixtures require old/new qualified-nonempty status equality.
8. A single natural-family Power −1, including in an ineligible metric, yields whole-family unavailable with null p/set/size and blocks the primary comparison. Include only-left, only-right, both-side missing families and a nonfamily/other-track −1 to test the precise scope. Reserved 11, truncation, extra frames, coordinate transposes, mislabeled metadata and duplicate JSON keys are technical failures. Missing evidence is never a zero code or q=0.
9. Set arithmetic: J(empty,empty)=1; J(empty,{A})=0; J({A,B},{B,C})=1/3. With two matched pairs L=[{A},{B}], R=[{B},{A}], observed exact/J=0, both full cross-pair baselines=1/2, excess=−1/2 and adjusted=−1. With every set fixed to {A,B}, O=B=1 and adjustment is undefined. With L=R=[empty,{A}], observed exact/J=1, baselines=1/2 and adjustment=1; the both-nonempty companion has n_B=1 and a degenerate baseline of 1. With L=R=[{A},{A,B}], mean cross-pair J=3/4, while ratio of expected intersection to expected union is 5/7: these must not be confused.
10. Restore all old-rule family/eligibility/tie/inclusive-overlap/empty/quality/binary64/nonfinite/round-trip fixtures from Round44. Mutate every identity/shape/pin category, an individual raw code, a single finite double by one ULP, signed zero, row/track order, status, and baseline candidate flag; every relevant mutation must fail the appropriate exact gate.

Required exhaustive small oracles, independent of retained data:

- For N=0..6, enumerate every pair of binary vectors (four paired outcomes per position). Check all cells, directional tails against explicit enumeration of 2**q discordance orientations, reverse direction, bounds, q=0, and exact marginal-count differences. N=0 is a tail-unit case only, never an accepted retained half.
- For family K=4 and N=1..4, enumerate all 2**(K*N) binary vector arrays and every eligibility subset. Apply exact full-family Holm and selection, checking counting, reverse-test exclusion, all empirical maxima, nonempty-E behavior, and invariant results under a consistent permutation of fixture labels with the frozen canonical tie mapping. These small vectors cannot reject at the frozen alpha because their smallest raw p is at least 1/16; they are counting/non-rejection checks. The N=8 and N=16 literal fixtures above provide actual rejecting edges and multilevel DAG checks, while the injected graph test checks simultaneous use of all originally eligible competitors. None of these tests estimates scientific error rates.
- Exhaustively compare step-down versus adjusted-p decisions for every length M=1..4 vector over [0,1/100,1/40,1/20,1/10,1], with additional exact threshold-equality/adjacent-rational fixtures at each rank. Separately include the fixed M=12 and M=42 cases above and their canonical-order ties. Test that eligibility changes leave every raw/adjusted p and Holm rejection unchanged. These bounds deliberately avoid exponential enumeration of 42-entry vectors.
- Independently enumerate small whole-set distributions, cross-pair baselines, type-7 quantiles, negative adjustments, degeneracy, shared-empty categories and zero-denominator companions. Verify exact count/rational equality between implementations.

After authorization, independently verify all 240 traces, all 720 families, all 15,840 ordered hypotheses, all old-selector native outputs, all new candidate/qualified sets/statuses, all 360 pair records and every summary denominator/rational. Fail on any mismatch; do not publish only the matching subset. Reviewer sign-off must distinguish synthetic-test success, retained-output parity and the limited scientific interpretation.

## 8. Bounded execution and stopping rules

One authorized retained analysis and its fixed independent verification pass; zero recalibrations, no new RNG calls, no replacement halves, no retries/resumption after retained failure, and no extra alternative rule/threshold. Independent deterministic verification is not an additional scientific sample and never increases denominators.

- At most one computing worker/process at a time; a lightweight supervisor/watchdog may coexist. Native baseline and Python/reference computation are sequential, not parallel scientific workers. Set DOTNET_PROCESSOR_COUNT=1 and disable .NET roll-forward/backups.
- Global 300-second wall budget from the driver before retained validation/counting begins through both analyses, old-native parity and post-run pin checks. It is not reset per half or reference pass. Source-only synthetic testing, implementation builds and manifest preparation occur before this clock and cannot read retained outcomes.
- Aggregate RSS ceiling 1 GiB over supervisor and owned descendants; report measured RSS and sampling frequency, not only managed heaps. At most five seconds additional termination/cleanup, with no new scientific work after the deadline. Kill and account for owned process groups on deadline/memory/error.
- New evidence-output ceiling 64 MiB, excluding read-only inherited inputs and pre-existing source binaries. Write bounded, streaming records; preserve all successful and failed records. Every user-delivered file/ZIP part must be strictly below 20,000,000 bytes. Split archives with explicit indexes/checksums rather than dropping records. Packaging may run separately for at most 120 seconds after scientific completion and may not calculate new comparisons.
- Outputs are create-new in a separately frozen Round46 directory. Preserve logs/partial files, deadline/memory observations, failure provenance, started/completed/not-started states, and exact byte inventories. A failed budget is a technical result, not permission for a faster approximation, a selected subset, or another retained run.

No outcome-dependent stopping, interesting-track continuation, top-pair reporting, threshold search, or replacement method is allowed. Technical acceptance requires every fixed input and old baseline verified, all 720 available families, all 15,840 ordered records, full exact native/reference parity, all rational summaries and denominators reconciled, independent approval, and unchanged production/input pins. Technical acceptance does not require an improvement in set size or agreement and is not scientific acceptance.

Stop after the complete checked comparison and bounded report are delivered, or report the precise blocker with all attempted evidence if acceptance fails. Further experiments need a separately proposed and reviewed protocol; this protocol does not automatically authorize them.

## 9. Required deliverables and report language

Deliver the final frozen protocol/binding/checksum; reviewed test-only implementation and independent reference; synthetic fixture/oracle logs; input/availability/native-baseline validation; full per-hypothesis/per-half/per-pair exact evidence; all method summaries and chance comparisons; resource/cleanup/post-pin audit; and independent review. Include exact raw-input retrieval references and verified hashes to the already delivered Round43–45 evidence, or package copies when needed for an independently openable evidence bundle. A private local path alone is not sufficient evidence delivery. Archive-part inventories must include failures, undefined values and non-significant hypotheses.

The short report must present all three tracks, exact denominators, set-size changes, old/new exact/Jaccard stability, each method's empirical baseline and adjusted values with degeneracy, all negative/worse outcomes, empty/unavailable counts, and absolute/qualified-power context together. Describe improved selectivity only if observed, without assuming improved stability or utility. An unchanged, larger, unstable, full-family, low-power or degenerate result is retained as such. No overall winner or scientific GO threshold is frozen.

State explicitly: this is a test-only posthoc comparison on old synthetic inputs; uncertainty refers to the conditional Monte Carlo kernel, not people, measurements, new research samples or validity of the scientific model; original powers/calibrations and production decisions are unchanged. A more selective candidate set alone is not evidence of a better scientific recommendation. The earlier negative scientific gates remain unchanged.

User-facing release documents may link other included documents. Validation JSON paths are source-only references and should be shown as plain code paths, not Markdown links that would be broken in release bundles which omit validation JSON. Generated evidence files must be delivered as verifiable artifacts under the size limit.

This document asserts no Round46 retained calculation, implemented result, selected metric, successful comparison, activation, or new scientific acceptance.


## Pre-execution clarification and provenance

Original proposed document SHA-256: b26da542c48f50d713bc5df1995a1833446abbde2795ea7ab0c2977ef216cd23. The preceding original text is preserved. The scientific reviewer approved the following implementation clarification before any Round46 retained calculation: the 1,001-count Wilson monotonicity sweep evaluates the documented formula independently in binary64; it does not claim observing 1,001 native outputs. Actual retained acceptance separately requires original native baseline/row parity and identical old/new qualification-nonempty status on all 720 families. No new native probe is needed.

The original Round44 native harness is reused without source changes for 120 sequential invocations (720 Build and 720 Summarize calls). It performs no calibration. The independent verifier is written and hash-bound before execution and runs sequentially within the same 300-second analysis budget. Human review and packaging after completion cannot calculate a new candidate rule or new comparison.
