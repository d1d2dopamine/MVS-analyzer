# Validation and limitations

MVS calibration is a simulation conditional on observed data and selected scenarios. It does not establish external validity or a universally optimal metric. Use independent data and a justified analysis plan for confirmatory conclusions.

## What checks mean

Automated regressions cover numerical identities, data handling, calibration persistence and report consistency. The synthetic benchmark is a diagnostic comparison under declared conditions. Passing a software test is not independent statistical certification, and a checksum proves consistency, not scientific correctness.

## Important limits

- Power and false-alarm estimates have Monte Carlo uncertainty; failed simulations are reported rather than discarded.
- Minimum detectable effect is reported only when the simulation grid and budget support it.
- Approximate equivalence is not proof of equality; selected-pair intervals for multiple groups are descriptive.
- Variance-component results depend on Gaussian-model assumptions. Conditional bootstrap power is not a universal population guarantee.
- Bias, MSE and efficiency studies use simulated data with known parameters; unknown real-data truth is not estimated by this comparison.
- MELSM is experimental and requires independent comparison and convergence/diagnostic review before substantive use.

Retain the input hash, settings, output manifest and diagnostics. Do not combine results from incompatible method versions as if they were the same analysis. See [Methods](METHODS.md) for the full definitions.

## Independent Python diagnostic checkpoint

The [validation tools guide](../validation/README.md) documents manifest-aware
score checks and reference protocol MVS-REFERENCE-2. The reference is an
independent Python implementation with regression fixtures, not a second
production engine or a certification of native results. Its updated twelve-metric
reports preserve historical filenames and benchmark archives. See the
[round 1 checkpoint](ROUND1_VALIDATION_CHECKPOINT.md) for the delivered scope and
remaining native verification.

Round 2 adds independent frozen rank-test fixtures, native Core regression
gates and full scientific CLI/Python comparison for the canonical analysis
case. The [round 2 checkpoint](ROUND2_NATIVE_VALIDATION_CHECKPOINT.md) distinguishes
locally verified Python/static work from unexecuted native checks. Small-sample
exact diagnostics are reported separately; the production asymptotic tests and
fixed twelve-metric Bonferroni family are unchanged.

The subsequent [Mann-Whitney numerical fix](ROUND2_MANN_WHITNEY_FIX.md) responds
to a user-reported native CI failure. Engine 1.6.1 restores full precision of
the normal-CDF coefficients while keeping the frozen rank fixtures and accuracy
gates unchanged. The original round 2 report remains a historical checkpoint.


## Connection maintenance validation (1.4.0 unchanged)

The preserved `tools/test_colab_connection.py` and
`tools/test_colab_lifecycle.py` suites exercise historical desktop/browser
simulations, not a live Colab session or future Google releases. The current
headless Core test project explicitly excludes `ColabBridgeChecks.cs`; the old
statement that ten loopback/socket tests are part of the current native count is
no longer applicable. Retired UI/connection suites contain a known stale
HeadlessRun hash pin. No pin was weakened, and no live Colab or Windows UI runtime
verification is claimed by the current CLI/Python checkpoint.

## Round 3: observed availability

Engine 1.6.2 separates observed rank-test eligibility from calibration diagnostics
and adds metric-specific independent-entity accounting. Four new native regression
cases cover complete simulation failure with valid observed data, individual metric
exclusions, the four-entity boundary, constant inputs, and JSON/CSV export. Artifact
checks cross-check counts/reasons/status against the new table; CLI/Python parity
compares that table exactly. See [round 3](ROUND3_APPLICABILITY_CHECKPOINT.md) for
executed checks and native verification limits.

The owner reported a successful GitHub build for the preceding 1.6.1 fix.
This is evidence for that snapshot, not for the subsequent 1.6.2 changes.
No new benchmark power/error-control claim is made at this checkpoint.


## Current development evidence (rounds 4–15)

The original round reports above remain dated snapshots. Subsequent local work
verified the round-3 source natively; public success was also observed for that
specific round-3 commit. This does not claim remote CI ran any later source ZIP.

- [Round 6](ROUND6_DEVELOPMENT_BASELINE.md): complete development BENCH-1.2.0,
  all 5,490 work units, per-replication reconciliation, **NO-GO preserved**.
- [Round 10](ROUND10_STAGED_HUBER_REPAIR.md): 136 expanded and all 20 original
  independent numerical cases pass on actual repaired native Huber output.
  Huber remains staged; old failures remain archived.
- [Round 12](ROUND12_HOLM_DEVELOPMENT_DIAGNOSTICS.md): full archived-vector
  comparator analysis. Holm retains Bonferroni's any-rejection event and can
  add both true and false member discoveries; production inference is unchanged.
- [Round 13](ROUND13_CLI_INPUT_PRESERVATION.md): 135 actual CLI safety cases
  protect explicit inputs and contain global-option failures within stated bounds.
- [Round 14](ROUND14_INTERNAL_MAXT.md): 40 actual native finite-matrix cases,
  104 maxT values independently checked; 135 native and 319 Python tests pass.
  This is unused arithmetic, not a validated MVS resampling procedure.
- [Round 15 readiness audit](ROUND15_PROJECT_READINESS_AUDIT.md): current coverage,
  Python launch-error fixes, remaining risks and scientific decision gates.

Full scientific-field CLI/Python parity currently covers the canonical three-group
summary-analysis workflow with an existing calibration. Variance, estimation and
MELSM have implementation/diagnostic checks, but their corresponding full
cross-interface numerical parity fixtures and external model validation remain
separate work. A native suite count is not a claim that every public workflow,
platform or statistical assumption has independent validation.

Release readiness requires a declared, justified inferential protocol followed by
unseen BENCH-2.0 evaluation after freezing the method and acceptance criteria.
The reused development protocol and green software tests do not satisfy that gate.


[Round 16](ROUND16_RELEASE_WORKFLOW_AUDIT.md) repairs release documentation coverage
and future release-gate consistency, with offline bundle and workflow checks.
This does not mean a self-contained binary release or remote workflow was executed.

## Bounded resource and cancellation observations

The [round 17 audit](ROUND17_CLI_RESOURCE_AUDIT.md) records one frozen Linux
CLI calibration/analysis resource profile and cancellation probe. These synthetic
smoke workloads are engineering observations, not a performance guarantee or
scientific validation. The report distinguishes executed outcomes, skipped cases,
remaining coverage limits and dependent scientific decisions.

## Existing scientific interfaces and final readiness boundary

The [round 18 audit](ROUND18_SCIENTIFIC_INTERFACE_AUDIT.md) distinguishes actual
variance/estimation/MELSM CLI/Python consistency from independent model validation.
Its frozen small workloads preserve diagnostic outcomes and scientific nulls.
The [current readiness handoff](PROJECT_READINESS_HANDOFF.md) consolidates remaining
scientific assumptions, operational limits and the decision needed before the
next dependent method-development stage.
