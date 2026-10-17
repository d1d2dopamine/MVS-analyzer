# Round 54: test-only within-variance comparator design

Status: prospective methodological specification, 2026-10-17. No implementation, scientific runs, generated datasets, package installation, or production changes were performed for this design. The candidate is not admitted to the current two-method prospective plan.

## Recommendation and limits

Retain **one candidate**: a two-sided, groupwise-centered empirical bootstrap of the Welch-studentized difference in the arithmetic means of independent entities' unbiased within-entity sample variances. Suggested identifier: `within_entity_variance_welch_centered_bootstrap_v1`.

This preserves the target residual variance, sigma_g^2, under the model below. “Robust” here means avoiding a Gaussian fourth-moment assumption when calibrating uncertainty; it does **not** mean bounded influence, resistance to arbitrary contamination, or finite-sample validity. A large residual can legitimately dominate an ordinary variance estimate. There is no established size guarantee at 16 entities/group, and this candidate has not been validated on independent data.

This is only a within-component test. It cannot replace, explain, or reproduce the between-component sensitivity previously observed for a between-SD multiplier of two. Do not label a hybrid of this test and the existing Gaussian between test a robust two-component family. No within or between confidence intervals, coverage results, or robust between estimator are supplied by this design.

## What the current source actually does

Read-only inspection used the preserved Round53 source baseline:

- `Core/VarianceAnalysis.cs:17–20,30–84,101–108`: Gaussian random-intercept likelihood; REML point estimates, ML likelihood-ratio tests. The within null constrains within variance across groups while leaving the between component group-specific; the converse holds for the between null.
- `Core/VarianceAnalysis.cs:87–99`: bootstrap cluster means are Gaussian and within sums of squares are generated as sigma_g^2 times a chi-square with repeat-count-minus-one degrees of freedom. This imposes Gaussian sample-variance variability.
- `Core/VarianceAnalysis.cs:160–210`: one fitted-null reference distribution per component; the reference p-value is `(1+k)/(m+1)` using its finite reference count. The shipped family allocates alpha/2 to each of two components, with strict `<` rejection. Internal evaluation draws do not refit a new bootstrap reference for every evaluation dataset; their rates are conditional on the original fitted null and reference.
- `Core/VarianceAnalysis.cs:129–132`: reported diagnostic within moment is pooled within sums of squares divided by pooled residual degrees of freedom. With equal repeat counts, this is exactly the arithmetic mean of the entity sample variances proposed here. The new comparator is not the existing fitted REML estimator.
- `Core/EstimationStudy.cs:34,46–54,92–93`: `normal_mad_variance` is a distinct normal-consistency-scaled MAD estimator. The current variance-estimation study rejects nonnormal shapes. Its existence does not validate a t5 variance comparator.
- `validation/variance_component_moment_oracle.py:20–26,76–111`: existing exact algebra checks the IID sample-variance identity. At 40 repeats and standardized t5 errors, the variance of each W is 157/40 = 3.925 times the Gaussian counterpart; group averaging over 16 entities preserves that ratio. The file expressly says these are moment identities, not likelihood-ratio calibration or validation of a robust test. It was inspected, not rerun.

The retained Round 50 result (5/32 t5 component-family null rejections versus 0/32 legacy-family rejections) motivates a prospective study. It does not identify which mechanism caused those particular rejections, establish a population false-positive rate, or license choosing a candidate by replaying those outcomes.

## Estimand, model, and admissible scope

Let g be 0 or 1, i index N_g independent entities, and j index m repeats:

`Y_gij = a_gi + epsilon_gij`, with `a_gi = mu_g + b_gi` constant across that entity's repeats.

For this first protocol, require:

1. Exactly two independent groups; entity vectors independent across entities and groups. No paired entities, shared batch shocks, crossed clustering, or repeated entities across groups.
2. A fixed, balanced repeat count m = 40 for every entity and N_0 = N_1 = 16 for the primary small-sample cell. Prospectively specified larger entity-count cells may use the same method. Do not silently pool unequal repeat-count strata into this first implementation.
3. Within each group, errors IID across repeats and entities, with mean zero, common variance `0 < sigma_g^2 < infinity`, and finite fourth central moment `mu4_g`. Each group may have its own error shape and fourth moment. Cleanly specify errors independent of entity intercepts in the generator.
4. The distributions of entity intercepts, their variances, and group locations need not be equal. They cancel from W algebraically. This does not make the test robust to numerical loss of precision from huge raw offsets.
5. No serial correlation, drift, repeat-specific means, repeat-specific error variance, informative repeat counts or missingness, outcome-dependent filtering, truncation, or entity-specific error-scale mixtures under the common-sigma interpretation. These require a different target or a separately justified design.

