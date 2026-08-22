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

### Planned

- Paired and repeated-measures designs.
- Post-hoc pairwise comparisons after a significant Kruskal–Wallis test.
- `TableLayoutPanel` relayout inside cards and DPI hardening for 125–150 % scaling.
- Persistent run history across sessions.
- Headless CLI over the existing engine.

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

[Unreleased]: https://github.com/d1d2dopamine/MVS-Analyzer/compare/v1.3.2...HEAD
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
