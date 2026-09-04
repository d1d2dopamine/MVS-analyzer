# Example datasets

- `demo_three_groups.csv`: original bundled 90-entity/4,500-row demo, unchanged; use it for the Linux 150-replication save/reload smoke check.
- `MVS_stress_test.csv`: original exploratory stress illustration, not an external validation study.
- `variance_demo.csv`: new synthetic independent-group random-intercept example. Use `mvs variance`.
- `repeated_conditions.csv`: new synthetic repeated-condition example with the same global entity IDs in A and B. Use `mvs melsm`, not the independent-group override.
- `scientific_examples.json`: generation seeds/parameters and purpose of the new examples.

Known generating parameters do not mean every finite sample equals its population truth. Example files demonstrate input semantics; they do not establish estimator calibration or clinical/scientific validity.
