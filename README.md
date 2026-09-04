<p align="center">
  <img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo">
</p>

<h1 align="center" id="mvs-analyzer">MVS Analyzer</h1>

<p align="center">▪</p>

<p align="center"><strong>English</strong> · <a href="#русский">Русский</a></p>

<p align="center">
  Metrics Value System. Which metric actually sees the change you care about?<br>
  Windows desktop · no accounts · no telemetry · local calculations; optional hosted-notebook links
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/app-1.5.0-1f6feb?style=flat-square" alt="app 1.5.0">
  <img src="https://img.shields.io/badge/engine-1.2.0-6f42c1?style=flat-square" alt="engine 1.2.0">
  <img src="https://img.shields.io/badge/formula-MVS--1.3.0%20frozen-brightgreen?style=flat-square" alt="formula MVS-1.3.0 frozen">
  <img src="https://img.shields.io/badge/made%20with-.NET%208-512BD4?style=flat-square" alt="made with .NET 8">
  <img src="https://img.shields.io/badge/Windows-10%2B%20x64-0078D6?style=flat-square" alt="Windows 10+ x64">
  <img src="https://img.shields.io/badge/NuGet%20dependencies-0-4b4b4b?style=flat-square" alt="zero NuGet dependencies">
  <img src="https://img.shields.io/badge/network-never-crimson?style=flat-square" alt="no networking">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
</p>

<p align="center">
  <a href="https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest"><img src="https://img.shields.io/github/v/release/d1d2dopamine/MVS-Analyzer?style=for-the-badge&label=download%20for%20Windows&color=0078D6&logo=windows&logoColor=white" alt="download for Windows"></a>
</p>

<p align="center">
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="docs/METHODS.md">Methods</a> ·
  <a href="docs/REMOTE.md">Remote</a> ·
  <a href="docs/VALIDATION.md">Validation</a> ·
  <a href="docs/ARCHITECTURE.md">Developer docs</a> ·
  <a href="examples/">Example data</a>
</p>


> **Authoritative version:** public application **1.4.0**, scientific engine **1.6.0**, formula **MVS-1.4.0**. The development snapshot supplied for this update was labelled 1.5.0; the public sequence resumes after 1.3.2. The original badge artwork above is intentionally preserved unchanged, so its embedded version strings are historical, not the version of this source tree.

## What the program is for

MVS Analyzer helps examine how entity-level summaries respond to specified changes in repeated measurements. It is a research and planning tool, not a device that discovers an unknown scientific truth or certifies a preferred metric.

The update combines the requested 1.6/1.7/1.8 development scope under one public release. Four workflows are now separate:

| Workflow | Question | Main output |
|---|---|---|
| Summary calibration | Which summary reacts to a centre, within-entity, or between-entity change under this generator? | Per-track power/FPR, Monte Carlo bounds, detection index, conditional MDE |
| Variance components | How much variation is within entities versus between latent entity intercepts? | Gaussian REML estimates, pointwise parametric intervals, separate bootstrap tests and power |
| Estimation study | How biased/variable are estimators of a **known, common target** under a specified mechanism? | Bias, MSE, RMSE, efficiency ratios, coverage and simulation uncertainty |
| MELSM · experimental | How do condition and optional time affect the mean and conditional variance in repeated observations? | Marginal-ML parameters, random-effect summaries and numerical diagnostics |

### Important distinctions

- SD of observed entity means contains measurement error; it is **not** the latent between-entity variance.
- Sensitivity of summary metrics to a between-entity scenario is **not** a variance-component hypothesis test. Use the separate model for that question.
- Bias/MSE require known truth. The estimation workflow generates synthetic data; it does not claim to know the true bias of an uploaded CSV.
- An insignificant p-value is not proof of equality. Two-group equivalence uses an explicitly approximate bootstrap-interval criterion; it is not an exact TOST implementation.
- The score is a **detection index**, not measurement validity, estimator efficiency, or a general quality certificate.

## Main changes

- Finite JSON numbers or `null`: unavailable MDE/interval values no longer crash calibration saving. `null` never means zero.
- Twelve summaries: median, SD, CV, MAD, IQR, normalized MAD/IQR, mean, RMS, range, geometric mean (positive observations only), and 20% trimmed mean.
- Three default sensitivity tracks: location, within variability, between heterogeneity. The optional decrease scenario is retained.
- A common pooled null and matched alternative, symmetric contamination, common random draws, consistent minimum-repeat rules and explicit simulation failures.
- The displayed difference decisions correct the **entire fixed metric registry** with Bonferroni, even when calibration used the same data. Approximate raw tests retain their limitations.
- Confidence-bound candidate gates; no arbitrary score ≥60 cutoff. Empty candidate sets are allowed.
- Calibration schema 2 freezes filtering, import-profile fingerprint, seed, alpha, margin, scenario, split policy, registry and method versions. Incompatible legacy states require recalibration.
- Flow-based result summaries, separately scrollable tables, a scrollable sidebar, saved-state loading, and a **Scientific models** section. Existing image assets and badges are preserved.

