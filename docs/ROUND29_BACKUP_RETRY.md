# Round29: preserve restore selection after failed initial publication

## Verified defect

A valid `BackupSession.Restore(document)` scope followed by `Begin(request)` could
lose its pending restore selection when the initial backup write failed. The
pending slot was cleared before `Flush(true)` succeeded. Retrying inside the same
restore scope then created a fresh document, with a new ID and no saved units.
Original archive files and the caller's document units were not deleted.

A second connected consequence was mutation of the restored environment history
before publication. Simply retaining pending would make a subsequent retry appear
to be in the same environment, potentially skipping the optimizer's required
reevaluation of saved simplex objective values. SavedUtc also changed on failure.

The counterexample uses only owned temporary data: a regular file obstructs the
configured backup directory; Begin throws IOException; the destination is repaired
and the SAME live restore scope retries. Baseline results: pending=false,
WasRestored=false, retained unit absent, original identity not preserved.

## Narrow repair

`Infrastructure/PortableBackup.cs` consumes pending only after the initial forced
flush succeeds. It remembers the original environment-list length and SavedUtc;
on exception it clears active as before and restores those mutable metadata fields,
then rethrows the original exception. Saved units, request, schema, serialization,
scientific identities and successful-call write order are unchanged. No automatic
retry or fallback-to-disabled behavior is added. The caller still owns retry choice.

A late failure can happen after a current `.mvsbackup` is installed but before the
collection ZIP is published. Tests deliberately obstruct `MVS_Backups.zip` with an
owned empty directory. The installed checkpoint remains readable with the original
identity/units; pending and in-memory metadata remain retriable. This is **not a
transactional disk rollback guarantee**. Files already published are preserved.

## Evidence and tests

Six targeted checks: repeated failed publication/identity/units, foreign-environment
optimizer reevaluation, late collection publication failure, restore-scope cleanup,
fresh-operation failure cleanup, request mismatch/disabled/nested behavior.
On unchanged Round28: three fail, three pass. On repaired Round29: all six pass.

The optimizer regression restores stale values[-999,-998] at points[1,2], uses the
quadratic objective and zero additional iterations, and requires exactly two fresh
evaluations and result value1. It proves the environment-transition flag survives
failure/retry instead of merely checking a metadata string.

Successful fresh/cached/restore paths were compared between separate baseline and
fixed builds: complete serialized result/request/unit documents match exactly after
excluding only top-level Id and SavedUtc. Environment history, RequestHash, schema,
formula and protocol fields remain in the comparison. No speed improvement is
claimed for this failure-path repair.

Initial targeted test compilation failed because the test referred to the nested
SimplexCheckpoint type without its NumericalMethods qualifier. This test-only
compile error is retained; it was corrected before old/fixed execution. The original
independent counterexample had already run successfully and exposed the defect.

## Scope and rollback

Only PortableBackup's initial-session publication failure path and additive native
regressions change. Core numerical methods, RNG and checkpoint keys remain intact.
Existing Dispose exception/retry semantics are unchanged and remain a separate
known design limitation. No statistics, library replacement or per-run recording
interface is included. That architectural seam is planned separately.

The frozen acceptance plan is `validation/round29-retry-plan.json`. Evidence/logs
and reproducer sources are in `validation/round29-evidence.zip`. Restore a source
backup of Round28 for rollback; no archive migration is required. This cumulative
25–29 PATCH preserves README files. Scientific NO-GO and the outstanding actual
Windows acceptance of Round26 remain unchanged.

## Explicit residual: restart after environment transition

This fix is limited to retry inside the SAME live Restore scope. A checkpoint
already published to disk can contain the current environment marker before old
cached simplex values have been reevaluated. After process death and reload,
EnvironmentChanged can therefore be false for those old values. This pre-existing
restart/per-unit provenance risk is not repaired by in-memory metadata rollback.
A separate deterministic reproduction and reviewed correction take priority over
the recording-interface extraction. Do not claim complete crash-safe numerical
restore from this patch.

Independent fresh-scope reproduction confirmed the residual: after late failure,
reload returned EnvironmentChanged=false, objective evaluations0 and value−999
from intentionally stale cached values instead of quadratic value1. Round29 alone
is not recommended as the final repair for cross-environment recovery. Round30
will address this before the next combined delivery.

Final checks: full native run163/163 passed; the added late-publication check
passed in the final six-check targeted run (164 unique native checks total).
Python536 discovered:522 passed,14 Windows-only skipped. CLI Release build
0warnings/0errors; all102 Python-wrapper checks were repeated with the newly
built CLI (88pass/14skip), including actual Linux native MCP.
