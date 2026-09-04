# Diagnostic benchmark

Protocol `MVS-BENCH-1.2.0` is declared in `BenchmarkProtocol.cs`; its exact UTF-8 specification checksum is pinned in source and `validation/method-hashes.json`. It is a declared source protocol, not evidence of external preregistration. No results for engine 1.6.0 are claimed in this package.

The shipped inference comparator now mirrors `AnalysisEngine.Results`: all applicable metric tests use Bonferroni over the complete twelve-metric registry. Candidate labels prioritize summaries but do not gate away the other displayed tests. Consequently this corrected family is closely related to the ordinary Bonferroni comparator; calibration must not be credited with extra inferential power by hiding tests.

Historical strict/lenient single-metric selectors remain **uncorrected diagnostic comparators**, not the shipped default. The pilot-fixed and genuinely pre-fixed metric comparisons answer different questions. The held-out oracle selects on one replication half and scores on the other; it does not get to exploit the test replication's noise.

Synthetic location changes are additive constant shifts **after** baseline flooring, preserving within/between spread under shared random draws. Synthetic dispersion scales residual SD; positivity flooring can affect its exact realized components. Real-data plasmodes use random group assignment and additive shifts, not multiplication of every raw value for a location effect. A randomization null does not mean identical realized sample distributions.

Profiles change simulation budgets only. “Standard” is not automatically publishable, and runtime is hardware-dependent. Rates in the legacy benchmark report are conditional on completed benchmark replications; failure counts and first errors must be reviewed. The new scientific modules separately report requested/failed denominators. Reproducibility is scoped to a recorded arithmetic environment, not guaranteed across every OS/runtime.

Run manually after CI, retain failure outputs, and review the assumptions in METHODS/VALIDATION before interpreting pass/fail thresholds. A threshold is a declared operational criterion, not a universal scientific law.
