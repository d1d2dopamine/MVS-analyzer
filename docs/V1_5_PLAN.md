# MVS 1.5.0 development plan

MVS 1.5.0 is the first CLI/Python-first development line. The Windows desktop application is frozen at 1.4.0 and is no longer part of CI, release builds, or active feature work. Its source remains in the repository for historical reproducibility.

The statistical goal for 1.5.0 is narrower than a general rewrite: preserve the error-control strengths of 1.4.0 while recovering power and making the automatic result describe the kind of change in repeated measurements rather than forcing all summary metrics into one ranking.

## Supported interface direction

The maintained stack is:

```text
Python API / notebooks
        |
headless MVS CLI
        |
MvsAnalyzer.Core
```

The .NET CLI remains the single executable statistical backend for now. Python controls that engine through the versioned machine protocol instead of reimplementing the statistics. Packaging can later bundle the compatible engine with Python if that improves installation without creating two scientific implementations.

## Scientific changes planned for 1.5.0

1. Replace the flat metric registry with structured metric metadata: family, applicability rules, requirements, interpretation, and implementation identity.
2. Separate location and variability summaries internally while keeping Automatic mode as the default user experience.
3. Add a small first wave of metrics aimed at known gaps: Huber location, Hodges-Lehmann location, Qn scale, and log-SD for positive multiplicative data.
4. Replace the mandatory top-1 winner with an uncertainty-aware candidate set.
5. Separate calibration from confirmatory inference. Calibration describes sensitivity and stability; it no longer decides whether a valid inferential procedure is allowed to run.
6. Keep Bonferroni as a legacy comparator, add Holm as a safe fallback, and develop a resampling maxT / step-down maxT procedure that can use dependence among correlated metrics.
7. Make the primary automatic result family-level: location, within-entity variability, and other supported families. Metric-level results explain the family signal rather than defining the entire scientific claim.

## Development sequence

### 1.5-A: registry and metrics - implemented

The structured registry and the four staged metrics are implemented and compile in CI. The active inferential registry remains the frozen 12-metric MVS 1.4 set, so this checkpoint does not change Bonferroni family size, saved calibration shape, or benchmark decisions. See `METRIC_REGISTRY.md`.

### 1.5-B: calibration redesign - implemented

Family-aware recommendation diagnostics are now implemented for the active legacy metrics. Candidate membership uses overlap with the best metric's Wilson power interval, the 0.70 lower-power threshold is a quality label rather than a hard deletion rule, and RMS is excluded from pure location/variability competition. The new `calibration_recommendations.csv` artifact keeps this layer separate from the still-unchanged 12-metric Bonferroni inference. See `CALIBRATION_RECOMMENDATIONS.md`.

### Validation bridge: observed availability - implemented and verified

Round 3 separates observed rank-test availability from calibration diagnostics,
exports metric-specific usable/excluded entity counts and reasons, and aligns the
registry-corrected benchmark comparator. Engine 1.6.2 keeps the twelve-metric family,
score formula and Bonferroni correction. See `ROUND3_APPLICABILITY_CHECKPOINT.md`.
The matching round-3 source has now passed 92 native tests and real CLI/Python
parity locally; its public CI also succeeded. Round 4 adds R1-07 per-replication
benchmark diagnostics and independent aggregate reconciliation; see
`ROUND4_BENCHMARK_DIAGNOSTICS.md` for the actual checks and open bugs.
R1-08 native reproduction confirmed two staged Huber numerical defects; the
original evidence remains in `ROUND5_HUBER_VALIDATION.md`. Round 10 repairs the
staged numerical path and passes the original and expanded independent gates;
see `ROUND10_STAGED_HUBER_REPAIR.md`. Huber remains staged: numerical readiness
does not itself satisfy its separate inferential activation requirements.
The complete engine-1.6.2 development baseline is finished with its NO-GO
outcome retained; see `ROUND6_DEVELOPMENT_BASELINE.md`. All 5,490 work units
completed without failures; the measured power/stability gaps remain.
Holm/maxT and family-level automatic inference retain their separate gates.

### 1.5-C: multiplicity engine

Implement Holm first, then maxT, then step-down maxT if the resampling assumptions and tests support it. Keep all methods selectable internally so benchmark comparisons remain possible.

Round 7 implements the internal Bonferroni/Holm vector arithmetic and independent
closed-intersection validation, without production activation. See
`ROUND7_INTERNAL_HOLM.md`. Full-family unavailable slots remain in the denominator.
Holm adds member discoveries but has the same any-rejection event as Bonferroni;
it alone cannot close the development benchmark global-power gap. Observable
integration, calibration identity and maxT scientific assumptions remain gated.

### 1.5-D: automatic inference and Python/CLI surface

Expose family-level automatic results through the machine protocol and Python result objects. Add a focused mode for hypotheses fixed before analysis.

### 1.5-RC: validation

