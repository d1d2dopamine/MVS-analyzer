# Changelog

## 1.4.0 — consolidated scientific update (source prepared 2026-09-05)

Public application 1.4.0 follows the author's last published 1.3.2. Engine 1.6.0 consolidates the requested 1.6/1.7/1.8 development scope. This entry records source changes; it does not assert a published binary or completed CI run.

### Added
- Separate within/between Gaussian variance-component estimation, pointwise parametric bootstrap intervals, two bootstrap tests and separate power.
- Known-truth bias/MSE/RMSE/efficiency/coverage study with common-target comparisons and Monte Carlo uncertainty.
- Optional experimental marginal-ML MELSM with global subject IDs, random location/scale, optional correlation/time and numerical diagnostics.
- Geometric and 20% trimmed means; three default sensitivity tracks; portable scientific regression harness and explicit shared-source registry.
- Scientific models UI, modern result tables, state restoration and new synthetic examples.

### Fixed
- Nonfinite values crashing calibration-state JSON saving; schema-2 state/configuration/payload validation and atomic file writes.
- Null/alternative mismatch, asymmetric contamination, minimum-repeat inconsistency, failure accounting and accidental scenario coupling.
- Uncorrected displayed metric selection: full-registry Bonferroni; Cliff sign; misleading selected-pair/equivalence/MDE descriptions.
- Stale settings and analysis halves, missing state in manifests, forced-reuse provenance, silent journal failures and unsafe manifest paths.
- Broken notebook-validation CI command, release-dispatch checkout/version mismatch, strict argument validation and remote job relative paths.
- Result label overlap, unreadably compressed grids, inaccessible sidebar overflow and misleading confidence language.

### Changed / migration
- Formula MVS-1.4.0; benchmark MVS-BENCH-1.2.0. Recalibration is required. Old numeric scores/results are not directly comparable.
- Detection score excludes the three descriptive diagnostics; candidate gates use uncertainty bounds with no score cutoff.
- Missing scientific numbers remain unavailable, never zero. Small smoke budgets intentionally do not estimate MDE.
- Documentation now distinguishes experimental models, conditional power, local checksums, preregistration and actual validation.
- Existing badge markup, image assets and packaged plugins are preserved unchanged. Legacy report templates can retain old vocabulary; new core CSV/JSON is authoritative.

### Validation
- No .NET compilation, C# runtime tests or Windows visual render during source preparation, as requested. See validation/PACKAGE_QA.md and the CI/manual acceptance gates.

## Historical development notes

The supplied archive was labelled 1.5.0, while the author's last public release was 1.3.2. Its original long changelog is preserved as `docs/history/CHANGELOG_development_snapshot.md` for traceability. It contains historical method/validation claims and should not be read as current documentation or independent evidence for engine 1.6.0.
