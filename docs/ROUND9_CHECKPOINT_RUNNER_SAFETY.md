# Round 9: checkpoint runner evidence preservation

Date: 2026-10-11 UTC. Starting checkpoint: round 8 evidence verifier.

## Reproduction and intended boundary

The old paper chunk runner deleted state/work directories before validating their
relationship to incoming evidence. A controlled reproduction used a disposable
incoming directory containing one synthetic marker and passed the same path as
state. The marker was deleted; the command then failed on unrelated Git provenance
lookup with exit 128. No user evidence was used in the reproduction.

The runner also treated any discovered manifest as completed for pass-through,
leaving verification until the final workflow. This could propagate invalid or
ambiguous evidence through later chunks.

The repair is confined to operational path/configuration validation, preservation
of incoming/output evidence, and verification before declaring completion. It
must not change benchmark seed, budgets, statistical rules, scientific NO-GO
handling, native backup format, or historical engine target.

## Risk and rollback

Refusing nonempty destinations is an intentional operational tightening: callers
must choose fresh output directories rather than expecting silent deletion of an
old checkpoint or result. The workflow's fresh state/work directories fit this
policy. Rollback is the complete round-8 ZIP; no source evidence or saved-state
migration is involved. Historical benchmark files are immutable inputs throughout.

Native computation is not required to reproduce or fix this shell/Python defect.
Fake-command tests exercise operational branches only and do not establish native
checkpoint/resume scientific equivalence. The most recent real native and parity
checks remain those in round 7; the full development benchmark remains NO-GO.

## Implemented behavior

- The runner never deletes output directories. Nonempty destinations are refused.
- Before writing, it validates positive numeric chunk/thread/time settings, frozen
  full profile/seed, existing incoming evidence, canonical disjoint paths and safe
  non-symlink destinations. Ancestor/descendant overlaps are rejected too.
- Incoming trees reject links, non-regular entries, control-character paths,
  ambiguous manifests/checkpoints and conflicting chunk provenance. A directory
  without a result or checkpoint cannot silently restart computation from zero.
- Valid completed historical results are verified before and after pass-through.
  Static historical source identity is required before actual start/resume;
  checking an already completed archive does not require recomputing it.
- Unexpected exits, invalid results and log-write failures cannot mark a run
  complete. Original incoming evidence and newly produced checkpoints are retained.
  A verified scientific NO-GO (native exit 2) is still completed evidence.
- A timed-out segment is incomplete and needs a newly emitted checkpoint; a
  manifest alone is insufficient to certify completion.

## Checks actually performed

**34/34 new runner test methods passed**, including parameterized path/configuration
cases. **174/174 existing CI-style Python tests passed**, including the 40 round-8
artifact-verifier regressions: 208 total. Bash syntax, source/CLI metadata, notebook
consistency and unchanged embedded-payload checks passed.

The original disposable incoming=state reproduction was rerun directly: the marker
survived unchanged, the runner exited 1 with a disjoint-path diagnostic, and no work
directory was created. Tests additionally cover parent/child overlaps, nonempty
outputs, unsafe roots, symlinks, malformed/ambiguous input, provenance mismatch,
configuration overrides, literal spaces/quotes/shell metacharacters, rejected control
characters, pass-through and verified NO-GO, unexpected exits, timeout, missing or
invalid manifests, and incoming/new checkpoint retention.

Operational branches use explicitly synthetic source-identity fixtures and shadow
Git/CLI commands. Historical artifact validation uses the real archived NO-GO.
Fake checkpoint bytes test preservation, not compatibility: payload/settings checks
remain the native resume validator's responsibility. No native resumed run, remote
workflow or full benchmark was executed. Static source identity and Git consistency
do not authenticate a historical revision or compiled binary.

Final pre-edit change guard and ZIP source completeness/integrity passed. Historical
and development benchmark evidence is byte-preserved. Existing native test results
are cited only as prior evidence, not rerun claims.
