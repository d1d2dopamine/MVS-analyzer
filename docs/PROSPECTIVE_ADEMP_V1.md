# MVS Statistical Components: prospective ADEMP protocol 1.0.0

**Identifier:** `MVS-STAT-COMPONENTS-PROSPECTIVE-1.0.0`. **Date:** 2026-10-17.
**State:** design frozen for review and reproducible planning; execution blocked.
The machine-readable specification is `validation/prospective-ademp-v1.json` in the full source archive. The command-line utility validates this specification and enumerates planned case identities; it does not generate observations, fit a model, or execute a simulation.

This is a prospective design for evaluating two already selected procedures on independently generated datasets. No outcomes from these planned datasets exist. Historical Round50 datasets and all other inspected studies remain development evidence. The mechanisms overlap historical development: new seeds cannot establish generalization to previously unseen mechanism families. Neither this document nor its local hash constitutes external preregistration. A final executable freeze, independent implementation review, and resource admission are prerequisites for generation.

## 1. Aims and scope

The primary aim is to estimate rejection probabilities of the current Gaussian variance-component procedure and the current 12-summary procedure, separating true-null errors from detection probabilities under explicitly named alternatives. Secondary aims are to quantify paired differences, method availability, and computational cost. We will not select a route after seeing a dataset, combine rejections by an OR rule, or select a favorable scenario for an overall score. No aggregate benchmark score is defined.

The study is conditional on the 12 specified data-generating cells, two groups of independent entities, and the pinned implementations. It cannot certify universal false-positive control, meaningful effects in a particular application, interval coverage, or superiority over all statistical methods. NIST numerical reference checks remain a separate layer: their agreement or disagreement does not determine statistical calibration here. ADEMP supplies the planning structure, not a certified dataset or a pass threshold [1].

## 2. Data-generating mechanisms

For group g in {0,1}, entity i=1,...,n, and repeat j=1,...,m,

    Y_gij = mu_g + tau_g B_gi + sigma_g E_gij.

All B and E draws are mutually independent. Each distribution has mean zero and variance one. The two available distributions are N(0,1) and sqrt(3/5) T_5. Thus Var(Y_gij)=tau_g^2+sigma_g^2, within-entity covariance=tau_g^2, and ICC=tau_g^2/(tau_g^2+sigma_g^2). Entity vectors, not individual rows, are independent experimental units. t5 has finite fourth moment, with standardized fourth moment nine; its sixth moment does not exist. This stress changes Gaussian sample-variance uncertainty while preserving the named variance parameters.

Group 0 always has (mu,sigma,tau)=(20,1,1). Unless shown otherwise, n=16 per group and m=40; group 1 also starts at (20,1,1). The distribution columns apply equally to both groups, avoiding an unannounced unequal-shape null.

| ID | English cell name | Group 1 change | B distribution | E distribution | n,m |
|---|---|---|---|---|---|
| C00 | Gaussian Global Null | none | Gaussian | Gaussian | 16,40 |
| C01 | Gaussian Location Shift | mu=22 | Gaussian | Gaussian | 16,40 |
| C02 | Gaussian Within-SD Shift, Large | sigma=2 | Gaussian | Gaussian | 16,40 |
| C03 | Gaussian Between-SD Shift, Large | tau=2 | Gaussian | Gaussian | 16,40 |
| C04 | Gaussian Joint-SD Shift, Large | sigma=tau=2 | Gaussian | Gaussian | 16,40 |
| C05 | Heavy-Tail Global Null | none | standardized t5 | standardized t5 | 16,40 |
| C06 | Gaussian Within-SD Shift, Moderate | sigma=1.25 | Gaussian | Gaussian | 16,40 |
| C07 | Gaussian Between-SD Shift, Moderate | tau=1.25 | Gaussian | Gaussian | 16,40 |
| C08 | Heavy-Tail Residual Null | none | Gaussian | standardized t5 | 16,40 |
| C09 | Heavy-Tail Intercept Null | none | standardized t5 | Gaussian | 16,40 |
| C10 | Small-Sample Gaussian Null | none | Gaussian | Gaussian | 8,5 |
| C11 | Small-Sample Heavy-Tail Null | none | standardized t5 | standardized t5 | 8,5 |

