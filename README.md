<p align="center"><img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo"></p>

<h1 align="center">MVS Analyzer</h1>
<p align="center">Statistical analysis for repeated measurements, with reproducible calibration, diagnostics and saved run metadata.</p>
<p align="center"><a href="#русский">Русский</a></p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/release-1.4.0-1f6feb?style=flat-square" alt="release 1.4.0">
  <img src="https://img.shields.io/badge/engine-1.6.2-6f42c1?style=flat-square" alt="engine 1.6.2">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
  <a href="https://doi.org/10.5281/zenodo.22836364"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.22836364.svg" alt="DOI: 10.5281/zenodo.22836364"></a>
</p>

MVS Analyzer compares summary metrics for repeated measurements and includes separate workflows for variance components, known-truth estimation studies and an experimental mixed-effects location-scale model. Active development now targets the headless CLI and Python API. The Python package delegates to the same compiled `MvsAnalyzer.Core` engine through the versioned CLI machine protocol instead of reimplementing the methods.

Current archived release: `1.4.0`, scientific engine `1.6.0`, formula `MVS-1.4.0`. The 1.5.0 development line is CLI/Python-first; the Windows desktop is frozen at 1.4.0 and is no longer built or released.

Current development engine: `1.6.2`. Observed rank-test availability is now
independent of calibration diagnostics. Results include metric-specific entity
counts and exclusion reasons in JSON and `metric_availability.csv`. Recompute
calibrations saved with engines `1.6.0` or `1.6.1`. The normal-CDF precision fix
from 1.6.1 is retained. See the [round 3 checkpoint](docs/ROUND3_APPLICABILITY_CHECKPOINT.md).

Development checkpoint `1.5-A` adds a structured metric registry and four staged metrics (Huber M, Hodges-Lehmann, Qn, and log-SD). They are not yet part of active calibration or multiplicity correction; the current inferential path retains the 12-metric registry and Bonferroni correction until the later 1.5 multiplicity redesign.

Current source checkpoint: the full development benchmark is completed with its
**NO-GO retained**; staged Huber is numerically repaired; internal Holm and maxT
arithmetic are tested but unused by production inference. CLI input preservation
and Python launch errors are hardened. See the [project readiness audit](docs/ROUND15_PROJECT_READINESS_AUDIT.md)
for actual checks, remaining limits and scientific decision gates. This is not a
1.5.0 scientific release. [Release packaging/gate checks](docs/ROUND16_RELEASE_WORKFLOW_AUDIT.md)
now preserve linked documentation and align future release verification with CI;
no release was published by these checkpoints. The [bounded CLI resource audit](docs/ROUND17_CLI_RESOURCE_AUDIT.md)
records resource/cancellation evidence. The [current readiness handoff](docs/PROJECT_READINESS_HANDOFF.md)
consolidates completed work, the final existing-interface audit and the next
scientific decision.

## What MVS does

The main workflow is designed for data where each independent entity has several measurements. MVS can simulate declared changes on the observed data, estimate detection power and false-alarm rates for 12 summary metrics, compare independent groups and save the settings and provenance needed to inspect the run later.

The project also contains:

- Gaussian within-entity and between-entity variance-component analysis;
- known-truth simulation studies for estimator bias, MSE and related performance measures;
- an experimental mixed-effects location-scale model for repeated conditions;
- benchmark, validation, audit and checkpoint tooling.

Calibration is conditional on the observed data and the selected simulation scenario. It does not establish a universally best metric or external validity. See [Methods](docs/METHODS.md) and [Validation and limitations](docs/VALIDATION.md) before using results for confirmatory work.

## Interfaces

### Python

The path-based Python API in `python/` is the primary user-facing interface for new development. It controls a compatible `mvs` engine through the versioned machine protocol and returns typed result objects and saved artifact paths. Statistical methods remain in the shared Core engine.

```bash
python -m pip install -e ./python
export MVS_CLI=/absolute/path/to/mvs
```

```python
import mvs
calibration = mvs.calibrate("data.csv", repetitions=5000, seed=20260719)
result = mvs.analyze("data.csv", calibration=calibration)
```

See [Python API](docs/PYTHON_API.md), [CLI machine protocol](docs/CLI_MACHINE_PROTOCOL.md) and [interface compatibility](docs/COMPATIBILITY.md).

### CLI

The headless CLI targets .NET 8 and references `MvsAnalyzer.Core`. Add `--json` for the versioned `mvs-cli-result/v1` machine response used by automation and Python. From a source checkout:

```bash
dotnet run --project MvsAnalyzer.Cli -- version
dotnet run --project MvsAnalyzer.Cli -- calibrate --in data.csv --out calibration --seed 20260719
dotnet run --project MvsAnalyzer.Cli -- analyze --in data.csv --calibration calibration --out analysis
```

Available command families include `calibrate`, `analyze`, `variance`, `estimation`, `melsm`, `benchmark`, `resume`, `state-check`, `version` and `env`. Run the CLI without arguments or with `--help` for the complete option reference.

