# Round 7: internal multiplicity arithmetic

Date: 2026-10-11 UTC. Starting checkpoint: round 6 full development baseline.

## Scope and result

The first bounded part of plan 1.5-C is implemented: an **unused internal**
Bonferroni/Holm adjustment API and independent numerical checks. It is not wired
into observed results, calibration, exports or benchmark decisions. Engine 1.6.2,
the active twelve-metric registry, public defaults, state compatibility, score
formula and frozen benchmark protocol remain unchanged. This is software
arithmetic readiness, not activation or a scientific release gate.

The full development benchmark's NO-GO is unchanged. In particular, Holm alone
cannot repair its global-any-detection power gap: for a fixed family and strict
rejection, both methods reject at least one hypothesis exactly when the minimum
available raw p-value is below alpha / family size. Holm can reject additional
members after the first. This invariant is explicitly tested.

## Definition and boundaries

`Multiplicity.Adjust` requires the complete, predeclared nonempty family vector
and matching explicit family size. It preserves input order and does not mutate
inputs. Bonferroni returns min(1, m*p). Holm orders available p-values, multiplies
by m-rank, takes the cumulative maximum, caps at one, and restores input order.
Unavailable NaN slots remain NaN and still count in m. Infinity, out-of-range
values, mismatched family sizes and unknown methods are rejected.

The separate rejection helper uses strict adjusted p < alpha, consistent with
the current engine's convention. Unavailable is never rejected. It does not
assign applicability, equivalence, metric families, calibration quality or a
confirmatory interpretation. No production caller uses this API.

The independent Python reference enumerates every nonempty subset of the full
family and computes closed Bonferroni intersection tests. An individual adjusted
p-value is the maximum local intersection p-value among subsets containing it.
This deliberately differs from the native sorting/cumulative-maximum algorithm.
Unavailable slots act as p=1 only inside this reference construction and are
restored to null in output. Exhaustive enumeration is limited to twelve members
and is a diagnostic reference, not production code.

Theory/source context: [R's official p.adjust documentation](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)
describes Holm, Bonferroni and explicit family size; it cites Holm (1979).
R was not installed or executed for this stage. Strong family-wise error control
requires valid marginal p-values. Arithmetic agreement does not establish the
validity of the engine's approximate rank tests in every small-sample setting.

## Checks actually performed

- Release .NET build succeeded, zero warnings/errors; runtime .NET 8.0.31.
- Complete native suite: **104/104 passed**, including seven new multiplicity
  groups and 4,096 fixed-grid families for invariants.
- Native exporter compared exactly to independent closed-intersection reference:
  **46 fixtures, 980 adjusted values, all rejection vectors passed**. Cases include
  analytical examples, ties, missing slots, all unavailable, zeros/ones, unsorted
  values, full twelve-member families and adjacent floating-point thresholds.
- New reference/checker regressions: 14/14 passed. Combined current CI-style Python
  suites: **134/134 passed** (86 validation, 4 wrapper, 21 round-2 runner,
  17 backup and 6 source tests). Injected child failures in runner tests are
  deliberate test inputs, not failing suite outcomes.
- Independent SciPy rank reference: 53 frozen cases passed. Mathematical identities,
  static source/CLI contracts, notebook consistency and limited C# structure passed.
- Fresh native CLI calibration (150 repetitions, seed 20260719), analysis and
  real Python/CLI scientific parity passed for every result row, CSV, scientific
  manifest and state. This is interface parity, not a new full benchmark.
- Embedded Colab source rebuilt through its existing builder and verified.
- Change guard checked against the pre-edit snapshot plus an explicit evidence
  extension. No old benchmark evidence was modified.

Actual native output and reconciliation are preserved as
`validation/multiplicity-native-v1.json` and `multiplicity-comparison-v1.json`.
The native evidence includes fixture and Core assembly hashes. The fixture SHA is
`110fce60248a0b0c2c52dd4db9fa3fc49860ba22fc7bc3c406fb5a2ae8cd6fcf`.
CI now reproduces this independent comparison rather than only testing a copy of
native arithmetic.

An initial CLI build without restore lacked its machine-local assets file;
normal restore/build succeeded. Initial parity invocation lacked its prerequisite
calibration fixture. A calibration attempt then encountered this cloud host's
read-only default application-data directory; rerunning with a writable
`XDG_DATA_HOME` succeeded. No scientific settings, tests or gates were changed.

## Risk, rollback and next gates

Before editing, the scope was limited to a standalone unused helper, test exporter,
independent fixtures/reference, CI, the shared compilation list and rebuilt source
payload. Risk is limited to compiling additional code; existing inference source
is unchanged. Rollback is the complete round-6 source ZIP, including its benchmark
archive; no migration is needed because no saved-state contract changed.

Observed-result integration is a separate stage. It must explicitly identify the
chosen method, assemble the complete p-vector before adjustment, prevent cached
results/calibrations being relabelled, and assess engine/state fingerprints.
Calibration rates currently describe legacy rejection decisions; they cannot be
silently reinterpreted as Holm performance. Equivalence thresholds also remain
unchanged and are not justified by Holm's difference-testing ranks.

maxT remains gated on a frozen statistic/orientation, null and exchangeability
assumptions, entity-level resampling, common resamples, unavailable-value policy,
Monte Carlo p-value convention/resolution, deterministic seeds and failure behavior.
Strong control under partial nulls needs its own justification; global-null
simulation is insufficient. Family-level results need explicit null meanings and
cross-family correction, especially for RMS, normalized spread and heterogeneity.
The four new metrics remain staged; the reproduced Huber defects still block its
activation. Final scientific release readiness requires frozen new validation,
not recycling MVS-BENCH-1.2.0 as unseen evidence.
