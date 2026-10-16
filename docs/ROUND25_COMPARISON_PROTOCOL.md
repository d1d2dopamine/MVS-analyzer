# Round25 pre-change engineering comparison protocol

Frozen before implementation/timing on 2026-10-16. Reference code: Round23
(source SHA256 ab459f7654db602621f11e59dd5fc8e5a8438bb963d981bdeabf9f3af798a855).
Round24 is reported documentation-only; its attachment is currently unavailable.
No claim of a new scientific holdout or improved statistical power is intended.

## Hypotheses and acceptance

1. Import identity must be SHA256 of the exact raw bytes decoded/parsed, including
   BOM and newline spelling. Replacing/deleting the source after capture must not
   change that result or cause a second identity read.
2. Import metadata travels with that import. Success, failure or an interleaved
   later import must not alter a prior explicit result. Retain legacy Read/Last*
   compatibility for unported callers, without claiming those globals thread-safe.
3. Stable-file observations, row order, metadata and hashes must be identical to
   baseline, including UTF8/UTF16 BOM, CP1251, LF/CRLF, custom delimiter/decimal
   profiles, invalid rows, sequence fallback and malformed input errors.
4. Active CLI calibration/analysis, variance and MELSM plus benchmark real-data
   loading consume that local result. Scientific settings/registry/corrections,
   output schema and numerical fields remain unchanged. Existing CLI/Python and
   MCP suites and actual native parity are required. Exclude only documented
   timestamps/run IDs/absolute paths/environment identities where appropriate.
5. Pre-cancelled import fails before file access. Check cancellation around decode
   and during row processing; do not claim interruptible synchronous ReadAllBytes
   or a streaming parser. Preserve output/input safety and negative error tests.
6. Frozen engineering timing: 4,500 / 45,000 / 150,000 synthetic rows, fixed
   generation seed and bytes, two warmups then seven matched old/new measurements,
   alternating AB/BA, same .NET/runtime, two CPUs, backups off. Preserve all raw
   wall/CPU/allocated-byte/GC/peak-memory observations available; unavailable RSS
   must be explicit. Investigate >20% median slowdown at 150,000 rows; do not
   repeat until green, tune seeds or discard failures. Speedup is not assumed.

The standalone probe freezes exact fixture/source hashes and command settings
before timing. Comparative output is retained even if this change is neutral or
slower. The decoder/parser still materializes bytes/text/rows; measure that cost,
not a claimed streaming improvement. No extra full input copy is required for
hashing, and returned results need not retain raw bytes.

## Scientific boundary and rollback

The existing 5,490-unit BENCH-1.2.0 remains NO-GO (power failed, stability
inconclusive). This change repairs association of data/results and isolates import
metadata; it cannot repair those statistical deficiencies. No current metric,
formula, Bonferroni gate, candidate policy or historical benchmark is changed.
Future method experiments require separately frozen scientific hypotheses and
unseen evaluation conditions. Old23 source/binaries remain rollback/comparator.
Archived Desktop callers and remote-transfer path races are outside this active
CLI/benchmark boundary and must be listed, not implicitly declared fixed.
