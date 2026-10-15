# Audit and provenance

Input and artifact SHA-256 values identify bytes. Calibration additionally freezes scientific configuration and validates a semantic payload checksum before replay. Manifest path traversal is rejected; calibration state is listed before the manifest is finalized. Forced cross-dataset reuse records both hashes.

The local append journal uses a cross-process lock and chains entries. Write failures are surfaced instead of silently suppressed. The journal is a useful local consistency check, but a person controlling the directory can rewrite the chain, omit runs, delete records or replace the program. It does **not** prove absence of selective reporting, authenticity, scientific correctness or preregistration. Keep a trusted external copy/commit if stronger provenance is needed.

A historical formula mismatch is a compatibility warning, not automatically evidence of tampering. Compare a historical run against the source/method version that produced it. Model reports have model-specific configurations, not the summary score formula. Older audit views may describe a model-only report as lacking summary-calibration metadata; inspect its model report and checksum list directly.

Pseudonymization does not guarantee anonymization. Before sharing, inspect calibration-state dataset names, group names, free text and model random-effect exports. Hosted notebook uploads leave the local machine.

## Journal path reliability (round 19)

The journal resolves an absolute local application-data root without requiring it
to exist first. Reads do not create the directory; append creates it or reports
failure. Empty/relative resolved roots are rejected instead of using the working
directory. Existing journal chains are preserved. Older working-directory journals
are not automatically migrated or merged. See [round 19](ROUND19_JOURNAL_PATH_REPAIR.md).

Since round 20, journal append failure after successful analysis is also visible
as `journal_write_failed` in machine diagnostics and Python results. It does not
change scientific exit status or saved artifacts. Retain the machine response when
that provenance-write warning must accompany a result export.

## Journal concurrency (round 21)

Readers and writers share the legacy session mutex and a persistent adjacent
exclusive-open lock file. Acquisition times out after approximately ten seconds;
disabled/unsupported exclusion is rejected by a second-open capability check.
Lock files are not removed on release. Existing-journal readers now need read/write
access to the lock file and creation rights if it is missing; no ACL is changed.
Upgrade all concurrent processes or use exclusive operation: older cross-session
writers do not cooperate. Local Linux tests pass; other platforms/filesystems and
hostile aliases remain unverified. See [the bounded evidence and limits](ROUND21_JOURNAL_CONCURRENCY.md).
