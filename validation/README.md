# Validation tools

This directory contains simulation inputs, reference scripts and machine-readable method/asset checks used by CI. Tests and synthetic data are not independent scientific certification.

- `method-hashes.json` pins the current formula and benchmark definitions.
- `cli-contract-v1.json` pins the current public CLI surface, canonical cases and comparison classes.
- `protected-assets.json` checks local binary artwork and plugin packages; README badge text and markup are freely editable.
- `reference_numerics.py` checks mathematical identities in Python independently of the C# implementation.
- `make_datasets.py`, `dgp.py`, `reference_simulation.py` and `analyze_results.py` support the diagnostic workflow.

Generated reports belong in CI artifacts, not the application download. See `docs/VALIDATION.md` for interpretation limits.

## Independent diagnostic tools

Install the optional NumPy/SciPy diagnostic dependencies and run the offline
regression suite:

```bash
python -m pip install -r validation/requirements-rank-reference.txt
python -m unittest discover -s validation -p 'test_*.py' -v
```

### Score reproduction

```bash
python validation/analyze_results.py path/to/results.csv --draws 500
```

The script automatically reads the sibling `run_manifest.json`. It accepts only
the pinned MVS-1.4.0 formula specification/hash and checks the decision alpha,
fixed family size and CSV checksum when a manifest file list is present.
An explicit `--manifest PATH` selects another manifest. Unknown formulas are
unsupported, not evidence of a calculation bug. Malformed applicable rows fail
instead of disappearing from diagnostics. An exported score discrepancy above
0.01 produces exit status 1; invalid metadata/arguments produce exit status 2.

For a CSV without a manifest, parameters must be supplied explicitly:

```bash
python validation/analyze_results.py results.csv --formula MVS-1.4.0 --alpha 0.05 --family-size 12
python validation/analyze_results.py historical.csv --formula legacy-five-component --alpha 0.05
```

The second command is an explicitly unverified historical diagnostic, not an
engine version identifier. If a sibling manifest exists, its identity and
parameters must match; explicit arguments cannot override incompatible metadata.
Robustness, repeatability and coverage remain diagnostics but do not enter the
current score. Exploratory weights do not change the frozen formula.
Rank diagnostics use average ranks/Spearman and Kendall tau-b; constant and
single-value inputs are undefined. Top ties are reported together.

### Reference simulations

```bash
python validation/reference_simulation.py 2000 primary --output-dir artifacts/reference
python validation/reference_simulation.py 2000 discriminating --output-dir artifacts/reference
```

Protocol MVS-REFERENCE-2 uses all twelve active legacy metric definitions and
tie-corrected, continuity-corrected asymptotic Mann-Whitney tests. Metric-specific
nonfinite entity summaries are excluded separately in each group/replication.
At least four usable entities per group are required; unavailable tests count
as non-rejections. `available_*` rows report the fraction of testable
replications. The individual rates use alpha 0.05. `any_of_twelve_unadjusted`
describes uncorrected select-then-test behaviour; `bonferroni_twelve` keeps the
fixed twelve-test family even when some tests are unavailable.

Files are named `reference_power_v2_<grid>.csv` and `.md`, so historical report
names are preserved. Version 2 results are not directly interchangeable with
old ten-metric diagnostics. The two existing grids are development scenarios,
not unseen validation data. Power estimates have Monte Carlo uncertainty and
do not certify the C# implementation or the small-sample approximation.

## Independent native rank-test fixtures (round 2)

`rank-test-fixtures-v1.json` freezes 49 SciPy numerical cases and four explicit
MVS empty/constant policies. Inputs include ties, unequal group sizes, the
four-entity boundary, two to ten groups and extreme tails. The inputs are entity
summaries, not repeated measurements treated as independent observations.
`MvsAnalyzer.Core.Tests/RankTestChecks.cs` calls the actual Core methods against
these values and checks group/order/affine invariances. Its fixture SHA-256 pin
prevents accidental regeneration from passing silently.

The independent settings are explicit: Mann-Whitney is two-sided, asymptotic,
tie-corrected and continuity-corrected; Kruskal-Wallis uses average tied ranks,
tie correction and the chi-square reference. Do not use SciPy's automatic
exact/asymptotic selection as a supposedly matching comparator.

```bash
python -m pip install -r validation/requirements-rank-reference.txt
python validation/rank_test_reference.py --check
python -m unittest discover -s validation -p 'test_*.py' -v
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
```

SciPy is an optional diagnostic dependency, never a production backend. The
fixture was generated with SciPy 1.17.0. Its verification uses absolute `1e-14`
and relative `1e-12` tolerances; provenance retains the generating version.
New fixtures can be written with `--write NEW_PATH`; existing files cannot be
overwritten by that command.

The native Mann-Whitney gate is absolute p-value error `2e-7`, reflecting the
existing polynomial normal CDF. The separate Kruskal-Wallis gate is `2e-10`.
These are numerical implementation gates, not population validity, FWER or
relative accuracy guarantees in extreme tails. An extremely small p-value can
round to zero and still satisfy the declared absolute gate. Constant/empty
cases are tagged `mvs-declared-policy`, not numerical SciPy agreements:
MVS returns one for constant pooled data and unavailable for an empty group;
SciPy Kruskal-Wallis instead raises on identical pooled observations.

