# Round41: retained-data focused-family diagnostics

Protocol: `R41-RETAINED-FOCUSED-FAMILIES-1`. The executable specification is
`validation/focused-family-protocol-v1.json` in the full source archive. Validation-only
assets are intentionally not runtime-bundle dependencies.
This is a **post-hoc development analysis**, not a preregistered study or an
independent confirmation. The original 1.6.2 benchmark and later R27/R32 outcomes
remain unchanged. No new datasets, seeds, calibration draws or permutation draws
are authorized by this protocol.

## Question and prior exposure

How much of the observed detection/selection behaviour is attributable to the
scope of the question, instead of a defective interface or a newly superior
statistical test? Source inspection identifies a twelve-metric global correction,
a legacy single-winner score and a variability label mixing absolute and relative
spread. The latter changes under additive shifts through its denominator.

Before this execution specification was frozen, a read-only diagnosis inspected
location4/variability7 counts: location1.05 66 versus baseline35 of250; dispersion1.30
97 versus72 of250; primary null16/23 versus18 of1000. A two-family half-alpha
comparison gave42 and69 of250. Exact winner agreement27/120 and registered-family
agreement97/120 were also inspected. These observations motivated this diagnostic;
they are disclosed, not treated as unseen results. Freeze now prevents subsequent
selective omission or changes to the remaining comparison, not retrospective
preregistration.

## Fixed comparisons

Every retained vector receives all six diagnostics: twelve metrics, four location,
seven legacy variability, four absolute-spread, three relative-spread and RMS alone.
Metric membership/order is fixed from the existing registry and listed in JSON.
No condition name selects a preferred procedure. The family must be selected
before observing future analysis data if used for a focused question.

For each metric the adjusted value is `min(1,p*m)`, with a fixed full family
size and strict adjusted value below0.05. Unavailable slots retain that divisor.
A four-way disjoint partition (location/absolute/relative/magnitude) additionally
uses the direct multiplier `4*m`: an equal-family-budget weighted Bonferroni
comparison. Its total weights are one. It downweights location/absolute summaries,
leaves relative summaries at the original threshold and upweights RMS. It is not
a dependence correction. Its algebraic error-control interpretation still requires
valid marginal p-values under the corresponding nulls.

The uncorrected union of four focused decisions is shown only as an uncontrolled
post-selection diagnostic. It must not become the default automatic decision.
Legacy variability7 is a parent diagnostic, excluded from this disjoint union.

## Evidence and acceptance

All5,370 vectors are included:5,250 main cases from18 scientific conditions,
and60+60 separate determinism passes. Each has exactly12 metric rows and8
procedure rows. The120 stability splits are separately preserved. All input
hashes, identities and budgets are pinned in the machine specification.

The engineering gate requires complete, nonduplicated evidence; exact reproduction
of both archived Bonferroni and registry-corrected baseline decisions; and exact
agreement of native test-only and independent Python family arithmetic, including
availability, nulls, member decisions and floating-point boundary cases.
Failures/missing evidence are distinct. No p-value is fabricated. Requested
denominators and failed-case counts remain visible.

Report all conditions separately, Wilson95% intervals, paired gains/losses and
descriptive differences. There is no candidate-selection, scientific GO or
activation threshold. Do not pool null conditions or choose the best family by
the known injected condition.

## Stability and interpretation

Retained splits contain only two global winners and an aggregate stability
statistic, not full score vectors or calibration intervals. Therefore no focused
reranking, uncertainty-aware candidate set or within-family tau can be recovered.
Report winner confusion, family coarsening, marginal frequencies, expected
agreement under independent marginals, and Cohen kappa. Coarser agreement can rise
merely because many winners belong to the same broad category; it is not evidence
of improved selection. The saved statistic is retained as historical output,
without claiming independent validation of its implementation.

Deterministic native translation/scaling fixtures illustrate the interpretation:
absolute spread is translation invariant, relative spread is not; dimensional
summaries scale with units. They do not prove that a summary-distribution test
isolates a latent location or variance component. Geometric mean is not additive
translation-equivariant.

## Deployment and rollback

The implementation lives only under validation/. Production Core, formula hashes,
registry, saved-state schemas, CLI/Python/MCP inference and archived evidence are
unchanged. The isolated native project references the same Core and is not shipped
as an activated inference mode. Round40 is the rollback source. Runtime evidence
and all negative findings are retained. The project scientific NO-GO remains.
