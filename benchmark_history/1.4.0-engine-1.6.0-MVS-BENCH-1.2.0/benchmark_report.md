# MVS benchmark report

Run 2026-09-18_215035, profile Full — largest included budget, seed 20260904, duration 117 min.

| Item | Value |
|---|---|
| Protocol | MVS-BENCH-1.2.0 |
| Protocol hash | `b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268` |
| Protocol unchanged | yes |
| Engine | 1.6.0 |
| Formula | MVS-1.4.0 (`10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c`) |
| Application | 1.4.0 |
| Environment | 340965b398b70264 |
| Threads | 4 |

## Verdict

**AT LEAST ONE THRESHOLD WAS MISSED.**

| Hypothesis | Question | Threshold | Observed | Result |
|---|---|---|---|---|
| A | Metric shopping inflates the false-positive rate and the MVS gate holds it at the nominal level | cherry-pick >= 0.15 and the shipped MVS default <= 0.075; fail above 0.10 | cherry-pick 17.8%, MVS two-track 1.8%, single-track 4.6% | pass |
| B | Controlling the error rate costs little power against a metric chosen with knowledge of the truth | loss <= 7 points; fail above 15 points | worst loss 30.8 pts  ·  location two-track 14.0%, single-track 44.0% vs held-out oracle median 44.8% (same-data oracle 46.0%); dispersion two-track 28.8%, single-track 5.6% vs held-out oracle coefficient_of_variation 53.6% (same-data oracle 54.8%) | **fail** |
| C | The ranking of metrics is stable across independent halves of the same study | median Kendall tau >= 0.70 and top-1 agreement >= 0.60; fail if tau < 0.40 | tau 0.714, top-1 agreement 22.5% over 120 splits | inconclusive |
| D | The error rate stays controlled when up to a tenth of the measurements are corrupted | MVS <= 0.075 at 10% contamination; fail if it already exceeds 0.10 at 2% | 2% 4.4%, 10% 4.8% | pass |
| E | The same seed reproduces the same result exactly | identical SHA-256 of the decision matrix | d246c87bcf9d644a vs d246c87bcf9d644a | pass |

## Headline: data with no effect in it

Two groups drawn from one population, 1000 repetitions. Every discovery here is a false one.

| Rule for choosing a metric | False discoveries | 95% interval |
|---|---|---|
| Try all twelve, report the best | 17.8% | 15.6% – 20.3% |
| Try all twelve, Bonferroni | 1.8% | 1.1% – 2.8% |
| Median, fixed in advance | 4.8% | 3.6% – 6.3% |
| Coefficient of variation, fixed in advance | 5.8% | 4.5% – 7.4% |
| MVS, metric locked on a pilot | 4.6% | 3.5% – 6.1% |
| MVS, gate respected | 4.6% | 3.5% – 6.1% |
| MVS, gate ignored | 4.6% | 3.5% – 6.1% |
| MVS, all applicable metrics with registry correction | 1.8% | 1.1% – 2.8% |

## Power

| Condition | Cherry-pick | Bonferroni | Fixed median | MVS gated | Oracle |
|---|---|---|---|---|---|
| location ×1.00 | 19.2% | 2.4% | 5.2% | 5.2% | 7.2% (iqr) |
| location ×1.02 | 24.8% | 4.8% | 12.4% | 12.4% | 12.8% (trimmed_mean_20) |
| location ×1.05 | 56.4% | 14.0% | 46.0% | 44.0% | 46.0% (median) |
| location ×1.10 | 98.8% | 76.0% | 96.4% | 94.8% | 96.8% (mean) |
| location ×1.20 | 100.0% | 100.0% | 100.0% | 21.6% | 100.0% (median) |
| dispersion ×1.02 | 15.2% | 2.4% | 5.2% | 5.2% | 5.6% (mad) |
| dispersion ×1.05 | 18.0% | 2.8% | 5.2% | 5.2% | 6.8% (standard_deviation) |
| dispersion ×1.10 | 24.4% | 4.4% | 5.2% | 5.2% | 12.0% (coefficient_of_variation) |
| dispersion ×1.20 | 48.4% | 12.8% | 5.2% | 5.2% | 30.8% (coefficient_of_variation) |
| dispersion ×1.30 | 72.8% | 28.8% | 5.6% | 5.6% | 54.8% (coefficient_of_variation) |

## Dirty data, other shapes, real recordings

| Condition | Cherry-pick | MVS gated | Repetitions |
|---|---|---|---|
| robust_null_2 | 20.8% | 4.4% | 250 |
| robust_null_5 | 21.2% | 4.8% | 250 |
| robust_null_10 | 20.0% | 4.8% | 250 |
| shape_normal_null | 19.2% | 4.0% | 250 |
| shape_lognormal_null | 13.6% | 2.0% | 250 |
| design_voice_null | 18.0% | 0.0% | 250 |
| design_voice_location_105 | 23.6% | 0.0% | 250 |

## Stability of the choice

Median Kendall tau 0.714, lower quartile 0.646, the same metric came first in 22.5% of 120 splits.

## Reproducibility

First pass: `d246c87bcf9d644a603b862c460205a0ef4954b02db9ba19a9d468d08805e97e`

Replay: `d246c87bcf9d644a603b862c460205a0ef4954b02db9ba19a9d468d08805e97e`

To repeat this entire run:

```
MVS_Analyzer.exe --benchmark --profile full --seed 20260904 --out <folder>
```

## What this benchmark does not prove

- The synthetic conditions are built from the same family of shapes the engine expects. That is a home advantage, and it is stated here on purpose.
- Two groups, one variable, independent entities. Paired designs, covariates and time series are outside this protocol.
- The plasmode stage reuses real recordings only if a folder of them was supplied. Without it, nothing here has touched measured data.
- Error control is a property of the procedure, not a promise about any single study.

