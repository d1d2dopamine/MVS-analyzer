# Validation suite

Seven synthetic datasets whose correct answer is known **by construction**, a
Monte-Carlo reference implementation that computes what the correct answer is,
and a post-hoc analyser for weight sensitivity.

The point is not to demonstrate that MVS Analyzer works. The point is to make
it possible for the tool to fail in public, on numbers, at a specified
threshold. The experiments, the thresholds and the interpretation of a failure
are fixed in advance in [docs/PREREGISTRATION.md](../docs/PREREGISTRATION.md);
the programme itself is in [docs/VALIDATION.md](../docs/VALIDATION.md).

| File | What it is |
|---|---|
| `dgp.py` | the seven data-generating mechanisms — single source of truth |
| `make_datasets.py` | writes the CSV files below |
| `reference_simulation.py` | Monte-Carlo truth table: which statistic actually wins, and by how much |
| `analyze_results.py` | weight sensitivity and discriminant validity of a finished run |
| `reference_power_primary.md` · `.csv` | truth table at the shipped effect sizes |
| `reference_power_discriminating.md` · `.csv` | truth table at effect sizes that keep power off the ceiling |
| `datasets/` | the CSV files, in the standard six-role import format |

Everything here needs Python 3 and numpy, and nothing else. None of it is part
of the application, none of it ships in the installer, and none of it touches
the engine.

---

## The datasets

All files use the standard layout from
[docs/DATA_FORMAT.md](../docs/DATA_FORMAT.md) — `entity,group,value,sequence,variable,unit`,
UTF-8, comma-separated, two groups (`Control`, `Treated`), one variable.
Unless stated otherwise: 20 entities per group, 20 measurements per entity.

| Dataset | Mechanism | Effect | A priori correct statistic |
|---|---|---|---|
| `A_normal_additive.csv` | normal entity effect + normal within-entity noise | +5 units on the level | the **mean**; the median pays the classic efficiency penalty |
| `B_lognormal_multiplicative.csv` | multiplicative (lognormal) noise, σ<sub>log</sub> = 0.45 | ×1.20 | the **geometric mean**; the median as its rank-equivalent |
| `C_heavy_tails.csv` | normal core + 12 % wide contamination (Tukey–Huber) | +4 units | the **median**, **MAD**, **IQR** |
| `D_scale_only.csv` | identical level, doubled within-entity dispersion | ×2 on the SD | the **spread family**; level metrics must stay silent |
| `E_null_01…10.csv` | one world, sampled twice (16 × 16) | none | nothing is detectable; every metric must sit at α |
| `F_small_n.csv` | mechanism A with 4 entities × 6 measurements | +5 units | **no metric qualifies** — an empty candidate set is the right answer |
| `G_ties_zero_spread.csv` | values rounded to whole units, one perfectly constant entity per group | +2 units | relative metrics must be reported *not applicable*, not filled in |

`E` ships as ten independent replicates on purpose. One null run tells you
nothing; ten let you count how often the pipeline fires when there is nothing
to find. See experiment **V2**.

---

## Running them against the app

1. Import the dataset. All seven files load with the built-in role recognition —
   no import profile needed.
2. Run the analysis with default settings (α = 0.05, 5 000 repetitions,
   `CalibrationSeed = 20260719`), unless the experiment says otherwise.
3. Export the run folder and open `results.csv`.
4. Compare the ranking against the truth table for that mechanism.

Record what you got, including the runs that went the wrong way. A validation
suite that only stores its successes is decoration.

---

## Regenerating everything

```bash
cd validation
python3 make_datasets.py                          # rewrites datasets/
python3 reference_simulation.py 2000 primary      # truth table, shipped effects
python3 reference_simulation.py 2000 discriminating
```

The seed is `20260823` and every stream is derived from it, so the CSV files
are byte-identical between runs and between machines. Change a mechanism and
both the datasets and the truth table move together — that is why they share
`dgp.py`.

## Analysing a finished run

```bash
python3 validation/analyze_results.py path/to/run/results.csv --draws 5000
```

Works on **any** run the app has ever produced, including runs on your own
data: `results.csv` already contains every component of the score, so the
weight analysis needs neither the raw measurements nor a change to the app.
