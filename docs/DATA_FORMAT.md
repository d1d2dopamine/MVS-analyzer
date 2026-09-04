# Data format

CSV/TSV with one outcome. Required columns: `entity`, `group` (or `condition`), `value`. Common aliases are recognized. Optional: integer `sequence`/`timepoint`, `variable`, `unit`. Import profiles can define mappings and decimal-comma behavior.

```csv
entity,group,value,sequence,variable,unit
P01,control,12.3,1,measurement,unit
P01,control,12.8,2,measurement,unit
```

- Summary/component workflows: 2–10 **independent** groups. Summary software minimum: four entities per group with six retained measurements (configurable ≥2). Component CLI defaults to ≥3 measurements. These are software limits, not scientific sample-size recommendations.
- Independent-mode IDs are group-scoped. If an ID occurs in different groups, CLI requires `--allow-group-scoped-ids`; the GUI asks whether those are genuinely different independent entities. Never use this switch for the same subjects under different conditions.
- MELSM: 1–10 conditions, IDs **global across conditions**, ≥8 subjects and ≥3 observations each. The same ID in A and B remains one subject. The dedicated import route accepts one condition.
- Time terms require a supplied, valid integer sequence/timepoint column. Failed parsing is reported and prevents time-effect fitting. Row order alone is not evidence of elapsed time. Irregular real dates and arbitrary covariate formulas are not implemented.
- Do not mix outcome variables or inconsistent nonempty units. Convert units outside the program. Missing unit labels do not establish compatibility.
- Nonfinite/invalid measurements, out-of-limit values and missing identifiers are excluded with import counts. Entities below the repeat minimum are then excluded. The original file is never rewritten. Review retained counts and missingness scientifically.
- Encodings include UTF-8, marked/recognized UTF-16, and a legacy Windows-1251 fallback. Verify the reported encoding; heuristic decoding cannot establish the intended text.
- Quoted separators and quoted newlines are supported. Unterminated quotes are rejected. Decimal-comma input should use an explicit profile/separator to avoid ambiguity.

`examples/variance_demo.csv` and `examples/repeated_conditions.csv` are reproducible synthetic examples, not external validation datasets. Generation parameters are in `examples/scientific_examples.json`. The bundled original demo and all image assets are unchanged.
