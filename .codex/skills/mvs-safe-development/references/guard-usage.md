# Change guard usage

The guard is an advisory filesystem/Git comparison, not an execution sandbox.
Require Python 3.10+; Git is optional for source ZIPs and required for Git checkouts.
It does not execute repository scripts or build/install anything.

## Commands

- inspect: identify the MVS source root, read live version metadata and report
  captured/excluded paths. Write nothing.
- snapshot: before editing, capture file SHA-256 values, kinds, modes, Git HEAD
  and semantic index entries plus the exact authorized paths. Write one new JSON
  file outside the project; refuse to overwrite it.
- verify: compare the current tree with the original file hashes and recorded
  scope. Report every changed/add/delete path and any violation. Write nothing.
- extend: before editing an additionally justified path, preserve the original
  hashes and scope in a new snapshot with an amendment link. Refuse when current
  changes already violate the previous scope. Keep all snapshots.

## Ordinary edit

```bash
python /skill/scripts/change_guard.py snapshot --root /repo/MVS --out /work/task-before.json --task "Correct the requested checker" --allow validation/analyze_results.py --allow validation/test_diagnostics.py --allow validation/README.md
python /skill/scripts/change_guard.py verify --root /repo/MVS --baseline /work/task-before.json
```

--allow permits additions/modifications at exactly those paths, not deletions.
--allow-delete separately permits deletion of an existing file. Renaming requires
a scoped addition and deletion. Wildcards, absolute scope paths, traversal,
directory permissions and Git metadata paths are invalid.

## Sensitive edit already authorized by the task

```bash
python /skill/scripts/change_guard.py snapshot --root /repo/MVS --out /work/method-before.json --task "Fix the explicitly requested Core defect" --allow Core/AnalysisEngine.cs --allow-sensitive Core/AnalysisEngine.cs --sensitive-reason "Owner requested this specific defect correction; preserve the registry and correction family"
```

Sensitive classifications include production scientific sources, interface
contracts, numerical pins, native regression contracts, source evidence/assets,
historical desktop, build/release metadata, workflow/check/build tools and
notebooks. Review all categories reported by the guard. Any change inside a
sensitive allowed file still requires final semantic review.

The --allow-sensitive flag records an authorization already present in the
request; it cannot authorize itself. Do not pass it just to suppress a refusal.
A user who asks to repair a specific statistical method has already authorized
the required source edits; do not ask the same permission again.

## Discover another required file

```bash
python /skill/scripts/change_guard.py extend --root /repo/MVS --baseline /work/task-before.json --out /work/task-extended.json --task "Add the necessary checker documentation" --allow docs/VALIDATION.md
python /skill/scripts/change_guard.py verify --root /repo/MVS --baseline /work/task-extended.json
```

Extend preserves initial file hashes even when previously allowed edits are in
progress. It cannot legitimize an already-unscoped edit. Explain a material scope
expansion to the owner first; ordinary necessary tests/docs are part of an
authorized fix. Do not use extend to turn a backlog suggestion into requested work.

## Git work and pre-existing edits

Capture the actual working tree, including pre-existing modified/untracked files,
rather than comparing only with HEAD. Preserve those files. Capture semantic
index entries so staging changes are visible without depending on volatile Git
stat caches. Do not read a parent workspace's Git repository as the MVS checkout.

By default, verification rejects changed Git HEAD or staged entries. Use
--allow-git-index and/or --allow-git-history at the initial snapshot only if the
user's task specifically authorizes those operations. The guard does not stage,
commit, reset, stash, clean, push or alter Git configuration.

## Coverage and limitations

Skip ordinary generated/cache directory names .git, __pycache__, .venv, venv,
node_modules, bin and obj, and root artifacts/publish. Still include Git-tracked
files in excluded-looking directories. In a source ZIP without Git, review the
original source manifest so source assets in such directories are not missed.
The exclusion list appears in reports. Empty directories are not tracked.

Record symlink identities without reading their targets. Never follow symlink
directories while scanning. Reject changed symlinks even when their path is
allowed; handle such a requested change with a separate explicit review. Refuse
unsupported special files/submodules and incomplete filesystem/Git probes.
Compare mode changes as well as bytes; ordinary builds may need review if they
change source executable bits.

Snapshot hashes detect an accidental snapshot edit, not malicious tampering by
an actor who can edit the JSON and recompute the hash. The guard cannot prove
who approved a flag, detect changes inside an allowed file that exceed the task,
record transient network/destructive actions, or observe concurrent writes after
the scan. Do not use PASS to imply any of these properties.

The snapshot also pins the guard implementation's SHA-256. A changed guard cannot
verify an old snapshot successfully unless someone bypasses or rewrites that
check. Do not edit the guard/exclusions to suppress a current task's failure.

## Exit statuses

| Code | Meaning | Next action |
|---|---|---|
| 0 | Snapshot/inspection completed, or scope verification passed | Continue the applicable checks and semantic review |
| 1 | Verification found unscoped/sensitive/symlink/Git changes | Preserve evidence, inspect ownership; do not ship as verified |
| 2 | Invalid input, unsupported root/metadata or incomplete scan | Fix the input or report the limitation; no verification claim |

Keep baseline documents outside source ZIPs: they may contain private filenames,
task descriptions and hashes of local data. Report only relevant changes to the
owner; do not publish baselines or unrelated local paths.
