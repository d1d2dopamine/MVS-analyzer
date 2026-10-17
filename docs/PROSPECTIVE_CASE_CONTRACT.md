# Prospective case, generation, and outcome contract

Round56 implements validation-only components for `MVS-STAT-COMPONENTS-PROSPECTIVE-1.0.0`. The frozen Round54 design remains authoritative. This document and its machine companion define software verification before any new study observations are generated. Historical numerical results and all production algorithms remain unchanged.

## Identity, units, and representation

A case binds the raw SHA-256 of the frozen protocol, explicit purpose, case identifier, cell ordinal, zero-based replication, native seed, entity/repeat counts, order, and every binary64 value. Planned identifiers and `engineering_literal/` identifiers are disjoint. Using a planned native seed on a literal fixture does not make that fixture a study observation.

There are two independent groups. Values are ordered by group, then entity, then repeat. Cells C00–C09 have 16 entities/group and 40 repeats; C10–C11 have 8 entities/group and 5 repeats. Each value is serialized as an exact 16-digit lowercase IEEE-754 binary64 hexadecimal bit pattern. The ordered data digest hashes the concatenation of little-endian eight-byte representations. The raw serialized case-file digest is separate and retained. Native parsing/building must retain all observations, group/entity/sequence identities, values and ordering; it may not filter or redraw an inconvenient dataset.

Strict schema validation rejects duplicates, unknown fields, ambiguous numeric types, incorrect dimensions/coordinates/seeds and mismatched digests before calculation. Nonfinite values fail input validation; finite values outside the frozen Build limits make both methods unavailable. Any future study coordinator must retain such an attempted case in its planned denominator, rather than replace it. A malformed/provenance-corrupt envelope is a technical halt, not an ordinary scientific non-rejection.

## Generator and randomness

The model, component distributions and factors are exactly those in Round54. Draw all 2n random intercepts before all 2nm residuals; scale t5 variates by sqrt(3/5). Assemble each row as the declared group mean plus between-SD times the corresponding intercept plus within-SD times its residual. Preserve start/end RNG state and NumPy version. The reserved data coordinates are `[2026101754,1,0,cell,replication]` for PCG64/SeedSequence with NumPy2.3.5. Native seed is `1540000000 + 1000*cell + replication`; stream1 is a provenance label, not another random integer draw.

This stage does not instantiate reserved study streams. Scripted arrays independently test assembly, ordering, distribution selection and scaling. Real PRNG checks use only a separate explicit engineering namespace. Distinct deterministic streams support reproducible separation; no claim of mathematical independence of pseudorandom streams is made. A future activation needs a frozen authorized execution entry point and complete bindings.

## Methods, unavailable cases, and reporting

Actual Core computes the Gaussian component route with evaluation100/reference199/effects2/alpha.05 and the unchanged12-summary asymptotic MW/Bonferroni route. Per-component bootstrap p uses `(1+k)/(B_finite+1)` with inclusive ties and the existing90% finite-reference usability requirement. Requested199 is not substituted for the realized denominator. Record convergence, boundary, failed reference counts and all observer events. The complete-only literal checks from Round55 are not an extra scientific availability rule.

Each route retains its outcome independently. Family rejection is true if any available member rejects; false only if all members are available and none rejects; otherwise unknown. The summary family retains multiplicity12, original finite-value filtering and minimum four usable entities/group/metric, with counts visible. Within/between component raw cutoffs are.025; family and summary cutoffs are.05, strict. No automatic selector or OR-combination between routes is introduced.

All12 cells retain the planned1000 denominators, including failures and unattempted cases. There are31 true-null endpoints:7 variance-family,9 within,9 between,6 summary-global. Report rejection bounds r/R through (r+unknown)/R and exact binomial confidence envelopes with tail probability .025/31 for these endpoints. Paired reports retain discordances and unknown pairs, with the frozen conservative Clopper–Pearson construction. No valid cases means conditional estimates are unavailable, not zero. C01 summary rejection measures location detection whereas variance rejection is an error under its component nulls; a paired difference there is not power superiority. No aggregate score or retrospective acceptance threshold is introduced.

Synthetic report fixtures test arithmetic and failure accounting only. They must remain explicitly labeled and cannot enter a scientific results registry.

## Four-call engineering comparison, frozen before execution

Only four calculations are planned, sequential fresh processes: large direct reference, large serialized case, small direct reference, small serialized case. The large fixture is the unchanged Round50 deterministic formula (1280 rows). The small fixture retains the original values of the first8 entities and first5 repeats in each group (80 rows); it does not recompute a different smaller formula. Both use the same methods and their respective native seeds1540000000 and1540010000.

Compare the two paths within each fixture exactly: full scientific payload, all ordered observer events, original values and hashes, missing/error statuses, and provenance. The only differing top-level completion fields allowed are `mode`, `requestSha256`, `buildTiming`, `runTiming`, `legacyTiming`, `caseWallSeconds`, `processTotalCpuSeconds`, and `processPeakWorkingSetBytes`; within `operationCounts`, only `fixtureMaterializationCount` differs (reference1, serialized0). These fields are validated separately. All payload fields, serialized byte count, provenance, remaining counts and every observer event must match. Start envelopes are strictly validated separately; unknown/missing fields fail. No numerical tolerance, retry, replacement, seed search or extra cases are allowed. A failed or unavailable comparison remains failed; it is not replaced by an easier fixture.

The shared lifecycle cap is300seconds, cleanup10seconds, one CPU per child, aggregate sampled RSS2GiB, retained evidence cap20,000,000bytes. Reuse the tested Round55 blocking-wait/process-group supervisor. Record all calls, source/binary/runtime/request identities and measured costs. Sampling limitations from the Round55 contract remain applicable. Freeze the implementation and inputs after independent review and before any of these four computations.

## Readiness boundary

Passing these checks demonstrates a correctly wired adapter/generator/report contract on specified fixtures. It does not establish false-positive control, statistical power or runtime on arbitrary study cases. Reserved data generation, an end-to-end large-study coordinator with durable failure/resume accounting, final admission and a frozen execution manifest remain separate requirements. The native `run-case` seam can execute caller-supplied planned cases; it is not an authorization-enforcement mechanism. This stage’s no-study guarantee is the bounded engineering driver and absence of a study launch, not an inability of the native API to compute. The existing Round54 readiness checker remains blocked; its historical snapshot is not rewritten to imply launch approval.
