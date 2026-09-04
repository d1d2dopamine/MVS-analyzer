> HISTORICAL SNAPSHOT REPORT: retained for traceability, not validation of engine 1.6.0. See ../docs/VALIDATION.md.

# Reference truth table (discriminating grid)

Grid: **discriminating**. Replications: 2000 per mechanism (4000 for the null). alpha = 0.05. Two-sided Mann-Whitney U on entity-level values. Rows marked * are not implemented in the engine and are shown for comparison only.

| metric | A_normal_additive | B_lognormal_multiplicative | C_heavy_tails | D_scale_only | E_null |
|---|---|---|---|---|---|
| median | 0.375 | 0.215 | 0.241 | 0.055 | 0.050 |
| mean | 0.406 | 0.247 | 0.114 | 0.048 | 0.048 |
| rms | 0.406 | 0.222 | 0.113 | 0.050 | 0.049 |
| standard_deviation | 0.048 | 0.103 | 0.052 | 0.917 | 0.051 |
| coefficient_of_variation | 0.070 | 0.041 | 0.051 | 0.910 | 0.048 |
| mad | 0.041 | 0.099 | 0.057 | 0.536 | 0.046 |
| iqr | 0.047 | 0.099 | 0.056 | 0.559 | 0.044 |
| normalized_mad | 0.052 | 0.051 | 0.060 | 0.530 | 0.048 |
| normalized_iqr | 0.055 | 0.054 | 0.063 | 0.547 | 0.049 |
| range | 0.049 | 0.091 | 0.048 | 0.800 | 0.052 |
| geometric_mean* | 0.406 | 0.256 | n/a | 0.047 | 0.048 |
| trimmed_mean_20* | 0.399 | 0.242 | 0.240 | 0.052 | 0.049 |
| **any of the ten (selection)** | 0.541 | 0.443 | 0.397 | 0.954 | 0.202 |
