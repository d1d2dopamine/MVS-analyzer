# Output contracts — schema 2

All newly written scientific JSON uses finite numbers or `null`. No bare NaN/Infinity, and no replacement by zero. Legacy named strings can be decoded by the numeric converter, but incompatible historical calibration schemas are deliberately rejected. CSV uses an empty numeric field for unavailable values; read the status columns.

## Summary workflow

`calibration_state.json` freezes input hash, method versions/hashes, ordered metric registry, actual tracks, seed, effect/scenario, alpha, equivalence margin, split policy, import-profile fingerprint and filtering limits. `SettingsHash` identifies this configuration. `PayloadHash` checks the serialized parsed payload with its own hash field empty; it is not an authentication signature. Unknown extra file bytes are not a substitute for artifact SHA-256 verification.

`calibration.csv` preserves leading legacy columns and appends counts/bounds/statuses. `calibration_tracks.csv` is long format: one metric/track row, power, Wilson bounds, MCSE, score, MDE, MDE status and failures. A small-budget blank MDE does **not** mean “effects above 20% are invisible”.

`results.csv` preserves raw `global_p`, then explicitly adds `adjusted_p`, selected pair, interval status and approximate equivalence bounds. Difference decisions use adjusted p, not raw p. `equivalence_p` is intentionally empty. `results.json` retains per-track arrays and all statuses. `data_quality.csv` has one row per retained entity and all twelve metric columns; it is not an import-exclusion log.

`run_manifest.json` records processing, actual calibration tracks, decision family, candidate sets per track, method specification/hash, plugin metadata, warnings and output checksums. Calibration state is written/copied **before** the manifest and included in its checksums. `--force` records both current and calibration input hashes. Input bytes are not embedded in the manifest. The execution-environment fingerprint is recorded alongside the original calibration environment stored in the state; different arithmetic environments do not promise bitwise replay.

Pseudonyms are deterministic truncated hashes and **not strong anonymization**. Dataset names may remain inside a calibration state for operational replay; inspect state files before external sharing. Paths, group names and project descriptions can also disclose information. CandidateSet is the union of selected tracks; candidateSetsByTrack is authoritative for the specific questions. Imported/exported text beginning with a spreadsheet formula character is escaped in new core CSV exports. Review third-party report templates separately.

## Model workflows

- `variance_report.json`, `variance_components.csv`, `variance_tests.csv`: REML estimates and pointwise component intervals; separate within/between tests, power/FPR curves, failure counts and boundary/MDE statuses. Model CSVs use record property names.
- `estimation_report.json`, `estimation_performance.csv`, `estimation_draws.csv`: known truth, DGP parameters, per-method bias/MSE/MCSE/efficiency/coverage and individual outer-replication estimates. This is a synthetic study, not CSV-truth recovery.
- `melsm_report.json`, `melsm_parameters.csv`, `melsm_random_effects.csv`: convergence, quadrature disagreement, parameter/interval status and conditional random-effect predictions. CLI pseudonymizes IDs unless `--include-entity-ids` is supplied.

Every scientific CLI/model UI run writes a model-specific manifest. These models **do not use the summary detection score**. Diagnostic exit code 2 still leaves a report to inspect; do not discard it as if it were a successful inferential fit.

## File safety

Writes are atomic per file, not per directory. Prefer a new output directory; `--overwrite` acknowledges replacing outputs in an existing one. Ordinary `analyze` creates a uniquely named child folder. Cancellation/failure can leave incomplete artifacts; a log message or directory alone is not proof of a completed analysis. Hashes do not establish scientific correctness.