Use `MVS-BENCH-1.2.0` only as a development diagnostic because its results have already informed the redesign. Once 1.5.0 behavior is frozen, define a separate `MVS-BENCH-2.0` protocol with unseen seeds and broader data-generating conditions. Record every run in `docs/BENCHMARK_HISTORY.md` and archive its raw files under `benchmark_history/`.

## Release criteria

A 1.5.0 release candidate should not be judged by whether every benchmark verdict is green. It should show, under a frozen protocol, that Automatic mode controls family-wise false positives, has materially better power than the 1.4.0 registry-wide correction in the target scenarios, identifies the correct change family with useful stability, reports uncertainty honestly, and remains deterministic within the declared arithmetic environment.

## Engineering audit checkpoints

Round 8 hardens the historical paper benchmark verifier against missing/truncated
evidence and adds fail-fast source identity to the paper workflow. Its frozen
engine-1.6.0 target is unchanged; the current engine-1.6.2 development NO-GO is not
relabelled. See `ROUND8_BENCHMARK_EVIDENCE_AUDIT.md` for checks, remaining runner
path-safety defects and separate engineering/method/scientific readiness criteria.

Round 9 fixes the reproduced chunk-runner deletion of overlapping incoming evidence,
refuses nonempty output resets, and validates completion before pass-through. See
`ROUND9_CHECKPOINT_RUNNER_SAFETY.md`. These operational repairs do not change the
benchmark protocol, historical source target or scientific NO-GO.

Round 10 repairs staged Huber scale/offset/overflow behavior with explicit failure
status and a new staged implementation ID. Actual native outputs pass 136 expanded
and all 20 original independent cases without relaxing tolerance. Active twelve-
metric results and pre-repair saved calibrations remain unchanged in the checked
fixture; no new metric is activated.

Round 11 identifies the best-supported historical paper source candidate from
public Actions metadata and verifies committed archive byte identity. Original
artifact retrieval requires authentication, so source/build/output binding remains
unverified. This narrowly blocked provenance check does not stop safe development;
see `ROUND11_HISTORICAL_SOURCE_PROVENANCE.md`.

Round 12 applies the unused internal native Holm comparator to every archived
round-6 vector and independently checks 128,880 adjusted values. Any-rejection
counts remain identical to Bonferroni; member discoveries increase in some cases,
including the global null. This is post-hoc development evidence, not activation
or a new benchmark verdict. See `ROUND12_HOLM_DEVELOPMENT_DIAGNOSTICS.md`.

Round 13 repairs reproduced CLI input/output collisions, incomplete calibration
`--overwrite` protection and global-option process aborts. Reserved-target
preflight preserves explicit dataset/job/profile inputs before writes; it is not
transactional output. See `ROUND13_CLI_INPUT_PRESERVATION.md` for actual checks and
remaining error-handling limitations. Scientific readiness and NO-GO are unchanged.

Round 14 adds unused single-step maxT arithmetic over supplied complete finite
joint score matrices. Forty actual native cases (104 values) match an independent
oracle, including a clearly bounded toy permutation-orbit identity. No production
resampling procedure, strong partial-null guarantee or family-level decision is
activated. See `ROUND14_INTERNAL_MAXT.md` for the explicit contract and gates.


## Current readiness boundary

Round 15 consolidates the risk-based project audit and repairs Python engine-launch
exception leakage. Local Linux engineering/numerical evidence supports continued
development; it does not complete the scientific plan. The next dependent stage
must specify family claims, valid joint/entity-level null resampling and partial-
null control before observable integration or step-down activation. See
`ROUND15_PROJECT_READINESS_AUDIT.md`; full development NO-GO and historical evidence
remain unchanged. Unseen BENCH-2.0 follows method/acceptance-target freeze.


Round 16 fixes omitted linked documentation/evidence in binary bundles and aligns
future release verification with the maintained CI gates. Local layout/syntax/tests
pass; no release or remote workflow was run. See `ROUND16_RELEASE_WORKFLOW_AUDIT.md`.

Round 17 adds a frozen bounded Linux CLI resource/cancellation audit, preserving
all outcomes and the development NO-GO. It consolidates the remaining scientific
decisions; more unused multiplicity scaffolding cannot close them. Existing
variance/estimation/MELSM interface parity remains a safe independent coverage
opportunity, distinct from external model validation. See
`ROUND17_CLI_RESOURCE_AUDIT.md`.

Round 18 is the final bounded existing-interface parity/error/export audit. It
checks actual variance, estimation and experimental MELSM workflows through CLI
and Python, without calling same-engine agreement external model validation.
See `ROUND18_SCIENTIFIC_INTERFACE_AUDIT.md` for executed outcomes and
`PROJECT_READINESS_HANDOFF.md` for the scientific claim/null decision, recommendation
and explicit stopping boundary. No unused layers or repeated development benchmark
runs can substitute for that decision and subsequent unseen validation.
