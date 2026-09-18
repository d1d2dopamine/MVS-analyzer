# Benchmark history

This document tracks frozen benchmark runs across MVS versions. It is a development record, not a substitute for each benchmark protocol or the raw run artifacts.

The main rule is simple: numerical differences are directly comparable only when the protocol version, protocol hash, profile, and relevant run settings are the same. A new protocol may answer a different question. In that case, this page records both runs but does not treat the difference as a version-to-version performance gain.

## Recorded runs

| Software | Engine | Protocol | Profile | Seed | Purpose | Overall |
| --- | --- | --- | --- | ---: | --- | --- |
| 1.4.0 | 1.6.0 | `MVS-BENCH-1.2.0` | full | 20260904 | development baseline | no-go |

The exact raw outputs for this run are archived under [`benchmark_history/1.4.0-engine-1.6.0-MVS-BENCH-1.2.0/`](../benchmark_history/1.4.0-engine-1.6.0-MVS-BENCH-1.2.0/). The frozen protocol hash is `b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268`.

## 1.4.0 baseline

The full run completed 5,490 planned work units with no failed benchmark replications. Runtime was 117 minutes on four threads under .NET 8.0.31 on Ubuntu 24.04.5 LTS.

### Headline results

| Quantity | Result |
| --- | ---: |
| Null false-positive rate, cherry-pick among 12 metrics | 17.8% |
| Null false-positive rate, registry-corrected MVS | 1.8% |
| Null false-positive rate, single-metric MVS gate | 4.6% |
| Location x1.05 power, registry-corrected MVS | 14.0% |
| Location x1.05 power, single-metric MVS | 44.0% |
| Location x1.05 held-out oracle | 44.8% |
| Dispersion x1.30 power, registry-corrected MVS | 28.8% |
| Dispersion x1.30 power, single-metric MVS | 5.6% |
| Dispersion x1.30 held-out oracle | 53.6% |
| Stability, median Kendall tau | 0.714 |
| Stability, top-1 agreement | 22.5% |
| MVS false-positive rate at 2% contamination | 4.4% |
| MVS false-positive rate at 10% contamination | 4.8% |
| Determinism replay | identical SHA-256 |

### Frozen verdicts

| Hypothesis | Result | Meaning for development |
| --- | --- | --- |
| A | pass | Metric shopping inflated the false-positive rate; MVS error control remained conservative. |
| B | fail | Error control cost too much power in some conditions, especially the registry-wide corrected procedure and dispersion selection. |
| C | inconclusive | Overall rankings were moderately stable, but the exact top-ranked metric was not stable enough to treat as a reliable winner. |
| D | pass | The gated procedure kept the false-positive rate controlled under the tested contamination levels. |
| E | pass | Repeating the same run in the same arithmetic environment reproduced the decision matrix exactly. |

The 1.4.0 run is the development baseline for the 1.5.0 redesign. It exposed three specific targets: recover power without giving up family-wise error control, separate metrics by the kind of change they measure, and stop treating a fragile top-1 metric as the main scientific result.

## How future runs are recorded

Every benchmark that is used to judge a released or release-candidate scientific engine should get its own immutable directory under `benchmark_history/`. Keep at least these files exactly as produced by the benchmark:

- `benchmark_manifest.json`
- `benchmark_protocol.txt`
- `benchmark_report.md`
- `benchmark_summary.csv`
- `benchmark_metrics.csv`
- `benchmark_choices.csv`
- `benchmark_stability.csv`
- `benchmark_verdicts.csv`
- `SHA256SUMS.txt`

Add one row to the table above and a short version-specific section below it. Mark the run as `development`, `validation`, or `replication`.

A development run may be used to change the method. Once a method has been tuned against a benchmark, that benchmark is no longer independent validation for the tuned version. Final validation therefore uses a separately frozen protocol and unseen seeds or data-generating conditions.

Do not rewrite an old result when a newer version improves it. The point of this file is to make the trajectory visible.
