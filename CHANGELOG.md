# Changelog

## 1.4.0

### Added

- Separate within-entity variability and between-entity heterogeneity scenarios and power estimates.
- Gaussian variance-component analysis, known-truth estimation studies and experimental MELSM.
- Optional Colab computation with saved-calibration reuse and result import.

### Improved

- Twelve summary metrics, uncertainty-aware calibration gates and multiplicity-adjusted results.
- Readable result tabs, resizing and optional-method navigation.
- User-facing documentation and clearer result interpretation.

### Fixed

- Nonfinite values are exported as JSON null rather than invalid numeric literals.
- Private .NET installations are used explicitly in Colab.
- Calibration, settings and import-profile checksums no longer depend on Windows/Linux JSON line endings.
- Compatible legacy fingerprints are verified and normalized; corrupted states still fail validation.
- Editing README badges or HTML formatting no longer fails source checks.

Application 1.4.0; numerical engine 1.6.0. See [Methods](docs/METHODS.md) for statistical definitions and [Validation](docs/VALIDATION.md) for limitations.
