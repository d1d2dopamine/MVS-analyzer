# R27-GLOBAL-MAXRANK-DEV-1: isolated development comparison

Status: statistical specification frozen before scientific pilot; arithmetic preflight and implementation checks are ongoing. No scientific pilot or
held-out evaluation is represented by this document's presence. The accompanying
`validation/global-rank-development-v1.json` records the exact machine settings.
This delivery was renumbered from the proposed R26 experiment after an intervening
Windows repair; RNG coordinates 26/27/28 remain unchanged.

## Question and claim

For two independent groups, can a prespecified maximum of twelve entity-summary
rank contrasts improve the reused-development rejection behavior relative to the
shipped raw twelve-member Bonferroni event? The null is equality of the complete
entity-summary distributions under exchangeability. This is not a test that
isolates latent location, within-entity variance or between-entity variance.
It does not identify individual metric discoveries or establish equivalence.
The maximum rank-location statistic is not sensitive to every joint-distribution
alternative: dependence-only and some symmetric shape changes may escape it.

Use unchanged AnalysisEngine.Build bounds ±1,000,000, minimum six measurements,
exactly two groups with at least four retained entities each. Keep twelve legacy
metrics in registry order. All summary slots must be finite; any unavailable slot
fails the whole candidate case. The synthetic expected entity counts must remain
intact. Do not drop failed cases, redraw inputs or change family size.

## Statistic and permutations

For each pooled metric column compute average ranks for exact equal values.
Let a_i=2*r_i−(N+1), D=sum of a_i over the case group, Q=sum of all a_i².
The score is D²*N*(N−1)/(n_case*n_control*Q), with a constant column Q=0 scored 0.
This is algebraically the squared rank-sum deviation divided by its tie-corrected
null variance. No continuity correction is applied.

Pre-run arithmetic amendment: integer ranks and exact rational comparisons define
maxima and inclusive ≥ tails. Doubles and the existing unused MaxT helper must
match exact score ordering and all exceedance counts; any disagreement blocks
execution/interpretation. No tolerance may erase a tie disagreement. The harness
bounds N≤128 and checks arithmetic; this is a test-harness scope, not a production
input limit. The current designs use 32 or 40 entities.

Each dataset gets 999 uniform fixed-size label assignments. Every Fisher–Yates
shuffle starts from identity and uses BenchmarkRandom.Next's unbiased bounded
sampler. Assign the first n_case indices to the case group and share that label
assignment across all twelve columns. Identity assignments and duplicates are
allowed. Data generation and label RNG streams are independent.

Global p=(1+count(random maximum≥observed maximum))/1000. Strict p<.05 permits
at most 48 exceedances. Same-draw marginal p_j uses each metric's own score; its
Bonferroni-12 event requires a count≤3. Fixed-median(index 0) and fixed-CV(index 2)
comparators use those same marginal permutation p-values with strict p<.05.
Shipped comparison uses unchanged asymptotic Mann–Whitney with its continuity
correction and twelve-member Bonferroni. No calibration, ranking/selection policy,
Holm activation or oracle-power claim is introduced.

Candidate-versus-marginal-Bonferroni differences combine joint maximum calibration,
dependence and the coarse Monte Carlo grid. They cannot all be attributed to
exploiting dependence. Costs of shared preprocessing, shipped-only inference and
candidate inference must be reported separately.

## Exact arithmetic and replay gates

Freeze literal inputs, then compute independent Python Fraction oracle outputs,
freeze those outputs, then compare native output. Primary tiny matrices use 4+4,
4+5 and 5+5 entities (70/126/252 complete assignments). Include distinct/tied/constant,
duplicate/reversed/differently ordered and strongly dependent columns. Include
nonzero cross-column equal scores with genuinely different tie-variance
denominators, beyond trivial duplicate/reversed ties.

For every assignment as observed compare exact scores/order, global/marginal/max
inclusive tail counts and decisions. Exact-orbit p=count/orbit size, including the
observed assignment once, with no extra plus-one. Existing MonteCarloSingleStep
with every other assignment once must produce that exact-orbit result. Check
row/column ordering and group-label reversal, all-constant p=1, invalid entire
arrays, and raw-measurement fixtures through unchanged summaries/Build.
Zero oracle mismatches are required. Reconstruct the prespecified archived
replications and verify seeds, all shipped p-values and rejection events against
archived evidence before evaluating the candidate. Zero unexplained replay
mismatches are required. This is reused development, not unseen validation.