SD multipliers 1.25 and 2 imply variance ratios 1.5625 and 4. They are benchmark perturbations, not asserted clinically or practically important effects. C00–C05 deliberately retain all six previously inspected Round50 mechanisms; C06–C11 add moderate effects, component-specific tail stress, and a joint small-n/small-m stress. This is a targeted, nonfactorial design. C10/C11 cannot distinguish loss from fewer entities versus fewer repeats, because both change. Near-zero components, skew, unequal repeat counts, informative cluster size, missingness, serial dependence, random slopes, group-asymmetric tail laws, and paired entities are unresolved external-validity gaps, not silently covered cases.

The generator must retain all raw binary64 values and entity/repeat order. The input settings are minimum measurements=2 and value bounds [-1000000,1000000]; if these bounds exclude a realized draw, the dataset is unavailable rather than redrawn. No clipping, transformations, sample replacement, or conditioning on metric availability is allowed. If the actual import/build path drops or changes any row, record input-retention failure for both methods. Raw byte identity and a canonical ordered binary64 digest are distinct, both retained.

## 3. Estimands, null hypotheses, and error families

The component parameters are sigma_g^2 (within-entity variance) and tau_g^2 (between-entity variance). The component nulls are H_W: sigma_0^2=sigma_1^2 and H_B: tau_0^2=tau_1^2, each leaving the other component and group means unconstrained. Their intersection H_V=H_W intersect H_B defines the component-family complete null. Under C01 both component nulls remain true: calling its variance-family rejection rate “power” would be incorrect.

For the summary route, the common global null H_D is equality of entity-vector distributions across groups. Under H_D, all 12 summary distributions agree. Its asymptotic Mann–Whitney tests are summary-level rank comparisons; their calibration and interpretation under unequal distributions are not a general test of equality of latent components. Under each stated alternative we report the probability of any summary rejection as a detection measure, not component identification or universal omnibus consistency.

The Gaussian route tests two components with Bonferroni family alpha=.05 and component cutoff .025. The summary route tests the fixed 12 metrics with Bonferroni family alpha=.05. Dependence among metrics alone does not invalidate Bonferroni; valid component p-values are required. We evaluate actual finite-sample behavior rather than assume those p-values are valid in all cells.

There are exactly **31 true-null cell/endpoint combinations**:

- Gaussian-route family: seven cells C00,C01,C05,C08,C09,C10,C11, nominal .05.
- Within component: those seven plus C03,C07, nominal .025.
- Between component: those seven plus C02,C06, nominal .025.
- Summary family: C00,C05,C08,C09,C10,C11, nominal .05.

In the four single-component alternatives the false rejection of the unchanged component is also the family-wise false-rejection event among true hypotheses. Report its .025 endpoint; do not duplicate it as an easier .05 criterion. These 31 endpoints are analysis-report multiplicity, separate from within-dataset Bonferroni correction.

## 4. Methods and fixed configurations

### Gaussian component family B199/E100

Execute the current `VarianceAnalysis.Run` with evaluation repetitions=100, reference replications=199, withinEffect=betweenEffect=2, alpha=.05, and a case-specific native seed. This is the pinned Round50 configuration, **not the CLI default of 200 evaluation repetitions**. Internal interval, power, FPR, and MDE diagnostics remain conditional plug-in calculations and are not outer-study validation outcomes.

The observed likelihood-ratio statistic fits unrestricted and appropriately constrained Gaussian random-intercept models. Preserve optimization, retry, boundary, reference-draw generation, inclusive ties, and unavailable-result semantics. The current reference p-value is (1+k)/(B_finite+1), where k is the count of finite reference statistics at least as large as observed. Usability requires at least 90% of requested reference draws, plus the production fit/statistic checks. Retain requested B, realized B_finite, failed draws, convergence and boundary diagnostics per component. Do not quietly replace this denominator with B+1 or discard an outer dataset because reference draws failed.

At B_finite=199, strict 2p<.05 rejects k<=3, with largest rejected p=.020. With failures, the attainable grid changes and must be reported. This fixed finite-B procedure is the method under study. No claim that a plug-in parametric bootstrap with a plus-one correction is an exact randomization test is made.

### Fixed 12-summary asymptotic MW/Bonferroni

