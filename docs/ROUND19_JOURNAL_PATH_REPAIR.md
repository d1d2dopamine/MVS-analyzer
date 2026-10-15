# Round 19: absolute journal path repair

## Outcome and scope

The newly supplied round-18 archive is byte-identical to the previous deliverable:
351 files, 6,253,590 bytes, SHA-256
`39e12a995db49d1aed0b8c13af2cdf8cb99f54c6a758c902716522f241afb790`.
It is the rollback checkpoint. Its ZIP integrity was verified before extraction.

This stage repairs the reproduced Linux journal-location fallback. With a fresh,
nonexistent absolute `XDG_DATA_HOME`, the old default `Environment.GetFolderPath`
call returned an empty string. Appending `MVS_Analyzer/run_journal.jsonl` then
silently used the process working directory instead of the configured data root.
A rebuilt, unmodified round-18 CLI reproduced this behavior on synthetic input.

The resolver now uses `SpecialFolderOption.DoNotVerify` and requires an absolute,
nonblank result. Path lookup is read-only; directory creation occurs on append.
An unresolved/relative root fails rather than becoming a working-directory path.
The append operation captures its resolved path once and preserves existing chain
bytes and cross-process locking. The option's behavior is documented in
[Microsoft's API reference](https://learn.microsoft.com/en-us/dotnet/api/system.environment.specialfolderoption?view=net-8.0).

**No old journal is automatically moved, merged, rewritten or deleted.** A journal
left in a working directory by older software may belong to a different context;
combining chains automatically would be unsafe. Keep it as historical evidence
and review provenance separately. The normal application-data journal location
and file format remain unchanged for existing directories.

## Changes and risk

Production changes are confined to `Infrastructure/RunAuditor.cs`. Native tests
cover the resolver, nonexistent XDG root, existing hash-chain prefix preservation,
obstruction, and read-only audit lookup. The opt-in Linux CLI regression tool
retains new pre/post outputs rather than overwriting them. The embedded portable
source ZIP is regenerated with the existing builder because its native source
changed. No scientific method, registry, default, saved-state schema or version is
changed. Engine 1.6.2, twelve active metrics, Bonferroni and scientific NO-GO remain.

Failure to append a journal still follows the existing CLI behavior: scientific
analysis may complete, with a warning on stderr. An app-data obstruction can fail
earlier during plugin initialization. Neither case falls back to the working-
directory journal. Machine-readable reporting of the post-analysis journal warning
is a separately identified reliability gap; this stage does not silently change
exit codes or claim all provenance writes succeeded.

## Executed checks

- Official Microsoft SDK **8.0.425**, runtime **8.0.31**, installed task-locally.
  The Linux x64 SDK archive was checked against SHA-512 in Microsoft's 8.0 release
  metadata before extraction. No system-wide SDK or project dependency was added.
- Unmodified round-18 CLI, repaired CLI and Core test project build: **PASS**,
  zero warnings/errors. Builds use one MSBuild worker and two logical .NET CPUs.
- Native suite: **141/141 PASS**, including six new journal checks on Linux.
  Only the platform-independent resolver checks run on non-Linux hosts; those
  platforms were not executed here.
- Actual Linux regression: old fallback reproduced; **seven fixed cases PASS**:
  missing/existing absolute XDG root, unset XDG, relative XDG (platform fallback),
  app-data root file, application subdirectory file, and journal path directory.
  Four normal journal writes and one journal-warning analysis preserve full
  scientific JSON/CSV/manifest/state parity with the old CLI. Two earlier plugin
  path errors preserve their obstruction and legacy cwd sentinel bytes.
- **440 Python tests PASS**, including source, backups, historical verifier,
  checkpoint runner, release bundle, API and validation tools; **53 frozen SciPy
  rank-reference cases PASS**. These are separate from native numerical execution.
- Actual Python/CLI summary parity passes with the old 100-replication saved state.
  A separate correctly budgeted 150-replication canonical calibration/analysis
  fixture verifies the maintained machine contract and wrapper parity.
- Source identities/links, CLI contract, notebooks and regenerated embedded source
  payload: PASS. Historical benchmark/reference bytes and protected scientific
  identities remain unchanged. Final guard and source ZIP checks are separate
  from runtime verification.

### Preserved test-development failures

The first CLI regression attempt assumed every obstruction would reach journal
append. The app-data-root file instead failed earlier at plugin directory setup;
its actual error response and all preceding outputs remain retained. The tool was
corrected to distinguish those earlier errors, and a dedicated journal-file
obstruction was added. This was a test expectation repair, not a relaxed production
gate. The final sequence contains one calibration, one old analysis and seven new
analyses/error cases, nine native invocations.

The 100-replication parity fixture passed scientific equality and output integrity,
but the canonical contract checker correctly rejected its smaller budget. Its
failure log is retained; a fresh 150-replication fixture was then used for the
canonical gate. No failed result was replaced or relabeled as a passing check.

## Limits and next bounded issue

This is not a filesystem-race, symlink-alias or transactionality guarantee. It does
not validate Windows/macOS runtime, journal authenticity, every unavailable-home
configuration, or a stronger statistical procedure. The prior development baseline
is not rerun and remains NO-GO.

The actual journal-file obstruction demonstrates a follow-on interface gap:
stderr contains the append warning while structured diagnostics do not expose it.
A separate narrowly scoped warning-propagation stage can improve automation without
altering scientific claims, completed artifacts or analysis exit semantics.

Raw reproduction/final/canonical outputs, logs and a checksum inventory are retained
in `validation/journal-path-round19.zip`; the compact result is
`validation/journal-path-round19.json`. These contain synthetic fixtures only.

Evidence archive: 259 files, 594,754 bytes; CRC and every listed SHA-256 verified.
SHA-256: `fab75ef342ed1651557786891ccb8d31579242d9fb819c5b1d16b3ec688fac85`.
