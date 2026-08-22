# Contributing to MVS Analyzer

Thanks for being here. This project has one unusual property that shapes every rule below: **it makes claims about statistical behaviour and then hashes them.** A change that quietly alters a number can invalidate every published run. So the process is strict where it matters and relaxed everywhere else.

## Ground rules

1. **No new dependencies.** The app builds with the .NET 8 SDK and nothing else — no NuGet packages, no vendored binaries. If a change needs a library, open an issue first and explain why the standard library is not enough.
2. **No network code.** Ever. Offline operation is a feature, not an oversight.
3. **No executable plugins.** Plugins are data. Any PR that loads code from `%LocalAppData%` will be closed.
4. **If the score definition changes, the formula version changes.** See [Changing the statistics](#changing-the-statistics).
5. **Honesty over polish.** A verdict of *not enough data* is a valid output. Do not replace it with something that looks more confident.

## Getting set up

```powershell
git clone https://github.com/d1d2dopamine/MVS-Analyzer.git
cd MVS-Analyzer

dotnet build MvsAnalyzer.csproj -c Release
dotnet run  --project MvsAnalyzer.Tests      # must print 12/12
dotnet run  --project MvsAnalyzer.csproj
```

Windows 10/11 x64 and the .NET 8 SDK are required (WinForms + `System.Drawing`). Visual Studio 2022 with the *.NET desktop development* workload works out of the box; Rider and `dotnet` CLI are fine too. Open `MvsAnalyzer.slnx`, or `MvsAnalyzer.csproj` directly if your tooling does not read `.slnx` yet.

CI runs exactly the two commands above on `windows-latest`. If they pass locally, they pass there.

## Style

- `.editorconfig` is authoritative: 4 spaces, CRLF for C#, file-scoped namespaces, nullable enabled.
- Keep engine code UI-free. `AnalysisEngine`, `OutputExporter`, `RunAuditor`, `CsvImporter` and `PluginManager` must never reference WinForms types — that boundary is what makes a future CLI possible.
- User-visible strings live in the localization tables, in **both** English and Russian. A PR that adds an English-only string will be asked for the Russian one.
- Numbers written to files use round-trip formatting and `CultureInfo.InvariantCulture`. No exceptions — a decimal comma in `results.csv` breaks other people's pipelines.
- Comments explain *why*, not *what*. The statistics deserve a sentence; the loop does not.

## Tests

`MvsAnalyzer.Tests` is a dependency-free console harness (the app exposes internals to it through `InternalsVisibleTo`). It currently covers 12 invariants:

`ProcessingLimits` · `MultiGroupBuild` · `MannWhitneySymmetry` · `KruskalWallisSeparation` · `CandidateThresholds` · `UniqueRunFolders` · `FormulaHash` · `DeltaSymmetry` · `EquivalenceVerdict` · `InsufficientVerdict` · `MdeCurve` · `SplitHalves`

Add a check for every behavioural change. A good check is deterministic (fixed seed), fast (< 1 s) and fails loudly with the expected and actual value printed.

## Changing the statistics

If your change affects any number that ends up in `results.csv`, `calibration.csv` or `run_manifest.json`, do **all** of this in the same commit:

1. Update the frozen specification string in `OutputExporter` and bump `FormulaVersion` (for example `MVS-1.2.0` → `MVS-1.3.0`).
2. Recompute the SHA-256 of the specification string and update `FormulaHash`.
3. Update the `FormulaHash` test so it asserts the new pair.
4. Bump `AnalysisEngine.EngineVersion` if the computation — not just the wording — changed.
5. Update [docs/METHODS.md](docs/METHODS.md), the badges in both READMEs, and [CHANGELOG.md](CHANGELOG.md).
6. Say in the PR description what happens to existing runs. `FORMULA_CHANGED` appearing in audits is expected and must be documented, never hidden.

> A PR that changes a computation without touching the formula hash will not be merged, even if the new statistics are better.

## Pull requests

- One topic per PR. "Fix DPI in the results card" and "add post-hoc tests" are two PRs.
- Describe the behaviour before and after. Screenshots help for UI work — attach them to the PR, do not commit images into the repository.
- Update docs in the same PR. Documentation that trails the code is how the 1.1 verdict bug survived a release.
- Fill in the PR checklist honestly. "Tested manually on one dataset" is a fine answer; silence is not.

## Reporting bugs

Use the [bug report form](.github/ISSUE_TEMPLATE/bug_report.yml). The three things that make a report actionable:

1. the app version and `engineVersion` + `formula.hash` from `run_manifest.json`;
2. a dataset that reproduces it — synthetic, please, never real subject data;
3. the exact settings (seed, scenario, effect multiplier, α, outlier and missing rates).

## Good first contributions

- Post-hoc pairwise comparisons after a significant Kruskal–Wallis (the largest missing feature).
- Replacing absolute coordinates inside cards with `TableLayoutPanel` so 125–150 % DPI stops shifting elements.
- A headless CLI over the existing engine — the separation is already there.
- Persisting run history between sessions.
- Additional import profiles for common lab instrument exports.
- Accessibility: keyboard mnemonics, focus order, screen-reader names.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Disagree with the statistics as much as you like; be decent to the person on the other side of the thread.
