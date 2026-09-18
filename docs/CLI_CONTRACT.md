# CLI contract

This document records the public CLI compatibility boundary. Human-readable text is intentionally not frozen line-for-line. Automation uses the additive machine protocol documented in [CLI_MACHINE_PROTOCOL.md](CLI_MACHINE_PROTOCOL.md).

The machine-readable source of truth is `validation/cli-contract-v1.json`. CI checks it with `tools/check_cli_contract.py`.

## What is frozen

The current public commands are `calibrate`, `analyze` (`analyse` alias), `variance`, `estimation`, `melsm`, `benchmark`, `resume`, `state-check`, `version` and `env`.

Exit codes have these meanings:

| Code | Meaning |
| --- | --- |
| `0` | The requested work completed. |
| `1` | Input/runtime failure or cancellation. |
| `2` | The command completed far enough to save/report a scientific or numerical diagnostic that did not satisfy its success criterion. |

A future JSON mode must preserve these process-level meanings unless a new protocol version explicitly changes them.

## Scientific equality versus operational metadata

Regression checks do not compare an output directory byte for byte. A completed run contains both scientific state and details that are expected to change between executions.

Exact fields include schema identifiers, application/engine/formula identifiers within a release, dataset and settings hashes, seeds, repetition counts, scenario/track names, metric registry, categorical decisions, failure counts and boolean flags.

Floating-point scientific results are compared numerically with an explicit tolerance. This includes p-values, effect estimates and intervals, calibrated FPR/power, MDE values, variance components, model parameters, estimation-study performance and benchmark rates. The contract stores the default tolerances used when a later parity harness is added.

Operational fields are excluded from scientific equality. They include timestamps, timestamp-derived run IDs, absolute output paths, generated folder names, wall-clock duration and progress text. Environment fingerprints are compared exactly only when the runs claim to use the same arithmetic environment; cross-environment replay is tolerance-based.

## Canonical cases

The contract pins fixed inputs and seeds for the first parity suite:

| Case | Input | Purpose |
| --- | --- | --- |
| `calibrate-demo-three-groups` | `examples/demo_three_groups.csv` | Frozen calibration identity and artifact set. |
| `analyze-demo-three-groups` | same input plus the calibration above | Frozen analysis identity and artifact set. |
| `variance-demo` | `examples/variance_demo.csv` | Variance-component command surface and diagnostics. |
| `estimation-mean-normal` | synthetic | Known-truth estimation command surface. |
| `melsm-repeated-conditions` | `examples/repeated_conditions.csv` | Experimental repeated-measures model surface. |

The first two cases already run in normal Linux CI. `tools/check_cli_contract.py --artifacts artifacts` verifies their identity fields and required output files after the existing smoke run. The remaining cases define the next parity fixtures without pretending that numerical baselines were generated in an environment where the .NET executable was not run.

## Stream behavior

Human mode writes progress and summaries to stdout and errors/warnings to stderr. With `--json`, stdout contains exactly one `mvs-cli-result/v1` object. Human progress and warnings are routed to stderr; `--quiet` suppresses progress. Exit-code meanings are unchanged. Python and shell automation must consume the JSON object rather than scrape prose.

## Change rule

If a change intentionally modifies a command, artifact, schema or exit-code meaning, update the implementation and `validation/cli-contract-v1.json` in the same change. A statistical-method change also needs the existing method-hash and scientific regression process; changing the CLI contract alone does not authorize a numerical change.
