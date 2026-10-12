# Round 4: benchmark replication diagnostics

Date: 2026-10-11. Source: `MVS-analyzer-round3-applicability(1).zip`, SHA-256
`a86ab6121f63e07f907d62dcdf12974e4e4fc18e4fe330460391ec8da581ebd7`.
All 250 source files match public commit
[`fa2c8017b4e469d9c75470ed0bb93c33771a1912`](https://github.com/d1d2dopamine/MVS-analyzer/commit/fa2c8017b4e469d9c75470ed0bb93c33771a1912).

## Outcome and scope

R1-07 adds inspectable rows for each benchmark condition replication, each
procedure and metric, both determinism passes, and each stability split. Failed
replications and withheld claims remain visible; unavailable diagnostics remain
blank. Historical checkpoints without these fields are explicitly incomplete.
The independent checker reconciles the new rows against historical aggregates
and reports unconditional rates over the requested denominator separately.

This is diagnostic instrumentation. Engine 1.6.2, application 1.4.0,
MVS-1.4.0 formula/hash, MVS-BENCH-1.2.0 protocol/hash, twelve active metrics,
Bonferroni, random streams, historical aggregate denominators and decisions are
preserved. No staged metric is activated and no new sensitivity/FWER claim is made.

See [benchmark documentation](BENCHMARK.md) for tables and checker use. The new
artifact schema is `MVS-BENCH-DIAGNOSTICS-1`; it is distinct from the frozen
scientific protocol. A new diagnostic schema does not redefine historical runs.
All reports under `benchmark_history/` remain unchanged.

## Previous checkpoint independently checked

The original attached round-3 source was actually compiled and run here using the
official .NET SDK 8.0.425 / runtime 8.0.31. It passed all 92 native tests, its
self-contained Linux CLI publish, canonical calibration/analysis, real Python/CLI
scientific parity, output/state checks, independent exported-score reproduction,
invalid-integer rejection and Python wheel build. The 86 existing Python tests,
53 frozen SciPy rank cases, source/notebook/method contracts and structural checks
also passed. This closes the locally unexecuted verification documented in the
historical round-3 report; that report is preserved unchanged.

The public [CI run](https://github.com/d1d2dopamine/MVS-analyzer/actions/runs/38155243109)
was independently observed successful for the matching commit. Counts above are
from actual local execution, not inferred from a green CI badge.

## Bugs reproduced and disposition

### B4-01: invalid JSON for unavailable stability — fixed

Reproduction: construct a stability result with `Tau=[]`, `Repeats=0` (for example,
all stability splits fail), then serialize the benchmark manifest. The old CSV
formatter returns an empty string for nonfinite values, yielding
`"medianTau": ,` and similarly invalid fields. The manifest now uses a JSON-only
formatter that emits `null`; CSV unavailable cells stay blank. Regression parses
the result as JSON and checks the null fields.

### B4-02: failure-blind legacy determinism verdict — documented

The legacy digest skips failed replications. If both passes completely fail,
both hash the empty decision matrix and verdict E can be `pass`. This stage
preserves that historical verdict/digest; both passes now have full status rows.
Inspect completion/failure statuses before accepting replay. A future deliberate
revision should require successful corresponding indices in addition to equal
scientific decisions, with its own compatibility/protocol assessment.

### B4-03: stale legacy source pin — documented, unchanged

`python tools/test_ui_patch.py` gives 17/18 and
`python tools/test_colab_connection.py` gives 47/48. Both failures concern the
unchanged `MvsAnalyzer.Cli/HeadlessRun.cs`: actual SHA-256
`679369121cd50769764033eeb30b202b2cbc1684338eebf88c00f19afa24d25a`, pinned
`608db77961a4c599e049a32d653687654c6d186d31a51af145cec65ba27f312f`.
No evidence-based reconciliation of that older change was in this task. Its pin
is not weakened to make the archived UI/connection checks pass.

### B4-04: aggregate stability rows lose failed split positions — addressed additively

The old `benchmark_stability.csv` enumerates successful tau values only, so its
`split` ordinal is not the original requested split index after a failure. The
new table preserves the original index and failure row without reinterpreting
historical CSVs. The old table stays unchanged for compatibility.

### Existing seed and claim semantics — explicitly retained

Seeds are not unique record keys: same-stage effect conditions deliberately
reuse streams, and plasmode names use a modulo-40 stream index (`dataset9` and
`dataset14` collide). Use condition/pass/index as identity. Changing allocation
would invalidate historical replay and is deferred. Legacy fixed-metric
`claimed=true` can coexist with an unavailable p-value; observed availability is
now separately visible. Do not interpret every legacy claim as a test executed.

## Verification of this stage

Passed locally on the changed source:

- Release compilation, no warnings/errors; **97/97 native tests**, including five
  new broad regression checks for serialization/legacy data, failures, seed draws,
  unchanged procedure decisions, aggregate reconstruction and worker-count replay.
- **108 Python unit tests** (86 previous + 22 new adversarial diagnostic fixtures),
  53 frozen rank-reference cases, independent numerical identities, source/CLI
  contracts, 73-file C# structural checks and notebook/payload consistency.
- Self-contained Linux CLI publication and actual calibration/analysis; full
  scientific CLI/Python parity and both exported-score checks.
- Baseline comparison: `results.json` and scientific manifest exactly equal;
  `results.csv` and `metric_availability.csv` byte-identical. Calibration states
  differ only in `CreatedUtc` and its dependent payload hash.
- Actual native diagnostic fixture export independently reconciled: 26 replication
  rows, 208 procedure rows, 312 metric rows, including two explicitly injected
  early/late failures and both real replay passes. This is a small technical
  diagnostic, not a full statistical baseline.
- End-to-end `BenchmarkReport.RunAndWrite` compact report also passed the
  independent checker (23 real replications); all twelve generated checksum
  entries verified against actual bytes. All diagnostic-missing counts were zero.
- Additional archived suites retain only the documented B4-03 failure: UI 17/18,
  connection 47/48. These failures are not reported as a green test run.

The existing CI now runs native diagnostic export and the independent checker
alongside its native/Python tests. Its YAML and embedded Python were parsed here;
the future GitHub run of this new workflow is not claimed as executed.

Reproduction commands (use .NET 8 and the existing Python validation dependencies):

```bash
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
python -m unittest discover -s validation -p 'test_*.py' -v
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release --no-build -- --export-benchmark-diagnostics /tmp/mvs-diagnostic-check
python validation/check_benchmark_diagnostics.py /tmp/mvs-diagnostic-check
# Also run the same checker on /tmp/mvs-diagnostic-check/pipeline/MVS_Benchmark_*
```

The checker verifies row completeness, identities, availability/decision semantics,
aggregate counts, chosen counts, legacy conditional rates and stability tau rows.
It does not reimplement native p-values, recompute every uncertainty/manifest field,
or establish a valid population error rate. The scope guard and source ZIP checks
are separate bookkeeping checks, not scientific certification. Final guard: PASS,
eight modified files, four added, no deleted or out-of-scope files. Packaging
retains all 250 original sources plus four additions; historical reports, original
assets, numerical fixtures, the supplied development skill, Core and CLI scientific
sources are unchanged except the deliberately rebuilt embedded CLI source payload.

## Deferred plan

R1-08 Huber native convergence validation is next. Then run and archive a complete
new MVS-BENCH-1.2.0 development baseline, retaining the diagnostics and all failed
replications. Holm precedes maxT and family-level automatic inference. A separately
frozen unseen MVS-BENCH-2.0 remains necessary for final 1.5 evaluation. Development
benchmarks already used for design are not independent confirmatory evidence.

This delivery is complete source, not a compiled application release.
