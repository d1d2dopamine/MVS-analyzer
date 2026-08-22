# Methods

Everything the engine computes, in the order it computes it. Implementation: `AnalysisEngine.cs` (engine version **1.2.0**), frozen specification: `OutputExporter.cs`.

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