## Build and test

The supplied source package was **not compiled or executed as a .NET application during preparation**, as requested. Static checks are documented in [validation/PACKAGE_QA.md](validation/PACKAGE_QA.md). The workflows below are the acceptance gates, not a claim that they have already passed.

```powershell
# Windows, .NET 8 SDK
dotnet build MvsAnalyzer.csproj -c Release
dotnet run --project MvsAnalyzer.Tests/MvsAnalyzer.Tests.csproj -c Release
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
.\build_release.bat
```

```bash
# Linux, .NET 8 SDK; no WinForms or drawing dependency
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -r linux-x64 \
  --self-contained true -p:PublishSingleFile=true -o publish/linux-cli
```

GitHub CI builds Windows, runs portable regressions on Windows/Linux, and repeats the reported **150-replication calibration → save → reload → analyze** sequence. An opt-in extended workflow exercises model diagnostics. A generated report, a passing smoke check, and independent scientific validation are different things.

## CLI quick start

```bash
./publish/linux-cli/mvs calibrate --in examples/demo_three_groups.csv \
  --out artifacts/calibration --repetitions 150 --seed 20260719
./publish/linux-cli/mvs analyze --in examples/demo_three_groups.csv \
  --calibration artifacts/calibration --out artifacts/analysis

# Separate within/between random-intercept components
./publish/linux-cli/mvs variance --in examples/variance_demo.csv \
  --out artifacts/variance --repetitions 200 --bootstrap 199 \
  --within-effect 1.3 --between-effect 1.3

# Known-truth estimation accuracy, not unknown truth from a CSV
./publish/linux-cli/mvs estimation --out artifacts/estimation --target mean \
  --shape normal --entities 20 --measurements 12 --repetitions 500

# Same IDs under different conditions: optional experimental MELSM
./publish/linux-cli/mvs melsm --in examples/repeated_conditions.csv \
  --out artifacts/melsm --quadrature 15
```

A 150-replication run is a **smoke check**, not publication-quality calibration; its MDE is intentionally unavailable. Model refits can be expensive. Reusing a non-empty scientific-output folder or an existing calibration requires `--overwrite`. `analyze` restores frozen settings; changing alpha, margin or preprocessing requires a new calibration. `--force` permits explicitly exploratory reuse on different input bytes but never bypasses method/schema compatibility.

## Desktop

1. Import one outcome in consistent units. Review entity/group counts and exclusions.
2. Choose scientific settings, then calibrate. Changing scientific settings invalidates reuse; changing preprocessing requires re-import.
3. Run analysis and read **adjusted p**, effect-interval status and per-track uncertainty.
4. Use **Scientific models** for variance components, known-truth estimation or MELSM. Each model writes a new output directory.
5. Review JSON/CSV diagnostics and the [Windows QA checklist](docs/WINDOWS_QA.md). Small windows, themes and high-DPI rendering still require testing on Windows.

Independent-group workflows use group/entity pairs. Repeated IDs across groups require explicit confirmation that they truly denote different independent entities. For the **same subjects across conditions**, choose MELSM; its IDs are global. Its present scope excludes AR(1), random slopes, ordinal/count likelihoods and arbitrary covariate formulas.

## Interpretation and reproducibility

Read [Methods](docs/METHODS.md), [Data format](docs/DATA_FORMAT.md), [Output schema](docs/OUTPUTS.md), [Validation](docs/VALIDATION.md), and [Migration](docs/MIGRATION.md) before comparing releases. No scientific performance claims are carried over from the old development snapshot.

The main test family contains twelve summary metrics; the two variance-component tests are a **different** family. Running both does not establish joint familywise control across all analyses. MELSM Wald intervals are pointwise and approximate. Choose the family and estimand before inspecting results.

Calculations are local, without telemetry or accounts. Opening a repository/notebook link uses your browser, and uploading to Colab/Kaggle transfers data to those services. Hashes detect accidental or unmatched edits only when compared with a trusted record; an editable local journal is not an external preregistration or proof against deliberate rewriting. Pseudonymous IDs are not irreversible anonymization.

## Documentation

- [Release notes](RELEASE_NOTES_v1.4.0.md) · [Changelog](CHANGELOG.md)
- [Methods](docs/METHODS.md) · [Model scope and limitations](docs/VALIDATION.md)
- [CLI and hosted notebooks](docs/REMOTE.md)
- [Architecture](docs/ARCHITECTURE.md) · [Audit](docs/AUDIT.md)
- [Benchmark](docs/BENCHMARK.md) · [Declared protocol](docs/PREREGISTRATION.md)
- [Data-only plugins](docs/PLUGINS.md)

---

## Русский

<p align="center">
  <img src="docs/assets/logo.png" width="176" alt="Логотип MVS Analyzer">
</p>

<h1 align="center" id="русский">MVS Analyzer</h1>

