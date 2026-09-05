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