Three Mann-Whitney fixtures also include exact labelled-assignment enumeration
as a separate diagnostic (including ties). With six separated observations in
each group, asymptotic p is about `0.0050748681`, while the exact diagnostic is
`0.0021645022`; these straddle `0.05/12`. This demonstrates a small-sample
approximation limitation, not an instruction to switch methods after inspecting
the result. Production methods, registry and correction remain unchanged.

## Reproduce the round 2 verification

With Python diagnostic dependencies and a .NET 8 SDK installed:

```bash
python tools/run_round2_validation.py --output artifacts/round2-new-run
```

The runner checks independent/static regressions, runs native Core.Tests,
publishes the CLI, executes canonical calibration/analysis, checks artifacts,
compares CLI/Python scientific results and reproduces exported scores. Its
CLI/Python check compares every JSON result field and CSV row, scientific
manifest fields, exact unavailable/decision states and saved calibration bytes.
Numerical tolerances come from the existing CLI contract. Run IDs, timestamps
and manifest file records are excluded from scientific equality; artifact
integrity is checked separately. This is same-environment parity for the
canonical calibrate/analyze case, not a full baseline for all workflows.

Every child command has a retained log and a `verification.json` entry. Exit `0`
means all declared checks passed; `1` means a check/preflight failed; `2` means
the verification is incomplete. Without .NET, or with `--python-only`, native
checks are explicitly `not_run` and the runner returns `2`. Existing output
directories are refused so prior evidence is preserved. Generated reports/logs
are not source ZIP contents. See the [round 2 checkpoint](../docs/ROUND2_NATIVE_VALIDATION_CHECKPOINT.md).

After the reported native `mw_overlap` failure, engine 1.6.1 restores full
normal-CDF coefficient precision. All 53 frozen fixtures and both accuracy
gates remain unchanged. Recompute old calibrations before running parity with
the repaired engine. See the [fix checkpoint](../docs/ROUND2_MANN_WHITNEY_FIX.md).

## Staged Huber repair accuracy gate (round 10)

The original `huber-fixtures-v1.json`, `huber-native-baseline-v1.json` and Decimal80
reference remain frozen. The old native evidence still fails 9/20 cases. The new
`huber-repair-fixtures-v1.json` includes those exact twenty cases and expanded
extreme/subnormal, reflection, permutation and zero-MAD controls.

`huber_repair_reference.py` computes median/MAD and the clipped-score root directly
from exact original binary64 inputs using Decimal1600. It does not use the native
normalization or reconstructed samples. The gate retains
`max(1e-10 * fixedMADscale, 4 * ulp(reference rounded to binary64))`; solver status
must also distinguish positive MAD from exact-zero fallback. Any unavailable native
result fails accuracy. Fixture, implementation, engine/staged/family and binary
provenance are checked. Synthetic documents in unit tests are explicitly test data.

```bash
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release --no-build -- --export-huber-diagnostics validation/huber-repair-fixtures-v1.json artifacts/huber-repaired-native.json
python validation/huber_repair_reference.py --native artifacts/huber-repaired-native.json --core-assembly MvsAnalyzer.Core.Tests/bin/Release/net8.0/MvsAnalyzer.Core.dll --out artifacts/huber-repaired-comparison.json
python -m unittest discover -s validation -p 'test_huber_repair_reference.py' -v
```

Exit 0 means every declared numerical/status comparison passed; 1 means valid
native evidence failed accuracy; 2 means invalid input/provenance. These are
numerical implementation checks for a staged metric, not scientific activation.
See [round 10](../docs/ROUND10_STAGED_HUBER_REPAIR.md) for actual native results.

## Post-hoc Holm diagnostics on the frozen development run

`holm_benchmark_diagnostics.py` derives fixed-12 comparisons from the immutable
round-6 per-replication p-vectors. It pins source hashes, preserves both replay
phases and failures/missing diagnostics, refuses overwrites, and checks actual
native output against exhaustive closed Bonferroni intersections.

```bash
python validation/holm_benchmark_diagnostics.py prepare --benchmark benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0 --out artifacts/holm-new
# Build the native test exporter first, then run:
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release --no-build -- --export-multiplicity-diagnostics artifacts/holm-new/multiplicity-fixtures.json artifacts/holm-new/multiplicity-native.json
python validation/holm_benchmark_diagnostics.py analyze --benchmark benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0 --out artifacts/holm-new --native artifacts/holm-new/multiplicity-native.json --core-assembly MvsAnalyzer.Core.Tests/bin/Release/net8.0/MvsAnalyzer.Core.dll
```

Exit 0 is a complete consistent diagnostic, 1 is arithmetic/decision disagreement,
and 2 is invalid or incomplete evidence. This does not run or pass a new benchmark.
See [round 12](../docs/ROUND12_HOLM_DEVELOPMENT_DIAGNOSTICS.md) for actual results:
any-rejection counts remain unchanged, original scientific NO-GO retained.
