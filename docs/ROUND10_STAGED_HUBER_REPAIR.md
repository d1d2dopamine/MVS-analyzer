# Round 10: staged fixed-MAD Huber numerical repair

Date: 2026-10-11 UTC. Starting checkpoint: round 9 runner safety.

## Scope and risk assessment

Round 5 reproduced two numerical defects in the staged Huber estimator: stopping
accuracy depended on units/common offset, and a large offset/outlier could trigger
a median fallback despite positive sample MAD. The original native evidence fails
9/20 reference cases and remains unchanged. Inspection additionally identified
unsafe shared median/MAD intermediate arithmetic for extreme finite inputs.

This stage repairs only the internal staged Huber path. It dispatches before the
shared Workspace; no common active-metric arithmetic, registry membership/order,
calibration, Bonferroni, score formula, benchmark protocol or saved-state semantics
is changed. All four new metrics remain staged. Engine 1.6.2 remains the active
method identity; a new staged implementation ID and binary hashes distinguish the
repaired unused estimator. Activation is a separately versioned scientific step.

Risk: floating-point normalization or reconstruction can introduce errors of its
own, especially at extreme exponent ranges. Acceptance therefore requires an
independent original-input high-precision oracle, explicit subnormal/overflow
controls, unchanged tolerance, native failure/status tests and active-path parity.
Rollback is the complete round-9 ZIP. No migration or evidence rewrite is involved.

## Numerical definition

The estimand remains the root of the Huber clipped-score equation with c=1.345
and fixed scale 1.482602218505602 times the original sample MAD. The declared
fallback remains the sample median when that MAD is exactly zero.

The solver uses an actual upper-median observation as anchor and a robust upper
median distance to choose power-of-two coordinates. Unlike scaling by the largest
absolute observation, this does not let a remote outlier erase a tiny positive
robust spread. Signed infinite normalized outlier residuals can be clipped safely;
nonfinite original inputs remain invalid. Shared Workspace arithmetic is untouched.

A bracketed monotone solve stops in scale units, with an explicit iteration budget.
Failed normalization, bracketing, scoring, reconstruction or exhausted iteration
budget produces an unavailable result with a diagnostic status. It does not return
the last iterate as converged or relabel failure as zero MAD. Reconstruction uses
scaled/cancellation-safe arithmetic and the known finite data hull.

Implementation ID: `fixed-mad-huber-normalized-score-v2`. Native diagnostics add
`implementationId`, `solverStatus` and `iterations` to the existing schema, alongside
fixture/Core assembly hashes, runtime, engine identity, staged flag and active count.

## Independent acceptance evidence

The new oracle uses Decimal1600 median/MAD and clipped-score bisection directly on
exact original binary64 values. It does not reuse native normalization or a rounded
transformed sample. The original Decimal80 checker is retained and rerun separately.
The unchanged tolerance is max(1e-10 times the exact fixed-MAD scale, four ulps of
the reference rounded to binary64). Positive MAD additionally requires converged
status; exact zero MAD requires zero_mad_fallback. Unavailable never passes accuracy.

Expanded fixture: 136 cases, comprising the original twenty unchanged plus 116 new
cases. They include extreme binary scalings, maximum finite magnitudes, opposite
signs/overflow, tiny positive MAD with an enormous outlier, half-subnormal midpoint,
large common offsets, reflections/permutations, strict-majority ties and constants.
Analytic symmetry/midpoint controls supplement numerical root comparisons.

Fixture SHA-256:
`798f077e41274ef939fdb3c585855896241fc46be03cdfbf65acf2fb96fe9ecb`.

This work checks a numerical estimator. It does not establish population validity,
robustness under every contamination mechanism, new metric calibration, family-wise
error control, benchmark power improvement or release readiness. The completed
MVS-BENCH-1.2.0 development result remains NO-GO. No full benchmark rerun is needed
for an unused staged numerical path.

## Checks actually performed

- Release native build: zero warnings/errors. **113/113 native tests passed**,
  including nine new Huber groups and all 104 preceding checks. New groups cover
  scale/translation/outliers, extreme/subnormal values, exact zero-MAD policy,
  explicit iteration failure, invalid inputs, immutability, permutation/reflection,
  exporter agreement/null failure serialization, and active-registry preservation.
- **136/136 actual native cases passed** the independent Decimal1600 gate, with the
  reported binary SHA verified against the actual Core DLL. Status counts: 114
  converged, 22 exact-zero-MAD fallbacks, no unavailable results. Maximum iterations
  were 46; 19 positive-MAD cases converged in one iteration.
- **20/20 original cases passed** the unchanged Decimal80 checker on a fresh export.
  Original failing native evidence remains 9/20 failures, as asserted by tests.
- **247/247 CI-style Python tests passed**, including 39 new oracle/checker tests.
  Synthetic checker documents are explicitly labelled and are not native evidence.
- Independent SciPy reference: 53 frozen rank cases passed; mathematical identities,
  static source/CLI contracts, C# structural check and notebook consistency passed.
- Fresh real CLI calibration (150 repetitions, seed 20260719), analysis and full
  Python/CLI scientific parity passed. The CLI also loaded the pre-repair round-7
  calibration state successfully: all scientific result/CSV/manifest fields and
  saved state bytes matched the pre-repair analysis **exactly**.
- A fresh recalibration matched all previous scientific fields exactly. Its creation
  timestamp and derived payload hash correctly differ. An initial whole-state-byte
  comparison across these separate calibrations failed for those expected fields;
  it was not treated as a scientific mismatch or a passing byte-identical check.
  The unchanged parity test passes when both interfaces use the same calibration.
- Registry definitions/applicability, ComputeLegacy, shared Workspace, denominator
  thresholds/quantiles and other staged-metric implementations are byte-preserved.
- Embedded Colab source rebuilt by its existing builder and verified. Native source
  export schema remains additive, and public engine/formula/protocol identities
  remain unchanged. Final scope guard and source ZIP completeness/integrity passed.

Actual native output and the independent comparison are archived as
`validation/huber-native-repaired-v1.json` and
`validation/huber-comparison-repaired-v1.json`.
Runtime: .NET 8.0.31. Core assembly SHA-256:
`23fda6adf0a605b614839f6f79fd7bbd911f947644e95c7e9ebf7541d06de5be`.

No full benchmark, Windows desktop run or remote GitHub CI was performed for this
stage. Existing scientific NO-GO and the separate multiplicity/family-level gates
remain. Passing these finite numerical fixtures does not prove accuracy for every
possible input; explicit failure status remains part of the estimator contract.
