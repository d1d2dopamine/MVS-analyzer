# Round33: partial export evidence

## Reproduced defect and boundary

A deterministic test invokes the actual CLI entrypoint, intercepts its post-preflight calibration banner, and creates an owned directory at `calibration_tracks.csv`. The first `calibration.csv` is saved, the next write fails, and the Round32 machine response reports `outputDirectory: null` and no artifacts. The saved CSV is 4,770 bytes; its SHA256 is `25e685ad5f16421dabbfb37eaaf200ebf503f0e5940f39b59c62378cef8911d0`. No filesystem timing race is needed to reproduce the defect.

Round33 tracks output emission in the active `calibrate`, `analyze`, `variance`, `estimation`, and `melsm` commands. This is error observability, not a transactional export implementation or a scientific-method change. Benchmark/resume and the archived desktop retain their existing output-reporting boundaries.

## Additive error contract

Existing successful/diagnostic envelopes retain their field semantics. Exit 1 remains `status: error`, `execution.completed: false`, with the existing scientific NO-GO. When output emission began, the error response additionally has:

- `outputDirectory`: selected output directory, even if incomplete;
- `artifacts`: only writes observed to complete in this invocation, whose file size and SHA256 still match at response construction;
- `manifestPath`: only a newly written, still-verifiable manifest; an untouched old manifest is not adopted;
- `partialOutput.status`: `incomplete`;
- `partialOutput.scope`: `current_invocation_successful_writes`;
- `partialOutput.attemptedPath`: a write started but not observed to complete, or null;
- `partialOutput.unverifiedPaths`: completed-write metadata that could not be captured or no longer verifies.

The attempted target is uncertain. It may be absent, unchanged, partially written, or replaced before a subsequent failure. It is never classified as a successful artifact merely because a file exists there. Starting another write to a previously tracked path invalidates its previous success entry. Untouched pre-existing files, including overwrite leftovers, are excluded. Early validation/preflight failures do not invent an output location.

Individual writes are observed through the existing writer sequence. The summary exporter has an optional internal observer; callers that do not supply one retain the original behavior. No calculation, RNG draw, metric order, checkpoint key, exit policy, or numerical-library choice changes.

## Limits

A crash can occur before a response or between a write and its observation. File hashes are checks at specific instants, not protection against an owner/admin or concurrent hostile filesystem mutation. A successful file write is not evidence that the overall analysis finished. A failed manifest write cannot be repaired by adopting an older manifest. No automatic retry, rollback, output deletion, or partial-result scientific interpretation is introduced.

Plugin reports already have a separate best-effort boundary: reports returned successfully by the existing plugin interface can be recorded; files created by a plugin that subsequently throws are not attributed as successful current output. Such files may remain on disk. Benchmark/resume, archived desktop, and all-file transactional publication remain outside this patch.

Python and workflow error-evidence details, executed tests, and exact comparison results are recorded in the final Russian report and `validation/round33-results.json`. Windows runtime acceptance remains pending until owner-run evidence passes; Linux testing is not a substitute.

## Python and local MCP

Validated error responses are attached as `MvsError.result` without changing
exception classification or message. Failed results do not fall back to
unlisted files through `artifact()`, cannot `copy_to()` an entire potentially
stale directory, and cannot be passed as a `Calibration` object to `analyze`.
The latter guard repairs a secondary reuse risk identified during review of the
new evidence API; no native command launches in that rejected path.

The workflow verifies each advertised successful partial file within its own
managed output directory. Its failed receipt retains only names, sizes and
hashes, plus uncertain target names. It omits absolute paths and native error
messages. Failed receipts remain idempotent; there is no automatic replay and
`read_artifact` remains completed-run-only. Old engines that omit partial
metadata retain the previous failure behavior. This is a point-in-time receipt,
not continuous verification of files after the failure.

Machine-mode tracking performs an extra size/hash capture after a successful
write. Human-only CLI calls skip the new capture. Existing success finalization
still uses the legacy artifact enumeration. Cost measurements include the
machine-mode tracking path and are reported descriptively.
