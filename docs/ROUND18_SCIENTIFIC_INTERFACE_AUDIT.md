# Round 18: existing scientific interface audit

## Acceptance boundary

This final bounded stage audits the existing variance, known-truth estimation and
experimental MELSM workflows through the actual CLI and Python wrapper. It checks
scientific-field, export, diagnostic and error consistency. Both paths call the
same native engine; agreement is not an independent numerical model validation.

The pre-edit rollback point is the round-17 complete source ZIP. The planned patch
is confined to diagnostic protocol/runner/tests/evidence, documentation and any
actually reproduced narrow Python input-error classification defect. Native
statistical code, defaults, method identity and historical evidence stay unchanged.

The protocol is frozen before real execution, with small legal simulation budgets,
fixed seeds and input hashes, serial two-CPU workloads and explicit resource/time
limits. Failed fits and exit-2 diagnostics are retained. A reduced-budget case is
not claimed as execution of the larger canonical contract fixture.

## Executed results

All frozen actual workloads completed. **16/16 CLI/Python pairs passed**: five
scientific fixtures and eleven invalid-input/preflight pairs. A separate strict
`ScientificDiagnostic` case preserved its typed result and accessible artifacts.
Two pre-fix invocations retain the original Python classification failure. These
are 35 workload invocations; wrapper version handshakes are additional calls.

The scientific fixtures are one variance analysis, a normal-mean estimation study,
random-scale MELSM on a frozen eight-subject subset, analytic no-random-scale MELSM
on the full example, and a deliberately constant variance fixture. Both MELSM
fixtures returned their experimental convergence status; that is not external
validation. The constant fixture retained exit 2, null scientific values and all
failed/reference denominators, rather than being removed from the comparison.

Complete reports, scalar CSV exports and scientific manifest fields are compared.
Only manifest `created`, `runId` and file-checksum records are excluded from
cross-run scientific equality; each run's actual file sizes/hashes and paths are
validated separately. Integer counts, identities, status, order and null semantics
are exact; finite floating-point fields use the existing contract tolerances.
Estimation bias/MSE/RMSE/coverage/accounting is also recomputed from exported draws.
This is a consistency check on the saved results, not an independent simulation
or validation of their data-generating assumptions.

### Reproduced Python error repair

Before the fix, actual `variance --min-measurements 1` returned native
`ArgumentOutOfRangeException` with exit 1, while Python raised `EngineError`.
The machine protocol serializes the concrete exception name; Python's known
input-error list included `ArgumentException` but not this subtype.

The narrow repair recognizes `ArgumentOutOfRangeException` as `InputError`, adds
a targeted regression, and preserves the native payload/exit and other exception
classes. The actual post-fix case is included in the frozen negative pairs. The
original wrapper bytes and pre-fix process evidence are retained. No native method,
option validation, error schema or statistical calculation is changed.

### Resource instrumentation limitation and repair

The actual audit used serial children with two-CPU launch affinity and explicit
timeouts. However, this execution sandbox does not expose
`/proc/PID/task/PID/children`. The first audit runner's process-tree sampler caught
that missing-file condition and returned no samples, so **tree RSS watchdog and
observed-affinity verification are unavailable for these scientific runs**.
Kernel `wait4` accounting was retained; it is not simultaneous process-tree RSS.
Scientific parity success must not be read as a successful resource-monitor check.

The exact executed harness is preserved separately before correcting the sampler
for future use. A bounded non-model child check and targeted tests verify the
correction; successful scientific workloads are not repeated merely to replace
this limitation with a green resource record. Round 17's separately executed
single-process resource profile and cancellation evidence remain unchanged.

### Verification and retained observations

- **440/440 current Python tests PASS**: 17 backup, six source, 40 evidence-verifier,
  34 checkpoint-runner, 34 release-bundle, 27 API, 21 round-2 and 261 validation-tool
  tests. The latter include **46 new interface/comparator/control tests**. The
  narrow wrapper mapping adds one API regression.
- **53 frozen SciPy rank-reference cases PASS**; these are independent Python
  reference checks, not a new native build.
- Actual canonical summary-analysis CLI/Python scientific parity also PASS after
  the wrapper edit, using the existing saved calibration and two fresh analyses.
  Output checks passed for eight JSON documents, three states and two manifests;
  machine contract, source identities/links and notebook/payload checks PASS.
- The corrected monitor's separate non-model parent/child smoke observed both
  processes across 12 samples, correct affinity and 14,960 KiB peak sampled sum.
  Three focused pure regressions cover missing task/children and process races.
- All native source/project bytes remain unchanged from the tested round-14 build.
  No redundant native suite, full benchmark, remote CI, release or external model
  comparison was run here.

The frozen audit used **35 workload invocations plus 18 version handshakes**,
53 native invocations in total. These counts exclude the later two summary-analysis
regression invocations and its Python constructor handshake. Forty-four scientific
output artifacts were verified in the frozen audit.

The normal-mean estimation smoke observed interval coverages **0.81, 0.82, 0.89**
for arithmetic mean, 20% trimmed entity mean and median of entity medians. These
are retained results at eight entities, six measurements, 100 replications and
99 bootstrap draws, not a claim that coverage is calibrated. Small-sample coverage
and model correctness still need their separately specified validation; parity
does not turn an unfavorable observation into scientific success.

The nested evidence ZIP has **308 entries / 307,010 bytes**. CRC and every archived
entry were independently compared with retained originals. Its SHA-256 is
`e0ca62bdc3b686dde2f9810b6a56d17230499e74d55ec76bf822df38713635a3`.
The compact summary SHA-256 is
`0da465109f942577c34a725899b0afd9004ec1454a53457e5de00f72afdde96c`;
the protocol SHA-256 is
`f9d9d1bd0b62273800d61623fc7c42a1c76fa5d1e265b17f29fcec2b16f3e0f5`.
The exact originally executed harness is preserved and matches the frozen hash;
the later corrected harness is separately identified. Final task scope and source
ZIP preservation checks are separate from runtime/scientific validation.

### Additional environment-specific journal observation

The later canonical summary regression set `XDG_DATA_HOME` to a fresh directory
that did not yet exist. In this environment .NET returned an empty
`LocalApplicationData` path; the existing journal code consequently appended two
new synthetic-run records to `MVS_Analyzer/run_journal.jsonl` relative to the task
working directory. Both records were preserved with the regression artifacts
outside source, and the source guard then passed. No pre-existing source or user
data was removed. This is documented as a journal-location fallback limitation,
not silently repaired by expanding this interface-only patch into native storage
changes. Controlled runners should create their isolated data directory before
native execution; robust application fallback remains an operational backlog item.

## Final readiness

See [current readiness and next decision](PROJECT_READINESS_HANDOFF.md) for completed
work, preserved development NO-GO, the substantive scientific choice, recommendation,
remaining validation/operational boundaries and the stopping criterion. This stage
is not automatic family-level activation or a scientific 1.5.0 release.
