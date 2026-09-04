# Changelog

<p align="center"><strong>English</strong> · <a href="#русский">Русский</a></p>

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The author's original Russian development notes — the long version, with the
reasoning behind every fix — are in the [second half of this file](#русский).

> **Reading the versions below.** `engine` is `AnalysisEngine.EngineVersion` and
> `formula` is the frozen specification recorded in every `run_manifest.json`.
> When `formula` changes, previously exported runs legitimately report
> `FORMULA_CHANGED` during audit and must be re-run before they are compared
> with new results.

## [Unreleased]

### Added

- **Benchmark (`MVS-BENCH-1.0.0`).** A pre-registered protocol that measures
  what the program claims: seven ways of getting from ten candidate metrics to
  one answer (cherry-picking, Bonferroni, two fixed metrics, a pilot-locked
  metric, and the MVS path with and without its gate) are run against data whose
  truth is known by construction, alongside an oracle that chooses with
  hindsight. Reported per condition: false-discovery rate with Wilson intervals
  and Monte-Carlo standard errors, power across the effect grid, the gap to the
  oracle, split-half Kendall tau, top-1 agreement, behaviour under 2/5/10 %
  contamination, and a determinism digest. The protocol text, the five pass/fail
  thresholds and the seeds are frozen in `Benchmark/BenchmarkProtocol.cs`; its
  SHA-256 is verified by the test suite and printed on every figure, so a
  threshold cannot be moved after a result without the change being visible on
  images that were already published.
- **Settings -> Developer -> benchmark.** Depth (quick / standard / full), seed,
  results folder and an optional folder of real recordings. Progress is
  cancellable, and the figures folder opens by itself when the run ends.
- **Headless mode**: `MVS_Analyzer.exe --benchmark --profile full --seed N --out
  <folder>`, with `--real-data`, `--lang` and `--quiet`. Exit code 2 when a
  pre-registered threshold is missed, so a regression in error control can fail
  a build pipeline.
- **Benchmark output**: 14 PNG figures in print, story, square and wide sizes
  (Okabe-Ito palette, safe zones respected, every figure footed with seed,
  protocol hash and formula hash), five CSV tables, the verbatim protocol, a
  manifest and `SHA256SUMS.txt`. Each run is also appended to a hash-chained
  `benchmark_journal.jsonl`; the application's own run journal is untouched.
- `docs/BENCHMARK.md` - the full protocol, the figure guide, instructions for
  checking somebody else's run, and an explicit list of what the benchmark does
  *not* prove.
- `benchmark_data/prepare_physionet.py` and `benchmark_data/README.md` - an
  optional plasmode stage on real gait recordings (PhysioNet gaitndd, ODC-BY).
  Standard-library Python only; no recordings are committed to the repository.
- Four benchmark tests in the suite: the protocol hash is unchanged, the random
  stream reproduces its golden values, the data generator has the planned shape,
  and Kendall tau and the Wilson interval behave.
- Application icon: multi-size `app.ico` (16 to 256 px, transparent background,
  generated from the master logo) is now embedded in the executable and used for
  the window, the taskbar and Explorer.
- Logo in the README header, stored as `docs/assets/logo.png`.
- In-app wordmark on the Home page, loaded from the embedded
  `Assets/inapp_logo.png`. Missing or damaged branding never blocks startup:
  the loader fails soft and the page simply starts with its first card.
- `validation/` — a validation suite with seven synthetic datasets whose correct
  answer is known by construction, the seven data-generating mechanisms behind
  them (`dgp.py`), an independent Monte-Carlo reference implementation
  (`reference_simulation.py`) that computes which statistic actually wins in
  each world, and `analyze_results.py`, which measures weight sensitivity and
  discriminant validity of any finished run. Python + numpy only; nothing ships
  with the application.
- `docs/VALIDATION.md` — the reference truth table on two effect-size grids and
  six experiments (ground-truth recovery, pipeline false-positive rate, weight
  sensitivity, discriminant validity, seed stability, degenerate input) with
  the numeric threshold that decides each one.
- `docs/PREREGISTRATION.md` — mechanisms, hypotheses H1–H7, pass/fail
  thresholds and the conditions under which the composite would be abandoned,
  all frozen before the first run.
- `docs/METHODS.md` — new sections: the three modes the tool can be used in and
  which of them are safe; the simulation design written out in ADEMP form; the
  dimensional analysis of the score and the declaration that its scale is
  ordinal; where the weights came from; and eight open methodological
  questions.

### Changed

- Documentation now states plainly that selecting a metric on the same data you
  report inflates the error rate — measured at **0.205** against a nominal 0.05
  for "any of the ten metrics" under a pure null — and that the score is a
  dimensionless, ordinal, non-compensatory index in which differences are not
  interpretable.
- The `score >= 60` candidate rule is documented as on notice for removal.
  No code has changed yet: `engine 1.2.0` and `formula MVS-1.2.0` are
  untouched, so every existing run remains valid and comparable.

### Planned

- Drop the `score >= 60` gate, keep the false-alarm and power gates, and report
  the score as a rank with an uncertainty band (bumps the formula version).
- Add the geometric mean — and a trimmed mean — to the metric set.
- Add estimation-quality components (bias, MSE, relative efficiency) to the
  score, which today measures detection only.
- Explicit mode selection (design / multiverse / exploratory) when a project is
  created, with exploratory runs labelled as such in every export.
- Warn instead of ranking when every applicable metric is at ceiling power.
- Paired and repeated-measures designs.
- Post-hoc pairwise comparisons after a significant Kruskal–Wallis test.
- `TableLayoutPanel` relayout inside cards and DPI hardening for 125–150 % scaling.
- Persistent run history across sessions.
- Headless CLI over the existing engine.

---

## [1.5.0] - 2026-09-05

`engine 1.2.0` · `formula MVS-1.3.0` · `protocol MVS-BENCH-1.1.0` — **all three unchanged.** This
release adds a place to run the program; it does not change a single number the program produces.
Runs exported by 1.4.0 stay comparable.

### Added

- **A headless engine (`mvs`).** The same analysis without a window: `mvs calibrate`,
  `mvs analyze`, `mvs benchmark`, `mvs env`, `mvs version`. It lives in its own project whose
  source files are listed one by one instead of globbed, so the next form somebody adds cannot
  quietly break the Linux build. Exit codes are `0` done, `2` a benchmark threshold was missed,
  `1` error — the middle one is a result, not a crash, and CI treats it that way. Published for
  `linux-x64` on every commit and attached to every release.
- **Calibration is a file now.** `calibrate` writes `calibration_state.json`, and `analyze` reads
  its settings from that file rather than from its own command line, so the two phases cannot
  disagree about the seed. This matters most in a hosted session that can be reclaimed at any
  moment: losing one costs a cell, not the whole run.
- **A calibration measured on other data is refused.** `analyze` compares the dataset hash with
  the one recorded in the calibration and stops. A calibration is a statement about one dataset
  and is worthless attached to another; the failure it prevents is a number that looks like a
  result and is not one. `--force` exists for when you know why the bytes changed, and both
  hashes go into the manifest either way.
- **Three notebooks (`notebooks/`).** Colab for calibration and analysis, Colab for the
  benchmark, Kaggle for the longer profiles. Each is exactly three cells: **calibrate**,
  **analyse**, **download a zip of the results**. The first cell fetches the source, installs the
  .NET build tools and compiles the engine, which takes a minute or two once per session.
- **Remote run card in Settings.** Buttons that open the prepared notebook, open Kaggle, open the
  repository, and build a **job archive** — a dataset packed together with every current setting,
  so a remote run is *the same analysis* rather than a similar one. The privacy warning sits next
  to the buttons rather than in a document nobody opens.
- **`--threads n` for the benchmark.** Two vCPUs is what a free session gives out, and a default
  of `ProcessorCount - 1` is wrong on a machine that small. Thread count cannot change a result:
  every replication owns its own random stream, so the parallel loops stay bit-identical however
  the work is scheduled.
- **Determinism has a scope.** Every benchmark manifest now records `environment`,
  `environmentHash` and `determinismScope: withinEnvironment`. Bit-identical replay was always an
  *inside one environment* claim: `Math.Log`, `Math.Exp`, `Math.Pow` and `Math.Cos` are not
  required to be correctly rounded and .NET makes no cross-platform promise about them, while
  `Math.Sqrt` is exact by specification. The hash covers the architecture, the runtime and a
  twelve-value probe of those functions — deliberately **not** the operating system build string,
  because a Windows patch changes that without changing any arithmetic, and a hash that moves for
  cosmetic reasons teaches its reader to ignore it.
- **`docs/REMOTE.md`**, plus CI that publishes the headless build on Linux, runs a calibration and
  an analysis on the bundled example, checks that a foreign calibration is refused, and verifies
  that every notebook is valid JSON with exactly three cells.

### Fixed

- **Four tests added in 1.4.0 never ran.** `TrackNormalisation`, `PerTrackGate`,
  `SpreadTrackCandidate` and `HeldOutOracle` were written and then never registered in the test
  list, so the suite reported 21 passes while 25 methods existed. They are registered now,
  together with the three added this release: 28 tests. A test that is not in the list is worse
  than no test, because it buys confidence without providing any.
- **Windows-only console attachment guarded.** `AttachConsole` is a `kernel32` import and ran
  unconditionally; the headless build would have died on Linux at the first `--benchmark`.
- **Figure code excluded from the headless project.** `System.Drawing.Common` does not draw
  outside Windows, so the figure step becomes a no-op there. Every table, report and manifest is
  still written, and the images can be produced later from the same folder on Windows.

### Not done, on purpose

- **The statistics planned for 1.6.0 are still in 1.6.0.** Permutation p-values, the Cucconi
  gatekeeper, closed testing and the two-gate selection cannot be *validated* without running the
  benchmark many times over, and running it many times over is what this release makes possible.
  The order is the reverse of how it looks: infrastructure first, because the statistics depend on
  it.
- **The offline mode is not removed.** Everything here is additive. Removing the local path would
  take the program away from exactly the people who cannot upload their measurements anywhere.
- **Sharding and resume.** One benchmark still runs inside one session. `--shard`, `merge` and
  `--resume` are 1.6.0 work; the quick profile fits in a session with room to spare.
- **The notebook link 404s until `notebooks/` is pushed.** A button cannot create a filled-in
  notebook in an account it holds no token for. What does work is the deep link Colab provides for
  public repositories, and that needs the files on the default branch first.

## [1.4.0] - 2026-09-05

Two tracks. Until this release the program calibrated every metric against a shift of the centre
and then applied the winner to whatever the data actually contained. In the benchmark condition
where only the spread changed, that cost 40 percentage points of power against an oracle.

### Changed

- Calibration runs one track per question. `AnalysisEngine.Calibrate` accepts a list of tracks and
  defaults to `location` and `variability`. Power, the power curve, the score and the MDE are now
  estimated separately in each track.
- The null sample, robustness, repeatability and coverage are computed once and shared by all
  tracks. They do not depend on the injected effect, so estimating them per track would only have
  added noise. The false alarm rate is therefore the same number as before, not a second estimate
  of it.
- The candidate gate is evaluated inside each track, with its own cap of four candidates, so one
  question cannot crowd the other off the results page.
- Results are ordered by whether a metric answers any of the asked questions, then by the best
  score it reaches in any track. Ordering by the centre track alone buried the spread answer.
- Formula refrozen as `MVS-1.3.0`, SHA-256 `dcc0ef643ff071d8c4c6e5d33a4329f86c49294d156a3463ee6398285709f9da`.
  The gate really did change, so the version and the hash had to change with it.
- Benchmark protocol refrozen as `MVS-BENCH-1.1.0`, SHA-256 `3bb871b666c189fd8b9188f920108e92b67542b7d63bfe2f1d24393dad5e9723`.
- Hypotheses A and B are judged on the procedure the program actually ships, which is now the
  two-track one. A second chance to reject is not free, so the two-track false alarm rate is
  measured rather than inherited from the single-track number.

### Added

- Procedure `mvs_two_track` in the benchmark. Each track selects its own metric and is tested at
  alpha divided by the number of tracks. The single-track procedures are kept, so the report shows
  the old and the new behaviour side by side instead of asserting an improvement.
- `results.csv` gains `tracks`, `track_powers`, `track_scores`, `track_mdes` and `candidate_tracks`.
  `calibration.csv` gains `tracks`, `track_powers`, `track_scores`, `track_mdes` and `track_curves`.
  Track values are pipe joined, so the column layout does not change shape when the number of
  tracks changes and an existing reader sees the file it saw before.
- `run_manifest.json` records the track list under `calibration.tracks`.
- Four tests: track normalisation, the per-track gate, a spread metric winning its own track, and
  the held-out oracle.

### Fixed

- The benchmark oracle was selection biased. `OracleMetric` chose the best of ten metrics and
  scored it on the same replications, which takes the maximum of ten noisy rates. At thirty
  replications the Monte Carlo standard error is about 4.6 points, so the oracle was inflated by
  roughly one to two of those, and all of that inflation was charged to MVS as lost power.
  `OracleMetricHeldOut` chooses on odd replications and scores on even ones. The biased figure is
  still printed next to it so the size of the old error stays visible.
## [1.3.3] - 2026-09-05

`engine 1.2.0` * `formula MVS-1.2.0` (unchanged)

An encoding and input-validation release. No statistic changed, so runs exported by
1.3.2 stay comparable: `formulaHash` and the benchmark `protocolHash` are untouched.

### Fixed

- **An unknown simulation scenario silently became a location shift.** `ApplyScenario`
  compared the scenario name against two string literals and treated everything else,
  including a typo or the `scale` spelling used in `docs/METHODS.md`, as *raise the
  level of the last group*. A plugin profile asking for a dispersion scenario therefore
  did not fail; it measured the wrong thing and reported the answer as if the requested
  scenario had run. Scenario names now live in one place, accept the documented
  aliases (`scale`, `dispersion`, `spread`, `location_up`, `location_down`), and an
  unrecognised name raises an error before any simulation starts.
- **Legacy CSV imports were decoded by assumption.** Anything that was not valid UTF-8
  was declared Windows-1251, so a CP866 or KOI8-R export arrived as garbage that looked
  like data. The importer now scores the candidate code pages against each other and
  keeps the most plausible reading, also recognising UTF-16 that carries no BOM. The
  chosen encoding is recorded in `CsvImporter.LastEncodingName` instead of being hidden.
- **Numbers carrying invisible separators were discarded as text.** Exports that group
  digits with a narrow or thin space, or that use a real Unicode minus sign instead of
  an ASCII hyphen, lost those measurements silently. They now parse.
- **Nine characters had been lost from the sources themselves.** `MainForm.Pages.cs`,
  `README.md` and `CHANGELOG.md` contained replacement characters committed by an
  earlier tool that had read them in the wrong encoding, so the interface displayed
  broken words. The letters were restored and a test now fails if any come back.
- **Benchmark CSV files opened as mojibake in Excel.** They are written with a BOM now,
  while markdown, txt and json stay BOM free so diffs and hashes do not change.
- **`--benchmark --lang ru` printed question marks.** The attached console inherited the
  OEM code page; it is switched to UTF-8, and a failure to do so is not fatal.

### Added

- Manifest declares `PerMonitorV2` DPI awareness and `activeCodePage=UTF-8`, which
  keeps the interface sharp on mixed-DPI setups and the process code page predictable.
- Five tests: a byte-exact Windows-1251 import, encoding detection, locale-noisy
  numbers, rejection of unknown scenarios, and glyph coverage of the scenario labels.

---
## [1.3.2] — 2026-08-22

`engine 1.2.0` · `formula MVS-1.2.0` (unchanged)

A correctness release. Both fixes were found while writing the stress dataset that now ships in `examples/`.

### Fixed

- **False-alarm rate was measured on the wrong world.** Inflation was previously evaluated against the smallest grid point of the effect simulation instead of the pooled null world, so a metric could look calibrated when it was not. The pooled-groups null is now the only source of the reported FPR, and `fpr_inflated` is raised when the measured rate exceeds `max(1.5 × α, α + 0.02)`.
- **Text reports were written after the manifest** and therefore escaped hashing. Plugin reports (`report_*.txt`) are now emitted before `run_manifest.json`, so every file in a run folder is covered by the integrity check.

### Changed

- The results card states explicitly when level metrics and spread metrics point at different groups, instead of presenting the highest-scoring metric as consensus.
- Audit output distinguishes a missing input hash (`NO_INPUT_HASH`, legacy runs) from a modified input file (`FILE_MODIFIED`).

---

## [1.3.0] — 2026

`engine 1.2.0` · `formula MVS-1.2.0`

### Added

- **Stress pack** plugin (`mvs.stress.pack`, `minAppVersion 1.3.0`): adversarial settings profiles and validation rules for deliberately hostile datasets.
- Split calibration (**Settings → Scientific rigour**): entities are split in half, the metric is chosen on one half and the answer computed on the other. Requires ≥ 8 entities per group; the mode is recorded in `calibration.calibrationSource`.
- `CANDIDATE_SET_UNSTABLE` and `SETTINGS_VARIED` audit codes: the same dataset producing different candidate sets, or different seeds/scenarios across runs, is now surfaced instead of being silently averaged over by the reader.

### Changed

- The candidate cap of four is enforced with an explicit **near-miss** report (within 2 points of the last candidate) so borderline metrics stop disappearing without explanation.

---

## [1.2.0] — 2026

`engine 1.2.0` · `formula MVS-1.2.0` · hash `70e1d577…e401e2f`

### Added

- **Minimum detectable effect (MDE)** per metric, interpolated at power 0.80 from the effect grid `1.00 / 1.02 / 1.05 / 1.10 / 1.20`, with the full power curve exported in `calibration.csv`.
- **Equivalence testing (TOST)** on the bootstrap distribution of Cliff's delta, default margin `0.147`, producing the *no difference* verdict.
- **Interval coverage** as the fifth score component (200 × 200 bootstrap) and **split-half repeatability** over 50 splits.
- **Lab pack** plugin (`mvs.lab.pack`): import profile for semicolon + decimal-comma instrument exports, strict-QC settings profile, Russian summary report template, validation rules and terminology.

### Changed

- **Formula bumped to `MVS-1.2.0`.** Weights are now power 0.30, false-alarm control 0.25, robustness 0.20, repeatability 0.15, coverage 0.10. Runs produced by `MVS-1.1.0` (hash `1aab2c38…107f5ab909`) report `FORMULA_CHANGED` and must be repeated.
- Verdicts are reported as one of *difference / equivalent / insufficient / not applicable* rather than a bare p-value.

---

## [1.1.0] — 2026

**formula MVS-1.1.0 (hash `1aab2c38…107f5ab909`)**

### Added

- Support for **3–10 groups** via the Kruskal–Wallis test, alongside Mann–Whitney for two groups.
- **Cliff's delta** with a 95 % percentile bootstrap interval (400 resamples) between the two most separated groups.
- **Plugin system**: `.mvsplugin` packages (data only), install/enable/disable, package hashing, and the **Report pack** (`mvs.report.pack`) with four declarative figure templates.
- **Run journal** with a SHA-256 hash chain, plus the **Audit** section for folder verification.
- Run manifests now hash the **input dataset** as well as every output file.

### Changed

- Run folders are never overwritten: each run gets `{prefix}_{runId}`.

---

## [1.0.0] — 2026

**Initial release.**

### Added

- Ten entity-level metrics: median, mean, standard deviation, coefficient of variation, MAD, IQR, normalized MAD, normalized IQR, RMS, range.
- Two-group comparison with the Mann–Whitney *U* test.
- Calibration by resampling the user's own measurements: false-alarm rate and power, with configurable seed, effect multiplier, scenario, outlier rate and missing rate.
- The MVS Score, candidate rules (`FPR ≤ 0.075`, `power ≥ 0.70`, `score ≥ 60`, max 4 candidates), and an explicitly empty candidate set when nothing qualifies.
- CSV/TSV import with delimiter and encoding detection (UTF-8/UTF-16 BOM, Windows-1251 fallback, decimal comma).
- Exports: `results.csv`, `calibration.csv`, `data_quality.csv`, `run_manifest.json` and figures.
- WinForms interface with guided and expert modes, light/dark/system themes, English and Russian localization, `Ctrl`+`1`…`Ctrl`+`0` navigation, and fully local storage under `%LocalAppData%\MVS_Analyzer\`.

[Unreleased]: https://github.com/d1d2dopamine/MVS-Analyzer/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.5.0
[1.4.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.4.0
[1.3.3]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.3.3
[1.3.2]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.3.2
[1.3.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.3.0
[1.2.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.2.0
[1.1.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.1.0
[1.0.0]: https://github.com/d1d2dopamine/MVS-Analyzer/releases/tag/v1.0.0

---

<h1 align="center" id="русский">История изменений</h1>

<p align="center"><sub>Оригинальные заметки автора</sub></p>

<p align="center"><a href="#changelog">English</a> · <strong>Русский</strong></p>

Это подробный журнал разработки: что именно было сломано, почему и как исправлено. Короткая версия по релизам — в [английской части выше](#changelog).

> [!NOTE]
> Текст сохранён как есть и только размечен в Markdown. Нумерация пунктов — авторская и сквозная, поэтому в разных разделах она продолжается, а не начинается заново.

---

## MVS Analyzer — исправления (engine 1.0.2)

Формула MVS Score и её хеш НЕ изменились (MVS-1.0.0).
Изменился порядок генерации случайных чисел и расчёт coverage, поэтому engineVersion = 1.0.2:
числа старых и новых запусков сравнивать напрямую нельзя.

### КРИТИЧНОЕ

- **1.** Калибровка больше не сканирует весь список наблюдений на каждый объект:
  измерения индексируются один раз в словарь. Часы → секунды/минуты.
- **2.** Ошибки в калибровке и анализе показываются сообщением, а не роняют программу
  (+ глобальный перехватчик в Program.cs).

### СТАТИСТИКА И ВОСПРОИЗВОДИМОСТЬ

- **3.** Отдельный генератор случайных чисел на каждую метрику: результат метрики
  больше не зависит от порядка и количества других метрик.
- **4.** Метрика, неприменимая к данным (например CV при среднем около нуля),
  помечается как «Неприменима / n/a» вместо тихого Score = 0.
  В results.csv и calibration.csv добавлен столбец applicable.
- **5.** Ручной и автоматический экспорт results.csv теперь один и тот же код (G17).
- **6.** Поля ResultRow переименованы честно: FirstGroupMedian, SecondGroupMedian,
  MedianRange (было GroupA/GroupB/Difference).

### ГРАФИКИ

- **7.** Единицы берутся из файла, а не зашиты как «ms».
- **8.** Палитра на 5 цветов: группы 3+ больше не сливаются со второй.
- **9.** Легенда перечисляет все группы, а не только первые две (раньше при одной
  группе был бы вылет по индексу).
- **10.** Неприменимые метрики не рисуются пустыми столбиками.

### ИМПОРТ И БЕЗОПАСНОСТЬ

- **11.** CSV читается один раз; поддержаны BOM UTF-8/UTF-16 LE/UTF-16 BE,
  а при битом UTF-8 — откат на Windows-1251 (без NuGet).
- **12.** Плагины: лимит 2000 файлов и 64 МБ распаковки (zip-бомба),
  проверка minAppVersion.

### ИНТЕРФЕЙС

- **13.** Тема «Системная» читает AppsUseLightTheme, а не режим высокой контрастности.
- **14.** Убраны искусственные задержки 1400–1600 мс.
- **15.** Тексты: было «семь метрик» — стало «десять» (их действительно 10).

### СOVERAGE (engine 1.0.2)

- **16.** coverage больше не константа 0.95. Теперь это измерение:
  для каждой метрики 200 раз моделируется исследование, внутри каждого строится
  95%-й percentile bootstrap-интервал для медианы метрики (200 перевыборок),
  и считается доля случаев, когда интервал накрывает истинное значение.
  Метрика со слишком узкими интервалами теперь теряет баллы, а не получает 0.95 даром.
  Строка формулы и её SHA-256 НЕ изменились — изменился способ получения одного входа.
  В run_manifest.json добавлено поле formula.coverageDefinition с описанием метода.
  Стоимость: ~40 000 перевыборок на метрику, один раз за калибровку (доли секунды).

### ЧТО ЭТО МЕНЯЕТ НА ПРАКТИКЕ

- Раньше множитель coverage^0.10 был одинаков у всех (0.9949) и не влиял
  на порядок метрик. Теперь он различает метрики, и из пяти компонентов
  формулы реально работают четыре вместо трёх.
- Абсолютные значения Score станут чуть ниже там, где интервалы недокрывают.
  Порог Score >= 60 не менялся, поэтому Candidate Set может стать строже.

### НЕ СДЕЛАНО (требует перевёрстки)

- MainForm.cs по-прежнему один файл с абсолютными координатами;
  на масштабе 125–150 % вёрстка может поехать. Нужен TableLayoutPanel.
- История запусков всё ещё только в памяти сессии.
- Код не был скомпилирован: в моём окружении нет .NET SDK.
  Перед использованием выполните: dotnet build и dotnet run --project MvsAnalyzer.Tests

## 1.0.3 — ПРОВЕРКА РАБОТЫ (АУДИТ)

- **17.** В манифест добавлен блок inputData: имя и SHA-256 ВХОДНОГО файла данных.
  Раньше хешировались только выходные файлы, поэтому привязать прогон
  к конкретному датасету было невозможно - вся проверка не имела смысла.
- **18.** Новый файл RunAuditor.cs:
- Журнал прогонов %LocalAppData%\MVS_Analyzer\run_journal.jsonl.
  Каждая строка хранит SHA-256 предыдущей строки (цепочка),
  поэтому удалить или подменить неудобный прогон незаметно нельзя.
- Audit(папка): рекурсивно ищет run_manifest.json, пересчитывает хеши
  всех записанных файлов и сверяет их с манифестом.
- **19.** Что находит проверка:
  FILE_MODIFIED / FILE_MISSING - результат правили или удалили после прогона;
  FORMULA_CHANGED - формула MVS отличается от замороженной;
  NO_INPUT_HASH - старый прогон без хеша входных данных;
  ENGINE_DIFFERS - другой номер версии движка;
  ORPHAN_RESULTS - results.csv без манифеста (проверить нечем);
  SETTINGS_VARIED - на одних и тех же данных меняли seed/эффект/сценарий;
  CANDIDATE_SET_UNSTABLE - одни данные дали разные наборы кандидатов;
  RUN_HIDDEN - журнал помнит прогон, которого нет в папке;
  JOURNAL_BROKEN - цепочка журнала разорвана.
- **20.** Новый раздел "Аудит" в боковом меню (виден во всех режимах):
  выбор папки, кнопка проверки, вердикт, таблица прогонов, таблица замечаний.
- **21.** EngineVersion 1.0.2 -> 1.0.3.

ВАЖНО И ЧЕСТНО: хеши доказывают ЦЕЛОСТНОСТЬ, а не честность. Они ловят правку
и удаление задним числом. Журнал дополнительно ловит спрятанные прогоны.
Но если человек с самого начала делает всё в чистой копии на другом компьютере,
никакая программа этого не увидит.

## 1.1.0 — РАЗМОРОЖЕНА ФОРМУЛА (MVS-1.1.0)

- **22.** ИСПРАВЛЕН КЛЮЧЕВОЙ БАГ: repeatability.
  Было: `repeatability = 1 - 3.92 * sqrt((power*(1-power)+0.0001)/N)`
  Это чистая функция мощности, то есть точность Монте-Карло, а не свойство метрики.
  Мощность учитывалась дважды (вес .30 плюс .15 через repeatability),
  а разные метрики получали одинаковое значение 0.999608 до 11-го знака.
  Стало: EstimateRepeatability - 50 случайных разбиений объектов каждой группы
  пополам; в обеих половинах считается групповая медиана метрики,
  расхождение нормируется на масштаб данных.
  Теперь это действительно ответ на вопрос: даст ли метрика ту же картину
  на другой половине выборки.
- **23.** Формула MVS-1.0.0 -> MVS-1.1.0, новый хеш спецификации:
  1aab2c38b5127fa911ffd38416b4ac499217cb5b7459800f28014c107f5ab909
  ВЕСА НЕ МЕНЯЛИСЬ, изменилось определение repeatability.
  Старые прогоны больше не сойдутся с новыми - аудит покажет FORMULA_CHANGED.
  Это ожидаемо: прогоны до 1.1.0 надо повторить.
- **24.** Если repeatability или coverage невозможно посчитать, метрика
  помечается Неприменимой, а не получает балл NaN.
- **25.** "Почти кандидат" (near_miss): метрика, которая прошла все правила,
  но отсечена лимитом в 4 кандидата, либо отстала от последнего
  кандидата меньше чем на 2 балла. Новая колонка near_miss в results.csv
  и статус "Почти кандидат" в таблице результатов.
- **26.** Формат чисел в CSV: G17 -> R. Было 0.047699999999999999, стало 0.0477.
- **27.** Поле group_summary больше не использует культуру системы.
  Было "Group 1=99,376" в CSV с запятой-разделителем (Excel читал 99376),
  стало "Group 1=99.376".
- **28.** В таблицу результатов добавлены колонки Repeatability и Coverage.
- **29.** В манифест добавлен repeatabilityDefinition. EngineVersion -> 1.1.0.
- **30.** Обновлён тест FormulaHash под новый хеш.

ОЖИДАЕМЫЙ ЭФФЕКТ НА ДЕМО-ДАННЫХ (проверено моделью формулы):
repeatability теперь разная у разных метрик: 0.949 ... 0.996 вместо одинаковых 0.9996.
Порядок метрик на чистых демо-данных не поменялся - это нормально:
на аккуратных данных все метрики повторяемы. Разница появится на шумных
данных, малых выборках и тяжёлых хвостах - там, где это и важно.

## 1.1.0 (b) — интерфейс

- **22.** Моргание при переходе между разделами.
  Причина: Navigate() пересоздаёт страницу целиком, и каждый контрол
  перерисовывался отдельно. Теперь перерисовка окна замораживается на время
  перестройки (Redraw.Suspend/Resume, WM_SETREDRAW) + SuspendLayout, а панели,
  страницы и таблицы наследуются от BufferedPanel / BufferedFlowPanel /
  BufferedGrid с двойной буферизацией.

- **23.** Фиксированная ширина 930 px заменена на ContentWidth = ширина окна − 78.
  Карточки, таблицы, вкладки и переносы текста растягиваются вместе с окном;
  host.Resize пересчитывает раскладку (FitContentWidth).

- **24.** Панель вердикта на странице «Результаты».
  Один крупный ответ до таблицы: лучшая метрика, различаются ли группы,
  MVS Score, p, мощность, FPR, отрыв от следующей метрики, число «почти
  кандидатов». Если правила кандидата не прошла ни одна метрика — явное
  предупреждение, что показана просто метрика с наибольшим баллом.

- **25.** MainForm.cs (719 строк) разделён на два partial-файла:
  MainForm.cs — оболочка (тема, навигация, Page/Card/Button/Grid, аудит окна),
  MainForm.Pages.cs — 13 методов Show* (страницы).

- **26.** Горячие клавиши Ctrl+1…Ctrl+0: Главная, Проект, Данные, Калибровка, Анализ,
  Результаты, Графики, Файлы, Аудит, Настройки (ProcessCmdKey, KeyPreview).

- **27.** Размер и состояние окна запоминаются между запусками
  (%LocalAppData%\MVS_Analyzer\window.txt), с проверкой границ экрана.

- **28.** Таблицы: сортировка и перестановка колонок, фиксированная высота заголовка.

- **29.** Версия в заголовке, статусной строке и манифесте: 1.1.0.

Не исправлено намеренно (нужен отдельный этап):

- внутри карточек координаты по-прежнему абсолютные (Location = new Point(...));
  полный переход на TableLayoutPanel — следующий шаг;
- нет мнемоник (&Анализ) и озвучивания для экранных читалок.

## 1.1.1 — косметика интерфейса

- **30.** Карточки: жёсткая рамка BorderStyle.FixedSingle заменена на CardPanel —
  скруглённый контур 8 px, отрисованный вручную, отступ снизу 16 px.
  Экран перестал быть сеткой коробок.

- **31.** Хром окна: вместо рамок — тонкие разделители (правый край боковой панели,
  низ верхней панели, верх строки состояния). Текст статуса и названия проекта
  приглушён до вторичного цвета.

- **32.** Таблицы: только горизонтальные линии, высота строки 28 px, отступы в ячейках,
  заголовок 34 px полужирным, внешняя рамка убрана.

- **33.** Числа в таблицах выровнены по правому краю, MVS Score выделен полужирным —
  колонки больше не «пляшут» при чтении сверху вниз.

- **34.** Наведение: подсветка пунктов бокового меню, hover и pressed для кнопок.

- **35.** Версия приложения 1.1.1. Версия движка осталась 1.1.0 — расчёты не менялись,
  хеш формулы MVS-1.1.0 прежний, старые прогоны 1.1.0 проходят аудит.

## 1.1.2 — графики больше не теряются

- **36.** ГЛАВНОЕ: если экспорт графиков включён, а список шаблонов пуст,
  программа раньше молча создавала ноль картинок. Теперь берутся четыре
  базовых шаблона.

- **37.** После анализа в сообщении видно число графиков и предлагается
  открыть папку запуска. Если графиков ноль - показывается предупреждение.

- **38.** run_manifest.json получил блок figures: enabled, mode, format, templates,
  generated. Прогон без картинок теперь отлаживается по файлу.

- **39.** На странице «Анализ» в сводке есть строка «Графики»: вкл/выкл,
  сколько шаблонов, формат, режим - до запуска, а не после.

- **40.** Раздел «Графики»: кнопка «Открыть папку», явная подсказка о месте
  сохранения и запрет сохранять пустой выбор шаблонов.

- **41.** Версия приложения 1.1.2. Движок и формула не менялись (1.1.0,
  MVS-1.1.0) - старые прогоны проходят аудит.

## 1.2.0 — графики и настоящие плагины

- **42.** FPR vs power: у оси X не было ни одной подписи — добавлены деления, числа и сетка.
- **43.** Подписи метрик на этом графике больше не налезают друг на друга (смещение + выносная линия).
- **44.** data_quality был сплошной стеной одинаковых столбиков. Теперь это распределение числа измерений с осью Y, порогом и числом объектов ниже порога; если у всех одинаково — пишется одной строкой.
- **45.** У сравнения групп появилась шкала значений (раньше столбики были без оси).
- **46.** Плагин-шаблон больше не подменяется встроенным графиком. Рисуется его собственная геометрия: chart = bar|scatter|histogram|line|box, source = results|calibration|participants|trials, плюс x, y и grouping.
- **47.** Шаблон ищется и по имени файла, и по полю id.
- **48.** Ненайденный или сломанный шаблон рисует карточку ошибки, а не чужой график.
- **49.** Новый модуль PluginAssets: плагин может добавлять профили импорта, профили настроек, шаблоны отчётов, правила проверки данных и словари терминов. Всё — только данные, код по-прежнему запрещён.
- **50.** Сломанный файл плагина больше не глотается молча: показывается в разделе «Плагины» и попадает в манифест.
- **51.** Раздел «Данные»: выбор профиля импорта и предупреждения по правилам плагинов.
- **52.** Раздел «Плагины»: карточка «что добавляют плагины» и кнопка применения профиля настроек.
- **53.** Отчёты плагинов (report_*.txt) пишутся в папку запуска до манифеста, поэтому они тоже хешируются.
- **54.** В манифест добавлен блок plugins: какие пакеты были включены, их хеши, какой профиль импорта применён, сколько шаблонов и правил действовало.
- **55.** Профили импорта умеют задавать разделитель, десятичную запятую (включая формат 1.234,56) и свои имена столбцов.
- **56.** В комплекте пример: plugin-lab-pack-source — профиль импорта, профиль настроек, отчёт, правила и термины.
- **57.** Аккаунтов и сети в программе нет и не планируется: обмен результатами — это папка запуска с хешами, которую проверяет раздел «Аудит» на любом другом компьютере.

## 1.2.1 — без кнопок «Применить»

- **58.** Убраны кнопки «Применить» / «Сохранить»: галочка, список или поле срабатывают сразу.
- **59.** Убраны все всплывающие окна «сохранено / применено». Остались только окна ошибок, подтверждение удаления плагина и итоговое окно анализа.
- **60.** Вместо окон — тихие подписи в карточках: «Изменения сохраняются сразу», «Выбрано: N» и т.п.
- **61.** Разделы без кнопок: Проект, Анализ (графики), Графики, Файлы, Настройки (режим, язык, тема, пределы, симуляция), Плагины.
- **62.** Профиль настроек плагина теперь применяется при выборе в списке; первый пункт — «Не применять профиль».
- **63.** Ошибка «минимум ≥ максимума» теперь показывается красной строкой в карточке, а не окном.
- **64.** Кнопка языкового экрана вместо окна просто меняет подпись на «Появится при следующем запуске».

## 1.3.0 — научная часть

- **65.** Раздел «Анализ» переименован в «Запуск»: там ничего не считается, там запускается расчёт.
- **66.** Появился размер эффекта — дельта Клиффа с 95% интервалом (бутстрэп, 400 повторов).
- **67.** Появился вердикт по каждой метрике: «Есть разница», «Разницы нет», «Данных не хватает», «Неприменима».
  «Разницы нет» — это результат теста эквивалентности (TOST), а не просто большой p-value.
- **68.** Появился MDE — минимальная разница, которую эти данные вообще способны заметить при мощности 0.80.
  Считается по сетке эффектов 1.00 / 1.02 / 1.05 / 1.10 / 1.20 с интерполяцией.
- **69.** Калибровка помечает завышенный FPR: если на нулевой точке сетки доля ложных срабатываний выше alpha,
  в таблице и в манифесте появляется флаг fpr_inflated.
- **70.** Новая опция «Раздельная калибровка» (Настройки → Научная строгость): объекты делятся пополам,
  метрика выбирается на одной половине, ответ считается на другой. Нужно минимум 8 объектов в группе.
- **71.** Настраиваемая граница эквивалентности (по умолчанию 0.147 — это «пренебрежимо малый» эффект).
- **72.** На странице «Результаты» появилась карточка «Вердикт»: одно предложение, счётчики по трём исходам,
  MDE и указание на источник калибровки (та же выборка или отдельная половина).
- **73.** В manifest добавлены блоки verdicts, powerCurves, calibrationSource, effectGrid, mdePowerTarget,
  equivalenceMargin; в results.csv и calibration.csv добавлены новые колонки.
- **74.** Формула обновлена до MVS-1.2.0, новый хеш формулы 70e1d577...e401e2f. Аудит старых запусков честно
  покажет FORMULA_CHANGED — это ожидаемо при смене версии.
- **75.** Добавлена иконка приложения app.ico (логотип: M V S в трёх кругах на белом фоне).
- **76.** Тесты: добавлены проверки дельты Клиффа, вердикта, MDE и раздельной калибровки (11 тестов).

## 1.3.1 — читаемый вердикт

- **77.** Две карточки («Вердикт» и «Лучшая метрика») говорили одно и то же. Объединены в одну.
- **78.** Первая строка теперь отвечает на вопрос целиком: какая метрика, какая группа выше и на сколько процентов.
- **79.** Новые поля ResultRow: EffectPair (кто выше кого) и EffectPercent (разница медиан в процентах).
- **80.** Строка уверенности: Уверенно / Слабо / Разницы нет / Данных не хватает, рядом дельта Клиффа, 95% ДИ и p.
- **81.** Строка согласия метрик. Если часть метрик видит рост, а часть снижение - красное предупреждение о расхождении.
- **82.** Кнопка «Как это посчитано» прячет всю статистику: score, power, FPR, устойчивость, повторяемость, покрытие, соседнюю метрику и источник калибровки.
- **83.** Баг: MDE показывал «от 0 %». Нулевая точка сетки (эффект 1.00) больше не участвует в расчёте: если мощность высока уже там, где разницы нет, это сломанная калибровка, а не сверхчувствительность.
- **84.** При завышенном FPR вместо числа MDE показывается предупреждение «вердикту доверять нельзя».
- **85.** Баг вёрстки: подпись «Граница эквивалентности» налезала на поле ввода. Позиция поля теперь считается от реальной ширины текста, а не жёстко по x=200.
- **86.** Иконка перерисована: 10 размеров, на 16-32 px три точки без букв, на 48+ кружки M V S.

## 1.3.2 — честный вердикт после стресс-теста

- **87.** Баг: флаг fpr_inflated стоял у всех метрик при здоровом FPR 0.05. Причина: он считался по нулевой точке кривой мощности, а эта точка не является нулём: в ней остаётся реальная разница между группами.
- **88.** Теперь флаг считается по измеренному FPR (объединённые группы, где разницы нет по построению). Порог тот же: выше max(alpha*1.5, alpha+0.02).
- **89.** Баг: строка «N из 10 метрик дали тот же ответ» считала слово «разница есть», а не пару групп. Метрики разброса указывали на самую грязную группу, метрики уровня - на сдвинутую, а карточка называла это согласием.
- **90.** Строка согласия переписана: «N метрик указывают на ту же пару X > Y, другую пару называют M, не смогли решить K».
- **91.** Если часть метрик указывает на другую пару - оранжевая подсказка, что они могут ловить разброс, а не сдвиг.
- **92.** Красное предупреждение о противоречии теперь только там, где оно есть: одна и та же пара групп с противоположными направлениями.
- **93.** Оба бага найдены стресс-тестом MVS_stress_test.csv (Control / Shift +6 % / Noise без сдвига).

## 1.3.3 - кодировки и белый список сценариев

- **94.** Главный баг. `ApplyScenario` сравнивал имя сценария с двумя строками, а всё остальное считал сценарием «поднять уровень последней группе». То есть опечатка в имени или написание `scale`, которое стоит в `docs/METHODS.md`, не давали ошибки: программа молча измеряла не то, что просили, и выдавала результат как ответ на заданный вопрос. Это ровно тот класс ошибок, против которого написана вся остальная программа, поэтому он исправлен первым.
- **95.** Имена сценариев вынесены в один файл `SimulationScenarios.cs`. Принимаются документированные синонимы (`scale`, `dispersion`, `spread`, `location_up`, `location_down`), неизвестное имя падает с ошибкой до начала симуляции, а не подменяется молча.
- **96.** Профиль плагина с неизвестным сценарием больше не применяется: настройка остаётся прежней, а причина отказа пишется в `PluginAssets.SettingsWarnings`.
- **97.** Импорт CSV больше не угадывает кодировку по одной ветке. Раньше всё, что не разобралось как UTF-8, объявлялось Windows-1251, и выгрузка в CP866 или KOI8-R приходила мусором, похожим на данные. Теперь варианты кодовых страниц оцениваются друг против друга, и берётся самое правдоподобное чтение. Плюс распознаётся UTF-16 без BOM.
- **98.** Выбранная кодировка перестала быть невидимой: она пишется в `CsvImporter.LastEncodingName`, так что неверную догадку видно, а не приходится подозревать.
- **99.** Таблицы кодовых страниц записаны escape-последовательностями, а не буквами. Иначе декодер, который лечит порчу кодировок, сам зависел бы от того, прочитан ли его собственный файл как UTF-8 - то есть ломался бы от той самой болезни, которую лечит.
- **100.** Числа с невидимыми разделителями разрядов (узкий и тонкий пробел, неразрывный пробел, мягкий перенос) и с настоящим минусом U+2212 вместо дефиса больше не выбрасываются как текст. Раньше такие измерения тихо терялись.
- **101.** В самих исходниках нашлось девять потерянных символов: `MainForm.Pages.cs`, `README.md` и `CHANGELOG.md` содержали символы замены, закоммиченные каким-то прошлым инструментом, который прочитал файлы не в той кодировке. Интерфейс из-за этого показывал слова с дырами. Буквы восстановлены, добавлен тест, который упадёт, если они вернутся.
- **102.** CSV бенчмарка пишутся с BOM, потому что Excel иначе угадывает системную кодовую страницу и портит кириллические заголовки. Markdown, txt и json остаются без BOM: там он был бы шумом в диффах и хешах.
- **103.** `--benchmark --lang ru` печатал вопросительные знаки: присоединённая консоль наследовала OEM-кодировку. Теперь выставляется UTF-8, и неудача этой попытки не считается фатальной.
- **104.** В манифесте объявлены `PerMonitorV2` и `activeCodePage=UTF-8`, в проекте `ApplicationHighDpiMode` приведён в соответствие с манифестом - иначе `ApplicationConfiguration.Initialize()` спорит с ним.
- **105.** Пять новых тестов: побайтовый импорт Windows-1251, определение кодировок, числа с локальным шумом, отказ на неизвестном сценарии, покрытие глифов в подписях сценариев.
- **106.** Статистика не менялась. `formulaHash` и `protocolHash` те же, выгрузки версии 1.3.2 остаются сравнимыми.

## 1.4.0 — два трека

До этой версии калибровка всегда искала сдвиг центра, а победителя применяли к любым данным. В условии, где менялся только разброс, это стоило 40 пунктов мощности.

- Калибровка идёт в два трека: `location` и `variability`. Мощность, кривая мощности, балл и MDE считаются в каждом треке отдельно.
- Нулевая выборка, устойчивость, повторяемость и покрытие считаются один раз и делятся между треками: они не зависят от внесённого эффекта, и вторая оценка добавила бы только шум.
- Порог кандидата проверяется внутри трека, со своим лимитом в четыре метрики.
- Сортировка результатов учитывает лучший балл в любом треке, иначе ответ про разброс оказывался внизу страницы.
- Формула перезаморожена: `MVS-1.3.0`. Правило отбора действительно изменилось, значит и версия с хешем должны были смениться.
- Протокол бенчмарка перезаморожен: `MVS-BENCH-1.1.0`.
- Новая процедура `mvs_two_track`: каждый трек выбирает свою метрику и проверяется на альфе, поделённой на число треков. Второй шанс отклонить гипотезу не бесплатен.
- Старые однотрековые процедуры остались в отчёте рядом с новой, чтобы улучшение можно было проверить, а не принимать на веру.

### Исправлено

- Оракул бенчмарка был смещён: он выбирал лучшую из десяти метрик и оценивал её на тех же репликациях. Теперь выбор идёт по нечётным репликациям, а оценка по чётным. Старое число печатается рядом.

### Не сделано

- `mad` по-прежнему без константы 1.4826. Умножение всех значений на одну константу — монотонное преобразование, а тесты ранговые, так что p-value не изменится ни на бит. На мощность и FPR это не влияет вообще — только на чтение абсолютного значения.
- Совместный тест Cucconi, перестановочные p-value и геометрическое среднее — 1.5.0.


## 1.5.0 — удалённые вычисления

Формула, движок и протокол бенчмарка не тронуты. Эта версия не меняет ни одного числа, которое
выдаёт программа, — она меняет только то, где программа может работать. Запуски 1.4.0 остаются
сравнимыми.

**Почему инфраструктура раньше статистики.** План был обратный, и я его поменял. Перестановочные
p-значения, критерий Куккони, closed testing и двухгейтный отбор невозможно *проверить* без
многократного прогона бенчмарка, а многократный прогон — это ровно то, что даёт эта версия.
Статистика без мощностей — это код, который нельзя проверить.

**Что появилось.**

- Движок без окна: `mvs calibrate`, `mvs analyze`, `mvs benchmark`, `mvs env`, `mvs version`.
  Отдельный проект с явным перечислением файлов, а не по маске, чтобы следующая добавленная
  форма не сломала тихо сборку под Linux. Коды выхода: `0` готово, `2` порог бенчмарка не взят,
  `1` ошибка. Средний — это результат, а не падение.
- Калибровка теперь файл (`calibration_state.json`). Анализ берёт настройки из калибровки, а не
  из своей командной строки, — две фазы больше не могут разойтись в зерне. В арендованной
  сессии, которую могут забрать в любой момент, это стоит одной ячейки вместо всего прогона.
- Анализ отказывается работать, если калибровка сделана на других данных (сверка хеша).
  Калибровка — это утверждение об одном наборе данных и бесполезна, приклеенная к другому.
  Флаг `--force` есть для случая, когда вы знаете, почему байты изменились; оба хеша всё равно
  попадают в манифест.
- Три ноутбука в `notebooks/`: Colab для калибровки и анализа, Colab для бенчмарка, Kaggle для
  длинных профилей. Ровно три ячейки: калибровка, анализ, скачивание zip с результатами.
- Карточка «Удалённый запуск» в настройках и сборка *задания*: данные вместе со всеми текущими
  настройками, чтобы удалённый прогон был тем же анализом, а не похожим. Предупреждение о
  приватности стоит рядом с кнопками, а не в документе, который никто не открывает.
- `--threads n` для бенчмарка. Бесплатная сессия даёт два ядра, и дефолтный `ProcessorCount - 1`
  там неверен. Количество потоков не влияет на результат: у каждой репликации свой поток
  случайных чисел.
- У детерминизма появилась область действия: `environment`, `environmentHash` и
  `determinismScope: withinEnvironment` в каждом манифесте. Побитовая воспроизводимость всегда
  была утверждением *внутри одного окружения*: `Math.Log`, `Math.Exp`, `Math.Pow` и `Math.Cos`
  не обязаны совпадать побитово на разных платформах (`Math.Sqrt` — исключение, он точен по
  стандарту). В хеш входят архитектура, версия рантайма и зонд из двенадцати значений этих
  функций. Строка сборки ОС в хеш сознательно **не** входит: патч Windows меняет её, не меняя ни
  одного арифметического результата, а хеш, который дёргается по косметическим причинам, учит
  своего читателя себя игнорировать.
- `docs/REMOTE.md` и job в CI, который собирает движок под Linux, прогоняет калибровку и анализ
  на встроенном примере, проверяет отказ от чужой калибровки и валидность всех трёх ноутбуков.

**Что исправлено.**

- Четыре теста, добавленные в 1.4.0, никогда не запускались. `TrackNormalisation`,
  `PerTrackGate`, `SpreadTrackCandidate` и `HeldOutOracle` были написаны и не зарегистрированы в
  списке тестов: харнесс докладывал 21 успех при 25 существующих методах. Теперь
  зарегистрированы, вместе с тремя новыми — 28 тестов. Тест, которого нет в списке, хуже
  отсутствующего теста: он даёт уверенность, ничего не проверяя.
- `AttachConsole` — это импорт из `kernel32`, и он вызывался безусловно; сборка без окна умерла
  бы под Linux на первом же `--benchmark`.
- Код графиков исключён из проекта без окна: `System.Drawing.Common` не рисует вне Windows.
  Таблицы, отчёты и манифест пишутся как обычно, картинки можно построить позже из той же папки
  на Windows.

**Что сознательно не сделано.**

- Статистика, запланированная на 1.6.0, там и осталась — по причине выше.
- Офлайн-режим не убран. Всё перечисленное — добавка. Убрать локальный путь означало бы забрать
  программу ровно у тех, кому нельзя никуда загружать свои измерения.
- Шардирование и возобновление. Один бенчмарк по-прежнему идёт внутри одной сессии. `--shard`,
  `merge` и `--resume` — работа для 1.6.0; профиль quick укладывается в сессию с запасом.
- Ссылка на ноутбук будет отдавать 404, пока `notebooks/` не выложены в публичный репозиторий.
  Кнопка не может создать заполненный ноутбук в аккаунте, к которому у неё нет токена. Работает
  только deep link, который Colab даёт для публичных репозиториев, а для этого файлы должны
  лежать в ветке по умолчанию.
