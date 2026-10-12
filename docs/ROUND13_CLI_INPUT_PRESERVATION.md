# Round 13: preserve CLI inputs and contain global-flag errors

## Scope and rollback

This is an operational repair following the authorized project audit. The round-12
source ZIP is the rollback point. It does not activate staged metrics or Holm,
change the twelve-metric family, numerical methods, seeds, calibration identity,
engine version or historical benchmark evidence. The full development benchmark
remains NO-GO. A fresh full benchmark is unnecessary for this input/output repair;
actual native regressions and CLI/Python scientific parity are the relevant gates.

## Reproduced defects before the repair

The audit used synthetic 48-row data (eight independent entities, six measurements
per entity), small 100-replication calibrations and two bounded MELSM calls. It did
not use private data or alter source. Failures were observed with the compiled
round-10 CLI, whose active source was unchanged through round 12.

1. **Input loss / P1.** Calibration accepted a dataset at
   `OUT/calibration.csv`, returned success, and replaced the dataset even without
   `--overwrite`. The actual Python API returned a completed Calibration too.
   Other reserved calibration targets could replace input with `--overwrite`;
   a job at `OUT/calibration_tracks.csv` was also overwritten. A parent directory
   symlink and an input-leaf symlink bypassed lexical path separation.
2. **Incomplete overwrite protection / P1.** A pre-existing calibration table
   was replaced without `--overwrite` when the state JSON did not exist. Only
   the state filename was used as an overwrite sentinel.
3. **Scientific-input loss / P1.** MELSM with `--overwrite` replaced an input
   named `melsm_parameters.csv` and an imported profile named `melsm_report.json`.
   The input manifest hash was computed after writes, so the collision recorded
   the replacement table's hash. The same write-before-hash pattern was found in
   variance source; an expensive variance reproduction was not needed or run.
4. **Partial generation / P2.** With a directory blocking
   `calibration_tracks.csv`, an overwrite run first replaced `calibration.csv`,
   then failed, leaving an older state that still passed state-check. The JSON
   error reported no output directory/artifacts despite the partial write.
5. **Process abort / P2.** Invalid global boolean values such as
   `--quiet=banana`, `--json=banana` and `--help=banana` were parsed outside the
   exception handler. Actual processes aborted rather than returning exit 1 and
   JSON. The Python API received generic EngineError instead of InputError.
6. **Help token mistaken for a value.** `--project -h --json` was intercepted as
   help. Flags were searched across values as well as option positions.

Output-leaf hardlinks and symlinks were separately tested before the repair:
atomic replacement preserved the outside input inode. They are not evidence of
input loss. The repair does not equate identical content with file identity.

## Implemented boundary

A shared CLI preflight checks reserved targets before computation and output
creation/writes. Calibration checks all four generated files for overwrite
permission. Variance, estimation and MELSM retain the existing nonempty-folder
policy. Dataset, explicit job (including directory-form `job.json`) and applicable
import-profile paths are protected from reserved-output collisions, even when
`--overwrite` is present. Existing parent aliases and input-leaf symlinks are
resolved. Output-leaf symlinks/reparse points are conservatively refused rather
than relied upon; ordinary distinct hardlinks and equal-content copies do not
cause false input-collision errors when overwrite is authorized.

Global flag parsing is handled through the normal exception boundary. Invalid
explicit JSON values request structured errors; a sole `--json=false` remains
human mode. Flags used as argument values are not standalone flags. Version/env
unknown-option policy and ordinary help rendering are not redesigned here.

## Limitations and deferred findings

- Preflight is not a filesystem transaction. Concurrent changes, permission loss,
  disk exhaustion and other unexpected mid-write failures can still leave a
  partial generation; complete partial-artifact reporting is a separate issue.
- Portable file attributes do not reliably identify every Unix FIFO/socket.
  Directory/device/reparse obstructions are covered where exposed by .NET; this
  is not a claim of comprehensive special-file or race protection.
- Alias checks resolve paths and symbolic links, not Linux bind-mount aliases or
  case-folded Linux filesystem identities. Windows/macOS comparisons are
  conservatively case-insensitive; platform-specific behavior was not executed
  on those systems.
