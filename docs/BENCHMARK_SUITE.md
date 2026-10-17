# MVS Benchmark Suite 1.1.0: specification and evidence policy

**Current evidence view:** Suite 1.1.0, assembled 2026-10-17 after the fixed NIST univariate numerical study. Current registry: `validation/benchmark-suite-v1.1.json` in the full source archive; generated view: [BENCHMARK_RESULTS_V1_1_RU.md](BENCHMARK_RESULTS_V1_1_RU.md). The original `validation/benchmark-suite-v1.json` and [Suite 1.0.0 table](BENCHMARK_RESULTS_RU.md) are preserved byte-for-byte as the Round52 historical snapshot. Its mapped-not-run entries describe that earlier state. Validation tooling is not shipped in the separate runtime bundle.

The suite is not an aggregate performance score, a certification scheme, or an assertion that MVS has achieved independent confirmatory validation. Round53 executed two numerical operations on nine official fixed vectors; no new scientific simulation was performed. The result is [16/18 numerical comparisons passing, with both failures retained](NIST_UNIVARIATE_RESULTS.md).

## 1. Purpose and external foundations

The suite separates numerical implementation accuracy, empirical statistical operating characteristics, stability of recommendations, and engineering integrity. These are distinct targets: agreement with a numerical reference cannot establish type-I error control, and a reproducible simulation can reproduce a poorly calibrated procedure.

