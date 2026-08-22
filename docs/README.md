# MVS Analyzer documentation

Start here if you want more than the [project README](../README.md).

| Document | Read it when you want to know… |
|---|---|
| [METHODS.md](METHODS.md) | what the statistics actually do: metrics, tests, calibration, the MVS Score, effect size, verdicts, MDE |
| [DATA_FORMAT.md](DATA_FORMAT.md) | how to shape a CSV so the importer understands it — roles, delimiters, encodings, limits, import profiles |
| [OUTPUTS.md](OUTPUTS.md) | every column of every exported file, and the full `run_manifest.json` structure |
| [AUDIT.md](AUDIT.md) | how run integrity works, what each audit code means, and what hashing cannot prove |
| [PLUGINS.md](PLUGINS.md) | the `.mvsplugin` format, security limits, and how to build a pack |
| [ARCHITECTURE.md](ARCHITECTURE.md) | how the source is organized and where to make a change |

## Fast answers

**"Which metric should I use?"** — run a calibration and read the candidate list. If it is empty, the honest answer is *none of them, on this dataset*. See [METHODS.md](METHODS.md#candidate-rules).

**"The verdict says *not enough data*."** — that is a result. The bootstrap interval covers both a real difference and no difference at all. Add entities (not measurements per entity — entities), or accept a larger equivalence margin. See [METHODS.md](METHODS.md#verdicts).

**"My results changed after updating the app."** — check `formula.hash` in both manifests. If it changed, the definition changed, and old runs must be repeated. See [AUDIT.md](AUDIT.md#formula_changed).

**"My CSV will not load."** — the importer needs three roles: entity, group, value. Everything else is optional. See [DATA_FORMAT.md](DATA_FORMAT.md#column-roles).

**"Can I share results without sharing the raw data?"** — yes. A run folder contains the *hash* of the input, not the input. Identifiers in `data_quality.csv` are pseudonymized by default. See [OUTPUTS.md](OUTPUTS.md#privacy).

## Assets

`assets/` is reserved for the logo, screenshots and diagrams. It is intentionally empty for now — see [assets/README.md](assets/README.md).
