# Run outputs

Every run writes a folder named `{prefix}_{runId}` (default prefix `MVS`). **Run folders are never overwritten** — a second run with identical settings produces a second folder.

```text
MVS_20260822T193014Z_a91c/
├─ results.csv
├─ calibration.csv
├─ data_quality.csv
├─ run_manifest.json
├─ value_distribution.png
├─ mvs_score.png
├─ fpr_power.png
├─ group_comparison.png
└─ report_summary_ru.txt        (if a plugin contributed one)
```

All numbers are written with round-trip formatting (`"R"`) under `CultureInfo.InvariantCulture`. A decimal point stays a decimal point in every locale.

---

## `results.csv`

One row per metric — the file you cite.

| Column | Meaning |
|---|---|
| `metric` | metric key (`median`, `mad`, …) |
| `group_summary` | per-group value of this metric, in group order |
| `range` | spread of the group summaries |
| `global_p` | Mann–Whitney (2 groups) or Kruskal–Wallis (3–10) p-value |
| `effect_cliffs_delta` | Cliff's delta between the two most separated groups |
| `effect_low`, `effect_high` | 95 % percentile bootstrap interval (400 resamples over entities) |
| `equivalence_p` | TOST p-value against the equivalence margin |
| `verdict` | `difference` · `equivalent` · `insufficient` · `not_applicable` |
| `mde` | minimum detectable effect at power 0.80 (blank when the FPR is inflated) |
| `calibrated_fpr` | measured false-alarm rate in the null world |
| `fpr_inflated` | true when `fpr > max(1.5α, α + 0.02)` |
| `calibrated_power` | detection rate in the effect world |
| `robustness`, `repeatability`, `coverage` | score components, 0–1 |
| `mvs_score` | 0–100 |
| `applicable` | false when the metric is undefined for this dataset |
| `candidate` | passed all candidate rules and fit within the cap of four |
| `near_miss` | passed the rules but lost the cap, or trails the last candidate by < 2 points |

> [!TIP]
> Read `verdict` and `fpr_inflated` **before** `mvs_score`. A high score on a metric whose false-alarm rate is inflated is a warning, not a recommendation.

---

## `calibration.csv`

One row per metric — the evidence behind the score.

| Column | Meaning |
|---|---|
| `metric` | metric key |
| `calibrated_fpr`, `fpr_inflated` | null-world behaviour |
| `calibrated_power` | power at the configured effect multiplier |
| `mde` | interpolated crossing of power 0.80 |
| `power_curve` | power at every grid point `1.00 / 1.02 / 1.05 / 1.10 / 1.20` |
| `robustness`, `repeatability`, `coverage` | score components |
| `mvs_score` | 0–100 |
| `applicable` | metric definable on this dataset |

`power_curve` is the most informative column in the whole export: a curve that is flat near 1.0 means the design cannot see small effects no matter which metric you pick.

---

## `data_quality.csv`

One row per entity — for spotting the device that ruined the study.

| Column | Meaning |
|---|---|
| `entity` | pseudonymized identifier `P_<sha256[..10]>` unless anonymization is off |
| `group` | group label |
| `valid_measurements` | measurements that survived filtering |
| `median`, `mean`, `standard_deviation`, `coefficient_of_variation`, `mad`, `iqr`, `normalized_mad`, `normalized_iqr`, `rms`, `range` | all ten metrics for this entity |

Sort by `valid_measurements` ascending to find entities near the exclusion threshold, and by `range` descending to find the one with the broken sensor.

---

## `run_manifest.json`

The provenance record. If you keep one file from a run, keep this one.

```jsonc
{
  "application": "MVS Analyzer",
  "version": "1.3.3",
  "engineVersion": "1.2.0",
  "runId": "20260822T193014Z_a91c",
  "createdUtc": "2026-08-22T19:30:14Z",

  "project":     { "name": "...", "variable": "...", "unit": "...", "notes": "..." },
  "inputData":   { "fileName": "demo_three_groups.csv", "sha256": "...", "rows": 4500 },
  "data":        { "groups": [...], "entities": 90, "measurements": 4500, "excluded": {...} },

  "processing":  { "minMeasurements": 6, "minValue": -1000000, "maxValue": 1000000,
                   "outlierRate": 0.02, "missingRate": 0.0 },

  "calibration": { "seed": 20260719, "repetitions": 5000, "scenario": "location",
                   "effect": 1.15, "alpha": 0.05,
                   "calibrationSource": "full" /* or "split" */,
                   "effectGrid": [1.00, 1.02, 1.05, 1.10, 1.20],
                   "mdePowerTarget": 0.80, "equivalenceMargin": 0.147,
                   "powerCurves": { "median": [...], "mad": [...] } },

  "formula":     { "version": "MVS-1.2.0", "hash": "70e1d577...e401e2f",
                   "specification": "score=100*power^.30*...",
                   "effectDefinition": "cliffsDelta",
                   "verdictDefinition": "difference|equivalent|insufficient|not_applicable",
                   "mdeDefinition": "interpolatedFromEffectGrid@power.80",
                   "repeatabilityDefinition": "splitHalfGroupMedianAgreement",
                   "coverageDefinition": "bootstrapIntervalCoverage" },

  "candidateRules": { "maxFpr": 0.075, "minPower": 0.70, "minScore": 60, "maxCandidates": 4 },
  "candidateSet":   ["median", "normalized_mad"],
  "verdicts":       { "median": "difference", "coefficient_of_variation": "insufficient" },

  "plugins":     [ { "id": "mvs.report.pack", "version": "1.0.0", "sha256": "...", "enabled": true } ],
  "figures":     { "templates": ["value_distribution", "mvs_score", "fpr_power", "group_comparison"],
                   "format": "png" },
  "files":       [ { "name": "results.csv", "sha256": "...", "bytes": 4213 } ]
}
```

The three fields that make a result citable: **`formula.hash`**, **`engineVersion`**, **`inputData.sha256`**. Together they say *what was computed*, *by which code*, *on which data*.

---

## Figures

Default templates: `value_distribution`, `mvs_score`, `fpr_power`, `group_comparison`. Format `png` (default) or `svg`; plugins can add more templates. Figures are rendered locally with `System.Drawing` — no external toolchain, no fonts to install.

---

## Text reports

Plugins may contribute `report_*.txt` files from declarative templates. Since 1.3.2 they are written **before** the manifest, so their hashes are included in `files[]` — in 1.3.1 and earlier they escaped verification.

---

## Privacy

A run folder contains:

- the **hash** of the input file, never its contents;
- per-entity metrics under **pseudonymized** identifiers (default);
- your settings, which may include a project name you typed.

That makes a run folder safe to attach to a paper or a ticket in most settings — but read `project.name` and `project.notes` once before you publish, because those are free text you wrote.

---

## Comparing two runs

1. Compare `formula.hash` — different hashes mean the definitions differ; stop and re-run the old one.
2. Compare `engineVersion` — different engines may compute differently even with the same formula string.
3. Compare `inputData.sha256` — identical hash means the same data, byte for byte.
4. Compare `calibration.seed`, `scenario` and `effect` — different settings explain different numbers honestly.
5. Only then compare `mvs_score` and `verdict`.

The **Audit** page does steps 1–4 automatically across a folder tree. See [AUDIT.md](AUDIT.md).
