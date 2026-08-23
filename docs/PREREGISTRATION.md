# Pre-registration of the validation programme

**Frozen:** 2026-08-23, before any of these experiments was run against the
application. **Engine at freeze time:** 1.2.0, formula `MVS-1.2.0`, hash
`70e1d5…e2f`. **Seeds:** datasets and reference simulation `20260823`,
application `CalibrationSeed = 20260719`.

Why this file exists: the fastest way to make a comparison study say what its
author wants is to run it, look at the result, and then decide what counted as
success. Writing the thresholds down first is the cheapest available defence,
and it is the one thing that separates a benchmark from a demonstration.

The protocol may be amended. Amendments are appended to the log at the bottom,
with a date and a reason, and the original text is never edited.

---

## Scope

This registers **what MVS Analyzer is measured against**, not what it is.
The object under test is the ranking the tool produces over ten entity-level
summary statistics, and the operating characteristics of the workflow that
ranking sits inside.

Out of scope for this round: the GUI, plugins, export integrity, and anything
about real-world data. Those are tested elsewhere or not at all.

---

## Data-generating mechanisms

Seven mechanisms, implemented once in `validation/dgp.py` and used both to
write the shipped datasets and to compute the reference truth table. Fixed in
advance:

| ID | Mechanism | Effect | Correct statistic, stated before running |
|---|---|---|---|
| A | additive normal, two variance components | +5 units | mean ≥ median |
| B | multiplicative lognormal, σ<sub>log</sub> = 0.45 | ×1.20 | geometric mean ≥ median > mean |
| C | normal + 12 % wide contamination | +4 units | median, MAD, IQR ≫ mean, SD, range |
| D | scale change only | ×2 SD | spread family only; level metrics at α |
| E | null | none | every metric at α |
| F | mechanism A, 4 entities × 6 measurements | +5 units | empty candidate set |
| G | coarse rounding, one constant entity | +2 units | relative metrics not applicable |

Two effect-size grids, both fixed before running:

- **primary** — the effect sizes above, matching the shipped CSV files.
- **discriminating** — every effect shrunk (A +2.0, B ×1.07, C +1.5, D ×1.20
  SD) so that the best statistic lands in the 0.3–0.8 power band. Rankings are
  judged here, because at ceiling power every ordering looks equally good.

Sample sizes are fixed at 20 entities × 20 measurements (16 × 16 for E) and are
not tuned after seeing results. Deviations go in the log.

---

## Estimands and performance measures

For each mechanism and each of the ten metrics:

- **Reference power** — rejection rate of a two-sided Mann–Whitney U test on
  entity-level values, α = 0.05, over 2 000 replications (4 000 for the null).
  Monte-Carlo standard error ≤ 1.2 pp; differences below ~2.5 pp are not
  interpreted.
- **Reference FPR** — the same quantity under mechanism E.
- **Selection FPR** — probability that *at least one* of the ten metrics is
  significant under E. This is the honest upper bound on what looking at the
  whole table costs.

For the application:

- **Rank agreement** — Kendall's τ between the app's score ordering and the
  reference power ordering.
- **Top-1 agreement** — whether the app's highest-scoring metric is in the
  reference top group.
- **Weight sensitivity** — top-1 stability, pairwise rank-flip rate and
  Kendall's τ across weighting schemes (equal, rank-order centroid,
  power-only, false-alarm-first, arithmetic aggregation, and 5 000 Dirichlet
  draws at concentration 50).
- **Discriminant validity** — Spearman correlation between `mvs_score` and the
  power component.

---

## Hypotheses and thresholds

Stated as pass/fail before the fact. "Pass" is not evidence that the tool is
good; it is only the absence of this particular failure.

| ID | Claim under test | Passes if | Fails if |
|---|---|---|---|
| H1 | Under contamination the tool prefers robust statistics | on C, every one of `median`, `mad`, `iqr` outranks every one of `mean`, `rms`, `standard_deviation` | any mean-family metric outranks any robust one |
| H2 | The tool does not invent effects in the wrong family | on D, no level metric (`median`, `mean`, `rms`) is reported as a candidate | a level metric is a candidate |
| H3 | The tool respects the classic efficiency ordering | on A, `mean` is not ranked more than two places below `median` | `mean` ranked ≥ 3 places below `median` |
| H4 | The score is not a relabelled power column | Spearman(`mvs_score`, power) < 0.95 on at least three of A–D | ≥ 0.95 everywhere |
| H5 | The ranking is data-driven, not weight-driven | top-1 metric unchanged in ≥ 80 % of Dirichlet draws | < 80 % |
| H6 | The workflow does not silently inflate error rates | measured selection FPR over the ten null replicates is reported, whatever it is, in `docs/VALIDATION.md` | it is not reported |
| H7 | Degenerate input degrades gracefully | on F: empty candidate set, no crash. On G: relative metrics flagged `not_applicable` | a recommendation is issued on F, or a number is invented on G |

H6 has no threshold on purpose. The number is what it is; hiding it would be
the failure.

---

## Analysis plan

1. Run the reference simulation on both grids. Publish both tables verbatim,
   including the rows that contradict the a priori expectation.
2. Run the application once per dataset at default settings; export
   `results.csv`; record the full ranking, not just the top metric.
3. Run `validation/analyze_results.py` on each exported `results.csv`.
4. Run the ten null replicates and count: (a) runs where the top-scoring
   metric is significant, (b) runs where any metric is significant.
5. Repeat one dataset with three different calibration seeds and report
   Kendall's τ between the three rankings.
6. Write every number into `docs/VALIDATION.md`, pass or fail, before any
   change is made to the engine in response.

Step 6 is the load-bearing one. Results are published before remedies.

---

## What would make us abandon the composite

Named in advance, so the decision is not made under pressure later:

- Top-1 stability under Dirichlet weights below 50 % on a majority of the
  mechanisms — the ranking would then be a statement about the weights.
- Spearman(`mvs_score`, power) ≥ 0.95 on every mechanism — four of the five
  components would be doing nothing.
- H1 failing — the tool would be worse than the textbook it is trying to
  operationalise.

---

## Amendment log

| Date | Change | Reason |
|---|---|---|
| 2026-08-23 | Initial version. | Written before the first run. |
