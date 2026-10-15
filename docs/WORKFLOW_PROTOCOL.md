# Local workflow protocol v1 (Linux / experimental Windows)

This optional application layer supports **summary `analyze` with an existing
calibration**, on Linux and experimental Windows 10+ x64 local NTFS.
Windows implementation is present; actual Windows runtime verification remains
gated on the [owner-run checks](ROUND23_WINDOWS_MCP.md). Existing native `mvs` commands and the
ordinary Python `Engine` API retain their previous platform scope and semantics.
No production statistical method, formula, threshold or historical result changes.

`mvs-workflow` and `mvs-mcp` call the same `WorkflowService`; it invokes the native
CLI as an isolated child, never as shared in-process static state. There is no
second statistical implementation. CLI inputs are one strict JSON object on stdin;
outputs are one `mvs-workflow-result/v1` object. Argument parsing/help remain normal
human CLI usage; correctly configured operation calls return structured results.

## Installation and first run

From the source root, with .NET 8 and Python 3.10+:

```bash
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -o publish/cli
python -m venv .venv
. .venv/bin/activate
python -m pip install ./python
mkdir -p /absolute/mvs-inputs
# Put your CSV and its existing calibration_state.json in that input directory.
# The work root must be separate, initially empty, and on a local filesystem.
printf '%s\n' '{"run_id":"explore-001","data":"study.csv","calibration":"calibration_state.json"}' |
  mvs-workflow --engine "$PWD/publish/cli/mvs" \
    --read-root /absolute/mvs-inputs --work-root /absolute/mvs-work run_analysis
```

The ordinary native `mvs calibrate` command still creates calibrations. This layer
does not automatically recalibrate or accept arbitrary native options. A calibrated
summary analysis fixes seed, alpha, processing, effects and other settings in the
calibration. Recalibrate explicitly through the existing interface to change them.
The native engine rejects a calibration from different input bytes; this layer
never adds `--force`. Native exploratory force remains available only outside this
bounded workflow, with its existing warnings.

## Operations and request fields

All unknown fields are rejected. Input filenames are relative to `--read-root`;
absolute/traversing/symlink/special-file paths are rejected. Calibration is a file,
not a directory. IDs are 1–64 ASCII letters/digits/hyphens/underscores.

- `register_protocol`: `protocol_id`, `data`, `calibration`, `question` (1–2,000
  characters), `prior_exposure`; optional `parent_protocol_id` and boolean
  `allow_group_scoped_ids` (default false).
- `get_protocol`: `protocol_id`.
- `run_analysis`: `run_id`, `data`, `calibration`; optional `mode` (default
  `exploratory`, or `frozen`), `protocol_id` (required only for frozen), and
  `allow_group_scoped_ids` (default false).
- `get_run`: `run_id`.
- `read_artifact`: `run_id`, `name`; only a recorded JSON/CSV/TXT artifact up to
  64 KiB, with verified hashes. No arbitrary file-read endpoint exists.

`prior_exposure` must be one of `unknown`, `previously_inspected`, or
`not_inspected_declared`. It is a caller declaration about prior inspection, not
an observation made by the software. A calibration already exists before freezing
and can have used the same dataset; every protocol explicitly records
`calibrationPreexisted: true`. Never call this a prospective preregistration or
confirmatory certification merely because a local timestamp was written.

Example local freeze and execution, using the same configured CLI roots:

```json
{"protocol_id":"plan-001","data":"study.csv","calibration":"calibration_state.json","question":"Inspect the existing entity-summary comparison","prior_exposure":"previously_inspected"}
```

Pass that object to `register_protocol`. Then pass this object to `run_analysis`:

```json
{"run_id":"frozen-001","data":"study.csv","calibration":"calibration_state.json","mode":"frozen","protocol_id":"plan-001"}
```

An amendment uses a new protocol ID plus `parent_protocol_id`. It never replaces
the parent. Parent content hashes are checked, and cycles/overlong chains fail.
A changed dataset, calibration byte, declared independence flag, native bundle or
runtime environment fingerprint cannot silently be reported as the same frozen
execution. A mismatch fails before native analysis. There is no automatic deviation
waiver or automatic amendment; explicitly choose a new exploratory run or register
a new record after deciding what the change means.

## Record and result identity

A local `mvs-local-protocol/v1` record has canonical JSON content and its SHA-256.
Content records the ID/time, question, exposure declaration, preexisting calibration,
current exploratory claim scope, raw input/calibration hashes, explicit calibration
settings, native engine/formula/state identity, runtime fingerprint, executable/DLL/
JSON/shared-library bundle digest, independence flag and optional parent reference.
Canonical encoding sorts keys, omits insignificant separators, preserves Unicode,
and forbids nonfinite numbers; duplicate keys and case-ambiguous calibration
metadata (including nested rows/processing) are rejected.

The engine and runtime are operator-configured trusted programs, not authenticated
by this local hash. Runtime fingerprinting is a reproducibility check, not a proof
of an untampered OS. Local clock time is not a trusted timestamp.

