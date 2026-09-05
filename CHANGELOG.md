# Changelog

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
