# Round 2: native validation gates and scientific interface parity

Date: 2026-10-11. Starting point: the user-provided
`MVS-analyzer-round1-validation(1).zip`, containing the round 1 checkpoint.
This is a source checkpoint, not a compiled release or a native-validation pass.

## Scope and status

The round addresses the verification work behind R1-01 and R1-05. It adds
independently checkable numerical references and makes native/interface checks
reproducible. It does not change the scientific engine.

| Task | Delivered | Remaining evidence |
| --- | --- | --- |
| R1-01 | One-command verification runner; full JSON/CSV/scientific-manifest CLI/Python comparison; preserved-state and failure gates | Execute Core.Tests, build/publish and real CLI flow with .NET 8 |
| R1-05 | 49 independently frozen numerical cases; four separate policy cases; native reference/invariance tests; exact small-sample diagnostics | Execute the native tests and assess their actual numerical differences |

Neither task is marked fully validated by Python-only results. R1-04, R1-06,
R1-07 and R1-08 remain separate work. Holm/maxT, activation of staged metrics,
DataFrame inputs and statistical redesign were not included.

## Changes

- `validation/rank-test-fixtures-v1.json`: 53 identified cases, explicit test
  settings, SciPy 1.17.0 provenance, seed 20261011 and declared accuracy gates.
- `validation/rank_test_reference.py`: independent reference generation/checking
  and exhaustive small-sample Mann-Whitney labelled-assignment diagnostics.
  Generation refuses overwriting an existing fixture.
- `validation/test_rank_reference.py`: 13 regressions for mathematical examples,
  enumeration, small-sample decisions, unavailable policies and tampering.
- `validation/requirements-rank-reference.txt`: optional SciPy diagnostic
  dependencies; production requirements remain unchanged.
- `MvsAnalyzer.Core.Tests/RankTestChecks.cs`: four native test groups covering
  reference p-values, empty/constant policies and rank invariances. The existing
  native harness registers them and its project copies the pinned fixture to
  the output directory. There is no new public CLI command.
- `tools/test_python_cli.py`: compares every result JSON field and CSV row,
  scientific manifest fields and original calibration bytes against the
  canonical CLI analysis. It uses the existing contract's numerical tolerances,
  preserves row order/nulls/decisions and refuses an existing parity output.
- `tools/run_round2_validation.py`: sequential checks with individual logs,
  machine-readable statuses, failure propagation and a fresh output directory.
  Missing native verification produces `incomplete`/exit 2, never `passed`.
- `tools/test_round2.py`: 16 regressions for scientific drift detection,
  unavailable/boolean states, malformed files, subprocess failure propagation
  and evidence preservation. These synthetic tests are not real CLI parity.
- CI installs optional reference dependencies, runs the new offline regressions
  and reference checker, and retains its existing real native/CLI execution.
- Validation guides describe scope, commands and numerical limitations.
- `.codex/skills/mvs-safe-development/` includes all seven supplied skill files,
  byte-for-byte unchanged, including references, agent metadata and guard tests.

## Scientific observations

The comparator deliberately specifies two-sided, asymptotic, tie-corrected,
continuity-corrected Mann-Whitney. Kruskal-Wallis uses its tie-corrected
chi-square reference. Matching a library's unspecified defaults is insufficient
because a small untied Mann-Whitney sample can select an exact method instead.
See the independent [SciPy Mann-Whitney documentation](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.mannwhitneyu.html)
and [Kruskal-Wallis documentation](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.kruskal.html).

For six separated observations in each group, the asymptotic p-value is
0.005074868097940253; exhaustive exact enumeration gives
0.0021645021645021645 over 924 labelled assignments. These lie on opposite sides
of the fixed `0.05/12` threshold. This is a reproducible approximation limitation;
it does not authorize choosing whichever test yields significance. No exact
procedure has been activated in production.

Native accuracy gates are absolute p-value errors, `2e-7` for the existing
polynomial-normal-CDF Mann-Whitney and `2e-10` for Kruskal-Wallis. They are
declared implementation checks, not precision guarantees in very small tails.
Constant/empty policies are labelled separately from SciPy numerical agreement.
The diagnostic suite does not establish FWER or validity under every null.

## Verification in the preparation environment

Python 3.12.14, NumPy 2.3.5 and SciPy 1.17.0 were available. The reproducible run:

```bash
python tools/run_round2_validation.py --output /path/outside/source/round2-checks
```

All 11 independent/static check stages passed:

- 38 validation tests (25 retained + 13 new);
- 4 Python-wrapper tests using a fake CLI;
- 16 new parity-checker/runner regressions;
- 17 backup and 6 source/documentation regressions;
- independent reproduction of all 53 rank fixtures;
- source metadata/payload/method-hash checks, CLI static contract checks,
  limited C# structure checks, notebook consistency and independent mathematical
  identities.

The five suites above contain 81 passed tests. Native checks were `not_run`, so
the runner intentionally returned exit 2 / `incomplete`. Local passing tests
do not imply real CLI/Python agreement or that the new C# harness compiles.

The .NET executable was absent from PATH and standard installation locations.
The official .NET 8 download metadata endpoint returned HTTP 403. No compiler,
SDK or runtime was installed; no native results are claimed. The workflow was
inspected locally; GitHub Actions was not executed in this environment.

## Reproduction with .NET

```bash
python -m pip install -r validation/requirements-rank-reference.txt
python tools/run_round2_validation.py --output artifacts/round2-native-new
```

Use a .NET 8 SDK and a new output directory. Inspect `verification.json` and the
individual logs. Only exit 0 after actual native tests, real CLI analysis,
scientific parity and score reproduction clears this checkpoint's native gate.
Failure leaves the logs intact. Do not relax fixture gates to obtain a pass.

The unchanged supplied guard also passed its 30 bundled regressions. CI YAML
and its embedded Python score-check step parsed successfully. The boundary
guard reported only the scoped changes, with no violations. These checks are
separate from the 81 project tests and do not establish native compilation.

## Preservation and packaging

Application 1.4.0, engine 1.6.0, formula MVS-1.4.0, active twelve-metric registry,
Bonferroni family, public schemas, production sources, historical benchmark
evidence and embedded Colab payload remain unchanged. All original source files
are retained; the supplied skill is copied without modification.

The source ZIP excludes only new local check logs, guard snapshots, bytecode
caches and build outputs. Archive integrity/completeness and patch boundary are
checked separately from runtime verification. No commits, tags, pushes or
releases were performed.
