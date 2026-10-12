# Diagnostic benchmark

Protocol `MVS-BENCH-1.2.0` is declared in `BenchmarkProtocol.cs`; its exact UTF-8 specification checksum is pinned in source and `validation/method-hashes.json`. It is a declared source protocol, not evidence of external preregistration. No results for engine 1.6.0 are claimed in this package.

The shipped inference comparator now mirrors `AnalysisEngine.Results`: all applicable metric tests use Bonferroni over the complete twelve-metric registry. Candidate labels prioritize summaries but do not gate away the other displayed tests. Consequently this corrected family is closely related to the ordinary Bonferroni comparator; calibration must not be credited with extra inferential power by hiding tests.

Historical strict/lenient single-metric selectors remain **uncorrected diagnostic comparators**, not the shipped default. The pilot-fixed and genuinely pre-fixed metric comparisons answer different questions. The held-out oracle selects on one replication half and scores on the other; it does not get to exploit the test replication's noise.

Synthetic location changes are additive constant shifts **after** baseline flooring, preserving within/between spread under shared random draws. Synthetic dispersion scales residual SD; positivity flooring can affect its exact realized components. Real-data plasmodes use random group assignment and additive shifts, not multiplication of every raw value for a location effect. A randomization null does not mean identical realized sample distributions.

Profiles change simulation budgets only. “Standard” is not automatically publishable, and runtime is hardware-dependent. Rates in the legacy benchmark report are conditional on completed benchmark replications; failure counts and first errors must be reviewed. The new scientific modules separately report requested/failed denominators. Reproducibility is scoped to a recorded arithmetic environment, not guaranteed across every OS/runtime.

Run manually after CI, retain failure outputs, and review the assumptions in METHODS/VALIDATION before interpreting pass/fail thresholds. A threshold is a declared operational criterion, not a universal scientific law.

## Cross-version record

Frozen benchmark outputs that are used to guide or validate released scientific engines are archived under `benchmark_history/` and summarized in [BENCHMARK_HISTORY.md](BENCHMARK_HISTORY.md). The history document distinguishes development runs from independent validation and does not treat runs under different protocol hashes as directly comparable.

## Per-replication diagnostics (round 4)

New runs retain each requested condition replication, including failures and both
independent determinism passes, in four additive tables:

- `benchmark_replications.csv`: condition/pass/index identity, status, errors,
  oracle half and the existing seed coordinates/draw.
- `benchmark_replication_procedures.csv`: selected metric and legacy
  claimed/rejected decisions for all eight procedures.
- `benchmark_replication_metrics.csv`: raw p-value, observed availability,
  uncorrected rejection and calibration eligibility/score/track gates for all
  twelve metrics.
- `benchmark_stability_replications.csv`: every requested stability split, its
  original index, status, tau and both selected metrics.

Indices are zero-based. Use condition + phase + index as identity; seed values
are intentionally shared across some conditions and are not unique keys.
`main`, `replay-first` and `replay-second` are separate phases. Do not pool replay
rows with experimental conditions or count the second pass in legacy summaries.
Failed replications retain a status/error and blank final decisions. Partial raw
diagnostics may be present if that stage was reached before failure.

Historical checkpoints may lack the new information. They are explicitly labelled
`legacy_missing`; a result with no retained outcomes has `unknown_legacy` status.
Blank values must not be converted into a zero p-value, a successful test, or a
fabricated rejection rate. Legacy `claimed` means the historical procedure offered
a claim, which is not always equivalent to an available observed test.

The existing summary rates/digests/verdicts remain unchanged for comparability.
Use the independent checker to reconcile complete diagnostics with those summaries
and compute rejection rates over all requested replications, counting failures as
non-rejections:

```bash
python validation/check_benchmark_diagnostics.py path/to/MVS_Benchmark_run
```

Exit 0 means internally consistent complete diagnostics; exit 1 means an error;
exit 2 means legacy diagnostics are incomplete. This is bookkeeping validation,
not independent certification of the native p-values or population error control.
A low rejection rate with frequent failures is not evidence of valid inference.
The legacy determinism verdict can pass when both runs fail; inspect the explicit
per-replication statuses before interpreting it. See the
[round 4 checkpoint](ROUND4_BENCHMARK_DIAGNOSTICS.md) for checks and open bugs.
