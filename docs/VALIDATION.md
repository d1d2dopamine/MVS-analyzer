# Validation programme

What this document is: the list of ways MVS Analyzer could be wrong, turned
into experiments with numbers attached. What it is not: evidence that the tool
works. Most of the experiments below have been designed and their reference
values computed; the runs against the application itself are still open, and
the results table says so honestly.

The thresholds were fixed before the first run — see
[PREREGISTRATION.md](PREREGISTRATION.md). The datasets, the mechanisms and the
scripts are in [`validation/`](../validation/README.md).

- [Why this exists](#why-this-exists)
- [The reference truth table](#the-reference-truth-table)
- [What the truth table already taught us](#what-the-truth-table-already-taught-us)
- [The experiments](#the-experiments)
- [Results so far](#results-so-far)

---

## Why this exists

A public review of the project in August 2026 made four points that could not
be answered by argument:

1. A summary statistic should be chosen *a priori* from the structure you
   expect the data to have. Searching for the best one on the data itself is
   inference in reverse.
2. The coefficients in the score are arbitrary and materially change the
   result.
3. The score has no units, and nobody said what it is on a scale of.
4. A score that claims to behave in a particular way has to be shown to behave
   that way, rigorously.

Points 1 and 3 are answered in [METHODS.md](METHODS.md) — in the
[modes](METHODS.md#three-modes-and-only-one-of-them-is-safe) section and the
[dimensional analysis](METHODS.md#dimensional-analysis-and-what-the-scale-is).
Points 2 and 4 need measurement, and measurement is what this document plans.

---

## The reference truth table

An independent Monte-Carlo implementation — `validation/reference_simulation.py`,
which shares no code with the engine — answers the only question that makes
"the best metric" meaningful: **in a world whose structure we fixed ourselves,
which entity-level statistic actually detects the effect most often?**

Method: 2 000 replications per mechanism (4 000 for the null), two-sided
Mann–Whitney U on entity-level values, α = 0.05. Monte-Carlo standard error is
at most 1.2 pp, so differences under ~2.5 pp are noise. Rows marked \* are
**not implemented in the engine** and are shown because a truth table should
include what you are missing.

### Primary grid (the effect sizes in the shipped datasets)

| Metric | A additive | B multiplicative | C heavy tails | D scale only | E null |
|---|---|---|---|---|---|
| `median` | 0.981 | 0.927 | **0.926** | 0.048 | 0.051 |
| `mean` | **0.988** | 0.959 | 0.578 | 0.051 | 0.054 |
| `rms` | 0.988 | 0.936 | 0.564 | 0.071 | 0.054 |
| `standard_deviation` | 0.049 | 0.536 | 0.058 | **1.000** | 0.047 |
| `coefficient_of_variation` | 0.140 | 0.049 | 0.065 | 1.000 | 0.046 |
| `mad` | 0.059 | 0.396 | 0.053 | 1.000 | 0.052 |
| `iqr` | 0.053 | 0.411 | 0.052 | 1.000 | 0.052 |
| `normalized_mad` | 0.082 | 0.046 | 0.073 | 1.000 | 0.050 |
| `normalized_iqr` | 0.073 | 0.051 | 0.062 | 1.000 | 0.051 |
| `range` | 0.051 | 0.430 | 0.058 | 1.000 | 0.043 |
| `geometric_mean` \* | 0.990 | **0.962** | n/a | 0.070 | 0.054 |
| `trimmed_mean_20` \* | 0.986 | 0.950 | 0.934 | 0.050 | 0.051 |
| **any of the ten** | 0.994 | 0.976 | 0.946 | 1.000 | **0.205** |

### Discriminating grid (effects shrunk to keep power off the ceiling)

A +2.0 units, B ×1.07, C +1.5 units, D ×1.20 SD. Ranking claims are judged
here: when everything detects everything, every ordering looks equally good.

| Metric | A additive | B multiplicative | C heavy tails | D scale only | E null |
|---|---|---|---|---|---|
| `median` | 0.375 | 0.215 | **0.241** | 0.055 | 0.050 |
| `mean` | **0.406** | 0.247 | 0.114 | 0.048 | 0.048 |
| `rms` | 0.406 | 0.222 | 0.113 | 0.050 | 0.049 |
| `standard_deviation` | 0.048 | 0.103 | 0.052 | **0.917** | 0.051 |
| `coefficient_of_variation` | 0.070 | 0.041 | 0.051 | 0.910 | 0.048 |
| `mad` | 0.041 | 0.099 | 0.057 | 0.536 | 0.046 |
| `iqr` | 0.047 | 0.099 | 0.056 | 0.559 | 0.044 |
| `normalized_mad` | 0.052 | 0.051 | 0.060 | 0.530 | 0.048 |
| `normalized_iqr` | 0.055 | 0.054 | 0.063 | 0.547 | 0.049 |
| `range` | 0.049 | 0.091 | 0.048 | 0.800 | 0.052 |
| `geometric_mean` \* | 0.406 | **0.256** | n/a | 0.047 | 0.048 |
| `trimmed_mean_20` \* | 0.399 | 0.242 | 0.240 | 0.052 | 0.049 |
| **any of the ten** | 0.541 | 0.443 | 0.397 | 0.954 | **0.202** |

---

## What the truth table already taught us

These are findings about the design of the tool, produced before the tool was
run. Four of the seven contradict something the project previously assumed.

**1. Looking at all ten metrics costs about four times the nominal error rate.**
Under the null, each individual metric sits where it should (0.043–0.054).
But the probability that *at least one* of the ten fires is **0.205** — the
same 0.20 on both grids. That is the price of the table, not of any metric in
it. It is an upper bound on what the app's own selection costs, because the app
selects on calibration components rather than on the observed *p*-value; the
lower bound is the nominal 0.05. Experiment **V2** measures where the app
actually lands. Whatever it is, it belongs in the UI, not in a footnote.

**2. The geometric mean is missing, and it wins exactly where it should.**
On the multiplicative mechanism it is the best statistic on both grids
(0.962 / 0.256), ahead of every implemented metric. It costs one line of code
and it is the textbook answer for multiplicative processes. Not shipping it
while claiming to search for the best metric is a real gap.

**3. The median does *not* beat the mean under lognormality, and our intuition
was wrong.** The expected result was median > mean for a multiplicative
process. Measured: mean 0.247, median 0.215 on the discriminating grid. The
reason is structural — Mann–Whitney on entity-level summaries is invariant to
monotone transformation, so raw-scale skew alone does not hurt the mean; what
matters is the sampling variability of the per-entity statistic, and at 20
measurements per entity the mean is still efficient. The consequence is
sharper than the finding: **the power component cannot see the distinction
that motivated the criticism.** Choosing the geometric mean over the mean for
lognormal data is about the estimate and its interpretation — bias, variance,
what the number means — not about the rejection rate of a rank test. A score
built only on rejection rates is structurally blind to it, which is why
estimation quality (bias, MSE, relative efficiency) is on the roadmap as a
sixth and seventh component.

**4. Under a multiplicative effect, "level" and "spread" are not separable.**
On mechanism B the spread metrics pick up the effect too (SD 0.536, range
0.430, IQR 0.411) because multiplying the data multiplies its dispersion. The
family taxonomy in [METHODS.md](METHODS.md#entity-level-metrics) is a property
of the metric, not of the effect, and the UI should stop implying otherwise.

**5. Relative metrics respond to pure level shifts.** On mechanism A, an
additive shift with unchanged dispersion still gives `coefficient_of_variation`
0.140 — nearly three times α — because the denominator moved. Correct
behaviour, easily misread as a spread effect.

**6. RMS leaks across families.** On the pure scale change, `rms` shows 0.071
against the 0.05 baseline, as it must: RMS² = mean² + variance. It is a level
metric with a spread term inside it.

**7. A ranking computed at ceiling power is not identified.** On the primary
grid, six metrics score 1.000 on mechanism D and four sit above 0.92 on A.
Any ordering among them is noise. This is a product bug as much as a study
design issue: when every applicable metric exceeds ~0.9 power, the app should
say *the ranking is not identified at this effect size* instead of printing a
leaderboard.

---

## The experiments

### V1 · Recovery of known ground truth

**Question.** In worlds where the correct statistic is known by construction,
does the tool rank it first?

**Procedure.** Run the app at default settings on `A`, `B`, `C`, `D`; export
`results.csv`; compare the score ordering with the discriminating-grid table
above using Kendall's τ and top-1 agreement.

**Passes if** H1 and H2 hold: on C every robust metric outranks every
mean-family metric, and on D no level metric is a candidate.

**If it fails**, the premise fails with it. A tool that cannot reproduce what
theory already knows has no business being used where theory is silent — and
that is the answer to the reviewer's central point, in whichever direction it
comes out.

### V2 · False-positive rate of the whole pipeline

**Question.** You choose a metric with this tool and then report that metric's
*p*-value. What is the real error rate of that sentence?

**Procedure.** Run all ten `E_null_*.csv` replicates at default settings. For
each run record: the top-scoring metric, its `global_p`, and whether any metric
has `global_p < 0.05`. Then repeat the whole thing with split calibration
enabled (Settings → Scientific rigour), which is the proposed remedy.

**Expected.** Roughly 2 of 10 runs should contain at least one significant
metric (reference: 0.205). If the top-scoring metric is significant far less
often than that, MVS-based selection is *less* dangerous than eyeballing the
table — which would be worth knowing and worth saying.

**Reported regardless of outcome.** Ten replicates give a standard error of
about 13 pp, so this is a smoke test, not an estimate; the full estimate needs
the experiment run inside the engine over thousands of replications.

### V3 · Weight sensitivity

**Question.** How much of the ranking is the data and how much is the weight
vector `0.30 / 0.25 / 0.20 / 0.15 / 0.10`?

**Procedure.** `python3 validation/analyze_results.py <run>/results.csv`.
Reports top-1 stability across 5 000 Dirichlet draws, the pairwise rank-flip
rate, Kendall's τ against equal weights, rank-order-centroid weights,
power-only weights, false-alarm-first weights, and arithmetic instead of
geometric aggregation.

**Passes if** H5 holds: top-1 unchanged in ≥ 80 % of draws. This is the
uncertainty-analysis step of the OECD/JRC composite-indicator protocol, and it
is the only honest reply to "your coefficients are arbitrary": they are, and
here is how much that matters.

### V4 · Discriminant validity

**Question.** Does the composite say anything the power column does not?

**Procedure.** Section 4 of the same script: Spearman and Kendall correlation
between `mvs_score` and the power component across metrics, on every dataset.

**Passes if** the correlation is below 0.95 somewhere. If it is 0.98
everywhere, the composite is a relabelled power column and four components are
decoration — the right response then is to delete them, not defend them.

### V5 · Stability across seeds

**Question.** Is the ranking reproducible, or is it resampling noise?

**Procedure.** Run `A_normal_additive.csv` three times with
`CalibrationSeed` = 20260719, 20260720, 20260721. Compute Kendall's τ between
the three rankings.

**Passes if** τ ≥ 0.8 for every pair. Below that, the reported ranking is not
a property of the data and the repetition count must go up.

### V6 · Graceful degradation

**Question.** What does the tool do when there is not enough data, or when the
data is degenerate?

**Procedure.** Run `F_small_n.csv` (4 entities × 6 measurements) and
`G_ties_zero_spread.csv` (heavy ties, one perfectly constant entity per group).

**Passes if** F yields an empty candidate set and `insufficient` verdicts, and
G flags the relative metrics `not_applicable` on the constant entity rather
than producing a number. No crash in either case.

---

## Results so far

| Experiment | Reference values | Run against the app | Verdict |
|---|---|---|---|
| V1 recovery | computed, both grids | not yet | open |
| V2 pipeline FPR | upper bound 0.205 | not yet | open |
| V3 weight sensitivity | script ready | not yet | open |
| V4 discriminant validity | script ready | not yet | open |
| V5 seed stability | — | not yet | open |
| V6 degenerate input | datasets ready | not yet | open |

This table is updated with numbers, not adjectives, and it is updated before
any change is made to the engine in response to a failure.

---

## References

- Morris, White & Crowther (2019), *Using simulation studies to evaluate
  statistical methods*, Statistics in Medicine 38(11) — the ADEMP structure
  used in [METHODS.md](METHODS.md#simulation-study-design).
- OECD/JRC (2008), *Handbook on Constructing Composite Indicators*, Step 8 —
  uncertainty and sensitivity analysis of weights.
- Saisana, Saltelli & Tarantola (2005), JRSS-A 168(2) 307–323 — variance-based
  sensitivity analysis for composite indicators.
- Berk et al. (2013), *Valid post-selection inference*, Annals of Statistics
  41(2) — why a *p*-value reported after a data-driven choice is not the
  *p*-value you think it is.
- Gelman & Loken (2013), *The garden of forking paths*.
- Boulesteix et al. (2013), *A plea for neutral comparison studies*, PLOS ONE
  8(4) — why the author of a method is the worst person to benchmark it, and
  what to do about that.
