# MVS 1.5.0 development plan

MVS 1.5.0 is the first CLI/Python-first development line. The Windows desktop application is frozen at 1.4.0 and is no longer part of CI, release builds, or active feature work. Its source remains in the repository for historical reproducibility.

The statistical goal for 1.5.0 is narrower than a general rewrite: preserve the error-control strengths of 1.4.0 while recovering power and making the automatic result describe the kind of change in repeated measurements rather than forcing all summary metrics into one ranking.

## Supported interface direction

The maintained stack is:

```text
Python API / notebooks
        |
headless MVS CLI
        |
MvsAnalyzer.Core
```

The .NET CLI remains the single executable statistical backend for now. Python controls that engine through the versioned machine protocol instead of reimplementing the statistics. Packaging can later bundle the compatible engine with Python if that improves installation without creating two scientific implementations.

## Scientific changes planned for 1.5.0

1. Replace the flat metric registry with structured metric metadata: family, applicability rules, requirements, interpretation, and implementation identity.
2. Separate location and variability summaries internally while keeping Automatic mode as the default user experience.
3. Add a small first wave of metrics aimed at known gaps: Huber location, Hodges-Lehmann location, Qn scale, and log-SD for positive multiplicative data.
4. Replace the mandatory top-1 winner with an uncertainty-aware candidate set.
5. Separate calibration from confirmatory inference. Calibration describes sensitivity and stability; it no longer decides whether a valid inferential procedure is allowed to run.
6. Keep Bonferroni as a legacy comparator, add Holm as a safe fallback, and develop a resampling maxT / step-down maxT procedure that can use dependence among correlated metrics.
7. Make the primary automatic result family-level: location, within-entity variability, and other supported families. Metric-level results explain the family signal rather than defining the entire scientific claim.

## Development sequence

### 1.5-A: registry and metrics - implemented

The structured registry and the four staged metrics are implemented and compile in CI. The active inferential registry remains the frozen 12-metric MVS 1.4 set, so this checkpoint does not change Bonferroni family size, saved calibration shape, or benchmark decisions. See `METRIC_REGISTRY.md`.

### 1.5-B: calibration redesign - implemented, awaiting CI

Family-aware recommendation diagnostics are now implemented for the active legacy metrics. Candidate membership uses overlap with the best metric's Wilson power interval, the 0.70 lower-power threshold is a quality label rather than a hard deletion rule, and RMS is excluded from pure location/variability competition. The new `calibration_recommendations.csv` artifact keeps this layer separate from the still-unchanged 12-metric Bonferroni inference. See `CALIBRATION_RECOMMENDATIONS.md`.

### 1.5-C: multiplicity engine

Implement Holm first, then maxT, then step-down maxT if the resampling assumptions and tests support it. Keep all methods selectable internally so benchmark comparisons remain possible.

### 1.5-D: automatic inference and Python/CLI surface

Expose family-level automatic results through the machine protocol and Python result objects. Add a focused mode for hypotheses fixed before analysis.

### 1.5-RC: validation

Use `MVS-BENCH-1.2.0` only as a development diagnostic because its results have already informed the redesign. Once 1.5.0 behavior is frozen, define a separate `MVS-BENCH-2.0` protocol with unseen seeds and broader data-generating conditions. Record every run in `docs/BENCHMARK_HISTORY.md` and archive its raw files under `benchmark_history/`.

## Release criteria

A 1.5.0 release candidate should not be judged by whether every benchmark verdict is green. It should show, under a frozen protocol, that Automatic mode controls family-wise false positives, has materially better power than the 1.4.0 registry-wide correction in the target scenarios, identifies the correct change family with useful stability, reports uncertainty honestly, and remains deterministic within the declared arithmetic environment.
