# Documentation

## Windows acceptance repair

[Round26: cleanup race and independent ACL probe](ROUND26_WINDOWS_GATE_REPAIR.md)
addresses the newly supplied failed Windows CI logs.
[Краткий отчёт и повторная проверка](ROUND26_WINDOWS_GATE_REPAIR_RU.md).
Windows acceptance remains pending an actual rerun.

## Input provenance and local import state

Round 25 binds active headless CLI and real-data benchmark imports to the exact
raw bytes consumed, with per-import metadata rather than shared `Last*` state.
See [engineering report and residual boundaries](ROUND25_IMPORT_BOUNDARY.md),
[краткий отчёт](ROUND25_IMPORT_BOUNDARY_RU.md), and the
[frozen comparison protocol](ROUND25_COMPARISON_PROTOCOL.md).


## Experimental local workflow checkpoint

Round 23 adds an experimental Windows local-NTFS backend to the Round 22
exploratory/frozen workflow and local stdio MCP. **Windows runtime verification
requires the owner-run manual CI gate; no Windows run is claimed here.** Existing native
commands remain compatible, and scientific NO-GO is retained. See
[workflow setup and contract](WORKFLOW_PROTOCOL.md),
[local MCP setup](LOCAL_MCP.md), and
[Windows setup, checks and remaining gate](ROUND23_WINDOWS_MCP.md).

Round 21 repairs reproduced cross-session journal chain races and unlocked reads.
The bounded concurrency evidence, locking compatibility limits and retained
scientific NO-GO are documented in [round 21](ROUND21_JOURNAL_CONCURRENCY.md)
and [кратком отчёте](ROUND21_JOURNAL_CONCURRENCY_RU.md).

- [Structured journal warning](ROUND20_JOURNAL_WARNING.md): privacy-minimal provenance warning through CLI/Python.
- [Этап 20: краткий отчёт](ROUND20_JOURNAL_WARNING_RU.md).

- [Journal path repair](ROUND19_JOURNAL_PATH_REPAIR.md): reproduced Linux fallback, preserved legacy journals and executed regressions.
- [Этап 19: краткий отчёт](ROUND19_JOURNAL_PATH_REPAIR_RU.md).

- [Current readiness and next decision](PROJECT_READINESS_HANDOFF.md): completed work, scientific NO-GO, recommendation and stopping boundary.
- [Existing scientific interface audit](ROUND18_SCIENTIFIC_INTERFACE_AUDIT.md): actual variance/estimation/MELSM wrapper and export consistency.

- [CLI resource and cancellation audit](ROUND17_CLI_RESOURCE_AUDIT.md): bounded Linux observations and remaining readiness decisions.

- [Release workflow audit](ROUND16_RELEASE_WORKFLOW_AUDIT.md): complete local documentation bundles and aligned future verification gates.
- [Current project readiness audit](ROUND15_PROJECT_READINESS_AUDIT.md): verified checkpoints, preserved NO-GO, operational limits and scientific decision gates.

- [Data format](DATA_FORMAT.md): columns, grouping and example inputs.
- [Methods](METHODS.md): metrics, simulation assumptions and inference limits.
- [Reports](OUTPUTS.md): exported tables, figures and saved calibration.
- [CLI contract](CLI_CONTRACT.md): frozen commands, exit codes, artifacts and parity rules.
- [CLI machine protocol](CLI_MACHINE_PROTOCOL.md): versioned JSON stdout for automation.
- [Python API](PYTHON_API.md): path-based Python wrapper around the same engine.
- [Interface compatibility](COMPATIBILITY.md): version and schema compatibility matrix.
- [Colab](REMOTE.md): cloud setup, reuse and file exchange.
- [Plugins](PLUGINS.md): declarative import profiles and templates.
- [Integrity checks](AUDIT.md): what output verification can and cannot establish.
- [Validation and limitations](VALIDATION.md): how to interpret the methods responsibly.
- [Benchmark history](BENCHMARK_HISTORY.md): immutable cross-version benchmark record.
- [MVS 1.5.0 plan](V1_5_PLAN.md): CLI/Python-first redesign and validation sequence.
- [Calibration recommendations](CALIBRATION_RECOMMENDATIONS.md): family-aware, uncertainty-aware 1.5 diagnostic candidate sets.
- [Metric registry](METRIC_REGISTRY.md): 1.5 metric families, staged robust metrics, and applicability rules.
- [Migration](MIGRATION.md): compatibility with older saved results.
