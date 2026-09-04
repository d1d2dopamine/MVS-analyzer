# Validation status

## What this source delivery establishes

The source was reviewed and amended; static package checks and independent standard-library Python mathematical checks are recorded in `validation/PACKAGE_QA.md`. **No .NET compilation, C# test execution, application run or Windows visual render was performed during preparation**, at the author's request. No benchmark results for this engine are asserted here.

Included acceptance gates:

1. Portable regressions: JSON null/legacy handling, strict arguments, metric-sign/multiplicity/transform identities, quadrature moments, known quadratic optimization, balanced REML identities and scale invariance, estimation accounting, state replay, analytic random-intercept MELSM special case and input semantics.
2. Existing desktop-linked harness, updated for the new method specification.
3. Linux CLI regression reproducing the reported 150-replication calibration save, then loading it and checking all manifest-listed hashes with strict JSON parsing.
4. Opt-in extended model workflow; a diagnostic report or convergence does not constitute scientific validation.
5. Windows manual layout/DPI/theme checklist.

## What is not established

- Nominal finite-sample type-I error or equivalence error rates of the approximate rank/bootstrap procedures across realistic mechanisms.
- Correct coverage of variance-component percentile intervals at zero boundaries or small cluster counts.
- Independent agreement of the native MELSM implementation with a trusted external package, global-optimum guarantees, or robust model adequacy.
- Stable candidate ordering across sampling variation, or universal superiority over a fixed estimand chosen in advance.
- Joint multiplicity control across workflows, exploratory model choices, repeated reruns or all parameter intervals.
- Cross-runtime bitwise numerical identity, code signing or an externally immutable audit trail.

## Before scientific release

Use an independently specified simulation matrix with balanced/unbalanced repeats, ties, skew, outliers, missingness, near-zero between variance, large/small scales and correlated within-entity errors. Predeclare estimands, parameter values, failures/denominators and acceptance thresholds. Report Monte Carlo uncertainty. Compare variance/MELSM estimates and likelihoods with a trusted independent implementation; validate interval coverage and identifiability. Record raw outputs, code revision and environment. Publish failures as well as successes.

The existing `validation/reference_*` files are **historical artifacts from the supplied development snapshot**. They are preserved for traceability, not treated as validation of engine 1.6.0. Re-run an appropriately revised independent study before quoting numerical performance. The benchmark is a declared, source-checksummed diagnostic protocol, not proof that an external preregistration occurred.