Under common repeat variance but serial correlation, the exact expectation is `E(W) = sigma^2 - 2 sum_{j<k} Cov(epsilon_j,epsilon_k)/(m(m-1))`. Repeat-mean drift adds another contribution. Thus resampling entities cannot repair the residual-variance estimand under those violations. Entity-level residual-scale heterogeneity can instead target an average entity variance, but that is not automatically the stipulated common sigma^2.

The key IID object for the proposed calibration is W within each group. Finite fourth residual moments ensure finite second moments of W. Require `0 < Var(W_gi) < infinity` in both groups for the stated asymptotic argument. The conditions are scientific assumptions, not properties certified by a sample kurtosis or a normality pretest.

## Formulas and derivation

For each entity compute:

`W_gi = sum_j (Y_gij - Ybar_gi)^2 / (m-1)`.

Then define:

`Wbar_g = sum_i W_gi / N_g`

`v_g = sum_i (W_gi-Wbar_g)^2 / (N_g-1)`

`D = Wbar_1-Wbar_0`

`SE = sqrt(v_1/N_1 + v_0/N_0)`

`T = D/SE`.

The hypothesis is `H0: sigma_1^2 = sigma_0^2`, against unequal variances. Do not replace W by its logarithm, rank, median, trimmed mean, winsorized value, or squared normalized MAD: those replacements do not generally preserve this mean-variance estimand.

The existing oracle's identity gives:

`E(W_gi) = sigma_g^2`

`Var(W_gi) = [mu4_g - ((m-3)/(m-1))*sigma_g^4]/m`.

Consequently `E(D) = sigma_1^2-sigma_0^2`, while its variance can differ across groups even under H0 because their fourth moments differ. The separate empirical v_g terms estimate that uncertainty instead of fixing Gaussian kurtosis. This algebra, together with an ordinary independent-groups central limit argument, is the reason to test means of W rather than equality of their entire distributions.

## Exact proposed resampling rule

For each of B independent bootstrap draws:

1. Draw N_0 indices independently and uniformly with replacement from group 0's entity indices. Independently draw N_1 indices from group 1. Never pool the two groups, permute labels, or resample raw repeats.
2. Let `Wbar_g*` and `v_g*` be the arithmetic mean and unbiased sample variance of the resampled W values.
3. Compute `T* = [(Wbar_1*-Wbar_1) - (Wbar_0*-Wbar_0)] / sqrt(v_1*/N_1 + v_0*/N_0)`.

This is algebraically equivalent to resampling the centered arrays `Z_gi = W_gi-Wbar_g`, whose empirical means are both zero, and computing the Welch statistic on Z. The resample's own denominator is essential. Negative centered Z values are valid; they are fluctuation values, not simulated physical variances, so do not clip them to zero. Adding the same arbitrary constant to both centered arrays changes nothing and is unnecessary.

Count `K = number of b with abs(T*_b) >= abs(T)`; ties belong to the upper tail. With all B draws valid, use the prespecified Monte Carlo convention `p_MC = (1+K)/(B+1)`. This is a two-sided absolute-statistic bootstrap test, not twice a one-sided p-value. Use a fresh centered bootstrap from every outer dataset; no reused reference distribution and no outcome-triggered increase of B.

Hall and Wilson's original paper supports null centering and recomputation of the studentizing scale for bootstrap testing. It does not prove that this particular n=16 variance comparator controls size. See [Hall and Wilson, 1991, sections 2–3](https://www.jstor.org/stable/2532163) and the [original article text](https://ruc-econometrics.weebly.com/uploads/2/3/3/8/23387606/two_guidelines_for_bootstrap_hypothesis_testing.pdf).

## What validity can and cannot be claimed

