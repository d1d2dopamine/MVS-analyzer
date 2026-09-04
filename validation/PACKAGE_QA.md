# Source package QA — public 1.4.0 / engine 1.6.0

Prepared for the author to compile and test in GitHub CI. **No .NET compilation, C# test execution, WinForms launch or Windows screenshot/render was performed during source preparation**, as requested. This file must not be quoted as a claim that the application builds or that scientific validation has passed.

## Checks actually executed

- `tools/check_source.py`: project/props/manifest/solution XML; explicit shared compile-source paths; Python AST; all three notebook JSON structures and Python cells; current method/protocol hash pins; application versions; required scientific command source; absence of the broken workflow placeholder.
- `tools/check_csharp_structure.py`: delimiters, comments and strings/interpolations across 46 C# files. **This is a limited lexical/structural check, not a C# grammar parser, semantic/type checker or compiler.**
- YAML parsing of the CI, release and extended-diagnostic workflows.
- Exact preservation of the original demo SHA-256, all 5 protected image/plugin assets and every original README image/badge tag (including both language headers).
- Python-only numerical identity checks: standard-normal quadrature moments for orders 3, 9, 15, 31, 61; direct covariance Cholesky versus the analytic rank-one likelihood identity at four variance values. Recorded in `reference_numerics_results.json`.
- Quadrature maximum absolute moment discrepancy: about 1.29e-14. Analytic/dense covariance discrepancy: about 1.07e-14. These support the mathematical identities/transcription only, **not runtime correctness of the C# implementation**.
- Source ZIP integrity, one-root layout and equality of archived source files to the prepared tree are checked during packaging.

## Implemented but not executed here

- Desktop-linked regression harness and a portable harness with the existing checks plus new scientific contracts.
- Linux CLI reproduction of the reported 150-replication calibration-save failure, followed by reload, analysis, strict JSON and manifest checksum verification.
- Optional extended Gaussian variance / known-truth estimation / MELSM diagnostic workflow.
- Windows/HiDPI/theme/keyboard/scroll checks in `docs/WINDOWS_QA.md`.

## Remaining release gates

1. Run all GitHub CI jobs; fix any compilation, runtime or regression failure. Static checks cannot replace this.
2. Test the Windows UI on actual Windows, including cancellation and stale-settings protection.
3. Inspect numerical diagnostics and test meaningful datasets; do not confuse an output file with a trustworthy fit.
4. Independently compare the experimental model fits with a trusted implementation and validate finite-sample error/coverage before scientific claims.
5. Publish only the binaries built from the intended tag. The release workflow checks the tag/version and waits for a Linux save/replay smoke before creating a draft.

## Known limits retained deliberately

Approximate rank tests and bootstrap equivalence; no post-hoc simultaneous selected-pair intervals; conditional plug-in power; separate multiplicity families; model-dependent variance intervals; experimental native MELSM without AR(1), random slopes or arbitrary covariates; no externally immutable preregistration; local pseudonyms are not strong anonymization. See METHODS/VALIDATION for details.

No empirical benchmark success or externally validated scientific superiority is claimed for this engine. Historical reference files, badge artwork and packaged plugin bytes are preserved and labelled appropriately.
