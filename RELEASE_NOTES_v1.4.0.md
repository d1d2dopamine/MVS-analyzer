# MVS Analyzer v1.4.0

[![Download for Windows](https://img.shields.io/badge/Download-Windows%20x64-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/MVS_Analyzer_v1.4.0_win-x64.zip)

**Public application 1.4.0 · Scientific engine 1.6.0 · Formula MVS-1.4.0**

This release follows public version **1.3.2** and consolidates the requested 1.6/1.7/1.8 development work. The previously supplied archive labelled 1.5.0 was a development snapshot, not the public numbering used here. The download badge targets the Windows asset above and becomes available when that release is published.

## Separate within-entity variation from between-entity heterogeneity

- Three summary-sensitivity tracks: location, within-entity variability, and between-entity heterogeneity.
- A separate Gaussian random-intercept workflow estimates **within and between variance components**, rather than mistaking the variance of observed entity means for latent heterogeneity.
- REML component estimates, pointwise parametric bootstrap intervals, ICC, transparent untruncated moment estimates, separate bootstrap tests, and separate power/FPR curves.
- Explicit failure counts, Monte Carlo uncertainty and boundary warnings. Scale effects multiply **SD**, not variance.

## Estimation quality with known truth

The new estimation study reports **bias, MSE, RMSE, empirical SD, efficiency ratios, interval coverage and Monte Carlo standard errors**. Comparisons use a common declared estimand under a chosen synthetic mechanism. It does not claim to know the true bias of an uploaded dataset.

## Optional MELSM — experimental

A native mixed-effects location-scale model supports global subject IDs across conditions, random location and scale, optional location–scale correlation, and optional linear time effects. Estimation uses marginal maximum likelihood, analytic random-intercept integration and adaptive quadrature, with convergence, boundary, information-matrix and quadrature diagnostics.

**This implementation remains experimental.** Numerical convergence does not establish model adequacy or independent validation. AR(1), random slopes, arbitrary covariate formulas and non-Gaussian response likelihoods are not implemented. Approximate parameter intervals are suppressed when numerical diagnostics fail.

## Fixes and methodological changes

- Fixed the calibration **save-time JSON failure** caused by nonfinite scientific values. New JSON writes finite numbers or `null`, never fabricated zeros.
- Matched null and alternative generators, symmetric contamination, consistent repeat minima, common random streams and explicit simulation-failure accounting.
- Added geometric and 20% trimmed means: twelve registered summaries in total.
- Displayed difference decisions now use **Bonferroni across the full metric registry**, not only selected candidates. Raw tests remain approximate.
- Corrected Cliff’s delta direction and labelled selected-pair intervals as descriptive. Approximate equivalence no longer exposes a misleading bootstrap-tail “p-value”.
- Small simulation budgets no longer imply a fabricated MDE or “effects above 20% are invisible”.
- The score is now a detection index; descriptive robustness, repeatability and pooled-median coverage no longer masquerade as estimator accuracy.
- Schema-2 calibration states freeze preprocessing, import interpretation and scientific settings. Manifests include the calibration state and both input hashes for explicitly forced reuse.
- Fixed strict argument handling, remote-job path resolution, silent journal failures, manifest traversal checks, the broken notebook-validation command, and release-dispatch checkout/version consistency.

## Desktop, CLI and notebooks

Results use wrapped summaries and independently scrollable tables. The sidebar can scroll, and **Scientific models** exposes component analysis, known-truth estimation and MELSM. Saved calibrations can be restored with compatibility checks. Existing badge markup, image assets and packaged plugins are preserved.

New CLI commands: `variance`, `estimation`, `melsm`. The three-cell notebooks use a pinned executable and verify its checksum/version. Hosted notebook uploads leave the local machine; use them only when appropriate for your data.

## Migration and validation

**Recalibrate from the original data.** Old calibration states, scores and benchmark results are not directly comparable to this engine. `--force` allows explicit cross-dataset exploration, not incompatible methods or schemas.

The supplied source package was **not compiled or run as a .NET application during preparation**, as requested. Portable/desktop regressions, the exact 150-replication save–reload smoke, static validators and an optional extended diagnostic workflow are included. Actual CI results and Windows/HiDPI visual checks remain release acceptance gates; this note does not claim they have already passed.

Read `docs/METHODS.md`, `docs/VALIDATION.md`, `docs/MIGRATION.md` and `validation/PACKAGE_QA.md` before scientific use. Local checksums are integrity aids, not external preregistration or statistical certification.

### Assets

- `MVS_Analyzer_v1.4.0_win-x64.zip` — self-contained Windows x64 desktop build.
- `MVS_Analyzer_v1.4.0_linux-x64-cli.zip` — self-contained Linux x64 CLI; run `chmod +x mvs` if needed.
- `MVS_Analyzer_v1.4.0_source.zip` — source archive generated by the release workflow.
- `SHA256SUMS.txt` — published asset checksums.
