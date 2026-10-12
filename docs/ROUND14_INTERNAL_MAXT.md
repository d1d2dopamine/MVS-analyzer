# Round 14: unused single-step maxT arithmetic

## Stage definition, risk and rollback

The existing plan calls for Holm, then maxT, then step-down if assumptions/tests
support it. Round 12 completed the available post-hoc Holm comparison; its
identical any-rejection event cannot close the development baseline power gap.
This next bounded step implements only arithmetic over caller-supplied joint
scores. The round-13 ZIP is the rollback point.

No production analysis/calibration/benchmark path calls this implementation.
There is no new CLI scientific mode, Python result field, metric activation,
resampling generator, statistic choice, RNG stream or step-down algorithm. The
active twelve-metric Bonferroni family, equivalence calculation, engine identity,
saved states and scientific NO-GO remain unchanged. Arithmetic readiness is not
inferential readiness or evidence of improved power.

## Explicit input and counting contract

`MaxT.MonteCarloSingleStep(observed, resamples, familySize)` is internal. Inputs:

- A complete, predeclared nonempty family of `m` finite observed scores.
- `B >= 1` complete common-resample rows, each containing exactly `m` finite
  scores in the same hypothesis order. Scores in a row share one joint draw;
  independent per-metric shuffles cannot be substituted without changing the null.
- Scores are already oriented so larger values are more extreme. The caller
  chooses fixed scientifically interpretable scales/statistics. Equal null
  variances/distributions are not a prerequisite for a complete-null maximum;
  differing scales can nevertheless dominate power and interpretation. The primitive does not
  take absolute values, standardize, studentize, convert p-values or decide sides.

For each hypothesis, count the rows whose maximum is greater than or equal to its
observed score. Include exact ties; no hidden numerical tolerance. Return integer
counts, family size, resample count and `(count + 1) / (B + 1)`. The plus-one
convention prevents zero and exposes finite Monte Carlo resolution. The existing
strict adjusted-value `< alpha` rejection convention is used in diagnostics.

Null arrays, empty budgets, family mismatches, ragged rows and any nonfinite
observed/resampled score fail explicitly. No unavailable slot, failed replication
or inconvenient draw is dropped, and no successful partial result is returned.
This is deliberately narrower than a future production missing-value policy.
Inputs remain unchanged; returned arrays are separate from the inputs.

## What the denominator does and does not mean

The API is named for the Monte Carlo plus-one counting convention. Calling the
number an adjusted p-value is conditional on a valid construction of the supplied
joint reference draws and scores; an arbitrary bootstrap/null matrix does not
become inferentially valid merely by passing shape/finite checks.

For random permutations drawn with replacement under a justified randomization
null, identity can occur among the random draws. That is different from supplying
a complete exhaustive orbit already containing the observed assignment and then
adding it a second time while claiming an exact enumeration. Exact enumeration
uses its own orbit denominator.

A separate tiny fixture identity deliberately enumerates all assignments of six
entities to two groups of three. Taking each assignment in turn as the observation
and supplying the other assignments makes the plus-one arithmetic equal the exact
full-orbit tail count. This special count identity is not a general equivalence
between Monte Carlo and exhaustive sampling, and is not an implementation of a
production entity-permutation procedure.

## Independent checks and scientific gates

The Python oracle uses per-hypothesis union indicators and integer/Fraction
arithmetic, independently of the native row-maximum loop. It checks actual native
exports, integer counts, all adjusted values and strict decisions, with fixture
and actual Core-assembly provenance. Hand fixtures and tiny assignment orbits
exercise dependence, ties, negative scores, one-member families, boundary
resolution, ordering and common positive affine transformations. Native negative
checks reject missing/nonfinite/ragged inputs without reducing the budget/family.

Even exhaustive arithmetic over a toy exchangeable orbit cannot establish strong
partial-null FWER for MVS. Before integration, specify and validate:

1. The marginal/family/global hypotheses and score orientation/scaling.
2. The null generating mechanism and exchangeability assumptions at the entity
   level, preserving repeated measurements and shared resample indices.
3. Null-distribution validity under partial alternatives, including any required
   subset-pivotality or alternative justification for strong error control.
