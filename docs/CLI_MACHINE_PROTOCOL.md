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