NIST Statistical Reference Datasets (StRD) supplies datasets with model-dependent reference values for univariate statistics, balanced one-way ANOVA, and linear/nonlinear regression. Its instructions require reproducing the specified calculation and comparing across relevant difficulty levels. NIST does not certify MVS or endorse software based on this use. See the official [instructions](https://www.itl.nist.gov/div898/strd/general/howto.html) and [FAQ](https://www.itl.nist.gov/div898/strd/general/faq.html). The direct mapping covers only arithmetic mean and sample standard deviation. Their first fixed StRD execution is MVS-NUM-NIST-UNIVARIATE-1.0.0, with 16/18 primary comparisons passing. All other mapped categories remain unsupported by the inspected MVS interfaces. Optimizer availability is not equivalent to a specified nonlinear least-squares implementation; Kruskal–Wallis and Gaussian random-intercept fitting are not NIST's balanced one-way ANOVA calculation.

ADEMP is a planning/reporting framework: Aims, Data-generating mechanisms, Estimands and other targets, Methods, and Performance measures. It is not a dataset, benchmark result, numerical oracle, accreditation, or set of universal acceptance thresholds. Source: Morris TP, White IR, Crowther MJ, *Using simulation studies to evaluate statistical methods*, Statistics in Medicine 2019;38:2074–2102, [doi:10.1002/sim.8086](https://doi.org/10.1002/sim.8086), [author manuscript](https://arxiv.org/html/1712.03198v3). The requirements below are the MVS project's explicit application of that framework; their inclusion does not establish that every historical study satisfied them prospectively.

## 2. Versioned identity and evidence classes

Method-version labels in this retrospective registry identify the method slot within the pinned original protocol; they are not newly assigned software releases or substitutes for the original source/binary hashes. For document-defined historical protocols, the listed original document and amendment hashes jointly define identity. Missing unified dataset digests remain explicit nulls rather than invented dataset identifiers.

The registry has a schema version and suite version independent of the engine, algorithm, and historical benchmark versions. A row's scientific identity is the tuple

\[
(\text{benchmark ID/version},\ \text{protocol identity},\ \text{method ID/version},\
 \text{data identity},\ \text{endpoint/family},\ \text{execution environment}).
\]

A display name cannot replace this tuple. **MVS-BENCH-1.2.0 retains its original identity and outcome.** The 5,490 recorded historical work units comprise 5,370 replication rows and 120 stability rows. Neither total is automatically a count of independent datasets: row independence and repeated or paired data must be established from the seed/data identities before making that claim. Subsequent development experiments are not new measurements of that same benchmark unless their full protocol/method/data compatibility is established. In particular, the Round50 variance-component comparison is a comparison of two existing procedures under different scientific questions, not a measured improvement in the shipped MVS-BENCH-1.2.0 score.

Evidence classes are deliberately separate:

1. **Numerical reference/contract:** fixed-input agreement with certified or independently calculated mathematical quantities. Scope ends at the tested quantity, input domain, and tolerance.
2. **Development simulation:** empirical operating characteristics on inspected design families. Historical development observations remain development even when they were initially frozen before execution.
3. **Computational audit:** reproduction of saved arithmetic, random assignments, checksums, or aggregates. An independent implementation audit is not an independent sample or independent scientific validation.
4. **Stability diagnostic:** repeatability or ranking agreement under the recorded perturbation/split design. Larger candidate sets can increase agreement mechanically; stability alone does not establish sensitivity or correctness.
5. **Engineering contract:** serialization, failure accounting, replay, and execution integrity. Technical success is distinct from statistical applicability.

No untouched confirmatory-validation track is populated. Retrospective registration of historical evidence in this registry is explicitly marked. It neither changes original stopping rules nor creates an earlier preregistration. A past numerical pass is preserved only for its original predeclared numerical contract; it is never promoted to a universal statistical pass.

## 3. Required study specification before new execution

A future executable study must freeze the following fields in its own immutable protocol before generating evaluation outcomes. A descriptive registry entry alone does not authorize or fully specify a new run.

### A: Aim and decision claim

State the scientific question, intended population/design domain, and whether the target is numerical error, bias, interval coverage, null rejection probability, power, metric selection, or computational cost. State separately whether the study compares software revisions holding a method fixed, or different methods holding the data fixed. A route-selection or union-of-tests policy is a new method, not an innocuous display choice.

### D: Data-generating mechanisms

Specify equations, distributions, parameter values, factor grid and interactions, independent units, group allocation, repeated-measurement structure, transformations, censoring/missingness, filtering, and the exact truth for every endpoint. For a balanced random-intercept example,

\[
Y_{gij}=\mu_g+B_{gi}+E_{gij},\quad
\operatorname{Var}(B_{gi})=\tau_g^2,\quad
\operatorname{Var}(E_{gij})=\sigma_g^2.
\]

Independence across entities, dependence within entities, conditional repeat independence, and distributional assumptions must be explicit, not inferred from the data format. Changes to \(\mu\), \(\sigma\), and \(\tau\) are distinct interventions. A multiplier of standard deviation is not a multiplier of variance. Future generalization designs must address, or explicitly exclude, unbalanced/informative cluster sizes, serial correlation, missingness, skewness, heavy tails, contamination, near-zero components, and changes in more than one component. No universal claim is supported by a convenient subset of these conditions.

### E: Estimands, nulls, and multiplicity

For the component route, define \(H_W:\sigma_0^2=\sigma_1^2\) and \(H_B:\tau_0^2=\tau_1^2\), including nuisance parameters allowed to differ. For a summary-distribution route, state the exact rank-test target and the family of summaries; it does not automatically identify a latent variance component. A location-only change can be an alternative for the summary family and simultaneously a null for both component hypotheses.

Specify sidedness, strict/non-strict threshold convention, alpha, family membership and size, missing-member policy, and the level of the error claim. Bonferroni controls a declared family only when its member p-values satisfy the required validity conditions. It does not repair model misspecification. Per-run family control does not control an unrecorded campaign of analytical choices. Pooling entity labels requires the applicable exchangeability conditions; equality of one variance component with unequal nuisance distributions does not imply exchangeability.

### M: Methods and comparators

Pin source and binary hashes, engine/method versions, preprocessing and numerical settings, optimization bounds/tolerances/restarts, bootstrap budgets, metric registry, calibration data, failure fallbacks, and any selection rule. Justify comparators by the question they answer and the information available to them. A truth-informed oracle must be labelled as such; it cannot be silently treated as an equally informed deployable method. Compare methods on the same datasets when paired inference is intended. Record any method-specific exclusions rather than silently changing denominators.

### P: Performance measures and uncertainty

For condition \(c\), method \(m\), and requested replicate count \(R_c\), retain every decision and availability state. Let \(K_{cm}\) be rejections and \(U_{cm}\) unavailable decisions. Report \(R_c\), attempted/completed/valid counts, the operational yield \(K_{cm}/R_c\), and failure bounds

\[
[K_{cm}/R_c,\ (K_{cm}+U_{cm})/R_c].
\]

Calling this yield a false-positive rate or power requires the corresponding null/alternative and a disclosed failure convention. Conditional-on-success rates, if reported, are additional views rather than replacements. Missing or inapplicable values are explicit, never zero-filled results.

For ordinary independent outer Bernoulli replications, a planning approximation is
\(\operatorname{MCSE}(\hat p)\simeq\sqrt{p(1-p)/R}\).
Choose \(R\) from a prespecified precision target and feasible cost; include uncertainty near zero/one using an appropriate binomial interval, not a zero-width Wald interval. Inner Monte Carlo randomness and parameter-fitting uncertainty are distinct from outer simulation uncertainty. A finite-bootstrap p-value \((1+k)/(B+1)\) has a discrete attainable grid; freeze how ties and failed reference draws affect its denominator.

For paired methods retain the full paired table, including missing states. With candidate-only rejections \(b\) and comparator-only rejections \(c\), the operational difference is \((b-c)/R\). Specify its paired interval before the run. Round50 retains its original conservative interval formed by subtracting endpoints of two 97.5% Clopper–Pearson discordance intervals; this is pointwise, not simultaneous across conditions. The suite does not replace historical Wilson intervals with a new convention after seeing results. Do not infer equivalence from overlapping intervals or superior power from a larger set of selected metrics.

## 4. Reproducibility, execution and stopping

Freeze method/protocol/data identities and the seed or RNG-state manifest before execution. Pin the RNG algorithm and library version, stream derivation, order of generation and task scheduling, and independence between outer data and inner simulation streams. Reusing a dataset across paired methods is intentional pairing; reusing inspected data for method development is not untouched validation. New seeds alone do not demonstrate generalization to unseen mechanism families.

Retain raw inputs or sufficient lossless inputs, per-replication outputs, all failures, original attempts, logs, execution identities, and aggregation code. Local hashes detect a mismatch against a trusted manifest; they do not prove prospective registration, completeness of all attempted campaigns, or resistance to the machine owner's rewriting of records. An external registration/archival mechanism is not implemented by this release.

Prespecify fixed replication count or a justified sequential design, time/memory/storage budgets, cancellation policy, and maximum retries. Stop for invalid harness/provenance rather than silently accepting a plausible result. Numerical failure, unavailable inference, resource timeout, and technical execution failure are different statuses. A failed attempt remains retained when a separately identified technical continuation is justified. No optional sampling, replacement seeds, threshold relaxation, or omission of unfavorable conditions is permitted to rescue a gate.

Measure wall time, CPU, memory, setup and serialization under matched conditions when claiming software performance changes. Streaming observer overhead and dissimilar workloads must be disclosed. Round50's full variance Run includes intervals and internal sensitivity calculations, while its legacy comparator executes observed tests only; their elapsed times are not an intrinsic inference-speed ratio.

## 5. Numerical-reference track: prospective NIST contract

The registry's operation mapping is a support inventory, not a result. Before a StRD execution, freeze the selected official datasets/fields, original byte hashes and URLs, parser treatment, exact method options, reference precision, domain, and absolute/relative error tolerances. Cover appropriate easy/intermediate/difficult cases and report each result. A tolerance is an MVS test-contract choice justified for the operation, not a NIST-issued universal pass mark. Preserve a certified zero or near-zero reference without dividing blindly by its magnitude.

Current direct candidates are arithmetic mean, \(\bar x=n^{-1}\sum_i x_i\), and sample standard deviation, \(s=\sqrt{\sum_i(x_i-\bar x)^2/(n-1)}\). Under the usual i.i.d. finite-variance sampling assumptions, the variance uses the unbiased n−1 denominator; the square root itself is not an unbiased estimator of population standard deviation. The adapter must preserve the supplied vector without filtering or restructuring it. Lag-one autocorrelation, the specified ANOVA calculation, ordinary linear least squares, and specified nonlinear least-squares models are not mapped to supported MVS APIs. No generic optimizer or different scientific model may be substituted to fill the table. Before an operation-specific contract and actual execution exist, statuses remain `mapped_not_run` or `unsupported`. Suite1.1 records these two operations as `executed_numerical`, which is an execution status rather than an all-pass or certification status.

## 6. Registration and validation rules

`python validation/benchmark_suite.py --root . --check` validates the registry, local reference paths/hashes, typed JSON-pointer observations, count bounds and required limitations, then checks that the committed evidence view is current. `--write` regenerates only that view from validated evidence. The command performs no scientific simulation, downloads, model fitting or native execution.

Changing a scientific method, scenario/claim, preprocessing rule, family, acceptance gate, or data-generation recipe requires a new protocol/method identity before a new evaluation. Corrections to registry metadata require a reviewed suite revision and retention of the prior version in version control. A local validator cannot prevent deliberate retrospective edits by an owner; the review and archival boundary is explicit. The registry may not mark historical evidence as untouched independent validation, invent missing uncertainty, or collapse outcomes into an aggregate score.

## 7. Known gaps and next eligible work

- Only mean/sample SD have been executed against StRD. Their two fixed-contract failures remain; unsupported operation categories have not been run.
- The historical development benchmark retains its NO-GO conclusions; numerical/reference success does not override them.
- Round50 has only 32 datasets per condition, strong SD multipliers of two, balanced repeats, and one heavy-tail stress family. It cannot certify a 5% error rate or general superiority. Its 5/32 variance-route rejections under equal-distribution t5 remain a robustness warning.
- A robust same-component estimand procedure has not been implemented or validated. Changing variance to MAD/winsorized scale would change the estimand and needs an explicit scientific specification.
- General unequal-nuisance between-component inference, boundary coverage, route-selection error control, campaign-level multiplicity, real-data transfer and independent validation remain open.
- Exact algebra checks from paused Round51 establish moment identities only; they neither calibrate the production likelihood ratio nor attribute the five stress rejections individually.

The first StRD mean/sample-SD study is complete and separately versioned. Further arithmetic or input-precision changes require a new frozen comparison; a new robustness simulation requires its own ADEMP protocol and precision/budget justification. Neither is implicitly executed by adding a registry row.


## Prospective statistical evaluation design (Round54)

[The prospective ADEMP protocol](PROSPECTIVE_ADEMP_V1.md) defines twelve cells, two fixed methods and31 simultaneous true-null endpoints. Its executable config/plan validator creates case identities only; no new outcomes have been generated and execution readiness is deliberately blocked pending implementation, binary/runtime, cost/storage and final-freeze admission. It does not add a result row or modify either historical registry snapshot. The separately specified within-variance comparator is not admitted into that run plan.
