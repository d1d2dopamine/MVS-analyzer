# MVS Benchmark

**Protocol `MVS-BENCH-1.0.0`** · frozen before the first run · hash printed on every figure

---

## 1. The question

A researcher measures ten things about the same recordings: the median, the standard deviation, the
coefficient of variation, the MAD, the IQR, and so on. Then a group difference is looked for. If the
metric that shows the difference is chosen *after* seeing which one shows it, the honest 5 % error
rate is gone, and nobody in the room can say what replaced it.

MVS Analyzer claims to answer that by calibrating metrics on data where the truth is known, and by
gating the final choice behind pre-set thresholds. **This benchmark is the test of that claim, with
the pass marks written down before the first number existed.**

The headline number the program has published so far comes from its own validation suite: picking
the best of ten metrics on null data fires in **20.5 %** of studies instead of 5 %. That figure is a
single scenario. This benchmark widens it into a protocol: several designs, three distributional
shapes, contamination, dispersion effects as well as location effects, and real recordings.

## 2. What is compared

Seven ways of getting from ten candidate metrics to one answer. All seven see exactly the same data
in every repetition, which is what makes the comparison fair.

| Procedure | Rule |
|---|---|
| `cherry_pick` | Run all ten tests, report the smallest p-value. No correction. This is the bad practice being measured. |
| `bonferroni` | Run all ten tests, multiply the smallest p-value by ten. The classic, conservative answer. |
| `fixed_median` | Decide before looking: always use the median. |
| `fixed_cv` | Decide before looking: always use the coefficient of variation. |
| `mvs_pilot` | Choose the metric once on a separate pilot dataset, then use it on every later study. |
| `mvs_strict` | The program's own path: split the data, calibrate on one half, and only report if the chosen metric passes the pre-set gate (FPR ≤ .075, power ≥ .70, score ≥ 60). |
| `mvs_lenient` | Same split and calibration, but the highest-scoring metric is reported even if the gate is not met. This is the honest "what if the user ignores the warning" case. |
| *oracle* | Not a procedure: the best fixed metric for that condition, chosen with hindsight. It is the ceiling nobody can reach in practice, and the yardstick for how much power a defensible method costs. |

## 3. Data

### Track S — synthetic, always runs

Two designs, chosen to bracket the measurement families the program is aimed at rather than to
flatter any single metric:

| Design | Entities per group | Measurements each | Within-entity CV | Shape |
|---|---|---|---|---|
| `gait_stride_like` | 16 | 40 | 0.025 | heavy-tailed (t, 5 df) |
| `voice_jitter_like` | 20 | 26 | 0.18 | lognormal |

Effects are injected into the second group only:

- **location** — the entity's own level is multiplied by k (1.00, 1.02, 1.05, 1.10, 1.20);
- **dispersion** — the entity's own coefficient of variation is multiplied by k. A dispersion effect
  is invisible to the median and obvious to the CV, which is exactly the situation where choosing a
  metric after the fact is most tempting.

**Contamination** replaces a share of measurements with a five-sigma excursion (2 %, 5 %, 10 %),
because real recordings contain coughs, dropped markers and mis-clicks.

### Track R — real recordings, optional

Plasmode resampling: entities from one real cohort are shuffled into two pseudo-groups. There is no
difference between them by construction, so every discovery is false by definition — but the noise,
the skew and the tails are exactly what a laboratory measured. See `benchmark_data/README.md` for
the converter. Every file used is recorded by name and SHA-256 in the run manifest.

## 4. What is measured

- **False discovery rate** on data with no effect, with a Wilson 95 % interval and the Monte Carlo
  standard error next to every rate. A rate without its uncertainty is a rumour.
- **Power** across the effect grid, and the **gap to the oracle** — the price of doing it properly.
- **Stability**: repeated random half-splits of the same dataset, scored with Kendall's tau between
  the two rankings, plus how often the same metric came first.
- **Robustness**: the same null conditions with 2 %, 5 % and 10 % contamination.
- **Determinism**: the whole protocol re-run with the same seed must produce a byte-identical digest.

## 5. Pre-registered thresholds

These are compiled into `Benchmark/BenchmarkProtocol.cs` as a single string whose SHA-256 is
`5557f86f…c36294`, checked by the test suite on every build and printed on every figure. Changing a
threshold changes the hash, and a changed hash is visible on every image that was already published.

| # | Claim | Pass | Fail |
|---|---|---|---|
| **A** | Metric shopping inflates the error rate, and the gated path removes it | cherry-pick FPR ≥ .15 **and** `mvs_strict` FPR ≤ .075 | `mvs_strict` FPR > .10 |
| **B** | The gate does not cost much power | oracle power − `mvs_strict` power ≤ .07 | gap > .15 |
| **C** | The choice is stable, not a coin flip | median Kendall tau ≥ .70 **and** top-1 agreement ≥ .60 | tau < .40 |
| **D** | Dirty data does not break the guarantee | `mvs_strict` FPR ≤ .075 at 10 % contamination | FPR > .10 already at 2 % |
| **E** | The run is reproducible | identical SHA-256 on a repeat with the same seed | any difference |

The overall verdict is **go** when every threshold passes, **no-go** when any one fails, and
**conditional** when nothing failed but not everything cleared its pass mark. The report prints the
verdict whichever way it lands; there is no code path that hides a bad result.

## 6. Running it

### From the program

**Settings → scroll to the bottom → "Developer — benchmark"**