Linux runs do not render figures, but the scientific tables, reports and manifests are still produced.

### Jupyter and Colab

The repository includes Jupyter and Colab notebooks that use the same CLI/Python stack. New notebook work should consume the Python package directly. The old desktop-to-Colab controller is retained only for 1.4.0 compatibility and is not part of the 1.5.0 development target.

## Data format

Use one row per measurement. The standard independent-group workflow expects these columns:

| Column | Meaning |
| --- | --- |
| `entity` | Person, sample, device or other measured object |
| `group` | Independent group membership |
| `value` | Numeric measurement |
| `sequence` | Optional integer order or timepoint |

Repeated conditions for the same subject require a repeated-measures workflow rather than the independent-group analysis. Column aliases, import rules, encodings and examples are documented in [Data format](docs/DATA_FORMAT.md).

## Reproducibility and outputs

Completed runs save structured results and metadata rather than only a displayed table. Depending on the workflow, the output can include calibration state, CSV/JSON results, a run manifest, input and settings hashes, engine and formula identifiers, environment information, diagnostics and artifact checksums.

A saved calibration can only be reused when its compatibility checks pass. `--force` can allow different input bytes for the standard analysis workflow, but it does not bypass incompatible methods or schemas.

See [Reports](docs/OUTPUTS.md), [Integrity checks](docs/AUDIT.md) and [Backups](docs/BACKUPS.md).

## Development direction

Development from 1.5.0 onward is CLI/Python-first. The Windows desktop is archived at 1.4.0 and has been removed from CI and release builds. Current priorities are the 1.5.0 statistical redesign, Python packaging, DataFrame serialization policy, notebook ergonomics and benchmarked CLI/Python reproducibility. See [MVS 1.5.0 plan](docs/V1_5_PLAN.md) and [benchmark history](docs/BENCHMARK_HISTORY.md).


## Documentation

- [Data format](docs/DATA_FORMAT.md)
- [Methods](docs/METHODS.md)
- [Reports and exported files](docs/OUTPUTS.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Benchmark](docs/BENCHMARK.md)
- [Benchmark history](docs/BENCHMARK_HISTORY.md)
- [MVS 1.5.0 plan](docs/V1_5_PLAN.md)
- [Metric registry](docs/METRIC_REGISTRY.md)
- [Paper benchmark run](docs/PAPER_BENCHMARK.md)
- [Colab and remote workflow](docs/REMOTE.md)
- [Backups and checkpoints](docs/BACKUPS.md)
- [Plugins](docs/PLUGINS.md)
- [Migration](docs/MIGRATION.md)
- [CLI machine protocol](docs/CLI_MACHINE_PROTOCOL.md)
- [Python API](docs/PYTHON_API.md)
- [Interface compatibility](docs/COMPATIBILITY.md)

## Privacy

Local analysis does not require an MVS account and the application does not send telemetry. Colab jobs are processed by Google's service, so review sensitive data before uploading a job or sharing a notebook. Job archives can contain the source measurements.

## License and citation

MVS Analyzer is released under the [MIT License](LICENSE). Citation metadata is provided in [CITATION.cff](CITATION.cff). Archived software version 1.4.0: [doi:10.5281/zenodo.22836364](https://doi.org/10.5281/zenodo.22836364).

## Русский

MVS Analyzer предназначен для статистического анализа повторных измерений. Основной сценарий сравнивает 12 сводных метрик на пользовательских данных с помощью моделирования, оценивает мощность и частоту ложных срабатываний, сравнивает независимые группы и сохраняет метаданные расчёта.

В проекте также есть анализ компонентов дисперсии, исследования свойств оценок на данных с известной истиной, экспериментальная mixed-effects location-scale модель, benchmark и инструменты проверки результатов.

Текущий исходный checkpoint: полный development benchmark завершён с сохранённым
NO-GO. Исправлена численная реализация staged Huber; внутренние Holm/maxT проверены,
но не включены в рабочий анализ. Актуальные проверки, ограничения и условия
готовности собраны в [итоговом аудите](docs/ROUND15_PROJECT_READINESS_AUDIT.md).
Проект ещё не объявлен научно готовым релизом 1.5.0.

### Как запускать

Новая разработка ведётся вокруг Python API и headless CLI. Python-пакет вызывает совместимый CLI и не дублирует статистические методы; Jupyter/Colab должны использовать тот же стек. Windows-приложение 1.4.0 остаётся архивной версией и больше не собирается в CI и новых релизах.

Формат данных и ограничения описаны в [документации](docs/README.md). Перед интерпретацией результатов стоит прочитать [методы](docs/METHODS.md) и [ограничения валидации](docs/VALIDATION.md).

### Куда развивается проект

Начиная с линии 1.5.0 основной интерфейс проекта — Python/CLI. План включает новый registry метрик, семейства location/variability, candidate sets вместо обязательного top-1, новый multiplicity layer и отдельный BENCH-2.0 после заморозки метода. История каждого frozen benchmark сохраняется в репозитории.