Use actual production metric computations, asymptotic Mann–Whitney p-values (including their tie and continuity conventions), and adjustment by 12. The ordered family is median, standard_deviation, coefficient_of_variation, mad, iqr, normalized_mad, normalized_iqr, mean, rms, range, geometric_mean, trimmed_mean_20. Preserve the current finite-value filtering and minimum four usable entities per group per metric, while recording all pre/post-filter counts and availability. No removal of an unavailable metric from the multiplicity denominator is permitted.

This comparator is the observed-data fixed-summary test family. It does not execute MVS calibration, metric selection, score-based recommendations, or their full pipeline. The comparison therefore cannot establish performance of a deployed adaptive selector. A future selector must be a separately identified method with its complete information and decision policy.

### Candidate outside this run plan

`within_entity_variance_welch_centered_bootstrap_v1` is specified separately in [the comparator design](WITHIN_VARIANCE_COMPARATOR_DESIGN.md). It targets the mean of unbiased entity sample variances, uses centered groupwise resampling, and requires an independent implementation/oracle and asymmetric-tail equal-variance nulls in both orientations. It is not admitted into these two-method results. There is no proposed robust between-component test or robust two-component family in this release.

## 5. Performance measures, precision, and uncertainty

There are R=1,000 planned datasets per cell, 12,000 total, paired between methods. R is fixed before data generation. For a Bernoulli rate p, MCSE=sqrt(p(1-p)/R): .006892 at p=.05 and .015811 at p=.5. Approximate unadjusted 95% half-widths are 1.35 and 3.10 percentage points; exact intervals and simultaneous bounds are wider. This is precision planning, not assurance that a desired conclusion will be reached. No additional samples may be appended because an interval or result is disappointing.

Planning arithmetic, without generating datasets: with all 1000 outcomes known, the simultaneous rule flags a nominal.05 endpoint from 74 rejections, and a nominal.025 endpoint from 43. A true family error.075 would be flagged with probability about 56.5%; at.06 the probability is about 3.93%, and at.10 about 99.8%. Thus the design can detect large inflation reliably but often cannot resolve mild excess. An observed50/1000 yields simultaneous bounds approximately[.03092,.07551], not evidence of a strict5% guarantee. These are binomial design calculations, not MVS results; statistical failure/missingness makes resolution worse.

For x rejections in N complete Bernoulli observations, define exact binomial bounds with one-tail probability a:

    L(x,N;a)=0 if x=0, otherwise BetaQuantile(a; x,N-x+1)
    U(x,N;a)=1 if x=N, otherwise BetaQuantile(1-a; x+1,N-x).

For the 31 null endpoints use a=.025/31 for both bounds. A union bound gives at least 95% joint coverage of all 62 bounds without assuming endpoint independence. Flag detected inflation only if the simultaneous lower bound exceeds that endpoint's nominal .05 or .025. Otherwise report inconclusive with respect to a strict nominal-error guarantee. **No tolerance-PASS, scientific GO, or calibrated label is available.** In particular, absence of a detected excess is not evidence that p<=alpha. Upper bounds quantify the remaining uncertainty.

For target-component detection, report within rejection in C02/C04/C06 and between rejection in C03/C04/C07; additionally report both components correctly rejected in C04. Family-any rejection can include the wrong component, so it is not a substitute for these endpoints. For alternative detection rates, report exact marginal two-sided 95% intervals (a=.025), MCSE, and denominators. These intervals are not simultaneous. Report all conditions, including ceiling effects and losses.

For each cell retain the paired family decisions. Let b count Gaussian-only rejection, c summary-only rejection, and n the number of complete pairs. The descriptive difference is (b-c)/n. A conservative marginal 95% interval is [L(b,n;.0125)-U(c,n;.0125), U(b,n;.0125)-L(c,n;.0125)]; this uses separate 97.5% intervals for discordance probabilities and a union bound, not independent-sample standard errors. If n=0, the conditional estimate and its interval are unavailable; do not evaluate BetaQuantile with N=0. The R-based failure-inclusive bounds remain available. All 12 intervals are descriptive and not simultaneously 95%. C01 compares different true-null states and is explicitly a negative-control contrast, not a power-superiority comparison. No endpoint, route, or scenario winner is selected by these intervals.

## 6. Availability, failures, stopping, and resumption