1. Pick a depth: *quick* (~5 minutes), *standard* (~25 minutes) or *full* (~1–2 hours).
2. Leave the seed alone unless you want a different run. The same seed reproduces the same numbers.
3. Choose the results folder. It defaults to your Downloads folder.
4. Optionally point at a folder of prepared real recordings.
5. Press **Run benchmark**. Progress and a time estimate appear; the run can be cancelled.

When it finishes, the figures folder opens by itself.

### From the command line

```
MVS_Analyzer.exe --benchmark --profile full --seed 20260904 --out C:\bench
```

| Option | Meaning |
|---|---|
| `--profile` | `quick`, `standard` or `full` |
| `--seed` | any positive whole number |
| `--out` | folder to write results into |
| `--real-data` | folder of prepared CSV recordings (optional) |
| `--lang` | `en` or `ru` for the report and figure labels |
| `--quiet` | no progress output |

Exit codes: **0** thresholds met or inconclusive, **2** at least one threshold missed, **1** error.
That makes the benchmark usable as a build step: a regression in error control fails the pipeline.

## 7. What lands in the folder

```
MVS_Benchmark_<runId>/
  benchmark_report.md        the readable write-up, verdict first
  benchmark_summary.csv      one row per condition and procedure, with intervals
  benchmark_metrics.csv      per-metric rejection rates, for finding the oracle by hand
  benchmark_choices.csv      which metric each procedure picked, and how often
  benchmark_stability.csv    Kendall tau of every half-split
  benchmark_verdicts.csv     the five hypotheses, their thresholds and the outcome
  benchmark_protocol.txt     the frozen protocol text, verbatim
  benchmark_manifest.json    versions, hashes, timings, and every real file used
  SHA256SUMS.txt             digest of every file above
  figures/                   14 PNG files
```

A hash-chained line is also appended to `%LocalAppData%\MVS_Analyzer\benchmark_journal.jsonl`. Each
line carries the hash of the previous one, so a run cannot be quietly deleted after the fact: the
chain breaks and anyone reading the file can see it. The application's own run journal is untouched.

## 8. The figures

Every figure carries the seed, the protocol hash, the formula hash and the run id in its footer, so
an image lifted out of context can still be traced back to the run that produced it.

| File | What it shows |
|---|---|
| `fig1_error_control` | The headline. False discoveries per procedure on null data, against the 5 % line. |
| `fig2_power_vs_error` | Error rate against power. The useful corner is bottom-right; anything above the 5 % line bought its power with false positives. |
| `fig3_power_curves` | Power across the effect grid for each procedure, with the oracle ceiling. |
| `fig4_metric_stability` | Kendall tau across repeated half-splits. A wide, low histogram means the choice is a coin flip. |
| `fig5_contamination` | Error rate as contamination rises from 0 to 10 %. |
| `fig6_metric_heatmap` | Which metric each procedure actually chose, per condition. |
| `fig7_verdicts` | The five hypotheses, pass or fail, with the observed value next to each. |

Each of the first two is written in four sizes — `_print` (2000×1250), `_story` (1080×1920, safe
zones respected top and bottom), `_square` (1080×1350) and `_wide` (1200×675) — so the same figure
can go into a paper, a story, a feed post or a link preview without being re-cropped by hand.

The palette is Okabe-Ito, which stays readable for the most common forms of colour blindness, and
no figure relies on colour alone: every series is also labelled or ordered.

## 9. What this benchmark does not prove

Stated here rather than buried, because a benchmark that only lists its strengths is advertising.

- **Home advantage.** The synthetic conditions are drawn from the same family of shapes the engine
  expects. A hostile benchmark would look for the shapes it handles worst. Track R exists to soften
  this, and it is optional, which softens it less than one would like.
- **Two groups, one variable.** Paired designs, covariates, repeated sessions and time-series
  structure are outside this protocol entirely.
- **The oracle is not achievable.** It is computed with hindsight over the same data. Beating it is
  not possible; the gap is the point.
- **Error control is a property of the procedure**, measured over many repetitions. It is not a
  promise about any single study, and no figure here should be read as one.
- **The plasmode stage inherits its cohort's quirks.** One database's gait recordings are not all
  gait recordings.

## 10. Checking someone else's run

1. Compare the protocol hash on their figure with the one your own build prints. If they differ, the
   protocol was edited and the runs are not comparable.
2. Re-run with their seed and profile. Compare `benchmark_manifest.json`: the determinism digest must
   match theirs exactly.
3. Verify `SHA256SUMS.txt` against the files in the folder.
4. If real data was used, the manifest lists each file's SHA-256. Re-run the converter and compare.

A claim that survives all four is reproducible. A claim that fails the first one is a different
experiment wearing the same name.

## 11. Method notes

- **Test.** Two-sided Mann-Whitney U on entity-level summaries, alpha = .05, matching the engine.
- **Randomness.** xoshiro256\*\* seeded through splitmix64. Every replication derives its own stream
  from (seed, stage, condition, replication), so results are identical no matter how many threads
  the machine has or how the work happens to be scheduled.
- **Calibration split.** Entities, never measurements, are split between the calibration half and
  the analysis half. Splitting measurements would leak an entity across both sides and quietly
  inflate everything.
- **The pilot procedure** locks its metric on a separate null pilot dataset, so it cannot peek at the
  study it will later be applied to.
- **Monte Carlo error.** With 1000 repetitions, a true 5 % rate is measured to about ±1.4 points at
  95 % confidence. Differences smaller than that are noise, and the report prints the interval next
  to every rate so this can be checked rather than trusted.