- The explicit dataset/job/profile boundary does not inventory every implicit
  local-settings or plugin asset that a run may read.
- `help --json` still prints human usage. Unknown/duplicate options on version/env
  retain their prior policy. These gaps remain documented, not declared fixed.
- Python construction with a non-executable path/directory can still leak a raw
  PermissionError; that independent wrapper issue is deferred.
- Historical retired UI/Colab tests have a pre-existing stale HeadlessRun hash
  pin. This source repair changes that file legitimately, but no historical pin
  is weakened to make a check pass.

## Verification

Results are recorded below only after execution; future CI wiring is not evidence
of a local pass. The actual-CLI safety harness is added to CI after CLI publication.

### Development review and harness issues

Independent code review found an additional bypass in the initial repair:
scientific commands imported the trimmed `Require("--in")` value but guarded the
untrimmed `Value("--in")`. The final implementation passes the exact imported path
into preflight; separate padded-path regression cases cover variance and MELSM.
Review also strengthened raw symlink targets containing `..`, so traversal follows
actual resolved parents rather than prematurely normalizing link contents.

Two verification invocations failed before their intended checks: an unsupported
`dotnet run --ignore-failed-sources` argument reached the test executable, and the
new Python harness initially used unnamed partial callables incompatible with
verbose unittest descriptions. Neither was a passing native/safety run. Correct
DLL invocation and named test callables were used for the subsequent real runs;
initial logs/evidence were retained outside the source tree.

### Executed results

- .NET 8 Release CLI build: PASS, zero warnings/errors, using SDK 8.0.425 and
  runtime 8.0.31 on Linux. Rebuilt after the reviewed padded-input fix.
- Native Core suite: **119/119 PASS**, including six new parser groups. This is
  actual compiled execution, not a structural source check.
- Real CLI safety suite: **135/135 PASS**, 1,690 assertions, 138 direct CLI calls
  and six actual Python-to-CLI invocations, zero platform skips, 17.562 seconds.
  Every rejection fixture compares before/after bytes/link identities. Separate
  positive cases exercise normal calibration, overwrite, saved state, job/profile
  loading, safe distinct hardlinks/copies and `-h` project values. Scientific
  preflight probes use an intentionally invalid late numeric option as a fuse;
  they must report the intended preflight error and do not run model/bootstrap
  computations. Counts and actual managed assembly hashes are preserved in
  `validation/cli-safety-round13-results.json`.
- Existing Python suite: **281/281 PASS** (17 backup, 6 source, 40 evidence
  verifier, 34 runner, 4 API wrapper, 21 round-2, 159 validation-tool tests).
- Independent rank reference: **53 frozen cases PASS** against SciPy; independent
  Python mathematical identities also pass. These are not additional native
  executions of the rank fixtures.
- Actual canonical calibration/analysis output checks and full CLI/Python
  scientific parity: PASS. Existing pre-repair calibration is accepted; results
  JSON/CSV, availability CSV and copied state bytes are exactly unchanged from
  round 10, and scientific manifest fields match exactly.
- Source/identity, CLI contract, generated notebooks, embedded source payload and
  limited C# structural checks: PASS. The latter is not compilation.
- Final scoped change guard and complete ZIP preservation/integrity checks: PASS.

CLI managed assembly SHA-256:
`0bf1c27a680b7d59af423492b00ff3a910242808c1f8ec54e3015a47372af063`.
Core assembly SHA-256:
`53d8d4c0680417a47c98c45b082da774c4e027720d34f2068446e929d4ca807e`.
The Core binary changes because shared argument parsing is compiled there;
production numerical source remains unchanged.

Reproduce the new real-CLI checks after building:

```sh
python tools/test_cli_safety.py --cli MvsAnalyzer.Cli/bin/Release/net8.0/mvs --artifacts artifacts/cli-safety
```

The harness creates a fresh evidence child and never replaces an earlier run.
The delivered ZIP is complete source, not a compiled release. Windows/macOS runtime
checks, live Colab/desktop interaction, external CI and a new full benchmark were
not run for this stage.
