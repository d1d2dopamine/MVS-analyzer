# Reference truth table (primary grid)

Grid: **primary**. Replications: 2000 per mechanism (4000 for the null). alpha = 0.05. Two-sided Mann-Whitney U on entity-level values. Rows marked * are not implemented in the engine and are shown for comparison only.

| metric | A_normal_additive | B_lognormal_multiplicative | C_heavy_tails | D_scale_only | E_null |
|---|---|---|---|---|---|
| median | 0.981 | 0.927 | 0.926 | 0.048 | 0.051 |
| mean | 0.988 | 0.959 | 0.578 | 0.051 | 0.054 |
| rms | 0.988 | 0.936 | 0.564 | 0.071 | 0.054 |
| standard_deviation | 0.049 | 0.536 | 0.058 | 1.000 | 0.047 |
| coefficient_of_variation | 0.140 | 0.049 | 0.065 | 1.000 | 0.046 |
| mad | 0.059 | 0.396 | 0.053 | 1.000 | 0.052 |
| iqr | 0.053 | 0.411 | 0.052 | 1.000 | 0.052 |
| normalized_mad | 0.082 | 0.046 | 0.073 | 1.000 | 0.050 |
| normalized_iqr | 0.073 | 0.051 | 0.062 | 1.000 | 0.051 |
| range | 0.051 | 0.430 | 0.058 | 1.000 | 0.043 |
| geometric_mean* | 0.990 | 0.962 | n/a | 0.070 | 0.054 |
| trimmed_mean_20* | 0.986 | 0.950 | 0.934 | 0.050 | 0.051 |
| **any of the ten (selection)** | 0.994 | 0.976 | 0.946 | 1.000 | 0.205 |
