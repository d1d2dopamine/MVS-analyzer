# Round 22: local workflow and stdio MCP checkpoint

**Experimental Linux/cloud implementation. Windows MCP/workflow support is not
complete.** This cumulative source checkpoint adds a bounded application layer,
not a scientific release. Engine 1.6.2, all 12 active metrics, formula identity,
Bonferroni, Core statistical bytes and historical benchmark evidence are preserved.
Scientific project readiness remains NO-GO.

## Implemented scope

- Native machine schema v1 gains compatible execution/readiness metadata. Existing
  fields, status/exit semantics, human-help exception, force behavior and journal
  warnings are retained.
- `mvs-workflow` is a new application CLI over the existing native engine, with
  default exploratory and explicitly frozen local execution records.
- `mvs-mcp` is a thin official-SDK stdio adapter over the same validated service.
  It has five tools and one fixed capability resource, no HTTP listener/shell tool.
- Supported computation is summary `analyze` with an existing calibration only.
  Settings are native-calibration-owned; no automatic calibration/force/plugins.
- Local records bind exact snapshots, settings, native bundle/runtime identity,
  declared prior exposure and linked amendments. A preexisting calibration is
  explicitly acknowledged. Atomic no-replace records and run-ID reservation avoid
  silently replacing plans or repeating an uncertain run.
- Child isolation, cooperative cancellation/timeout, path boundaries, output/hash
  checks, explicit quotas and failure evidence apply equally to CLI and MCP.

See [workflow contract and commands](WORKFLOW_PROTOCOL.md) and
[MCP setup](LOCAL_MCP.md). Those documents define the supported trust/platform
boundary, diagnostic exit semantics, incomplete-state recovery and uncertain commit
reconciliation. Local hashes/timestamps do not prove prospective registration,
complete campaign capture, authenticity or campaign-wide multiplicity control.

## Acceptance and verification

The acceptance checklist was saved before implementation in
`validation/round22-acceptance.json`. The exact unmodified Round21 attachment was
verified by SHA-256 and CRC; 369 prior entries form the rollback baseline.
Baseline builds passed with zero warnings/errors, 144 native tests passed, and
canonical 150-repetition calibration/native/Python scientific parity passed.

Final checks: **144/144 native tests**, **490/490 Python tests with zero skips**,
and **53 frozen SciPy rank fixtures** passed. The Python total includes 28 legacy
API, 35 workflow, 14 MCP, 152 other tooling and 261 validation tests. The MCP tests
include actual native execution; synthetic process-control cases are separately
identified. Native builds had zero warnings/errors. Source/machine/notebook/payload
checks passed. A wheel was built and installed in an isolated environment; both
entrypoint help commands and an installed `mvs-workflow` native analysis passed,
with no broken package requirements. Exact results are recorded in
`validation/round22-results.json`; raw evidence is in its companion ZIP. Verification
covers native builds/tests, legacy Python and source regressions, official SDK wire
exchange, actual CLI/MCP scientific-output parity, native diagnostic exit 2,
immutable/deviation/idempotency cases, malformed metadata, containment and bounded
cancellation. Statistical parity uses the same native engine and is not independent
model validation. No full benchmark, remote CI, Windows/macOS runtime, device-agent
installation or external registrar was executed.

## Defects caught during implementation

Read-only independent review and targeted tests found and corrected these defects
in the new draft before delivery:

- wrong native state-check argument (`--in` instead of `--calibration`);
- malformed native identity/unsupported exit-code fail-open cases;
- basename-only manifest matching and insufficient stored request/result binding;
- cancellation arriving during final verification, process-group cleanup, final
  stderr bound and artifact reread validation;
- case-insensitive calibration metadata and nested duplicate-key ambiguity;
- retained staging copies on idempotent replay.

An actual MCP/native smoke exposed .NET diagnostic sockets conflicting with the
new managed-storage special-file guard. Child runtime diagnostics are disabled;
the guard was not weakened. The original failing test's temporary workspace was
automatically cleaned by unittest; only its recorded failure excerpt is retained,
not falsely described as a complete raw capture. Initial Python baseline invocation
omitted PYTHONPATH and failed imports; the corrected 28-test baseline passed.
The first combined test attempt also reached README link checking before this new
report file had been written; that intermediate missing-target failure is retained.
The final complete suite ran after the documentation existed and passed.
Both execution limitations and corrected checks are recorded honestly.

## Rollback and remaining gates

Rollback is the complete Round21 ZIP. New workflow data lives in a separate managed
workspace and does not migrate legacy artifacts/journals. An operator may continue
using the native CLI and old Python API without the optional MCP dependency.

Windows workflow needs native application-data redirection, portable locking and
no-replace semantics, process-tree cancellation and actual Windows validation.
Removing the platform guard is not an acceptable shortcut. Scientific development
still needs the owner’s claim/null decision and separately frozen independent
validation; this infrastructure does not improve the retained power/stability
NO-GO. No commits, pushes, publications or remote service were made.
