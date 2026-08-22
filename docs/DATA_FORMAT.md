# Data format

How to shape a file so `CsvImporter` understands it on the first try.

- [Shape of the data](#shape-of-the-data)
- [Column roles](#column-roles)
- [Delimiters](#delimiters)
- [Encodings](#encodings)
- [Numbers](#numbers)
- [Limits and filtering](#limits-and-filtering)
- [Import profiles](#import-profiles)
- [Troubleshooting](#troubleshooting)

---

## Shape of the data

**Long format, one measurement per row.** Not a matrix, not one column per group.

```csv
entity,group,value,sequence,variable,unit
G1_01,Group 1,117.828,1,demo_measurement,unit
G1_01,Group 1,102.150,2,demo_measurement,unit
G1_02,Group 1,110.402,1,demo_measurement,unit
G2_01,Group 2,124.771,1,demo_measurement,unit
```

Requirements:

| Rule | Value |
|---|---|
| Variables per run | exactly 1 |
| Groups | 2–10, independent |
| Entities per group | ≥ 4 (≥ 8 for split calibration) |
| Valid measurements per entity | ≥ 6 by default, configurable |
| Header row | required |

An entity belongs to exactly one group. If the same entity id appears under two groups, it is two different entities and the analysis is no longer independent — paired designs are not supported yet.

---

## Column roles

The importer maps header names to roles, case-insensitively, ignoring spaces and underscores.

| Role | Required | Recognized names |
|---|---|---|
| **entity** | ✅ | `entity`, `entity_id`, `device`, `device_id`, `machine`, `asset`, `item`, `sample`, `object`, `participant`, `subject`, `id` |
| **value** | ✅ | `value`, `measurement`, `reading`, `result`, `signal`, `rt`, `rt_ms`, `reaction_time`, `response_time` |
| **group** | ✅ | `group`, `condition`, `class`, `category`, `variant`, `model`, `arm` |
| **sequence** | — | `sequence`, `index`, `trial`, `trial_number`, `measurement_number`, `timepoint`, `step` |
| **variable** | — | `variable`, `metric`, `parameter`, `measurement_name`, `signal_name` |
| **unit** | — | `unit`, `units` |

- **sequence** is used for ordering and quality diagnostics, never as a statistical factor.
- **variable** lets one file hold several variables; you pick one per run.
- **unit** is carried into reports and figure labels.
- Unrecognized columns are ignored, not an error — export the extra metadata if you like.

If a required role is missing, the Data page says which one and shows the headers it did find. Rename the column, or use an [import profile](#import-profiles).

---

## Delimiters

Auto-detected from the header line, in this order: `,` `;` tab. `.csv`, `.tsv` and `.txt` are all accepted. Quoted fields (`"Group A, extended"`) are handled, including doubled quotes inside a quoted field.

---

## Encodings

Detection order:

1. **BOM** — UTF-8, UTF-16 LE, UTF-16 BE are honoured immediately.
2. **Strict UTF-8** — the file is decoded with error detection; if it decodes cleanly, UTF-8 wins.
3. **Windows-1251 fallback** — for legacy Cyrillic exports that would otherwise turn into replacement characters.

This is why `examples/lab_device_ru_win1251.csv` exists and why it must stay in Windows-1251: it is the regression test for step 3.

---

## Numbers

| Input | Parsed as |
|---|---|
| `117.828` | 117.828 |
| `117,828` | 117.828 (decimal comma) |
| `1.234,56` | 1234.56 (European thousands + decimal comma) |
| `1,234.56` | 1234.56 |
| `1.2e3` | 1200 |
| `` (empty), `NA`, `NaN`, `—` | missing — the row is skipped, the entity is kept |

Decimal-comma handling is decided per column, not per cell, so a file cannot silently mix conventions.

---

## Limits and filtering

Set in **Settings → Processing**:

| Setting | Default | Effect |
|---|---|---|
| `minMeasurements` | 6 | entities with fewer valid measurements are excluded |
| `MinValue` | −1 000 000 | values below are treated as invalid |
| `MaxValue` | 1 000 000 | values above are treated as invalid |

Everything that is excluded is counted and reported on the Data page and in `data_quality.csv`. Nothing is dropped silently — if a third of your rows disappear, the app tells you before you run.

---

## Import profiles

When renaming columns is not an option (an instrument writes what it writes), a plugin can ship an **import profile**: a small JSON file that declares the delimiter, decimal convention and column mapping.

```json
{
  "id": "lab-device",
  "name": "Lab device export (RU)",
  "delimiter": ";",
  "decimalComma": true,
  "columns": {
    "entity": "Образец",
    "group": "Группа",
    "value": "Значение",
    "sequence": "Повтор",
    "variable": "Показатель",
    "unit": "Единица"
  }
}
```

Profiles live in a plugin's `import-profiles/` folder and appear in a dropdown on the Data page. The active profile is recorded in the run manifest, so a reader can tell how the columns were interpreted. See [PLUGINS.md](PLUGINS.md) and `plugin-lab-pack-source/`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Required column not found" | header not in the recognized list | rename it or use an import profile |
| Cyrillic headers look like `????` | file is neither UTF-8 nor Windows-1251 | re-export as UTF-8 |
| All values become missing | decimal comma in a file the importer read as thousands separators | use a profile with `"decimalComma": true` |
| Far fewer entities than expected | `minMeasurements` filtered them out | lower it, or collect more repeats |
| "Too many groups" | more than 10 distinct group labels | aggregate categories, or filter to the comparison you care about |
| Groups look right but power is terrible | too few *entities* — extra measurements per entity do not help | add entities |

### A note on privacy

Entity identifiers are pseudonymized in exports by default (`P_<sha256[..10]>`), so a run folder can be shared without shipping subject or serial numbers. Turn it off in **Settings** only if the identifiers are already non-sensitive.
