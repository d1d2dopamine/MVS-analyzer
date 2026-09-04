# Architecture

Public application 1.4.0; numerical engine 1.6.0. Desktop: .NET 8 WinForms, Windows. CLI and portable regression harness: plain net8.0. No third-party NuGet package is required.

`SharedSources.props` is the explicit shared-source registry for the CLI and portable tests. There is **not** a separate Core DLL in this release. The desktop compiles root/Benchmark sources and excludes the CLI and both test-project directories. Portable projects define `MVS_NO_FIGURES`, excluding Windows drawing calls. Keep the source registry updated when adding modules.

| Module | Responsibility |
|---|---|
| AnalysisEngine | Entity metrics, empirical sensitivity, rank tests, adjusted decisions, effects |
| VarianceAnalysis | Gaussian within/between ML/REML, bootstrap inference/power/intervals |
| EstimationStudy | Known-truth DGPs, common-target estimators and performance |
| MelsmAnalysis | Experimental conditional-Gaussian mixed-effects location-scale likelihood |
| NumericalMethods | Bounded optimizer, quadrature, information-matrix diagnostics |
| ScientificInfrastructure | Finite JSON, atomic text writes, seed derivation, frozen configuration |
| CalibrationPersistence | Schema/version/registry/configuration and payload validation |
| OutputExporter / ScientificTables | CSV/JSON/model manifests; spreadsheet-safe text |
| MainForm.Science / MainForm.Results | Optional model workflows and flow-based results |
| CLI HeadlessRun / ScientificCommands | Noninteractive execution, cancellation and model exports |
| Benchmark | Declared simulation protocol and diagnostic comparisons |

Only pure data/captured options go to background calculation tasks; Windows controls are updated through progress callbacks. Cancellation is cooperative. Large model refits can be slow. Individual files are written atomically, but a whole output directory is not a transactional filesystem snapshot. A final manifest identifies listed completed artifacts.

A settings fingerprint excludes cosmetic/output preferences but includes statistical/preprocessing choices. The GUI checks it before analysis. Saved states do not silently restore a missing or changed import plugin. CLI defaults are deterministic application defaults; saved desktop settings are opt-in.

`RunAuditor` uses a local cross-process mutex for append operations and rejects traversal paths in manifests. Checksums and a local hash chain are integrity aids, not authentication, model validation or external preregistration.

Run `python tools/check_source.py`, the two .NET harnesses, Linux save/reload smoke and the optional diagnostic workflow before release. See `WINDOWS_QA.md` for actual UI checks still needed.