Under the stated IID, finite-positive-Var(W) assumptions, with both N_g tending to infinity at nonvanishing relative proportions, the ordinary studentized mean CLT and independent groupwise empirical bootstrap give a **pointwise first-order asymptotic justification**. This is an application of the mean/studentized-bootstrap theory of [Bickel and Freedman, 1981, section 2](https://www.math.ntu.edu.tw/~hchen/teaching/LargeSample/references/BickelFreedman81.pdf), not a newly established finite-sample theorem. No uniform accuracy over every finite-fourth-moment residual law follows. An ideal bootstrap quantile or a suitably increasing B separates this sampling argument from finite simulation error.

At N_g = 16, the empirical tail shape is estimated from only 16 W values. Standardized t5 residuals have fourth moment 9 when variance is one; sixth and higher residual moments do not exist. Thus W has finite variance but can be very skewed and lack a finite third moment. Do not invoke generic second-order accuracy, an Edgeworth rate, “bootstrap robustness,” or the number of raw repeats (640/group) as a small-sample certificate. Forty repeats do not create 640 independent W observations.

Unstudentized label permutation or pooled bootstrap requires stronger distributional conditions than equality of E(W). Properly studentized permutation procedures can be asymptotically valid under weaker nulls; they are not generically finite-sample exact under equal means alone. This distinction is established by [Chung and Romano, 2013](https://arxiv.org/abs/1304.5939). This design selects the groupwise-centered bootstrap, not a second candidate permutation procedure.

With B = 9,999, the p-value grid spacing and minimum are 0.0001. At component alpha 0.025 and strict rejection, K must be at most 248. Conditional Monte Carlo standard error for K/B near 0.025 is approximately 0.00156. The plus-one convention avoids a reported zero and fixes a reproducible grid; it does **not** turn estimated-null bootstrap samples and the observed sample into an exact exchangeable randomization ensemble. Report B and K, not just p, and distinguish inner Monte Carlo uncertainty from outer false-positive-rate uncertainty. Increasing B does not fix small N_g calibration error.

## Failure and degeneracy policy

Prespecify a deliberately conservative availability contract for this first candidate:

- Reject the input as unavailable if the scope checks fail, any W or intermediate quantity is nonfinite, or either observed v_g is zero. Do not insert arbitrary epsilons, use a pooled denominator, or return p=0 or p=1 as if it were a completed test.
- For any bootstrap draw with zero total denominator, nonfinite statistic, overflow, or another arithmetic failure, record the exact reason and draw index. Do not drop that draw, reduce B, or generate a replacement draw. The dataset-level comparator is unavailable if any draw fails. A legitimate zero group-specific v_g* is permitted if the combined denominator is positive.
- Use numerically stable two-pass or compensated variance accumulation. A common positive scaling of all W can be used without changing T or T*, but the arithmetic policy and scaling must be frozen and tested before results are opened. Centering, clipping and rounding must not create unrecorded differences between routes.
- Retain the planned B and attempted/completed/failed counts. An unavailable result is not evidence for equality or successful error control.
- In an outer study with N planned datasets, R valid rejections and F unavailable datasets, report R/N, F/N and the failure-sensitivity interval `[R/N,(R+F)/N]`. A successful-only R/(N-F) rate is secondary and explicitly conditional. Do not pass a calibration gate because failures happen to count as non-rejections. Require zero unavailable datasets for an unqualified primary calibration result, or classify that gate as incomplete pending a separately approved handling rule.

The strict bootstrap failure rule is an implementation contract, not a general statistical necessity. Its rationale is to prevent silent conditioning on successful resamples. Under the stated nondegenerate distributions the exceptional resampling event vanishes asymptotically; its actual small-sample frequency must be reported. No adaptive replacement method is authorized by this specification.

## Prospective evaluation and attribution

Use new, frozen outer data and random-stream coordinates, with paired identical outer inputs across comparators. Specify all scenario and method choices before viewing results. Retained Round 50 data remain development evidence, not independent validation. In each new dataset, compare this test's within decision with the shipped within decision at the same 0.025 allocation; keep legacy-family and Gaussian two-component-family decisions separate.

Minimum cells for the eventual plan:

- Gaussian common sigma null; Gaussian location-only and between-variance-only changes, both still within-null cells.
- Standardized t5 common sigma null in both groups.
- Equal sigma with Gaussian errors in one group and standardized t5 in the other, both group orientations. This is the essential unequal-nuisance-shape null missing from a common-shape-only check.
- Corresponding within-SD multiplier alternatives (e.g. the predeclared 2x SD, which is a 4x variance alternative), retaining all other scenario coordinates. Power means rejection of a false within null, not any family rejection.
- Predeclared larger independent entity counts to characterize finite-N behavior; no search over N based on favorable results.

Freeze the main protocol's outer N, Monte Carlo interval method, size tolerance, multiplicity, power targets, and gates before execution. Report binomial uncertainty and per-cell failures. A nominal-level benchmark at 0.025 is not the same as a gate at 0.05. Do not equate the single within test's rejection rate with two-component familywise error.

The Gaussian within pooled-sums-of-squares F reference remains useful where Gaussian assumptions hold; the current balanced design has 16*(40-1)=624 residual degrees of freedom per group. [NIST's F-test description](https://itl.nist.gov/div898/handbook/eda/section3/eda359.htm) defines the variance-ratio reference. It is not a distribution-robust comparator on t5 data. [NIST's Levene description](https://itl.nist.gov/div898/handbook/eda/section3/eda35a.htm) uses absolute deviations; it does not supply the entity-aware sigma^2-preserving calibration needed here for different error shapes. This is why MAD or a routine Levene replacement is not selected.

## Executable configuration field suggestions

The following is valid JSON suitable as a prospective config section; it is not a runnable implementation or evidence that the method exists. The containing benchmark protocol must assign outer dataset counts and concrete random-stream seeds before any execution. No placeholder may silently fall back to a default.

```json
{
  "method_id": "within_entity_variance_welch_centered_bootstrap_v1",
  "status": "specified_not_implemented_not_validated",
  "production_enabled": false,
  "estimand": "sigma_squared_common_within_each_group",
  "null": "sigma_squared_G0_equals_sigma_squared_G1",
  "component": "within_only",
  "groups": ["G0", "G1"],
  "independent_unit": "entity",
  "primary_entities_per_group": [16, 16],
  "fixed_repeats_per_entity": 40,
  "unequal_repeat_counts": "unavailable_in_v1",
  "entity_statistic": "unbiased_sample_variance_ddof_1",
  "group_estimator": "arithmetic_mean_entity_variances",
  "studentizer": "sqrt(samplevar_W_G1_ddof1/N1+samplevar_W_G0_ddof1/N0)",
  "bootstrap_unit": "entity_variance",
  "bootstrap_sampling": "independent_with_replacement_within_each_group",
  "bootstrap_sample_sizes": "original_entity_counts",
  "bootstrap_centering": "subtract_original_group_mean_in_each_group",
  "bootstrap_studentizer": "recompute_from_each_resample",
  "bootstrap_draws": 9999,
  "bootstrap_tail": "absolute_statistic_greater_than_or_equal",
  "bootstrap_p": "(1+exceedances)/(1+planned_draws)",
  "bootstrap_draw_replacement": false,
  "bootstrap_reference_reuse_between_datasets": false,
  "bootstrap_adaptive_extension": false,
  "required_seed_fields": ["protocol_seed", "scenario_id", "outer_replication", "method_id", "group_id"],
  "seed_and_rng_binding_required_before_execution": true,
  "random_stream_role": "inner_bootstrap_disjoint_from_outer_generation",
  "primary_component_alpha": 0.025,
  "primary_rejection": "p_less_than_alpha",
  "alpha_allocation_rationale": "matched_within_slot_of_existing_two_component_family",
  "maximum_exceedances_for_primary_rejection": 248,
  "complete_robust_component_family_claim": false,
  "observed_zero_group_variance": "dataset_unavailable",
  "bootstrap_zero_total_denominator": "dataset_unavailable",
  "nonfinite_arithmetic": "dataset_unavailable",
  "maximum_failed_bootstrap_draws": 0,
  "drop_failed_draws": false,
  "unavailable_dataset_p": null,
  "outer_failure_handling": "retain_all_planned_datasets_report_failure_bounds",
  "unqualified_primary_gate_requires_zero_unavailable": true,
  "within_interval": "not_supplied",
  "between_estimator_or_test": "not_supplied",
  "coverage_claim": "none",
  "finite_sample_size_guarantee": "none",
  "asymptotic_scope": "pointwise_first_order_finite_positive_variance_of_W",
  "required_outputs": [
    "scenario_id", "outer_replication", "input_hash", "method_version",
    "seed_binding", "N0", "N1", "m", "Wbar0", "Wbar1", "v0", "v1",
    "difference", "standard_error", "T", "B_planned", "B_completed",
    "B_failed", "exceedances", "p_MC", "alpha", "reject",
    "status", "failure_reason"
  ]
}
```

Before implementation approval, add literal nonrandom fixtures for unbiased W, exact centering equivalence, intercept-shift invariance, common-scale invariance, group reversal with matched index tapes, K ties and strict-grid boundaries, observed and resampled degeneracy, nonfinite arithmetic, no replacement, and all failure-count denominators. Independent arithmetic checks are required before any new scientific run. None were executed here.
