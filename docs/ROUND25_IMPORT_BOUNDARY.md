# Round 25: source-bound import results

## Defect and changed boundary

A deterministic counterexample reproduced the old active caller pattern:
`CsvImporter.Read(path)` consumed A, the pathname was then replaced with B, and
`OutputExporter.HashFile(path)` recorded B. Observations and claimed input digest
therefore described different bytes. A second import also replaced process-global
`LastImportSummary`, `LastEncodingName`, and `LastSequenceWasProvided` belonging
to the first import. Neither defect requires a change in statistical formulas.

`CsvImporter.Import` now returns one `CsvImportResult`: observations, import
summary, encoding, supplied-sequence status and SHA256 of the same raw byte
buffer used for decoding and parsing. BOM and newline bytes are included in the
hash. The result does not retain the raw buffer. Metadata is init-only; the
observations remain an independently owned mutable List for engine compatibility.
This is local ownership, not deep immutability.

Migrated callers are headless calibration and analysis, scientific variance and
experimental MELSM, and real-data benchmark loading. MELSM validates sequence
availability from its own result. Scientific manifests receive the captured raw
input hash instead of reopening the input after computation. Synthetic estimation
retains its existing canonical identity. CLI/Python/MCP public schemas, settings,
exit codes and statistical calculations are unchanged.

## Compatibility, cancellation and limits

- Legacy `Read` and `ReadText` retain process-global Last* behavior for unported
  callers, including legacy update points on failed imports. New `Import` never
  publishes those fields, on success, error or cancellation.
- Decoder fallback, delimiter/profile behavior, numeric conversion, filtering,
  sequence fallback, observation order and parser error messages are preserved.
  Invalid encoding is still handled by the existing decoder policy; this change
  does not silently impose strict UTF8 or rewrite source values.
- Cancellation is checked before file access, around decoding, in parsing and row
  processing. Synchronous ReadAllBytes, hashing, decoding and initial text Split
  are not interruptible. No cancellation-latency bound is claimed. Normal malformed
  inputs retain their parse errors; a cancelled operation may stop before parsing.
- Byte/text/CSV-row materialization remains. This is not a streaming parser or a
  bounded-memory import. Import profiles must not be concurrently mutated by their
  owner during a call; no new deep-copy contract is introduced.
- The hash identifies the bytes actually captured, not an atomic filesystem
  snapshot under a concurrent in-place writer. Replacement/deletion after capture
  does not alter the result. Current-path identity may subsequently differ.
- State-check intentionally hashes the current path without importing it. Output
  artifact hashing is also unchanged; these are different identities.

## Explicit residual backlog

Archived Desktop/MainForm import paths and MainForm.Science sequence metadata
still use legacy globals. Desktop/Remote packaging can reread a source and is not
an atomic source-transfer snapshot. They are outside this active headless and
benchmark fix. Existing desktop canonical-observation digests retain their
meaning; a raw-byte digest has not been silently substituted for them.
A future desktop migration should carry one result through UI/science/transfer
ownership and test replacement, interleaving and canonical/raw digest separation.

## Scientific and platform boundary

The existing 5,490-unit development benchmark remains NO-GO: power failed and
stability was inconclusive. Better input provenance does not demonstrate improved
scientific power, calibration or real-world validity. No full benchmark was rerun
for this unchanged-science patch. Production Bonferroni, twelve metrics and the
method fingerprint are retained. The newly supplied Windows CI logs fail the 18-check gate: a process cleanup
wait contract and ACL test-probe failures require a separate correction. This
import patch does not fix those failures. Linux results cannot establish Windows
acceptance; the subsequent Windows repair will need a fresh owner-run gate.

Round23 is the byte-pinned code comparator and rollback copy. Round24 was reported
as documentation-only; its inaccessible attachment was not retrieved through an
alternative route. Delivery is therefore a PATCH over the existing Round24 checkout, not a
cumulative full-source archive. The patch omits the root README and documentation
index, preserving user documentation. The complete Round23-based working tree is
only the development/comparison source.

## Executed verification

Final counts and paired comparison are recorded in validation/round25-results.json
and the accompanying evidence archive. The first 42 timing observations were
contaminated by concurrent native tests and are retained as exploratory evidence.
One prospectively documented complete clean repetition uses the same frozen
inputs, binaries, sample count and alternating order; no favorable sample selection
is permitted. See the frozen comparison protocol and evidence for exact outcomes.

## Actual results (Linux, 2026-10-16)

- Native build: zero warnings/errors; 158/158 native checks, including ten new
  import boundary checks. The earlier overlapping test attempt was interrupted
  and retained separately, not counted as a completed suite.
- Python/API/MCP and tool suites: 512 discovered, 498 passed, 14 Windows-only
  skips. Actual native MCP round-trip ran. First validation invocation used the
  MCP-only environment and failed for missing NumPy/SciPy; the retained corrected
  scientific-runtime invocation passed all 261 validation tests and 53 SciPy cases.
- CLI input/output safety: 135 cases, 1690 assertions, 138 direct CLI calls and
  six actual Python-to-CLI calls; zero skips.
- 17 frozen import fixtures match baseline exactly. Both deterministic old
  provenance/metadata failures are corrected.
- Paired native old/new calibration, analysis, variance, analytic MELSM and two
  input-error cases: 152 checks pass with zero numeric tolerance; sixteen exports
  are byte-identical. 42 machine artifact entries, 28 manifest entries and four
  state payload checksums independently verified. An initial mismatch caused by
  CreatedUtc-derived PayloadHash is retained; both checksums are validated before
  excluding only timestamp and its derived hash from state equality.
- Clean paired median milliseconds, baseline→candidate: 4500 rows 28.0037→27.1021;
  45000 rows 91.5200→89.8711; 150000 rows 239.3787→234.3617. Allocation is essentially
  unchanged. No material regression observed; the small differences do not prove
  a general speedup. All 42 clean and 42 contaminated samples are retained.

The clean run occupied 14:01:43.465–14:02:13.528 UTC with coordinated competing
project computations stopped. These are host-specific engineering observations,
not scientific-performance evidence or a machine-wide isolation guarantee.
