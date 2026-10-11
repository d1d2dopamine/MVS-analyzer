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

Run `python tools/test_colab_connection.py` for the 47 new offline contract/cache/transport regressions. Run `python tools/test_colab_lifecycle.py` for automatic reconnection and orderly download/stop regressions. These tests simulate the desktop/browser; they do not certify a live Colab session. Simulated 40-step additive transport/controller updates are NOT a claim of testing 40 future Google releases. Real generated JavaScript is executed against a fake fetch, not Google. Native Core.Tests now links the actual loopback bridge and includes 10 additional contract/replay/socket tests; compile and run it on Windows/Linux with .NET 8. These native tests and the Windows UI harness were not executed in the preparation sandbox.

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
