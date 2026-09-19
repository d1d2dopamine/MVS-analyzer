# Metric registry - 1.5 development line

MVS 1.5 introduces a structured metric registry so that summary statistics are no longer treated as one undifferentiated list. Each metric has a stable key, family, applicability rule, interpretation, and implementation status.

The registry checkpoint deliberately does **not** change inferential behavior. The active calibration and multiplicity family remains the frozen 12-metric registry from MVS 1.4.0. Four new metrics are implemented and tested, but remain staged until the later calibration and multiplicity redesign is ready.

## Registry

| Key | Family | Status in 1.5-A | Applicability | Interpretation |
| --- | --- | --- | --- | --- |
| `median` | location | active legacy | finite data | robust central location |
| `mean` | location | active legacy | finite data | arithmetic central location |
| `trimmed_mean_20` | location | active legacy | finite data | 20% trimmed central location |
| `geometric_mean` | location | active legacy | all values > 0 | multiplicative central location |
| `huber_location` | location | staged | finite data | Huber M location, `c = 1.345` |
| `hodges_lehmann` | location | staged | finite data, exact pairwise limit | median of Walsh averages |
| `standard_deviation` | variability | active legacy | finite data | sample within-entity SD |
| `mad` | variability | active legacy | finite data | unscaled median absolute deviation |
| `iqr` | variability | active legacy | finite data | interquartile range |
| `coefficient_of_variation` | variability | active legacy | mean sufficiently far from zero | SD / abs(mean) |
| `normalized_mad` | variability | active legacy | median sufficiently far from zero | MAD / abs(median) |
| `normalized_iqr` | variability | active legacy | median sufficiently far from zero | IQR / abs(median) |
| `range` | variability | active legacy | finite data | max - min |
| `qn` | variability | staged | finite data, exact pairwise limit | robust Qn scale |
| `log_sd` | variability | staged | all values > 0 | SD of natural-log measurements |
| `rms` | magnitude | active legacy | finite data | root mean square; combines level and spread |

The `magnitude` label for RMS is intentional. RMS is retained for backward compatibility but is not forced into a pure location or variability family.

## New metric definitions

### Huber M location

The implementation solves the Huber location estimating equation by iteratively reweighted averaging with tuning constant `c = 1.345`. The starting value is the sample median. Scale is fixed at `1.482602218505602 * MAD`; if that scale is numerically zero, the median is returned. The conventional `c = 1.345` choice is commonly used for about 95% asymptotic efficiency under a normal model while bounding the influence of large residuals.

### Hodges-Lehmann location

The one-sample Hodges-Lehmann estimate is the median of all Walsh averages `(x_i + x_j) / 2` with `i <= j`. This exact implementation is quadratic in the number of repeated measurements. Milestone 1.5-A therefore declares an explicit computational limit of 2048 measurements per entity for this metric. The limit is an implementation constraint, not a scientific threshold, and can be removed later with a more efficient exact algorithm.

### Qn robust scale

`Qn` is computed from pairwise absolute differences. For sample size `n`, let `h = floor(n/2) + 1` and `k = choose(h, 2)`. The raw statistic is the `k`th ordered value among `|x_i - x_j|`, `i < j`.

MVS uses the corrected normal-consistency constant `2.219144465985076`, rather than the historical `2.2219` typo, together with finite-sample correction factors compatible with the modern robustbase definition. The exact pairwise implementation currently shares the 2048-measurement computational limit with Hodges-Lehmann.

### Log-scale SD

`log_sd` is the sample standard deviation of `ln(x)`, so all measurements must be strictly positive. Multiplying every measurement by the same positive constant leaves `log_sd` unchanged, which makes it useful for multiplicative or approximately lognormal variability.

## Why the new metrics are staged

Adding metrics immediately to the active family would change the Bonferroni denominator from 12 to 16 and would therefore change adjusted p-values before the new multiplicity method exists. That would mix two development steps and make benchmark differences hard to interpret.

During the registry/calibration checkpoints:

- `AnalysisEngine.MetricKeys` remains exactly the 12-metric MVS 1.4 order;
- saved 1.4 calibration shape remains 12 metrics;
- current Bonferroni decisions remain a 12-test legacy path;
- the four new metrics can be computed and unit-tested through `MetricRegistry`;
- later milestones will explicitly activate families and replace the flat multiplicity layer.

This boundary is intentional so that a benchmark change can be attributed to a specific method change rather than to several changes landing at once.


The next calibration checkpoint uses these family labels to build uncertainty-aware recommendations among the active legacy metrics. See [Calibration recommendations](CALIBRATION_RECOMMENDATIONS.md). The four new metrics remain staged until the multiplicity layer is replaced.
