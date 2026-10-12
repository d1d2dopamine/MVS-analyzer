# MVS current readiness and next decision

## What is ready

The current deliverable is a reproducible **development source checkpoint** of the
CLI/Python-first architecture. The maintained stack is one .NET statistical engine
behind a versioned machine protocol, with Python as a wrapper. It is not a compiled
release or a declaration that MVS 1.5.0 has met its scientific release criteria.

Completed work includes observed-applicability verification, per-replication
benchmark diagnostics, the full development baseline and its reconciliation,
independent staged Huber validation and numerical repair, internal Holm and maxT
arithmetic checks, evidence/checkpoint safety, concrete CLI input-loss and Python
launch-error repairs, release-layout/gate alignment, and bounded resource and
cancellation observations. Each stage has its own report and complete source ZIP.
Historical evidence, including failed numerical cases and the development NO-GO,
remains available rather than being replaced with later passing results.

The final existing-interface audit is documented separately in
[round 18](ROUND18_SCIENTIFIC_INTERFACE_AUDIT.md). The final full Python suite passed 440 tests; its 16 actual scientific-interface
CLI/Python pairs passed, and a reproduced input-error classification
bug was repaired. These outcomes are wrapper/export consistency, not independent
certification of variance, estimation or experimental MELSM models. Its original
process-tree memory sampler was unavailable in this sandbox; that limitation is
retained separately from the passing scientific comparisons.

## Scientific result that still governs readiness

The complete BENCH-1.2.0 development run completed **5,490/5,490 work units** without
failed units. Its scientific outcome remains **NO-GO**: A/D/E passed, B (power)
failed and C (stability) was inconclusive. The tested protocol has already informed
development and cannot become unseen validation by changing its label.

Holm increases some metric-member discoveries but has exactly the same
any-rejection event as fixed-family Bonferroni. The extra member findings include
false positives under the global null. This does not solve the measured global
power gap. maxT currently performs tested arithmetic on supplied finite matrices;
it has no validated production null generator and is not activated.

The active scientific engine remains **1.6.2**, with the legacy **12 metrics**,
**Bonferroni** correction and formula **MVS-1.4.0**. Huber, Hodges–Lehmann, Qn and
log-SD remain staged. Numerically repairing Huber is not authorization or evidence
for activating it as a confirmatory method.

## One substantive choice before the next dependent stage

**What should an automatic family finding actually claim?**

1. **Distributional differences in entity summaries.** For example, a location
   family summarizes differences in distributions of entity location summaries;
   it does not prove that only an underlying mean changed. This is closest to the
   existing summary-metric/rank-test architecture.
2. **Isolated data-generating component changes.** For example, a finding would
   specifically concern mean, within-entity variability or between-entity
   heterogeneity while allowing other components to vary. This needs explicitly
   chosen models/nulls and independent validation against confounding component
   changes; the existing rank-summary path does not establish this interpretation.

**Recommendation:** retain the current architecture and first specify the narrower
entity-summary distributional claim, with clear interpretation limits. A global
joint-distribution test under an explicitly justified entity-label exchangeability
assumption can be a development comparator, with family descriptors initially
reported descriptively. Do not present that comparator as isolated component
identification, or silently substitute it for the second goal.

This recommendation is a proposal, not an activated scientific decision. Once the
intended claim is chosen, the method specification must still fix statistics and
orientation, entity-level joint resampling, complete-null versus strong partial-
null guarantees, unavailable/failure handling, across-family correction and the
relationship of exploratory calibration to confirmatory inference. Step-down
arithmetic alone does not supply these guarantees.

Only after those definitions are frozen should implementation deliberately change
method/version/state/result identity. Then freeze acceptance criteria and run a
new **BENCH-2.0** with unseen seeds and broader conditions, retaining every outcome.
Do not choose seeds, remove failed cases or relax gates to obtain a passing result.

## Operational boundaries and external evidence

- With a nonexistent synthetic `XDG_DATA_HOME`, this Linux environment returned
  an empty .NET application-data path and the existing journal fell back to the
  working directory. The new synthetic entries were preserved outside source.
  Create isolated runner data directories before execution; a robust application
  journal-location fallback remains a separate operational repair.
- Current output preflight protects demonstrated predictable input collisions and
  obstructions. It does not make multi-file output transactional or eliminate
  concurrent filesystem races. Unexpected mid-write failure remains a separate
  output-transaction design problem, requiring a risk/rollback plan.
- The one resource profile observed at most 68.6 MiB RSS and a 13.52-second largest
  calibration at 15,000 rows/100 repetitions. One SIGINT cancellation succeeded.
  These shared-host observations are not a capacity guarantee, broad scaling
  study or assurance of cancellation during every phase.
- Windows/macOS runtime, live Colab/desktop behavior and independent external
  model comparisons were not executed here. Retired desktop hash pins were not
  weakened or relabeled as passing maintained-interface tests.
- Public metadata identifies the best-supported historical paper source revision,
  but original Actions artifact download returned an authentication requirement.
  Source/build/output binding remains unverified. If that provenance check is
  pursued, request only the access needed to read the specific archived artifact;
  no commit/push permission or persistent credential is needed merely to inspect it.
- Workflow edits and local package-layout checks are not an executed remote CI run
  or a published release. No commit, push, tag, remote workflow or release was made.

## Stopping criterion for this development session

After the bounded resource and existing-interface audits, stop at the scientific
claim/null specification gate. More unused resampling layers, repeated successful
checks, or reruns of the already-used development benchmark would add activity
without establishing the missing scientific readiness. Resume dependent work when
the intended claim and its validation assumptions are decided, or when new concrete
failure evidence supports a separately bounded safe repair.
