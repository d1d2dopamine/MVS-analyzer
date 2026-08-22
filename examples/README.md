# Example datasets

Three synthetic datasets, generated deterministically so that anyone can reproduce the same numbers. None of them contain real measurements from real subjects or devices.

| File | Rows | Groups | What it is for |
|---|---|---|---|
| [`demo_three_groups.csv`](demo_three_groups.csv) | 4 500 | 3 × 30 entities × 50 measurements | the happy path — a clean, well-powered three-group comparison |
| [`MVS_stress_test.csv`](MVS_stress_test.csv) | 2 880 | 3 × 24 entities × 40 measurements | disagreement on purpose — level metrics and spread metrics point at different groups |
| [`lab_device_ru_win1251.csv`](lab_device_ru_win1251.csv) | 864 | 3 × 12 entities × 24 measurements | a hostile file format — semicolons, decimal commas, Russian headers, Windows-1251 |

---

## `demo_three_groups.csv`

Standard layout, UTF-8, comma-separated, all six recognized roles present:

```csv
entity,group,value,sequence,variable,unit
G1_01,Group 1,117.828,1,demo_measurement,unit
```

*Group 1* is the reference, *Group 2* is shifted upward by roughly 6 %, *Group 3* is shifted upward by roughly 12 % and is also slightly noisier. Around 2 % of values are contaminated outliers, so robustness genuinely separates the median-like metrics from the mean-like ones.

**Expect:** a *difference* verdict, several qualifying candidates, `median` and `normalized_mad` scoring well, `range` scoring badly.

---

## `MVS_stress_test.csv`

The dataset the 1.3.2 fixes came from. Three groups — `Control`, `Shift +6%`, `Noise` — where:

- `Shift +6%` differs from `Control` **in level** but has the same spread;
- `Noise` has the **same level** as `Control` and roughly double the spread;
- every entity carries heavy-tailed contamination.

Metrics of central tendency therefore rank `Shift +6%` highest, while metrics of dispersion rank `Noise` highest. **They are both right, and they answer different questions.** The results card is required to say so instead of presenting the top-scoring metric as consensus — if a future change makes the app quietly pick a side, this file is the regression test.

**Expect:** disagreement between level and spread metrics, at least one metric flagged `fpr_inflated`, and a smaller candidate set than the demo dataset.

---

## `lab_device_ru_win1251.csv`

A deliberately awkward export in the style of older laboratory instruments:

- `;` as the delimiter,
- `,` as the decimal separator,
- Russian column headers (`Образец`, `Группа`, `Значение`, `Повтор`, `Показатель`, `Единица`),
- **Windows-1251** encoding, no BOM.

> [!WARNING]
> Do not "fix" this file to UTF-8. Its whole purpose is to exercise the Windows-1251 fallback in `CsvImporter` and the `lab-device` import profile shipped by the Lab pack plugin. It is marked `-text` in `.gitattributes` so Git will not normalize it.

**How to load it:** install `plugin-lab-pack-source` (or point the app at that folder), then choose the **lab-device** import profile on the Data page. Without the profile, the importer will still detect the delimiter and encoding but will not know the Russian column names.

---

## Regenerating

All three files are produced by fixed seeds (`7791`, `20260719`, `4242`). Regenerating them with the same seed produces byte-identical output, which is what makes them usable as fixtures: if `results.csv` changes for one of these datasets without a formula bump, something in the engine changed by accident.

## Bringing your own data

Minimum requirements: one variable per run, 2–10 independent groups, ≥ 4 entities per group, ≥ 6 valid measurements per entity. Full reference: [../docs/DATA_FORMAT.md](../docs/DATA_FORMAT.md).