Results separate:

- `execution.status`: completed, error, cancelled, or incomplete;
- `execution.nativeExitCode`: the native code when a completed native result is
  accepted; exit 2 has `outcome: completed_with_diagnostic`, never unqualified success;
- `scientificReadiness`: project release readiness remains `no_go`, with the
  MVS-BENCH-1.2.0 development basis and no independent confirmatory certification;
- `data.native`: preserved native scientific metadata/diagnostics/artifact hashes,
  with managed output paths made relative to the workspace;
- `error`: a stable error code/message for rejected operations.

Workflow CLI exits: 0 completed native-0/read/registration; 2 completed native
scientific diagnostic; 1 error/cancelled; 3 incomplete/uncertain run. The retained
project NO-GO is not converted into an execution failure for every successful read.
Consumers must inspect readiness, outcome and native diagnostics. A legacy
`journal_write_failed` warning remains a completed native analysis with its warning;
it does not imply the entire campaign has been captured.

## Input snapshots and persistence

Data/calibration are copied into private managed snapshots (Linux files 0600,
run folders 0700; Windows protected current-user/SYSTEM directory ACLs). Native state-check verifies the snapshot without normalization; analysis
receives those snapshot paths only. Hashes are checked after execution. Source data
is never rewritten. Snapshots use the stable internal filename `input.csv`, which
can change a descriptive export filename compared with the original native call;
input byte hashes and statistical results remain the substantive identity.

On Linux, records commit by a no-replace atomic link from a fully written
temporary file; file/directory fsync is attempted. On Windows a flushed same-folder
temporary file is published by MoveFileExW with WRITE_THROUGH, without REPLACE_EXISTING
or COPY_ALLOWED. No power-loss durability guarantee is claimed. This requires the tested local filesystem
semantics. A failure after link but before directory fsync can mean an uncertain
commit: inspect `get_protocol` or `get_run`; do not blindly retry with replacement.
This is not a transaction across native output artifacts and the local receipt.

Run IDs reserve one execution. Same ID and same input/request returns the verified
stored result; different bytes/settings conflict. Replays do not create additional
staging copies or relaunch native computation. A reserved directory without a
terminal receipt reports `in_progress_or_interrupted` and never reruns automatically.
If the controller is forcibly killed, partial native work may remain or still be
running; absence of a receipt is not proof the native operation never happened.
Inspect the local processes/evidence before deliberately issuing a new run ID.

## Resource, platform and trust limits

- One native computation per workspace, including cross-process clients. A second
  concurrent computation receives `busy`; retry/read deliberately, not with a new
  ID intended to bypass it. Coordination is local, not campaign-wide.
- Default native timeout 120 seconds, configurable 1–3,600. Cancellation/timeout
  sends SIGINT to the owned process group, then SIGKILL if necessary, and reaps the
  child on Linux. On Windows cancellation forcibly terminates the owned Job Object
  tree and retains partial evidence; it is not graceful SIGINT cancellation. Job
  assignment occurs at process creation and kill-on-close protects controller death.
  Actual Windows cleanup behaviour remains a runtime acceptance gate. Linux
  forcibly killed controllers remain outside the cooperative cleanup guarantee.
- Request 32 KiB; input CSV 100 MiB; calibration 16 MiB; each artifact 32 MiB;
  child stdout/stderr 2 MiB each; workspace 512 MiB/10,000 files. Quotas are checked
  at capture and while native work runs. Sampling can overshoot briefly; this is
  not an OS memory/filesystem sandbox. Native worker hint is two processors.
- Needed failure evidence and staging snapshots are retained. Quota exhaustion
  fails closed. Archive finished work explicitly or choose a new empty work root;
  this version has no automatic evidence deletion/garbage collector.
- Native application-data/plugins/journal, backup settings, temporary
  paths and cwd are redirected inside the workspace. Backups are explicitly
  disabled for these new runs; originals remain untouched. Runtime diagnostics
  sockets are disabled for the child. OS/runtime IPC is not a filesystem sandbox.
- Installed import profiles are unsupported: profiles and their external assets
  are not silently inherited. The process environment is deliberately restricted.
- Trusted host/operator and local filesystem only. Preflight symlink checks and
  hashes do not stop a malicious same-user owner from racing directories, changing
  the program, rewriting every record, or omitting runs. This is not proof against
  selective reporting, full campaign accounting, authenticity or campaign-level
  multiplicity control. External registration/anchoring is a future design.
- Windows 10+ x64 is experimental, requires local fixed NTFS, short paths, no
  reparse points/UNC/ADS/device aliases, and a new nonexistent workspace path.
  Existing ordinary directories with inherited broad ACLs are rejected, never
  silently permission-repaired. Actual Windows testing is pending. macOS workflow
  remains unsupported; existing native/Python interfaces keep their prior scope.

The scientific claim/null specification and independent unseen validation remain
separate open gates. See [current readiness](PROJECT_READINESS_HANDOFF.md).
