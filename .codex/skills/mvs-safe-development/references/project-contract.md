# MVS project contract

Treat this file as a map of risks, not a frozen release status. Read the live
source and owning documents. Do not copy a current version or method hash into
this skill as permanent truth.

## Ownership map

| Area | Owning source and documents | Preserve unless the task changes it |
|---|---|---|
| Statistical execution | Core/, MvsAnalyzer.Core/, docs/METHODS.md | Single .NET production engine; declared test settings and units |
| Metrics and calibration | Core/MetricRegistry.cs, Core/AnalysisEngine.cs, Core/CalibrationRecommendations.cs, docs/METRIC_REGISTRY.md | Active versus staged registry, order, availability, calibration meaning |
| CLI and Python | MvsAnalyzer.Cli/, python/src/, docs/CLI_CONTRACT.md, docs/CLI_MACHINE_PROTOCOL.md, validation/cli-contract-v1.json | Schema, arguments, streams, exit codes and compatible backend identity |
| Saved state and export | Core/ScientificInfrastructure.cs, Infrastructure/OutputExporter.cs | Hashes, compatibility checks, null/unavailable semantics and artifact fields |
| Benchmark | Benchmark/, docs/BENCHMARK_HISTORY.md, benchmark_history/ | Protocol, procedures, raw archived evidence and run provenance |
| Independent diagnostics | validation/, docs/VALIDATION.md | Independence from the production engine; explicit version and assumptions |
| Build and packaging | project files, .github/workflows/, tools/build_*, notebooks/, Assets/ | Real build boundaries; source-controlled payloads/assets |
| Historical desktop | Desktop/, MvsAnalyzer.Ui.Tests/, live roadmap | Archived status and reproducibility until explicitly changed |

Locate the active task in repository documents, including docs/V1_5_PLAN.md and
any newer checkpoint. A newer plan supersedes old status statements only within
the scope expressly adopted by the owner.

## Scientific invariants

- Preserve participants/entities as the independent unit when the method requires
  it. Repeated measurements are not independent participants.
- Preserve the distinction between location, within-entity variability and
  between-entity heterogeneity. Do not claim that a rank test isolates all three.
- Determine the active inferential registry from source. Staged metrics do not
  join the family merely because their implementations exist.
- Preserve the declared correction family and unavailable-case policy. Do not
  quietly change the correction multiplier to the number of successful tests.
- Distinguish observed-data testability, calibration availability, recommendation
  heuristics and confirmatory rejection. Do not hide one behind another without
  an explicitly documented method change.
- Report failed/unavailable replications and actual denominators. Do not obtain
  better power/FPR by silently removing failures from the calculation.
- Do not describe overlapping marginal intervals as proof of equal power;
  calibration tolerances as guaranteed error control; or a small Cliff's delta
  as equality of distributions, variances or all effects.
- Keep exploratory tuning distinct from evaluation on a protocol frozen before
  results were inspected. Reused development scenarios are not unseen validation.
- Keep benchmark comparators identified by the actual procedure they execute.
  Reusing the engine's p-value function is not independent numerical validation.
- Require explicit tie, continuity, sidedness, asymptotic/exact and small-sample
  settings for external numerical comparisons.

For a requested method change, write the intended before/after definition first.
Assess formulas, registry count/order, versions, hashes, serialization and saved
calibrations together. Never bypass a mismatched fingerprint. If identity must
change, update its owning specification and necessary tests together; do not bump
unrelated application/UI versions to make metadata look current.

## Evidence, data and compatibility

Keep original input bytes, seeds, configurations, raw results and archived
manifests. Do not overwrite an old run with results from new software. Regenerate
an embedded source payload only through its live builder when the requested
change requires it, then verify notebook/payload consistency.

Preserve API/machine contracts even when human prose changes. Parse structured
CLI output rather than scraping progress text. Compare scientific floating-point
fields with declared tolerances and operational fields according to their own
rules; do not enforce byte-for-byte equality of timestamps and output paths.

Do not add telemetry, external uploads, network calls or execute a user's raw
dataset against a new service as incidental debugging. Use small synthetic
fixtures where possible. Keep local source ZIP delivery separate from publication.
