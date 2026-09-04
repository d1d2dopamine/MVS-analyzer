# Methods — application 1.4.0 / engine 1.6.0

## 1. Data and estimands

One outcome in consistent units per run. Ordinary summary and component analyses assume independent entities and independent groups. Repeated rows within an entity are not independent subjects. `MELSM` instead uses global entity IDs and allows conditions to change within subjects.

The summary registry is ordered and fixed: median, sample SD, CV, MAD, IQR, normalized MAD, normalized IQR, arithmetic mean, RMS, range, geometric mean, 20% trimmed mean. The first ten positions preserve legacy indexing. The geometric mean is unavailable if an entity has non-positive values. Relative measures use absolute denominators and are unavailable within 1e-12 of the largest absolute entity value (a unit-relative near-zero guard). Trimming removes floor(0.2n) observations at each end. Quantiles use linear interpolation (type 7).

## 2. Empirical summary calibration

A common empirical pool contains whole entity measurement vectors. Both null and alternative sample entities from this same pool into the original group sizes. Repeated values are bootstrapped within each sampled entity, treating observations as exchangeable. This empirical generator is **not** a consistent latent-variance estimator; within resampling can change the variance of resampled entity means. Use the parametric component model for latent variance inference.

Let c_i be an entity's sample mean, C the mean of pooled entity means, and S=max(abs(C), pooled RMS within SD), with a fallback of 1 for a degenerate scale. For the **last group in input order** and multiplier k:

- location: y' = y + (k−1)S;
- decrease: y' = y − (k−1)S;
- within variability: y' = c_i + k(y−c_i);
- between heterogeneity: y' = C + k(c_i−C) + (y−c_i).

At k=1 all transformations are identities. These transformations separate the intended components **before optional missingness/contamination**. Missingness and finite resampling can alter realized sample means and variances. k is a relative shift parameter for location and an **SD multiplier** for scale tracks; variance is multiplied by k². It is not a universal percentage change of every metric.

Contamination and missingness use the same mechanism in every group, including the null. Common random streams are reused across metrics/tracks/effect sizes to reduce comparison noise, not to create independent estimates. The processing minimum is retained after missingness. Failed tests count as non-rejections in the requested-replication denominator. More than 10% failures suppress the corresponding rate; counts remain visible.

## 3. Inference and selection

Two groups: two-sided asymptotic Mann–Whitney with tie correction. Three to ten: asymptotic Kruskal–Wallis with tie correction. All ties return p=1. These are **not exact/permutation tests**. Four entities per group is a software minimum, not an assurance of valid asymptotics. A rejection concerns distributional differences, not necessarily a pure difference of medians.

With M=12 registered metrics, adjusted p=min(1,M·p). Every displayed difference decision uses adjusted p<alpha. Bonferroni includes the full registry, including unselected or unavailable metrics; candidate selection cannot add an uncorrected rejection opportunity. Validity still depends on the raw tests. Candidate labels do not remove the other displayed tests.

For each track, candidates must be applicable, have an acceptable FPR, and satisfy:

- upper 95% Wilson FPR bound ≤ max(1.5·alpha/M, alpha/M+0.02);
- lower 95% Wilson power bound ≥0.70;
- at most four candidates, ordered by the track's score (registry order breaks ties).

There is no score cutoff. A Wilson gate is an operational calibration heuristic, **not proof** of error control; its FPR allowance is stated explicitly.

The detection index is

    penalty = exp(−max(0, FPR−alpha/M)/(alpha/M))
    score = 100 sqrt(power × penalty)

It is not estimator MSE, construct validity or general scientific quality. Robustness, split-entity repeatability and pooled-median coverage are exported **descriptive diagnostics excluded from the score**.

## 4. Effect sizes and approximate equivalence

Cliff's delta is P(first>second)−P(first<second). Its sign agrees with the displayed `first vs second` pair. A 400-draw percentile bootstrap gives a **pointwise 95% descriptive** interval.

For more than two groups the pair with largest absolute delta is selected. Its unadjusted interval is explicitly labelled `selected_pair_descriptive`: it is not a multiplicity-controlled post-hoc claim and does not establish global equivalence.

Only two groups can receive the `equivalent` label. The 4,000-draw percentile interval at confidence 1−2(alpha/M) must lie strictly within the user-defined ±delta margin, and an adjusted difference takes priority. This is an **approximate interval-based criterion**, not an exact TOST p-value. The legacy `equivalence_p` field is intentionally blank/null. Percentile intervals at such extreme tails need validation, especially for small, discrete or highly tied samples. A non-rejection alone is `insufficient`.

## 5. Power curves and MDE

Grid k = 1, 1.02, 1.05, 1.10, 1.20. Replications cycle across grid points; the main requested-effect power still uses every replication. MDE is the first upward crossing of power 0.80 by linear interpolation, expressed as k−1. There is no monotonicity enforcement, extrapolation, or invented value above 20%. A crossing is not computed with fewer than 100 requested simulations per grid point, invalid rates, or unsuitable null behavior. A non-monotonic empirical curve can remain noisy. MDE uncertainty is not estimated in this release.

Unavailable values carry statuses such as insufficient simulations, target not reached, invalid curve or zero baseline. `null` does not imply no detectable effect. Binomial MCSE and Wilson intervals describe finite Monte Carlo uncertainty; they do not cover uncertainty in the empirical generator.