4. Availability/failure rules, seeds, budgets, Monte Carlo uncertainty and replay.
5. Family-label interpretation, across-family multiplicity and saved-state/version
   impact. Rank/distribution differences do not automatically identify a pure
   location/within-variability/between-heterogeneity change.
6. A frozen, unseen evaluation protocol before any confirmatory improvement claim.

The [Rempala and Yang study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3873102/)
explains why dependence-aware permutation arithmetic alone is insufficient for
arbitrary marginal strong control, and distinguishes joint from marginal nulls.
[Phipson and Smyth](https://arxiv.org/abs/1603.05766) discuss nonzero p-value
calculation for randomly drawn permutations. These primary references support the
stated cautions; they do not certify this project's resampling assumptions.
[Hemerik and Goeman](https://pmc.ncbi.nlm.nih.gov/articles/PMC6405018/) make the
group/null-invariance and random-draw conditions explicit: uniform sampling with
replacement from the group, or without replacement excluding identity, has a
different justification from arbitrary filtered draws. The toy fixtures remove
only the observed assignment index and retain equal-statistic assignments.
The [official multtest package](https://www.bioconductor.org/packages/release/bioc/html/multtest.html)
is a possible later external comparator; it was not installed or executed here.

## Verification record

Only executed results are recorded below. A future CI step is not local evidence.

### Executed results

- Native Core and CLI Release builds: PASS, zero warnings/errors, .NET SDK
  8.0.425 / runtime 8.0.31 on Linux.
- Native suite: **135/135 PASS**, including 16 new maxT groups covering hand
  counts, ties, finite extremes, resolution, order/scaling/family invariants,
  input preservation, all invalid slots and evidence-output preservation.
- Actual native export: **40 cases / 104 adjusted values PASS** against the
  independent integer/Fraction union-count reference, with exact binary64
  equality and strict rejection decisions. No tolerances were relaxed.
- Python: **319/319 PASS**, including 38 new maxT tests. The final checker was
  rerun after its robustness review. Existing 53 SciPy rank fixtures pass too.
- All 20 toy assignment/orbit identities pass. Strict any-rejection counts on
  that one complete-null toy at alpha 0.05, 0.1, 0.2, 0.25, 0.5 and 1 are
  respectively 0, 0, 0, 4, 8 and 18 of 20. These are exact finite-orbit counts,
  not Monte Carlo estimates or MVS error-rate validation. Supplying the full
  orbit to the plus-one API instead differs from exact enumeration in 18/20
  toy cases, which is explicitly tested.
- Actual CLI/Python analysis parity on the existing canonical calibration: PASS.
  Pre-maxT result JSON/CSV, availability CSV and saved-state bytes are exactly
  unchanged; scientific manifest fields match exactly. A fresh calibration or
  full development benchmark was not rerun for this unused helper.
- Source/identity, CLI contract, notebook, embedded payload and structural checks:
  PASS. Final guard and ZIP checks preserve every prior source/evidence file.

Fixture SHA-256:
`b1a18dea6cb95678cca8a8a95f980a0313a0f3eb2fbbcad5cd09e1205269bdcc`.
Tested Core SHA-256:
`0b5e856f110927c1d270a82da2fcecc13406b5645a16377db2a6d5e364d6725d`.

Evidence is `validation/maxt-native-round14.json` and
`validation/maxt-comparison-round14-final.json`. The initial comparison is retained
as `maxt-comparison-round14.json`; its numerical records are identical, while the
final checker adds explicit frozen-fixture-definition verification. Both passed.
Hashes bind supplied bytes, not external execution authenticity.

Reproduce after building the test project:

```sh
dotnet MvsAnalyzer.Core.Tests/bin/Release/net8.0/MvsAnalyzer.Core.Tests.dll --export-maxt-diagnostics validation/maxt-fixtures-v1.json NEW-native.json
python validation/maxt_reference.py --native NEW-native.json --core-assembly MvsAnalyzer.Core.Tests/bin/Release/net8.0/MvsAnalyzer.Core.dll --out NEW-comparison.json
```

Existing evidence paths are refused rather than overwritten. External R/multtest,
Windows/macOS execution and a new benchmark were not run. Step-down, production
integration and family-level automatic decisions remain pending their gates.