A component has a known binary decision only when the production observed test is available and finite. A family outcome is true if any available member rejects, false only if all members are available and none rejects, and otherwise unknown. Save both the unmodified native payload and this conservative benchmark classification; the latter does not change the public CLI decision contract.

With R planned cases, r observed positive outcomes and f unknown/unattempted outcomes, report [r/R,(r+f)/R] as worst-case event-rate bounds. For null uncertainty use [L(r,R;a),U(r+f,R;a)]; this remains conservative without a missing-at-random assumption. Also report conditional-on-availability rates, clearly labeled; if no outcomes are available, their estimate and interval are unavailable rather than zero. Numerical failures, timeouts, malformed outputs, reference failures, and availability failures stay in their original denominators. Partial native artifacts are evidence, never successful decisions.

For paired rates, show complete-pair counts, both discordances, and u incomplete pairs out of R. A conservative failure-inclusive difference interval is [L(b,R;.0125)-U(c+u,R;.0125), U(b+u,R;.0125)-L(c,R;.0125)]. Its pointwise feasible difference range is [(b-c-u)/R,(b-c+u)/R]. Do not conceal paired missingness by reporting only complete-pair significance.

There are no replacement datasets, discretionary retries, or significance-driven early stops. A scientific or fit failure records that method's failure and continues the fixed plan, retaining the other method. Identity/hash/schema corruption or a deterministic harness defect halts the attempt. Resource exhaustion produces an incomplete study. Preserve all cases and the original failed attempt. A separately reviewed technical continuation may use only identical manifest-bound case identities; unknown partial native work is not automatically recomputed. Any changed scientific design requires a new protocol version and cannot retroactively pass the original.

## 7. Randomization, provenance, and independence

The proposed generator is NumPy 2.3.5 PCG64 initialized via SeedSequence with coordinates [2026101754,1,stream,cell_index,replication_zero_based]. Stream0 generates data. Stream1 labels native-case provenance only; the signed-int32 native seed is the collision-free reserved mapping `1540000000+1000*cell_index+replication_zero_based` (range1540000000–1540011999). This matches the native int32 API; it is not a truncated uint64 draw. Native and generator RNG algorithms differ; their implementations and versions must be pinned at execution freeze. SeedSequence stream partitioning is deterministic reproducibility engineering, not proof of mathematically independent pseudorandom streams.

Generate all 2n intercepts in group/entity order, then all 2nm residuals in group/entity/repeat order. Gaussian draws use `standard_normal`; t5 draws use `standard_t(5)*sqrt(3/5)`. The same realized dataset is supplied to both methods. Save starting/ending generator state, seed coordinates, derived native seed, ordered raw data, effective input counts, binary64 hashes, output envelopes and exit codes. Changing worker count must not change data or seeds; no global mutable RNG or worker-index seed is permitted. Check all native seeds for uniqueness and int32 range before use; a collision is a technical halt, not a seed-search invitation. The production per-operation seed mixing and runtime Random implementation remain pinned; distinct root seeds alone do not prove independent internal streams.

The utility in this release emits only coordinates and deterministic IDs, without instantiating NumPy or drawing a seed. Source bindings cover statistical implementations and historical registry/evidence. Final execution additionally requires source/binary/runtime hashes, generator and adapter tests, per-case provenance validation, report-analysis hashes, and an immutable execution manifest. Machine-owner tampering and complete campaign capture are outside local-hash guarantees.

## 8. Cost and execution admission

The retained Round50 run used 192 datasets with eight workers and 667.6336285640136 seconds including serialization. Simple linear scaling gives 41,727.10178525085 seconds (11.59 hours) for 12,000 datasets. This is an uncertain reference calculation, not a measured forecast: small cells, convergence, hardware, tracing and resource contention change cost. It is not valid to substitute inference-only microtiming for full public `Run` work.

The proposed ceiling is 24 hours total, eight workers, 2 GiB aggregate measured RSS, and 300 seconds per case. The fixed engineering probe is specified separately from the study: use the existing deterministic `Fixture()` in `validation/variance_sensitivity/Program.cs` (1280 formula-defined values, no RNG), with the exact B199/E100/effects2 configuration. Run three fresh sequential calls and one batch of eight fresh parallel calls, at most11 calls and300 seconds total. Every call uses native seed52000000, a one-CPU runtime cap, disabled backups and no restore/cache replay. The existing Round50 `Complete` observer contract must verify all expected callbacks exactly once, complete reference/evaluation/grid counts, finite required statistics, and correct session ownership for every call; an incomplete cheaper run cannot admit the budget. Measure input build, full variance work, summary computation, serialization and process lifecycle. Preserve every cost and failure. No inferential outcome from this fixture may choose scenarios, effect sizes, R, B, or the study seed.

