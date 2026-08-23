# MVS Analyzer documentation

Start here if you want more than the [project README](../README.md).

| Document | Read it when you want to know… |
|---|---|
| [METHODS.md](METHODS.md) | what the statistics actually do: modes, simulation design, metrics, tests, calibration, the MVS Score, what scale it is on, open questions |
| [VALIDATION.md](VALIDATION.md) | how the tool can be proven wrong: the reference truth table, the six experiments and their thresholds |
| [PREREGISTRATION.md](PREREGISTRATION.md) | the mechanisms, hypotheses and pass/fail thresholds, frozen before the experiments were run |
| [DATA_FORMAT.md](DATA_FORMAT.md) | how to shape a CSV so the importer understands it — roles, delimiters, encodings, limits, import profiles |
| [OUTPUTS.md](OUTPUTS.md) | every column of every exported file, and the full `run_manifest.json` structure |
| [AUDIT.md](AUDIT.md) | how run integrity works, what each audit code means, and what hashing cannot prove |
| [PLUGINS.md](PLUGINS.md) | the `.mvsplugin` format, security limits, and how to build a pack |
| [ARCHITECTURE.md](ARCHITECTURE.md) | how the source is organized and where to make a change |

## Fast answers

**"Which metric should I use?"** — run a calibration and read the candidate list. If it is empty, the honest answer is *none of them, on this dataset*. See [METHODS.md](METHODS.md#candidate-rules).

**"Can I pick a metric with this and then report its *p*-value?"** — not without a correction. Choosing on the same data you report inflates the error rate; under a pure null the chance that at least one of the ten metrics fires is 0.205, not 0.05. Use split calibration, or choose the metric before looking. See [METHODS.md](METHODS.md#three-modes-and-only-one-of-them-is-safe).

**"What are the units of the score?"** — it has none, and it is an ordinal scale: rankings mean something, differences do not. See [METHODS.md](METHODS.md#dimensional-analysis-and-what-the-scale-is).

**"The verdict says *not enough data*."** — that is a result. The bootstrap interval covers both a real difference and no difference at all. Add entities (not measurements per entity — entities), or accept a larger equivalence margin. See [METHODS.md](METHODS.md#verdicts).

**"My results changed after updating the app."** — check `formula.hash` in both manifests. If it changed, the definition changed, and old runs must be repeated. See [AUDIT.md](AUDIT.md#formula_changed).

**"My CSV will not load."** — the importer needs three roles: entity, group, value. Everything else is optional. See [DATA_FORMAT.md](DATA_FORMAT.md#column-roles).

**"Can I share results without sharing the raw data?"** — yes. A run folder contains the *hash* of the input, not the input. Identifiers in `data_quality.csv` are pseudonymized by default. See [OUTPUTS.md](OUTPUTS.md#privacy).

## Validation

[`validation/`](../validation/README.md) holds seven synthetic datasets whose correct answer is known by construction, an independent Monte-Carlo reference implementation, and a script that measures how much of the ranking is the weights rather than the data. Nothing in it ships with the application.

## Assets

`assets/` holds the logo and other brand images — see [assets/README.md](assets/README.md).
