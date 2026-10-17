# Round43: same-recipe replay of 120 historical stability splits

The machine-readable execution specification is
`validation/stability-replay-protocol-v1.json`. It is fixed before executing any
Round43 calibration. It pins the original full-precision stability CSV, manifest,
protocol text, execution record and checkpoint archive.

## Question and limits

Round42 corrected demonstrated tau-b arithmetic defects. The original 120 split
score-vector pairs were not retained. This stage regenerates **only the same 120
historical recipes**, saves their vectors, and computes old and corrected tau on
each same pair. It is not a new power/null study or a rescue of a failed gate.
Even perfect agreement with the retained diagnostics cannot prove byte-identical
original vectors. The permitted claim is only “same-recipe replay matching all
retained diagnostics,” with explicit source/runtime qualifications.

## Frozen recipe

Run seed 20260904; stage 5, stream 1, indices 0–119 exactly once. Use the original
BenchmarkRandom, gait-heavy generator, Build limits ±1,000,000/minimum six, then
consume the split seed and left/right calibration seeds in the original order.
Call the original private BenchmarkRunner calibration/score/winner helpers.
Each half uses 1,000 repetitions and the original effect/scenario/contamination/
missingness/alpha/track settings. Both tau implementations receive the same
projected twelve scores. No alternate seed, reduced repetition count, selected
subset or independent recalibration for one coefficient is allowed.

## Gates and retained failures

Before execution, bind protocol/history/source/native/runtime identities. Repeat
integrity checks afterward. All 120 legacy tau values must equal the archived
binary64 values exactly, with identical left/right winner keys, matched flags,
completed/retained status and empty error. A mismatch blocks the compatibility
claim. Preserve every output and failure; do not relax tolerances or retry until
a favorable result appears. Old archives are never rewritten.

Retain ordered generated/built/split rows, their precisely defined canonical
hashes, consumed seeds, full calibration rows, projected score vectors, both
coefficients and undefined reasons. Hashes describe newly retained replay bytes,
not hashes recorded by the old run. Full-precision legacy CSV agrees with the
old checkpoint but does not contain the missing vectors.

## Fixed resource budget

Eight child processes, one declared .NET processor per child; 900 seconds total
execution wall time, 4 GiB aggregate sampled RSS, 384 MiB per-child .NET GC heap
cap, and bounded 10-second cleanup. No scientific retry. A timeout or resource
failure preserves partial evidence and blocks a completed-replay claim. Build,
reference review and pure synthetic tests occur before this execution window.
Call-count scaling from the old full run suggests a few minutes, but is not a
performance prediction or promise.

## Reporting fixed before seeing replay results

Show all 120 old/new pairs and comparisons. Show requested, usable, undefined
and execution-failed counts. Preserve existing aggregation: nonfinite tau is
excluded from both tau and top-one denominators. Also show matched/120 to expose
any denominator change. Median and lower quartile use the existing benchmark
quantile definitions. Historical top-one agreement is 27/120 and remains a
separate failure; correcting tau cannot improve the observed winner choices or
repair power deficits. Report actual cost descriptively, not as a speedup.

No production method, threshold or scientific readiness is changed. The existing
scientific NO-GO remains regardless of this diagnostic replay's outcome.
