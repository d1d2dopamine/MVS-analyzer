# CLI machine protocol

MVS CLI commands accept the additive global option `--json`. In this mode **stdout contains exactly one JSON object** using schema `mvs-cli-result/v1`. Human progress and warnings are written to stderr; `--quiet` suppresses progress.

The process exit code remains authoritative and is repeated in `exitCode`:

| Exit | `status` | Meaning |
| --- | --- | --- |
| `0` | `completed` | Work completed. |
| `1` | `error` | Input/runtime failure or cancellation. |
| `2` | `diagnostic` | Artifacts were saved, but a scientific/numerical diagnostic or benchmark threshold requires inspection. |

Every response identifies `command`, application and engine versions, formula identity, output directory, run ID when available, manifest path, generated top-level artifacts, diagnostics and a structured error object on failure. Artifact entries include path, size and SHA-256.

`mvs version --json` also retains the existing Colab identity fields (`appVersion`, `stateSchema`, `cliProtocol`, `transport`) so notebook compatibility checks do not depend on human-readable text.

Example shape:

```json
{
  "schemaVersion": "mvs-cli-result/v1",
  "status": "completed",
  "command": "analyze",
  "exitCode": 0,
  "runId": "2026-09-18_103000",
  "outputDirectory": "/work/analysis/MVS_Run_...",
  "applicationVersion": "1.4.0",
  "engineVersion": "1.6.0",
  "manifestPath": "/work/analysis/MVS_Run_.../run_manifest.json",
  "artifacts": [],
  "diagnostics": [],
  "error": null
}
```

Fields may be added compatibly inside schema v1. A removal, semantic change, or incompatible type change requires a new machine schema. Scripts should reject unknown schema identifiers instead of guessing.

## Input-error boundary (round 13)

Malformed global `--json`, `--quiet` and help boolean values are caught by the
command error handler. An explicit invalid `--json=...` produces one v1 error
object and exit 1; a sole valid `--json=false` retains human output. Reserved
output/input collisions and predictable target obstructions are input errors,
not successful calibration or scientific diagnostics. They are rejected before
output creation/writes and report no newly generated artifacts.

The existing human help path remains an exception to the machine-output
promise (`help --json` prints usage). This known gap is recorded rather than
represented as a passing structured-help check. Unexpected failures after writes
begin can still leave partial artifacts; preflight is not transactional output.

## Completed analysis with a provenance warning (round 20)

If analysis artifacts were saved but local journal append failed, `diagnostics`
contains level `warning`, code `journal_write_failed`. The generic message omits
local journal paths and exception details. Existing stderr detail remains local
troubleshooting output. Status remains `completed`, exit code 0 and error null;
other diagnostics and generated artifacts are preserved. Consumers must inspect
diagnostics even on successful exit. This is runtime response metadata, not a new
manifest field. See [round 20](ROUND20_JOURNAL_WARNING.md).

## Additive execution/readiness metadata (round 22)

The schema remains `mvs-cli-result/v1`; all earlier fields, types and exit/status
meanings remain. New `execution.completed` is true for exits 0 and 2; its
`outcome` distinguishes `completed`, `completed_with_diagnostic` and `failed`.
New `scientificReadiness` explicitly describes **project release readiness**,
with retained development `no_go`, not a new per-run hypothesis verdict.
A successful version command or analysis is not scientific certification.
The existing human `help --json` exception is unchanged.

The optional `mvs-workflow-result/v1` envelope is a separate application-layer
contract, shared by `mvs-workflow` and local MCP; it does not replace native v1.
See [scope, exit semantics and examples](WORKFLOW_PROTOCOL.md).

### Failed output emission (Round33 additive metadata)

For `calibrate`, `analyze`, `variance`, `estimation` and `melsm`, a failure after
output emission begins retains exit 1/error and may include `partialOutput`.
Its `status` is `incomplete` and `scope` is
`current_invocation_successful_writes`. `outputDirectory` locates the incomplete
output; `artifacts` lists only successfully observed current writes that still
verify. `attemptedPath` identifies an uncertain attempted target, and
`unverifiedPaths` lists writes whose metadata could not be verified. Neither is
a successful artifact. Untouched old files/manifests are excluded. An older
backend may omit this metadata. Successful/diagnostic envelopes are unchanged.
See [the complete boundary and limits](ROUND33_PARTIAL_OUTPUT_REPORTING.md).

Round34 extends this same additive failure evidence to `resume` for calibration,
analysis, variance, estimation and MELSM checkpoints. Observation starts only
at output emission; failures before that boundary do not acquire partial-output
metadata. Benchmark resume remains outside this observer boundary. See
[resume scope and checkpoint guarantees](ROUND34_RESUME_OUTPUT_REPORTING.md).
