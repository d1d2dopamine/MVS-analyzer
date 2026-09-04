# Benchmark data

The benchmark runs to completion with an empty folder here. Everything in the default run is
generated on the spot from a frozen protocol, so the archive stays small and works offline.

This folder exists for the optional stage that uses **real recordings**.

## Why real recordings are optional

Synthetic data has a known truth by construction, which is exactly what a benchmark needs and
exactly what real data never gives you. Real data brings the opposite virtue: the noise, the skew
and the tails are whatever a laboratory actually measured, not what a model assumed.

The benchmark therefore uses real recordings in **plasmode** form. Entities from one real cohort
are shuffled and split into two pseudo-groups. There is no difference between those groups by
construction, so the false-discovery rate is measurable on real measurement noise. The effect under
test is then injected into one half, so power is measurable on the same noise.

## Preparing the recordings

```
python prepare_physionet.py --out .
```

This downloads the Gait in Neurodegenerative Disease Database (gaitndd 1.0.0) from PhysioNet and
writes one CSV in the shape the program reads. Without a network connection, download the `.ts`
files by hand and pass the folder:

```
python prepare_physionet.py --out . --local ./downloaded_ts_files
```

The script keeps the **left stride interval** column, drops detector artefacts outside 0.2-3.0 s,
and skips any recording with fewer than 40 usable strides.

- Source: https://physionet.org/content/gaitndd/1.0.0/
- Licence: Open Data Commons Attribution License v1.0 (ODC-BY). Attribution is required if you
  publish figures derived from it.

## Any other CSV works too

The benchmark reads every `*.csv` in the chosen folder using the program's normal importer, so any
file the application can open can serve as plasmode material:

```
entity,group,value,sequence,variable,unit
control1,control,1.0872,1,stride_interval,s
control1,control,1.1034,2,stride_interval,s
```

Requirements per file:

- the largest group needs at least **8 entities** with enough measurements each, otherwise the file
  is skipped and the reason is written into the report;
- at least 6 measurements per entity, which is the program's own import floor.

Every file that is used is recorded in `benchmark_manifest.json` by name and SHA-256, so a figure
made from real data can always be traced back to the exact file it came from.

## What is not here on purpose

No recordings are committed to this repository. Public medical databases carry their own licences
and attribution rules, and quietly vendoring them into an unrelated archive is how those rules get
lost. The converter is small enough to read in one sitting; the data stays at its source.