## Fixed development matrix

Data master 20260904; Derive(master,data stage,data stream,index).
Indices start 0 and continue to count−1:

| Ordinal | Archived condition | Count | Stage/stream |
|---|---|---:|---|
|0|primary_null, gait heavy-tail|200|1/1|
|1|shape_normal_null, gait normal|200|4/0|
|2|robust_null_10, gait heavy-tail10%contamination|200|3/1|
|3|design_voice_null, voice lognormal|200|4/12|
|4|power_location_105, gait location1.05|250|2/1|
|5|power_dispersion_130, gait dispersion1.30|250|2/1|

Reuse the exact BenchmarkDatasets generator, floors and draw consumption. The two
power conditions deliberately share underlying data streams. Label seed is
Derive(2026102601,26,conditionOrdinal,index). Total 1300 datasets, 999 draws each.
At most two workers, 1 GiB per-process RSS watchdog, 20-minute pilot wall limit.
Limits retain incomplete/failure evidence; no smaller run substitutes for the plan.

## Frozen reporting and development screens

All four null conditions are reported separately using two-sided 95% Wilson
intervals. Eligible upper bound≤.10; material-inflation stop if lower bound>.075;
otherwise inconclusive. These screens do not certify nominal .05 control.

For each power condition publish candidate-versus-shipped and candidate-versus-
marginal-permutation discordance tables. Let b=candidate-only and c=comparator-only
rejections among n=250. Delta=(b−c)/n. Construct separate two-sided 97.5%
Clopper–Pearson intervals for b/n and c/n: beta quantiles .0125 and .9875 with
usual zero/all boundaries. Report [L(b)−U(c),U(b)−L(c)]. The union bound provides
at least 95% marginal coverage for each paired difference without assuming the
counts independent. Four such intervals are not simultaneous 95% intervals.

Exact one-sided McNemar p=sum(k=b..b+c)choose(b+c,k)/2^(b+c), or 1 when b+c=0.
The label “promising” requires every oracle/replay/availability gate, all four
null eligibility gates, candidate-minus-shipped delta≥0 in both power conditions
and ≥.05 in at least one. “Pilot evidence of improvement” additionally requires
McNemar p<.025 for at least one of the two prespecified candidate-versus-shipped
endpoints. Secondary comparisons are descriptive. A strong paired difference
cannot override a failed validity/null gate. Report missing-outcome bounds using
the full planned denominator; missing is never silently no-rejection.

## Untouched evaluation remains blocked

Reserve data master 2026102602/stage 27 and permutation master 2026102602/stage 28
with the same condition ordinals, counts and B. Do not generate those data until
independent evaluation acceptance/interpretation is separately frozen after the
development review. Same-family independent draws still would not establish
external generalization or component identification. There is no held-out mode
in this implementation. Production activation and scientific GO are outside scope.

## Reproducibility and rollback

Keep source/protocol/fixture/binary/runtime hashes, entity matrices/order, both
seeds, observed scores, counts, label-draw digests, every decision and failure,
per-case timing/memory, and complete denominators. Preserve all original evidence.
The harness is separate from production projects and has no automatically invoked
scientific mode. Existing engine calculations, fingerprints and NO-GO remain
unchanged; the preceding source checkpoint is the rollback.

Frozen literal fixture SHA256: `6deb504907cca453a000caa3433da3cd45a2a8556dd8d12c6e732616e5400c78`.
Independent expected exact-orbit output SHA256: `e289eb7f06478f4a96ff2b75eaf97a1f311de7c4f67c6efca8f313dc35607cb5`.
The consolidated freeze record was written during arithmetic preflight. Independent
expected outputs were generated from literal inputs before native comparison.
The first native arithmetic comparison started approximately14:23:13UTC,
while the consolidated record was written14:23:23.835UTC. Thus no stronger
prospective-registration claim is made. No simulated development case had run.
Scalar independent-oracle numeric values use the preexisting2e-13absolute and
relative tolerance; all count, ordering and tie comparisons remain exact.