## 6. Gaussian variance components

    y_gij = mu_g + b_gi + e_gij
    b_gi ~ N(0, tau_g²), e_gij ~ N(0, sigma_g²)

Entities are independent; conditional residuals are independent and Gaussian. Means and both variance components can differ by group. Unbalanced repeat counts are retained. For each entity, the likelihood uses n_i, its sample mean and within sum of squares. Var(entity mean)=tau_g²+sigma_g²/n_i; the model explicitly separates measurement error from between-entity dispersion.

REML supplies group means, within/between estimates and ICC=tau²/(tau²+sigma²). The raw variance of entity means and the **untruncated** method-of-moments estimate Var(means)−pooledWithinVariance·mean(1/n_i) are also exported; negative moment estimates are not disguised as positive heterogeneity.

Two distinct ML likelihood-ratio tests constrain either all sigma_g² or all tau_g² to equality, leaving the other component group-specific. A plug-in parametric null bootstrap avoids relying on a chi-square reference near a variance boundary. Bootstrap p=(1+number of reference statistics ≥ observed)/(valid reference size+1). The two component hypotheses receive Bonferroni alpha/2. This is **separate from** the 12-summary family, not joint correction across workflows.

Reference simulations and evaluation simulations use separate streams. Null and alternative evaluation draws share random numbers. Alternative SD multipliers affect only the last group's tested component, while the other component remains at its fitted null values. Power/FPR intervals are conditional on fitted nuisance parameters and the one simulated reference distribution. Numerical failures count as non-rejections; excessive failures suppress rates. Multiplying a boundary-zero component does not define meaningful relative power, so that power/MDE is unavailable.

An additional parametric entity bootstrap from the full fitted REML model provides **pointwise** percentile 95% intervals for each variance component. It retains group/repeat counts and records successful refits. These are neither simultaneous intervals nor guaranteed to cover correctly at a boundary. The profile objective omits additive constants common to models on the same data; it is not an absolute full likelihood for comparison between datasets.

## 7. Known-truth estimation quality

This is a separate ADEMP-style study: aims, data-generating mechanism, estimand, methods, performance. It generates balanced random-intercept data with Gaussian, standardized t5 residuals, or a lognormal transform. Lognormal location/SD parameters are on the log scale.

Supported targets: population mean, population median, geometric mean (lognormal only), within variance and between variance (Gaussian only). Methods are compared **for one common target under the chosen mechanism**; mean and median do not get compared as if their targets were identical on a skewed distribution. Symmetric models allow robust location summaries to target the same population center, but finite-sample bias is measured, not assumed absent.

Outputs include bias, bias MCSE, MSE, MSE MCSE, RMSE, empirical SD, mean interval width, conditional coverage among valid intervals, unconditional coverage over requested replications, and failure counts. Whole entities—not independent rows—are resampled for percentile intervals. The first named estimator is the reference. Relative MSE efficiency=reference MSE/method MSE; relative variance efficiency is reported separately and can be misleading if biases differ. Zero denominators produce unavailable ratios. These results do not establish the true bias of a real uploaded file.

## 8. Optional experimental MELSM

    mean(y_ij | b_i,v_i) = mu_condition + beta·centered_scaled_time + b_i
    log Var(e_ij | b_i,v_i) = 2log(sigma_condition) + gamma·time + v_i
    (b_i,v_i) are jointly Gaussian

Global entity IDs identify subjects across conditions. At least eight subjects and three observations per subject are required by the software; reliable random-scale inference often needs substantially more. Time effects require a real integer sequence/timepoint column. Both slopes are optional. Random scale and location-scale correlation are optional; a correlation requires random scale.

The implementation integrates the normal random intercept analytically and the random log-variance effect numerically with subject-adaptive Gauss-normal quadrature. Bounded deterministic Nelder–Mead, alternate starts, independent quadrature orders and observed-information diagnostics are used. Quadrature-order agreement is a numerical check, **not a rigorous integration-error bound or global-optimum proof**. The common between-intercept variance, conditional residual variance at v=0, random log-variance SD and optional correlation are explicitly distinguished. Marginal residual variance includes the exp(omega²/2) factor.

Approximate pointwise Wald intervals are transformed from the optimization scale and suppressed for failed convergence, boundary fits, unstable quadrature or singular information. Empirical-Bayes random-effect summaries are conditional predictions, not independent observations or proof of a causal subject effect.

Not supported: AR(1), random slopes, arbitrary covariate formulas, ordinal/count responses, outcome transformations chosen automatically, nonignorable missingness, or automatic model selection. Conditional independence and the missingness assumption must be justified outside the program. The native implementation is **experimental and not independently validated**.

## References and validation status

- Morris, White & Crowther (2019), simulation studies and ADEMP: https://pmc.ncbi.nlm.nih.gov/articles/PMC6492164/
- Hedeker & Nordgren (2013), mixed-effects location-scale estimation: https://pmc.ncbi.nlm.nih.gov/articles/PMC3676904/

These references motivate methodology; they do not validate this implementation or imply equivalence to a published package. See [VALIDATION.md](VALIDATION.md) for what has and has not been tested.
