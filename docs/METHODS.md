# Methods

Everything the engine computes, in the order it computes it. Implementation: `AnalysisEngine.cs` (engine version **1.2.0**), frozen specification: `OutputExporter.cs`.

- [Three modes, and only one of them is safe](#three-modes-and-only-one-of-them-is-safe)
- [Simulation study design](#simulation-study-design)
- [Entity-level metrics](#entity-level-metrics)
- [Statistical tests](#statistical-tests)
- [Calibration](#calibration)
- [The MVS Score](#the-mvs-score)
- [Candidate rules](#candidate-rules)
- [Effect size](#effect-size)
- [Verdicts](#verdicts)
- [Minimum detectable effect](#minimum-detectable-effect)
- [Determinism](#determinism)
- [Assumptions and limits](#assumptions-and-limits)
- [Open methodological questions](#open-methodological-questions)

---

## Three modes, and only one of them is safe

The engine does one thing: it measures how ten summary statistics behave on data shaped like yours. What that measurement *means* depends entirely on **when** you run it, and the same output supports three very different claims.

| Mode | When you run it | What the output licenses |
|---|---|---|
| **Design** | before the real analysis, on pilot or simulated data | a pre-specified choice of statistic, made from the structure you expect the data to have. Fully legitimate. |
| **Multiverse** | after a pre-specified analysis | a robustness display: here is how the conclusion moves across every reasonable statistic. Legitimate, and more informative than one number. |
| **Exploratory** | on the same data you are going to report | a hypothesis, not a result. |

The failure mode this design has to be honest about: pick the statistic *because* it scored best on this dataset, then report that statistic's *p*-value as if it had been fixed in advance. The nominal error rate does not survive that, and the cost is measurable. Under a pure null, the probability that at least one of the ten metrics comes out significant is **0.205**, not 0.05 — see [VALIDATION.md](VALIDATION.md#the-reference-truth-table).

That number is an upper bound on what this tool costs you, because the ranking is computed from calibration components rather than from the observed *p*-value. The lower bound is the nominal 0.05. Where the tool actually sits between them is experiment V2 in [VALIDATION.md](VALIDATION.md#the-experiments), and it is not answered yet.

Two remedies exist today, one is planned:

- **Split calibration** (Settings → Scientific rigour) selects the metric on one half of the entities and reports on the other. This is the honest way to run the exploratory mode.
- **Pre-registration** of the metric before looking. The tool cannot enforce it; the manifest can record it.
- **Planned for 1.4.0:** the mode is chosen explicitly when a project is created, and exploratory runs are labelled as such in every export.

Version 1.3.3 never asks which mode you are in. It should, and until it does, the safe assumption in any report is *exploratory*.

---

## Simulation study design

Calibration is a simulation study, so it is described the way simulation studies are described — the ADEMP structure of Morris, White & Crowther (2019). A reader who has seen one methods paper can then audit the design instead of reverse-engineering it from the source.

**Aims.** For each candidate summary statistic, on data with the structure of the user's file, estimate its false-alarm rate, its power against a declared effect, its stability under contamination, its split-half repeatability and the coverage of its bootstrap interval; then rank the statistics by a declared aggregation of those five quantities.

**Data-generating mechanisms.** Resampling of the user's own rows rather than a parametric model. The null world pools all groups and redraws synthetic groups of the original sizes; the effect world does the same and then applies the configured multiplier to the last group. Configured contamination (default 2 % outliers) and missingness (default 0 %) are applied to the raw values before the metrics are recomputed. Entities — never individual measurements — are the resampling unit.

**Estimands.** Two, and they are different things. Per metric: the group-level value of that statistic. Per comparison: the between-group contrast, reported as Cliff's delta on entity-level values. The five components of the score are properties of the *procedure*, not estimands of the data.

**Methods.** Ten entity-level reductions crossed with one global rank test (Mann–Whitney for two groups, Kruskal–Wallis for three to ten).

**Performance measures.** False-alarm rate and power as rejection rates at α; robustness as stability under injected contamination; repeatability as split-half agreement over 50 splits; coverage as the empirical coverage of the 95 % bootstrap interval over 200 × 200 resamples. At the default 5 000 repetitions the Monte-Carlo standard error of a rate near 0.05 is about 0.3 pp, and near 0.5 about 0.7 pp — so differences of one or two points between metrics are noise, and the UI should stop presenting them as a ranking.

**The known weakness of this design.** Mechanisms derived from the user's own data inherit that data's idiosyncrasies and cannot represent a world the file does not contain. If your file has no heavy tails, the robustness column cannot tell you which metric would survive them. Real-data-based simulation is convenient and partly circular; the fixed synthetic mechanisms in [`validation/`](../validation/README.md) exist precisely to cover the part it cannot.

---

## Entity-level metrics

Each entity (device, sample, participant, machine…) contributes its repeated measurements. The engine reduces them to **one value per entity per metric**, and every downstream test is run on those entity-level values — never on raw measurements pooled across entities. That is what keeps repeated measurements from being counted as independent observations.

| Key | Definition | Family |
|---|---|---|
| `median` | 50th percentile | level |
| `mean` | arithmetic mean | level |
| `rms` | root mean square | level |
| `standard_deviation` | sample SD | spread |
| `coefficient_of_variation` | SD / mean | spread, relative |
| `mad` | median absolute deviation | spread, robust |
| `iqr` | Q3 − Q1 | spread, robust |
| `normalized_mad` | MAD / median | spread, robust, relative |
| `normalized_iqr` | IQR / median | spread, robust, relative |
| `range` | max − min | spread, maximally fragile |

A metric is marked **not applicable** when it cannot be defined for the data — for example a relative metric on values centred at zero. Not-applicable metrics are reported, not silently dropped.

---

## Statistical tests

| Groups | Test | Reported |
|---|---|---|
| 2 | Mann–Whitney *U* | global *p* |
| 3–10 | Kruskal–Wallis *H* | global *p* |

Both are rank-based, so they do not assume normality — which matters, because most of the metrics above are not normally distributed even when the raw measurements are.

> [!NOTE]
> With three or more groups the global *p* answers **"is there any difference among the groups?"**, not **"which pair differs?"**. Post-hoc pairwise comparison is not implemented yet; the effect size below is computed between the two most separated groups precisely so that the report is not silent about direction.

---

## Calibration

Calibration is what makes the ranking a measurement rather than an opinion. For every metric the engine builds two artificial worlds **out of your own rows**:

### The null world

All groups are pooled and resampled into synthetic groups of the same sizes. By construction there is no difference. The share of resamples in which the test still returns `p < α` is the measured **false-alarm rate (FPR)**.

Inflation is flagged when

$$\mathrm{FPR} > \max(1.5\alpha,\ \alpha + 0.02)$$

and `fpr_inflated` is written to `results.csv` and `calibration.csv`. When a metric is inflated, its MDE is suppressed and replaced by a warning: a detection threshold computed on a miscalibrated test is meaningless.

### The effect world

The same resampling, but a known multiplier is applied to the last group according to the configured scenario:

| Scenario | Effect |
|---|---|
| `location` (default) | multiplicative shift of the level |
| `location_down` | shift in the opposite direction |
| `scale` | increased variability at unchanged level |

Your configured **outlier rate** (default 2 %) and **missing rate** (default 0 %) are applied to the raw values before the metrics are recomputed. The share of resamples where the test detects the planted effect is the **power**.

### Split calibration

Optional, in **Settings → Scientific rigour**. Entities are split into two halves; calibration — and therefore metric selection — uses the first half, and the reported answer is computed on the second. Requires ≥ 8 entities per group. The mode is recorded as `calibration.calibrationSource` in the manifest, so a reader can tell which discipline was applied.

Defaults: `CustomRepetitions = 5000`, `CalibrationSeed = 20260719`, `CalibrationEffect = 1.15`, `Alpha = 0.05`.

---

## The MVS Score

A weighted geometric mean of five measured components, scaled to 0–100:

$$\mathrm{MVS} = 100 \cdot P^{0.30} \cdot F^{0.25} \cdot R^{0.20} \cdot S^{0.15} \cdot C^{0.10}$$

| Symbol | Component | Weight | Measurement |
|---|---|---|---|
| $P$ | power | 0.30 | detection rate in the effect world |
| $F$ | false-alarm control | 0.25 | $\exp\!\left(-\max(0,\ \mathrm{FPR}-\alpha)/\alpha\right)$ |
| $R$ | robustness | 0.20 | stability of the metric under injected contamination |
| $S$ | repeatability | 0.15 | split-half agreement of the group median over 50 splits |
| $C$ | coverage | 0.10 | empirical coverage of the 95 % bootstrap interval, 200 × 200 resamples |

**Why a geometric mean?** Because a metric that fails one component cannot buy its way back with the others. A metric with power 0.95 and a false-alarm rate of 0.30 is not a good metric, and an arithmetic mean would let it look like one.

**Why is $F$ exponential rather than linear?** A false-alarm rate at the nominal $\alpha$ costs nothing ($F = 1$). Beyond it the penalty grows quickly: at $\mathrm{FPR} = 2\alpha$ the factor is $e^{-1} \approx 0.37$. Over-firing is treated as a much worse sin than under-detecting, because a false positive gets published and a missed effect usually does not.

### Dimensional analysis and what the scale is

The exponents sum to one: 0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1. That single fact settles most of what can be asked about units.

- Every component is a probability or a bounded ratio between 0 and 1, so every component is **dimensionless**. The score inherits that: MVS has no units, and no unit can be assigned to it. "78" is not 78 of anything.
- Because the exponents sum to one, the aggregation is a **weighted geometric mean** and is therefore **homogeneous of degree one**: multiply every component by a constant and the score multiplies by the same constant. That is the minimum coherence requirement for an index, and it holds.
- The range is exactly 0 to 100 and both ends are attainable: all components 1 gives 100, any component 0 gives 0.
- It is **non-compensatory**. A zero anywhere zeroes the score, and near-zero components are punished hard. This is deliberate and it is the main reason the aggregation is geometric rather than arithmetic — a metric with power 0.95 and a false-alarm rate of 0.30 is not a good metric, and an average would let it look like one.
- It is invariant to the order of the components, and it is **not** invariant to monotone rescaling of a single component. Replacing power $P$ by $P^2$ is not a cosmetic change, it is a different index. Any future change to how a component is measured is a formula change and must bump the version.

**So what scale is the result on?** Ordinal, and nothing stronger. The five components are heterogeneous constructs — a rejection rate, a penalty function, a stability ratio, an agreement coefficient and a coverage probability — measured in incommensurable ways and combined with judgement weights. The ordering they produce can be defended. Distances between the numbers cannot.

Three consequences the project accepts:

1. No arithmetic on score differences, anywhere. "Metric A scores 8 points higher" is not a statement about the world; "metric A ranks above metric B" is.
2. The fixed cut at `score >= 60` is a distance claim on an ordinal scale. It is on notice — see [Candidate rules](#candidate-rules).
3. Any published comparison should be a **rank with an uncertainty band**, not a single number. The band is computable today from an exported run with `validation/analyze_results.py`.

### Where the weights came from

Honestly: judgement. They encode the position that a false alarm is worse than a missed effect and that both matter more than convenience. There was no elicitation protocol, no data, and no external panel. That is a fair criticism of the index, and the answer to it is not a better story — it is measurement.

`validation/analyze_results.py` recomputes the ranking of any finished run under equal weights, rank-order-centroid weights, power-only weights, false-alarm-first weights, arithmetic instead of geometric aggregation, and 5 000 Dirichlet draws around the current vector. It reports top-1 stability, the pairwise rank-flip rate and Kendall's tau against the current ranking. If the ordering survives that, the weights are not doing the work; if it does not, the honest output is a rank interval and the index needs rebuilding. This is the uncertainty-and-sensitivity step of the OECD/JRC composite-indicator protocol, applied to our own index.

One piece of luck in the existing architecture: because the weights live inside the frozen formula string, any change to them already forces a version bump, a new hash and a `FORMULA_CHANGED` flag on old runs. Multi-version sensitivity work needs no new audit machinery.

### The frozen specification

The full definition is stored as a single string and hashed:

```text
score=100*power^.30*falseAlarm^.25*robustness^.20*repeatability^.15*coverage^.10;
rawValueScenario;globalRankTest;
repeatability=splitHalfGroupMedianAgreement;
coverage=bootstrapIntervalCoverage;
candidate=fpr<=.075&&power>=.70&&score>=60;maxCandidates=4;nearMissReported;
effect=cliffsDelta;interval=percentileBootstrap400;
equivalence=tostOnBootstrapDelta;
verdict=difference|equivalent|insufficient|not_applicable;
mde=interpolatedFromEffectGrid@power.80;effectGrid=1.00,1.02,1.05,1.10,1.20;
inflatedFpr=nullGridPointAboveAlpha
```

```text
FormulaVersion  MVS-1.2.0
FormulaHash     70e1d57723df1ca2bbc1b7856357f04d844cd77f36a83ad5fefd02565e401e2f
Previous        MVS-1.1.0  1aab2c38b5127fa911ffd38416b4ac499217cb5b7459800f28014c107f5ab909
```

The hash is asserted by the `FormulaHash` unit test, written into every manifest, and compared during audit. Changing any part of the definition without bumping the version is a build failure, by design.

---

## Candidate rules

A metric is recommended — a **candidate** — only if all three hold:

```text
calibrated_fpr   <= 0.075
calibrated_power >= 0.70
mvs_score        >= 60
```

> [!IMPORTANT]
> The third rule is on notice. `score >= 60` is a cut on an ordinal composite, which is the one thing an ordinal scale does not support: 60 was chosen because it looked reasonable, not because anything was calibrated at it. The first two rules are cuts on quantities that have a meaning — a false-alarm rate and a detection rate — and they can be defended on their own terms.
>
> Planned for 1.4.0: drop `score >= 60`, keep the FPR and power gates, and report the score as a rank with an uncertainty band instead of a number with a threshold. That is a change to the formula definition, so it bumps the formula version and hash, and old runs will be flagged `FORMULA_CHANGED` — by design.

At most **four** candidates are reported. A metric that satisfies every rule but misses the cap, or trails the last candidate by less than 2 points, is reported as a **near miss** rather than dropped.

**The candidate set may be empty.** When no metric clears the bar, the results card says so and labels what it shows as *the highest-scoring metric*, explicitly not a recommendation. Treat an empty set as information about the study design, usually "too few entities per group".

---

## Effect size

Cliff's delta between the two most separated groups:

$$\delta = \frac{\#(x_i > y_j) - \#(x_i < y_j)}{n_x \, n_y}$$

It is non-parametric, bounded in $[-1, 1]$, and it survives the same outliers the metrics are being judged on. The 95 % interval is a **percentile bootstrap over entities** with 400 resamples — entities, not measurements, because entities are the independent unit.

Conventional reading: $|\delta| < 0.147$ negligible, $< 0.33$ small, $< 0.474$ medium, above that large. The negligible boundary is also the default equivalence margin below.

---

## Verdicts

| Verdict | Condition |
|---|---|
| **difference** | `p < α` **and** the bootstrap interval for δ excludes 0 |
| **equivalent** | the whole interval lies inside ± the equivalence margin (TOST on the bootstrap distribution) |
| **insufficient** | the interval covers both a meaningful effect and no effect — the data cannot decide |
| **not_applicable** | the metric is undefined for this dataset |

Default equivalence margin: `0.147`. Raising it makes equivalence easier to declare; lowering it makes *insufficient* more common. Whatever you choose is written to the manifest, so the choice travels with the result.

> Two significance-shaped mistakes this design refuses to make: reporting "no significant difference" as evidence of equivalence, and reporting a significant *p* without a direction or an effect size.

---

## Minimum detectable effect

Power is estimated on the grid `1.00 / 1.02 / 1.05 / 1.10 / 1.20`, and the **MDE** is the effect multiplier at which the interpolated power curve crosses **0.80**. The full curve is exported in `calibration.csv` so you can see the shape rather than only the crossing point.

Interpretation: *"with this many entities and this much noise, this metric would reliably notice a change of at least X %."* If your effect of interest is smaller than the MDE, a null result says nothing about the world — only about the study.

When the FPR is inflated, the MDE is suppressed.

---

## Determinism

Same input file + same settings + same engine version = byte-identical outputs, apart from timestamps and the run id. The seed is explicit (`CalibrationSeed`, default `20260719`), all resampling flows from it, and the seed is recorded in the manifest. Reproducing somebody's run means copying their settings block; nothing hidden participates.

---

## Assumptions and limits

- **Independent groups only.** Paired and repeated-measures designs are not supported — do not feed before/after data from the same entities into two groups.
- **One variable per run.** If your file contains several, filter first; the importer will ask.
- **Entities are the unit of analysis.** More measurements per entity improves the entity estimate; only more *entities* improves power.
- **The outlier model is generic**, not a physical model of your instrument. Robustness is a comparative signal between metrics, not an absolute guarantee.
- **No post-hoc tests** after Kruskal–Wallis yet.
- **Ten metrics on one dataset.** Selection is treated as calibration — judged by measured FPR, with inflation flagged per metric — not as ten independent hypothesis tests. For a strictly pre-registered answer, use split calibration.
- **Not a clinical or safety authority.** Use it as an input to a decision, alongside independent validation.

---

## Open methodological questions

A project that lists only its features is advertising. These are the unresolved problems, in the order they would change the product. Progress against them is tracked in [VALIDATION.md](VALIDATION.md).

1. **The composite may not be earning its keep.** If the score correlates with the power component at 0.95 or above on every dataset, then four of the five components are decoration and the right response is to delete them, not to defend them. Measured by experiment V4.

2. **The five components measure detection, not estimation.** There is nothing in the score about bias, mean squared error or relative efficiency — nothing about whether the number a metric produces is *right*, only about whether a test on it fires. The reference simulation showed why that gap matters: on a multiplicative mechanism the arithmetic mean and the median differ by about 3 pp in power, which the score can see, but they estimate genuinely different quantities, which the score cannot. Adding estimation-quality components is the largest planned change to the formula.

3. **The geometric mean is not implemented.** It is the textbook summary for multiplicative processes and it is the best-performing statistic on the multiplicative mechanism in the reference table — ahead of all ten shipped metrics. Searching for "the best metric" from a menu that omits the right answer is a real limitation, not a rounding error.

4. **The metric families are not clean.** `rms` responds to a pure scale change, `coefficient_of_variation` responds to a pure level shift, and under a multiplicative effect every spread metric detects the level change. "Level" and "spread" are properties of the metric, not of the effect, and the UI currently implies otherwise.

5. **No multiplicity control across metrics.** Ten metrics are examined and the framework treats selection as calibration rather than as ten tests. Under the null, the chance that at least one metric fires is 0.205. Whether an FDR-style adjustment or split-sample discipline is the better answer is open.

6. **Mechanisms built from the user's own data are partly circular.** They cannot exhibit structure the file does not already contain, so the robustness and power columns are conditional on the file being representative.

7. **Neutrality.** Every experiment here was designed by the author of the tool, which is the single strongest predictor of an over-optimistic benchmark. Independent replication is welcome and the datasets, seeds and reference implementation are in the repository specifically so that it costs an outsider nothing.

8. **Ranking at ceiling power is not identified.** When every applicable metric exceeds about 0.9 power, the ordering among them is Monte-Carlo noise and the app should say so instead of printing a leaderboard.
