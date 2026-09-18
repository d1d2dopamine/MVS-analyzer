<p align="center"><img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo"></p>

<h1 align="center">MVS Analyzer</h1>
<p align="center">Statistical analysis for repeated measurements, with reproducible calibration, diagnostics and saved run metadata.</p>
<p align="center"><a href="#русский">Русский</a></p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/app-1.4.0-1f6feb?style=flat-square" alt="app 1.4.0">
  <img src="https://img.shields.io/badge/engine-1.6.0-6f42c1?style=flat-square" alt="engine 1.6.0">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
</p>

MVS Analyzer compares summary metrics for repeated measurements and includes separate workflows for variance components, known-truth estimation studies and an experimental mixed-effects location-scale model. The same compiled `MvsAnalyzer.Core` statistical engine is used by the Windows application and the headless .NET CLI; the Python package delegates to that CLI instead of reimplementing the methods.

Current release line: application `1.4.0`, scientific engine `1.6.0`, formula `MVS-1.4.0`.

## What MVS does

The main workflow is designed for data where each independent entity has several measurements. MVS can simulate declared changes on the observed data, estimate detection power and false-alarm rates for 12 summary metrics, compare independent groups and save the settings and provenance needed to inspect the run later.

The project also contains:

- Gaussian within-entity and between-entity variance-component analysis;
- known-truth simulation studies for estimator bias, MSE and related performance measures;
- an experimental mixed-effects location-scale model for repeated conditions;
- benchmark, validation, audit and checkpoint tooling.

Calibration is conditional on the observed data and the selected simulation scenario. It does not establish a universally best metric or external validity. See [Methods](docs/METHODS.md) and [Validation and limitations](docs/VALIDATION.md) before using results for confirmatory work.

## Interfaces

### Windows desktop

Download the current Windows x64 release from [Releases](https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest), extract it and run `MVS_Analyzer.exe`. The self-contained release does not require a separate .NET installation.

### CLI

The headless CLI targets .NET 8 and references the same `MvsAnalyzer.Core` assembly as the desktop application. Add `--json` for the versioned `mvs-cli-result/v1` machine response used by automation and Python. From a source checkout:

```bash
dotnet run --project MvsAnalyzer.Cli -- version
dotnet run --project MvsAnalyzer.Cli -- calibrate --in data.csv --out calibration --seed 20260719
dotnet run --project MvsAnalyzer.Cli -- analyze --in data.csv --calibration calibration --out analysis
```

Available command families include `calibrate`, `analyze`, `variance`, `estimation`, `melsm`, `benchmark`, `resume`, `state-check`, `version` and `env`. Run the CLI without arguments or with `--help` for the complete option reference.

Linux runs do not render figures, but the scientific tables, reports and manifests are still produced.

### Python

The path-based Python API lives in `python/` and controls a compatible `mvs` executable through the machine protocol. It returns typed result objects and saved artifact paths while keeping the statistical implementation in .NET.

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

### Jupyter and Colab

The repository includes [MVS_Colab.ipynb](notebooks/MVS_Colab.ipynb) and the Python controller used by the current Colab workflow. The notebook executes the .NET CLI rather than reimplementing the statistics in Python. See the [Colab guide](docs/REMOTE.md) for the desktop bridge, manual mode and file exchange.

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

The first interface-layer milestone is now implemented: a compiled Core boundary, versioned CLI machine output, a thin Python API, a local Python quick-start notebook and cross-interface parity checks. Remaining work focuses on broader packaging, DataFrame serialization policy and additional notebook ergonomics without duplicating the statistical methods.


## Documentation

- [Data format](docs/DATA_FORMAT.md)
- [Methods](docs/METHODS.md)
- [Reports and exported files](docs/OUTPUTS.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Benchmark](docs/BENCHMARK.md)
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

MVS Analyzer is released under the [MIT License](LICENSE). Citation metadata is provided in [CITATION.cff](CITATION.cff).

## Русский

MVS Analyzer предназначен для статистического анализа повторных измерений. Основной сценарий сравнивает 12 сводных метрик на пользовательских данных с помощью моделирования, оценивает мощность и частоту ложных срабатываний, сравнивает независимые группы и сохраняет метаданные расчёта.

В проекте также есть анализ компонентов дисперсии, исследования свойств оценок на данных с известной истиной, экспериментальная mixed-effects location-scale модель, benchmark и инструменты проверки результатов.

### Как запускать

Для обычной работы можно использовать Windows-приложение из [Releases](https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest). Для автоматизации и серверных расчётов в репозитории есть CLI на .NET 8 с машинным режимом `--json`. В каталоге `python/` есть Python API, который вызывает тот же CLI и не дублирует статистические методы. Jupyter/Colab также использует .NET-движок.

Формат данных и ограничения описаны в [документации](docs/README.md). Перед интерпретацией результатов стоит прочитать [методы](docs/METHODS.md) и [ограничения валидации](docs/VALIDATION.md).

### Куда развивается проект

Первый этап интерфейсного плана реализован: выделен `MvsAnalyzer.Core`, добавлен версионированный JSON-протокол CLI, path-based Python API, локальный Jupyter quick start и parity-проверка Python/CLI. Следующие шаги — упаковка Python-релиза, формальная политика DataFrame-сериализации и расширение notebook-интерфейса без отдельной реализации статистики.