The conservative admission calculation is twice the larger of the maximum sequential case wall time and the eight-call batch wall time, multiplied by12000/8; it must fit86400 seconds. Storage requires twice the maximum retained bytes per case times12000 plus1 GiB free margin; peak aggregate RSS must fit2 GiB. These are fixture-based resource screens, not worst-case guarantees for all stochastic datasets. Hard study limits still apply, and the study remains incomplete if they are reached.

Before admission, these fixed deterministic fixtures must establish the actual adapter's resource behavior, cleanup, complete failure recording, and cost under the selected machine. Keep all probe costs. Admission also requires measured storage and retention capacity: approximately 105.9 MB of historical logical evidence for 192 datasets scales to 6.62 GB for 12000 before packaging copies, with uncertain compression and different cells. No raw evidence may be silently dropped to fit a source ZIP. If this cannot fit the ceiling, stop before study generation and revise engineering or protocol transparently. Do not reduce R, B, or difficult cells after looking at outcomes. There is no paid-compute authorization in this plan.

A future inference-only adapter could avoid internal conditional power calculations, but it must first prove exact observed-decision/RNG equivalence against the full configured route. Such an optimization is not implemented here and cannot silently replace the baseline.

## 9. Executable contract and review gates

From the full source root:

    python validation/prospective_ademp.py --root . --check
    python validation/prospective_ademp.py --root . --plan /new/path/plan.json
    python validation/prospective_ademp.py --root . --check-execution-readiness

The first validates the fixed design and source bindings. The second creates a write-once plan of 12,000 IDs/coordinates, with config/document/utility hashes; this is not a simulated dataset. The third intentionally returns nonzero with missing adapter, binary/runtime, cost admission, and final-freeze blockers. Unknown fields, altered policies, missing or changed bindings, and inconsistent truths are rejected. Design validity cannot be promoted into execution readiness by editing a status field.

Before any scientific run: review the exact executable generator/adapter and endpoint derivation; validate hand cases and independent numerical/interval oracles; verify current methods against retained stable fixtures; freeze all identities and report analysis; admit measured cost; then obtain authorization for the bounded execution. No mandatory new exploratory 100-per-cell run is inserted merely to retest unchanged methods. If a new comparator needs development, those outcomes remain a separate development phase and all revisions finish before its evaluation freeze.

## 10. Unresolved questions and decisions

The immediate engineering gaps are adapter implementation, exact interval/report verification, artifact sizing, and measured resource admission. They do not require the owner to choose statistical formulas. The first scientifically useful result would be an honest map of error and sensitivity under this limited grid, not an automatic production recommendation.

The owner-level choice eventually concerns the intended scientific question: detection of any distributional change versus separately interpretable within/between variance changes, and the acceptable computational budget for a real application. Recommendation: keep both questions visible and their procedures separate until application requirements are specified. Do not combine methods or promise the Gaussian route is robust after its existing t5 warning. This design can be completed without that product decision; production routing cannot.

## References

[1] Morris TP, White IR, Crowther MJ. Using simulation studies to evaluate statistical methods. *Statistics in Medicine*. 2019;38:2074–2102. [doi:10.1002/sim.8086](https://doi.org/10.1002/sim.8086); [author manuscript](https://arxiv.org/html/1712.03198v3). ADEMP, Monte Carlo uncertainty, and reproducible streams motivate the structure; our specific cells and rules are our own.

[2] NIST. [Statistical Reference Datasets: how to use](https://www.itl.nist.gov/div898/strd/general/howto.html). Numerical reference checks have a narrower scope than statistical validation.

[3] Lazic SE. The problem of pseudoreplication in neuroscientific studies: is it affecting your analysis? *BMC Neuroscience*. 2010;11:5. [doi:10.1186/1471-2202-11-5](https://doi.org/10.1186/1471-2202-11-5). Repeated rows do not create independent entities.
