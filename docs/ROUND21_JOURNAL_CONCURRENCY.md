# Round 21: bounded journal concurrency repair

Date: 2026-10-12. Cumulative source checkpoint after round 20. Scientific status:
**NO-GO retained**. Engine, formula, 12 active metrics, Bonferroni and the completed
5,490-replication development evidence are unchanged. No benchmark was rerun.

## Reproduced defects

The original bounded six-scenario audit used actual native journal operations on
isolated synthetic data. Three same-session writers appended 72 unique IDs with a
valid chain. Across three separate OS sessions, all 72 IDs were present and every
writer exited successfully, but the chain broke at lines 24, 26 and 71. The named
mutex used by older versions is session-scoped on this tested Unix runtime.

An unlocked reader also finished in about 0.015 seconds while a cooperative writer
held the production mutex and paused after writing the first byte of an entry.
It falsely reported JOURNAL_UNREADABLE. Releasing the writer produced a valid
one-entry journal. Ordinary overlap did not reproduce that race in this bounded
sample; that negative result is retained. Persistent malformed JSON and a broken
previous hash were correctly rejected even before repair.

## Repair and rollback

Readers and writers now acquire the same coordination lease. The existing session
mutex remains for compatibility with older same-session writers. A persistent
per-journal empty `.lock` file opened with FileShare.None additionally coordinates
upgraded processes across sessions. The lease is released by disposing its handle;
**the lock file is never deleted**. This avoids a delete/recreate inode race.
Acquisition has a shared approximately 10-second contention budget and then fails
explicitly. The synchronous API has no new cancellation-token contract.

Official .NET source also shows that Unix file sharing locks can be disabled or
unsupported. Actual probes with DOTNET_SYSTEM_IO_DISABLEFILELOCKING=1 and =true
confirmed that merely opening FileShare.None can silently succeed without a lock.
The final implementation checks that a second exclusive open is rejected while
the first handle is held. If both opens succeed, it throws NotSupportedException
before reading or appending journal data. It does not proceed unlocked. This
capability check is necessary local-filesystem evidence, not a security boundary.

The journal JSON/chain format is unchanged. Existing entries are not rewritten,
merged, migrated or repaired. Analysis journal failure retains round 20's completed
analysis/exit semantics and privacy-minimal journal_write_failed warning.
Rollback is the complete round-20 source ZIP; no repository history was altered.
A retained empty lock file is harmless to older versions; do not remove it while
any upgraded process may be using the journal.

## Executed verification

The final frozen revision-3 protocol has eleven scenarios, all passing:

1. Three same-session appenders: exactly 72 IDs and valid hashes.
2. Three separate-session appenders: exactly 72 IDs and valid hashes.
3. Two appenders plus 96 reader audits: 48 large entries, no false failures.
4. Controlled partial write: same-session reader waits, then reads the full entry.
5. Malformed JSON: JOURNAL_UNREADABLE, original bytes retained.
6. Broken chain: JOURNAL_BROKEN, original bytes retained.
7. Controlled partial write across OS sessions: reader waits correctly.
8. Abrupt termination of the owned synthetic writer releases the lock; the reader
   reports the preserved partial JSON as corrupt instead of hanging or repairing it.
9. Held cross-session lock: reader reports IOException after about 10 seconds;
   releasing the writer then leaves a valid chain.
10. Disabled Unix locking, value 1: explicit rejection and no journal entry.
11. Disabled Unix locking, value true: explicit rejection and no journal entry.

Protocol revision 1 preceded defect discovery; revision 2 added cross-session
reader/crash/timeout cases before repair validation; revision 3 added disabled-lock
cases after the runtime-option discovery. All versions, original failures and
intermediate results are preserved. This is not an unchanged preregistered protocol
or a stress/performance certification. Final checks: **144/144 native checks**, **441/441 Python tests**, **53 frozen
SciPy rank fixtures**, source/notebook/payload/CLI contracts and a fresh release
documentation bundle all pass. Builds report zero warnings/errors.

The native suite additionally exercises actual same-process FileShare exclusion,
persistent empty lock files and a lock-path obstruction. CLI regressions cover
round-19 path cases and round-20 warning visibility, artifact parity and privacy.
A further actual strict Python/CLI analysis with disabled locking retained completed
status/exit 0, exposed journal_write_failed, verified all artifact hashes and matched
the normal scientific outputs. Its first harness attempt passed an unsupported
Engine timeout argument and failed before any native execution; that runner/error
is preserved, and the corrected run uses a 60-second outer watchdog.
Builds use official SDK 8.0.425/runtime 8.0.31. Probe children share two allowed CPUs,
have a 20-second watchdog and sampled aggregate RSS guard of 512 MiB. Sampling is
not an exact maximum-memory measurement. All operations use disposable synthetic
data; no real user journal is opened.

## Compatibility and limits

- Every simultaneously active reader/writer should upgrade, or run exclusively.
  Older processes in other OS sessions ignore the new file lock. Retaining the
  old mutex cannot make mixed-version cross-session operation safe.
- Reading an existing journal now needs permission to create/open its adjacent
  lock file for read/write. Read-only journal installations can fail explicitly.
  No ACL or security permissions are expanded; ordinary application-data rights
  and the existing process umask apply. Reading an absent journal creates nothing.
- Verified here: this Linux host, local filesystem and .NET runtime. Windows,
  macOS, network/distributed filesystems, unusual mounts and hostile path changes
  were not executed. Do not claim those platforms passed.
- Use one canonical application-data location. Symlink/hard-link aliases or
  replacement of the journal/lock path are not protected or authenticated. The
  lock coordinates cooperating application processes, not arbitrary file editors.
- A process crash can leave an incomplete final entry. The audit reports it; it
  does not delete, truncate or silently repair evidence. No power-loss durability,
  transactional multi-file export or absence-of-selective-reporting guarantee.
- Scientific readiness remains gated by the user claim/null decision and future
  independent validation. Lock correctness does not improve the retained NO-GO.

Evidence: validation/journal-concurrency-round21.json and its checksummed ZIP.
Sources: [Microsoft Mutex constructor documentation](https://learn.microsoft.com/en-us/dotnet/api/system.threading.mutex.-ctor),
[FileShare documentation](https://learn.microsoft.com/en-us/dotnet/api/system.io.fileshare),
and [.NET Unix file-handle implementation](https://github.com/dotnet/runtime/blob/v8.0.0/src/libraries/System.Private.CoreLib/src/Microsoft/Win32/SafeHandles/SafeFileHandle.Unix.cs).
