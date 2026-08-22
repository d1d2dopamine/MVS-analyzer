## What this changes

<!-- One or two sentences. What is different after this PR? -->

## Why

<!-- Link the issue if there is one: Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / cleanup (no behaviour change)
- [ ] Statistics or output format change (**read the section below**)

## Statistics and output changes

Does this PR change any number that appears in `results.csv`, `calibration.csv` or `run_manifest.json`?

- [ ] No — outputs are byte-identical for the same input and settings
- [ ] Yes — and I did **all** of the following in this PR:
  - [ ] bumped `FormulaVersion` in `OutputExporter`
  - [ ] recomputed and updated `FormulaHash`
  - [ ] updated the `FormulaHash` test
  - [ ] bumped `AnalysisEngine.EngineVersion` if the computation changed
  - [ ] updated `docs/METHODS.md` and the badges in both READMEs
  - [ ] documented in `CHANGELOG.md` that existing runs will report `FORMULA_CHANGED`

## Checklist

- [ ] `dotnet build MvsAnalyzer.csproj -c Release` succeeds
- [ ] `dotnet run --project MvsAnalyzer.Tests` prints 12/12 (or more, if I added checks)
- [ ] No new NuGet packages, no network calls, no code loading from plugins
- [ ] Engine files still contain no WinForms references
- [ ] New user-visible strings exist in **both** English and Russian
- [ ] Numbers written to files use round-trip formatting and invariant culture
- [ ] Documentation updated in this PR, not "later"

## Testing

<!-- Which datasets did you try? examples/demo_three_groups.csv, examples/MVS_stress_test.csv, your own? What settings? -->

## Screenshots

<!-- UI changes only. Attach images to the PR; do not commit them to the repository. -->
