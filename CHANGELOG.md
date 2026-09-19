# Changelog

## 1.5.0 development - calibration recommendation checkpoint

- Added family-aware calibration recommendations for location, variability and entity-centre heterogeneity tracks without changing the current 12-metric Bonferroni inference.
- Replaced forced top-1 recommendation logic in the new diagnostic layer with a candidate set based on overlap with the best metric's Wilson power interval.
- Recast the old 0.70 lower-power gate as a recommendation-quality label in the new layer; weak calibration is reported as uncertain rather than silently deleting every candidate.
- Added `calibration_recommendations.csv` and manifest-level `developmentRecommendations`. Legacy `candidate` result fields remain unchanged until the later multiplicity/automatic-inference switch.

## Unreleased - 1.5.0 development line

- Added the structured 1.5 metric registry with family, applicability, interpretation, and legacy-inference metadata.
- Implemented four staged metrics: Huber M location, Hodges-Lehmann location, Qn robust scale, and log-scale SD.
- Kept the active 1.4 12-metric inference family unchanged during milestone 1.5-A so adjusted p-values and saved calibration shape do not change yet.
- Added Core regression checks for registry stability, robust-metric identities, scale/translation behavior, and applicability limits.
- Retired the Windows desktop from active development, CI and release packaging. Version 1.4.0 remains the archived desktop release.
- Made the headless CLI and Python API the maintained interface stack. The .NET Core engine remains the single statistical implementation.
- Added an immutable benchmark archive and cross-version benchmark history, seeded with the full 1.4.0 / engine 1.6.0 / `MVS-BENCH-1.2.0` run.
- Added the 1.5.0 redesign plan, including metric families, candidate sets, new robust metrics, and a new multiplicity layer.

## Interface-layer implementation — application version remains 1.4.0

- Added a compiled `MvsAnalyzer.Core` project referenced by both desktop and CLI without changing statistical method sources or method hashes.
- Added versioned CLI machine responses (`mvs-cli-result/v1`) with structured status, artifacts, diagnostics, environment identity and stable stdout/stderr behavior.
- Added a path-based Python package with typed results for calibration, analysis, variance, estimation, MELSM and benchmark workflows; statistics remain delegated to the .NET engine.
- Added a local Python/Jupyter quick start, compatibility documentation, wrapper tests and a Linux CI parity smoke against the built CLI.
- Moved benchmark figure rendering outside the platform-neutral Core boundary while preserving Windows rendering through the desktop renderer.
- Updated the embedded Colab source payload so the new Core project is carried with the CLI source.


## Connection maintenance — application version remains 1.4.0

- Decoupled UI labels from CLI identity; added structured CLI/scientific checks and a known legacy 1.4.0 adapter.
- Added independent transport negotiation, bounded recovery, structured errors and exact idempotent status delivery without lease/command resurrection.
- Approved desktop jobs now carry the matching controller and integrity manifest; updated notebooks keep an embedded old-desktop fallback.
- Cached CLI source/builds are verified and rebuilt in staging, without deleting calibration/results.
- Added 47 offline regressions (including simulated additive updates), six native contract checks and four native socket checks. Native tests are added to CI, not claimed executed in the patch environment.
- Kept app 1.4.0, engine 1.6.0, numerical methods and the separate Colab window/theme fixes.


## Исправления UI/Colab в пакете 1.4.0 (без смены версии)

- Отдельное окно Colab вместо страницы в боковом меню; единый экземпляр, сохранение при навигации, измеряемые строки кнопок.
- Исправлены команды запуска дополнительных методов и возможность остановки старого задания после смены локальных данных.
- Модальное окно прогресса не меняет managed Enabled всей формы; прогресс, неактивные кнопки и меню используют текущую тему.
- Наблюдаемое оборудование Colab и отмена при подготовке контроллера; выбор ускорителя остаётся подтверждением в интерфейсе Google.
- Добавлены офлайн-регрессии и расширен Windows UI harness. Расчётные исходники и версии неизменны.


## 1.4.0

### Added

- Separate within-entity variability and between-entity heterogeneity scenarios and power estimates.
- Gaussian variance-component analysis, known-truth estimation studies and experimental MELSM.
- Optional Colab computation with saved-calibration reuse and result import.
- A themed Colab control panel with calibration, analysis, cancellation, downloads and live CLI progress.
- Recoverable connection codes, explicit reconnect/disconnect controls and export of the current notebook.
- Single-flight commands, runtime ownership, ordered status packets and command receipts.
- Controller regressions and portable session-lifecycle tests in CI.

### Improved

- Twelve summary metrics, uncertainty-aware calibration gates and multiplicity-adjusted results.
- Readable result tabs, resizing and optional-method navigation.
- User-facing documentation and clearer result interpretation.
- Notebook addresses are retained independently of connection leases, allowing reuse without forced copies.
- Verified calibration and received results survive reconnection; temporary result-delivery failures can be retried.
- Manual job upload and result import remain available when browser local access is blocked.

### Fixed

- Stale busy/opening states expire instead of permanently blocking Colab recovery.
- Repeated commands and stale runtime messages cannot silently start duplicate work or restore obsolete state.
- Partial outputs are not packaged as completed results.
- Nonfinite values are exported as JSON null rather than invalid numeric literals.
- Private .NET installations are used explicitly in Colab.
- Calibration, settings and import-profile checksums no longer depend on Windows/Linux JSON line endings.
- Compatible legacy fingerprints are verified and normalized; corrupted states still fail validation.
- Editing README badges or HTML formatting no longer fails source checks.
- Damaged Russian interface strings have been corrected.

Application 1.4.0; numerical engine 1.6.0; frozen formula MVS-1.4.0. Update the desktop and notebook together. See [Methods](docs/METHODS.md), [Colab](docs/REMOTE.md) and [Validation](docs/VALIDATION.md) for usage and limitations.
