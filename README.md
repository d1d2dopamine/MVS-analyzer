<p align="center"><img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo"></p>
<h1 align="center">MVS Analyzer</h1>
<p align="center">Explore what repeated measurements can reveal about differences between groups.</p>
<p align="center"><a href="#русский">Русский</a></p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/release-1.4.0-1f6feb?style=flat-square" alt="release 1.4.0">
  <img src="https://img.shields.io/badge/engine-1.6.2-6f42c1?style=flat-square" alt="engine 1.6.2">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
  <a href="https://doi.org/10.5281/zenodo.22836364"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.22836364.svg" alt="DOI: 10.5281/zenodo.22836364"></a>
</p>

MVS Analyzer is a local statistical tool for data where each person, sample or device is measured several times. It compares independent groups using summaries of each entity's measurements, keeping the entity as the unit of comparison.

The central question is practical: **which summaries are sensitive to the kind of change you want to detect, under the conditions represented by your data?** MVS simulates specified changes, compares detection power and false-alarm rates, and saves the assumptions and results for inspection.

## What you can do

- Explore sensitivity to shifts in measurement level, within-entity variability and between-entity heterogeneity.
- Compare independent groups using summary metrics and inspect effect sizes, uncertainty and diagnostics.
- Use separate workflows for variance components, estimator performance on simulated data with known truth, and experimental repeated-condition modelling.
- Keep calibration, results and run metadata together so an analysis can be checked and reproduced.

Calibration depends on the observed data and chosen simulation scenario; it does not identify a universally best metric. The development version is not yet validated for confirmatory use: see [validation and limitations](docs/VALIDATION.md) and [project readiness](docs/PROJECT_READINESS_HANDOFF.md).

## Quick start

Install the [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0), then run from the repository root:

```bash
dotnet run --project MvsAnalyzer.Cli -- calibrate --in examples/demo_three_groups.csv --out calibration --repetitions 150 --seed 20260719
dotnet run --project MvsAnalyzer.Cli -- analyze --in examples/demo_three_groups.csv --calibration calibration --out analysis
```

This small demonstration uses 150 simulation repetitions, not a recommended budget for a research calibration.

The first command calibrates on the bundled example; the second uses that calibration to analyze the same data. Inspect the exported tables and diagnostics in the output directories. See [output files](docs/OUTPUTS.md) for their meaning, or run the CLI with `--help` for options.

For your own CSV/TSV file, use one row per measurement:

- `entity`: the person, sample or device being measured
- `group`: independent group membership
- `value`: the numeric measurement
- `sequence`: optional integer measurement order or timepoint

Use one outcome in consistent units. Repeated conditions on the same subjects need a repeated-measures workflow, not the independent-group comparison. See [input requirements and examples](docs/DATA_FORMAT.md).

## Ways to use MVS

- **CLI:** run analyses locally or from scripts.
- **Python, Jupyter and Colab:** use the [Python API](docs/PYTHON_API.md), which calls the same compiled engine. A compatible CLI is required; statistical methods are not reimplemented in Python.
- **Local MCP:** an optional [experimental interface](docs/LOCAL_MCP.md) for summary analysis with an existing calibration. Windows runtime verification is still pending.

Development focuses on CLI and Python. The desktop application is archived at version 1.4.0.

## Documentation

Start with [methods](docs/METHODS.md), [validation and limitations](docs/VALIDATION.md), or the [documentation index](docs/README.md). Setup guides, output formats, compatibility rules and development reports live there.

## Privacy

Local analysis requires no MVS account and sends no telemetry. Colab runs on Google's service; review sensitive data before uploading or sharing a notebook or job archive.

## License and citation

MVS Analyzer is released under the [MIT License](LICENSE). Use [CITATION.cff](CITATION.cff) for citation metadata. Archived software version 1.4.0: [doi:10.5281/zenodo.22836364](https://doi.org/10.5281/zenodo.22836364).

## Русский

MVS Analyzer — локальный инструмент для анализа данных, в которых каждый человек, образец или прибор измеряется несколько раз. Основной сценарий сравнивает независимые группы по сводным характеристикам каждого объекта. Повторные измерения одного объекта не считаются отдельными независимыми наблюдениями.

Идея MVS — проверить, какие характеристики чувствительны к интересующему изменению в условиях ваших данных. Для этого программа моделирует заданные изменения уровня и вариабельности, оценивает мощность и частоту ложных срабатываний, а затем сохраняет результаты вместе с настройками и диагностикой. Калибровка зависит от данных и сценария: она не выбирает универсально «лучшую» метрику.

Также доступны отдельные сценарии анализа компонентов дисперсии, сравнения оценок на моделируемых данных с известными параметрами и экспериментального моделирования повторных условий. Текущая разрабатываемая версия ещё не прошла валидацию для подтверждающих научных выводов; [ограничения](docs/VALIDATION.md) и [состояние готовности](docs/PROJECT_READINESS_HANDOFF.md) описаны отдельно.

Для запуска используйте команды из раздела [Quick start](#quick-start): нужен .NET 8 SDK. Собственный CSV/TSV должен содержать столбцы `entity`, `group`, `value`, по одной строке на измерение. Подробности — в [формате данных](docs/DATA_FORMAT.md).

Основные интерфейсы — CLI и [Python API](docs/PYTHON_API.md), использующие один вычислительный движок. Есть экспериментальный [локальный MCP](docs/LOCAL_MCP.md) для анализа с готовой калибровкой; проверка его работы на Windows ещё не завершена. Desktop-версия 1.4.0 архивная. Все руководства и технические отчёты собраны в [документации](docs/README.md).
