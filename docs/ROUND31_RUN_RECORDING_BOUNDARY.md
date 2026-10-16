# Round31: per-invocation run recording

## Purpose and scope

Computation previously acquired `BackupSession` directly in calibration, summary results, variance, estimation and MELSM. That coupling made it difficult to test storage failures, session ownership and cache behavior independently of real disk storage. This change adds an internal per-invocation factory/session boundary. It is structural testability work; it does not improve statistical power or change the scientific readiness decision.

`Core/RunRecording.cs` defines `IRunRecordingFactory` and `IRunRecording`. Each of the five explicit internal `*WithRecording` methods receives its factory as its first argument and owns the acquired session through the existing `using` scope. Legacy entrypoints preserve signatures/defaults and delegate to a stateless singleton `PortableRunRecordingFactory`, which calls the original `BackupSession.Begin`. The session explicitly forwards `Try`, `Cached`, `Put`, `Finish` and `EnvironmentChanged` to the original implementation. There is no mutable global factory or new ambient service locator.

The optimizer has a separate internal `MinimizeWithRecording` entrypoint. It borrows a session and never disposes it. The legacy optimizer signature, including optional/named `BackupSession` argument, remains available. MELSM passes its owned session to the borrowed optimizer path.

## Preserved contracts and boundaries

- Request construction, validation and acquisition positions, progress/cancellation calls, cache keys, numerical bodies and random draws remain in their original order.
- The default adapter retains existing ambient nesting, disabled-backup and restore behavior. Round29 retry and Round30 conservative simplex-cache provenance rules remain in the production adapter.
- Dispose and failure propagation retain C# `using` semantics, including a disposal exception replacing an earlier exception. No retry or failure suppression is introduced.
- `BackupRequest` remains the existing compatibility descriptor. The assembly/source layout is not completely decoupled from portable storage; this is a narrow invocation boundary.
- Fake recordings serialize/deep-copy cached values so mutable arrays cannot masquerade as persisted snapshots. Target-only ordered interface traces are not presented as baseline instrumentation that did not exist.
- Existing completed-result shortcuts, archived desktop/import residuals, Windows runtime acceptance and scientific NO-GO remain separate limitations.

## Verification and rollback

The prespecified comparison is in `validation/round31-recording-plan.json`; complete comparator protocol and raw evidence accompany the results. Round30 is the immutable comparator. Six workloads cover calibration, results, variance, estimation, MELSM and the optimizer; scientific outputs, progress and decoded checkpoints are compared. Only explicitly enumerated top-level volatile checkpoint fields are omitted. Timing is descriptive and separately coordinated to avoid overlapping test work.

Final executed counts and artifact hashes are recorded in `validation/round31-results.json` and the Russian report. New regression fixtures are engineering checks, not additional scientific pilot samples. Revert the Round31 file set or restore the saved Round30 source tree to roll back; do not mix old and rebuilt assemblies. Public CLI/Python/MCP protocols are not changed by this internal boundary.

For the separate build-versus-buy assessment, see `NUMERICAL_LIBRARY_REUSE_ASSESSMENT_RU.md`. No numerical library is added in this stage.

## Companion evidence

Full raw comparison material is delivered separately as `MVS-analyzer-round31-comparison-evidence.zip` (7,130,592 bytes; SHA256 `4cc2a82be8a6f5e7469eda15585828366e85dfb4c6b5a83ae62521258551e3ec`). Keep/extract it outside the source tree; no build, CI or test requires this archive. The source patch contains the concise results and native regression tests. All 72 observations are retained, including the disabled-estimation median increase of about 19.7%. There was no predefined numeric performance gate; three pairs support descriptive comparison only, not a no-regression assertion.