<p align="center">▪</p>

<p align="center"><a href="#mvs-analyzer">English</a> · <strong>Русский</strong></p>

<p align="center">
  Metrics Value System. Какая метрика действительно видит изменение, которое вам важно?<br>
  Настольное приложение для Windows · без аккаунтов · без телеметрии · вообще без сетевого кода
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/app-1.5.0-1f6feb?style=flat-square" alt="app 1.5.0">
  <img src="https://img.shields.io/badge/engine-1.2.0-6f42c1?style=flat-square" alt="engine 1.2.0">
  <img src="https://img.shields.io/badge/formula-MVS--1.3.0%20frozen-brightgreen?style=flat-square" alt="formula MVS-1.3.0 frozen">
  <img src="https://img.shields.io/badge/made%20with-.NET%208-512BD4?style=flat-square" alt="made with .NET 8">
  <img src="https://img.shields.io/badge/Windows-10%2B%20x64-0078D6?style=flat-square" alt="Windows 10+ x64">
  <img src="https://img.shields.io/badge/NuGet%20dependencies-0-4b4b4b?style=flat-square" alt="zero NuGet dependencies">
  <img src="https://img.shields.io/badge/network-never-crimson?style=flat-square" alt="no networking">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
</p>

<p align="center">
  <a href="https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest"><img src="https://img.shields.io/github/v/release/d1d2dopamine/MVS-Analyzer?style=for-the-badge&label=%D1%81%D0%BA%D0%B0%D1%87%D0%B0%D1%82%D1%8C%20%D0%B4%D0%BB%D1%8F%20Windows&color=0078D6&logo=windows&logoColor=white" alt="скачать для Windows"></a>
</p>

<p align="center">
  <a href="CHANGELOG.md">Изменения</a> ·
  <a href="docs/METHODS.md">Методы</a> ·
  <a href="docs/REMOTE.md">Удалённо</a> ·
  <a href="docs/VALIDATION.md">Валидация</a> ·
  <a href="docs/ARCHITECTURE.md">Документация</a> ·
  <a href="examples/">Примеры данных</a>
</p>


> **Версия этого исходного пакета:** приложение **1.4.0**, научный движок **1.6.0**, формула **MVS-1.4.0**. Прежние бейджи и картинки сохранены по просьбе автора; цифры внутри старых бейджей не являются версией этого дерева исходников. Публичная версия продолжает последовательность после 1.3.2; загруженный снимок разработки назывался 1.5.0.

### Что изменилось

- Разделены три трека чувствительности: сдвиг уровня, внутрисущностный разброс и межсущностная гетерогенность.
- Добавлена отдельная гауссова модель компонентов дисперсии: REML-оценки, модельные интервалы, раздельные bootstrap-тесты и мощность для within/between. Дисперсия средних сущностей больше не выдаётся за латентную межсущностную дисперсию.
- Добавлена симуляция качества оценивания: bias, MSE, RMSE, эффективность, покрытие и ошибки Monte Carlo. Истина известна из генератора; на реальном CSV неизвестное смещение не «угадывается».
- Добавлен **экспериментальный MELSM** для повторных измерений: маргинальное правдоподобие, адаптивная квадратура, случайные эффекты уровня/масштаба, необязательная корреляция и линейное время.
- Исправлено сохранение `NaN`/Infinity: JSON содержит числа или `null`, а не ложные нули. Малый бюджет симуляций не создаёт фиктивный MDE.
- Перестроены нулевая/альтернативная симуляции, учёт отказов и множественных проверок; исправлено направление Cliff’s delta.
- Выводы о различиях используют Бонферрони по всем 12 метрикам. Кандидаты — приоритеты, а не способ спрятать остальные проверки. Балл — индекс обнаружения, не универсальная «точность».
- Калибровка фиксирует научные настройки и версию импорта. Старые состояния несовместимы; нужна новая калибровка.
- Переработан экран результатов, добавлены раздельная прокрутка таблиц, прокрутка меню и раздел **Научные модели**. Визуальные проверки Windows/HiDPI ещё нужно выполнить.

### Как начать

Соберите приложение в GitHub CI или командами выше. Прогон на 150 симуляций предназначен для проверки сохранения/загрузки, а не для обоснования научного результата. Для раздельных компонентов используйте `variance`, для качества оценивания `estimation`, для повторных условий на одних ID — `melsm`.

**Во время подготовки исходников .NET-компиляция и запуск C#-тестов не выполнялись**, как и было запрошено. В пакет включены тесты и рабочие инструкции CI; их успешность должен установить реальный прогон. MELSM остаётся экспериментальным: сходимость не доказывает адекватность модели. Хеши и локальный аудит не заменяют внешнюю предрегистрацию и независимую валидацию.

Потенциально полезное назначение программы — прозрачное исследование чувствительности и планирование измерений. Не следует позиционировать её как автоматический выбор «правильной» метрики, подтверждение отсутствия эффекта или сертифицированный статистический пакет.
