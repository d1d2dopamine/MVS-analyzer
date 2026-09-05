<p align="center"><img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo"></p>
<h1 align="center" id="mvs-analyzer">MVS Analyzer</h1>
<p align="center"><strong>English</strong> · <a href="#русский">Русский</a></p>
<p align="center">Which metric best reflects the changes in your measurements?</p>
<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/app-1.4.0-1f6feb?style=flat-square" alt="app 1.4.0">
  <img src="https://img.shields.io/badge/engine-1.6.0-6f42c1?style=flat-square" alt="engine 1.6.0">
  <img src="https://img.shields.io/badge/formula-MVS--1.4.0%20frozen-brightgreen?style=flat-square" alt="formula MVS-1.4.0 frozen">
  <img src="https://img.shields.io/badge/made%20with-.NET%208-512BD4?style=flat-square" alt="made with .NET 8">
  <img src="https://img.shields.io/badge/Windows-10%2B%20x64-0078D6?style=flat-square" alt="Windows 10+ x64">
  <img src="https://img.shields.io/badge/NuGet%20dependencies-0-4b4b4b?style=flat-square" alt="zero NuGet dependencies">
  <img src="https://img.shields.io/badge/network-optional-4b4b4b?style=flat-square" alt="optional networking">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
</p>
<p align="center"><a href="https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest"><img src="https://img.shields.io/github/v/release/d1d2dopamine/MVS-Analyzer?style=for-the-badge&label=download%20for%20Windows&color=0078D6&logo=windows&logoColor=white" alt="download for Windows"></a></p>
<p align="center"><a href="docs/DATA_FORMAT.md">Data format</a> · <a href="docs/METHODS.md">Methods</a> · <a href="examples/">Examples</a> · <a href="CHANGELOG.md">Changelog</a></p>

---

## 🧩 What is MVS Analyzer?

When each person, sample or device produces many measurements, choosing a summary metric matters. The mean, median and measures of spread can respond very differently to the same change.

**MVS Analyzer helps you compare those choices on your own data.** It simulates specified changes, estimates how often each metric detects them and how often it signals a difference under the simulated null. You get a comparison of metrics, uncertainty estimates and readable results — not a recommendation hidden behind a single p-value.

It is designed for researchers and analysts working with repeated measurements within independent entities: reaction times, laboratory readings, production cycles and similar data.

## ✨ What you can do

| Feature | What it gives you |
|---|---|
| Compare 12 metrics | Mean, median, SD, CV, MAD, IQR, normalized MAD/IQR, RMS, range, geometric mean and 20% trimmed mean |
| Separate two kinds of spread | Within-entity variability and between-entity differences, with separate power estimates |
| Compare independent groups | Analysis of 2–10 groups with effect sizes and multiplicity-adjusted p-values |
| Explore sensitivity | Power curves and a minimum detectable effect when the simulated range supports it |
| Use additional models | Gaussian variance components, known-truth estimation studies and experimental MELSM for repeated conditions |
| Keep your results | CSV/JSON reports, figures, saved calibration and integrity checks |
| Work locally or in Colab | Windows desktop analysis, plus optional cloud computation |

Calibration is conditional on the observed data and the scenarios you choose. It does not establish ground truth or guarantee that a selected metric will work equally well on new data. MELSM is experimental; bias/MSE estimates belong to known-truth simulation studies, not unknown real-world truth.

## ⚡ Get started

1. Download the **Windows x64** archive from [Releases](https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest), extract it and open `MVS_Analyzer.exe`.
2. Load your CSV/TSV, or try the [three-group example](examples/demo_three_groups.csv).
3. Choose the effect scenario and run calibration.
4. Run the analysis, inspect the results and save the report.

**Requirements:** Windows 10/11, x64. The self-contained Windows release does not require a separate .NET installation. If Windows warns about the unsigned application, verify the release checksum before running it.

<p><a href="https://colab.research.google.com/github/d1d2dopamine/MVS-Analyzer/blob/main/notebooks/MVS_Colab.ipynb"><img src="docs/assets/colab.png" width="28" alt="Colab"> <strong>Run via Colab</strong></a></p>

Colab is an alternative when you want to run calculations in the cloud. A matching saved calibration can be reused. Google account access and an internet connection are required; see the [Colab guide](docs/REMOTE.md) for setup and file exchange.

## 📄 Your data

Use **one row per measurement**, with these columns:

| Column | Meaning |
|---|---|
| `entity` | Person, sample, device or other measured object |
| `group` | Group membership |
| `value` | Numeric measurement |
| `sequence` | Optional measurement order |

The standard workflow assumes independent entities across groups. Repeated conditions for the same subject need an appropriate repeated-measures model, not independent-group analysis. See [data format and examples](docs/DATA_FORMAT.md).

## 📊 Understanding the output

Results combine the metric comparison, estimated power and false-alarm rate, group comparisons and uncertainty. A result may indicate a difference, approximate equivalence, insufficient evidence or an inapplicable metric. An empty candidate set and an unavailable minimum detectable effect are valid outcomes.

Exported files let you examine results outside the application and retain the settings used. [Report reference](docs/OUTPUTS.md) · [Statistical methods and limits](docs/METHODS.md).

## 🔒 Privacy

Local analysis needs no MVS account and sends no telemetry. If you choose Colab, the selected job and its measurements are processed by Google's service. Review sensitive data before uploading or sharing a notebook.

## ❓ FAQ

<details>
<summary>Do I need to program?</summary>

No. The Windows application provides the standard import, calibration, analysis and export workflow.
</details>

<details>
<summary>Can it tell me which metric is always best?</summary>

No. Performance depends on the data, effect and assumptions. MVS helps make that dependence visible instead of choosing by convention alone.
</details>

<details>
<summary>Can I use it without the cloud?</summary>

Yes. Local analysis works without Colab. Cloud execution is optional.
</details>

## 📚 Documentation

[Data](docs/DATA_FORMAT.md) · [Methods](docs/METHODS.md) · [Reports](docs/OUTPUTS.md) · [Colab](docs/REMOTE.md) · [Plugins](docs/PLUGINS.md) · [Validation and limitations](docs/VALIDATION.md)

## License

[MIT](LICENSE). Citation metadata is available in [CITATION.cff](CITATION.cff).

---

<p align="center"><img src="docs/assets/logo.png" width="176" alt="MVS Analyzer logo"></p>
<h1 align="center" id="русский">MVS Analyzer</h1>
<p align="center"><a href="#mvs-analyzer">English</a> · <strong>Русский</strong></p>
<p align="center">Какой показатель лучше отражает изменения в ваших измерениях?</p>
<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/d1d2dopamine/MVS-Analyzer/ci.yml?branch=main&label=build&style=flat-square" alt="build">
  <img src="https://img.shields.io/badge/app-1.4.0-1f6feb?style=flat-square" alt="app 1.4.0">
  <img src="https://img.shields.io/badge/engine-1.6.0-6f42c1?style=flat-square" alt="engine 1.6.0">
  <img src="https://img.shields.io/badge/formula-MVS--1.4.0%20frozen-brightgreen?style=flat-square" alt="formula MVS-1.4.0 frozen">
  <img src="https://img.shields.io/badge/made%20with-.NET%208-512BD4?style=flat-square" alt="made with .NET 8">
  <img src="https://img.shields.io/badge/Windows-10%2B%20x64-0078D6?style=flat-square" alt="Windows 10+ x64">
  <img src="https://img.shields.io/badge/NuGet%20dependencies-0-4b4b4b?style=flat-square" alt="zero NuGet dependencies">
  <img src="https://img.shields.io/badge/network-optional-4b4b4b?style=flat-square" alt="optional networking">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT license">
</p>
<p align="center"><a href="https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest"><img src="https://img.shields.io/github/v/release/d1d2dopamine/MVS-Analyzer?style=for-the-badge&label=%D1%81%D0%BA%D0%B0%D1%87%D0%B0%D1%82%D1%8C%20%D0%B4%D0%BB%D1%8F%20Windows&color=0078D6&logo=windows&logoColor=white" alt="скачать для Windows"></a></p>
<p align="center"><a href="docs/DATA_FORMAT.md">Формат данных</a> · <a href="docs/METHODS.md">Методы</a> · <a href="examples/">Примеры</a> · <a href="CHANGELOG.md">Что нового</a></p>

---

## 🧩 Что такое MVS Analyzer?

Когда каждый участник, образец или прибор даёт много измерений, выбор итогового показателя важен. Среднее, медиана и показатели разброса могут по-разному реагировать на одно и то же изменение.

**MVS Analyzer помогает сравнить эти варианты на ваших данных.** Программа моделирует заданные изменения и оценивает, как часто каждый показатель их обнаруживает и как часто даёт ложный сигнал при моделируемом отсутствии различий. На выходе — сравнение метрик, оценки неопределённости и понятные результаты, а не рекомендация на основании одного p-value.

Программа предназначена для исследователей и аналитиков, работающих с повторными измерениями внутри независимых объектов: временем реакции, лабораторными показаниями, производственными циклами и похожими данными.

## ✨ Возможности

| Возможность | Что она даёт |
|---|---|
| Сравнение 12 метрик | Среднее, медиана, SD, CV, MAD, IQR, нормированные MAD/IQR, RMS, размах, геометрическое и 20%-усечённое среднее |
| Два уровня разброса | Вариативность внутри объекта и различия между объектами с отдельными оценками мощности |
| Сравнение независимых групп | Анализ 2–10 групп, размеры эффектов и поправка на множественные проверки |
| Анализ чувствительности | Кривые мощности и минимально обнаруживаемый эффект, когда его позволяет оценить диапазон симуляции |
| Дополнительные модели | Гауссовские компоненты дисперсии, симуляционные исследования оценивания и экспериментальная MELSM для повторных условий |
| Сохранение результатов | Отчёты CSV/JSON, графики, сохранённая калибровка и проверка целостности |
| Локально или в Colab | Настольное приложение Windows и необязательные облачные вычисления |

Калибровка зависит от наблюдаемых данных и выбранных сценариев. Она не устанавливает истинные параметры и не гарантирует такой же результат на новых данных. MELSM — экспериментальная модель; bias/MSE оцениваются в симуляциях с известной истиной, а не для неизвестных истинных параметров реальных данных.

## ⚡ Начало работы

1. Скачайте архив **Windows x64** со страницы [релизов](https://github.com/d1d2dopamine/MVS-Analyzer/releases/latest), распакуйте его и откройте `MVS_Analyzer.exe`.
2. Загрузите CSV/TSV или попробуйте [пример с тремя группами](examples/demo_three_groups.csv).
3. Выберите сценарий эффекта и запустите калибровку.
4. Выполните анализ, изучите результаты и сохраните отчёт.

**Требования:** Windows 10/11, x64. Для автономной Windows-сборки не нужна отдельная установка .NET. Если Windows предупреждает о неподписанном приложении, перед запуском проверьте контрольную сумму релиза.

<p><a href="https://colab.research.google.com/github/d1d2dopamine/MVS-Analyzer/blob/main/notebooks/MVS_Colab.ipynb"><img src="docs/assets/colab.png" width="28" alt="Colab"> <strong>Запустить через Colab</strong></a></p>

Colab позволяет перенести вычисления в облако и использовать подходящую сохранённую калибровку. Потребуются доступ к аккаунту Google и интернет. Настройка и обмен файлами описаны в [руководстве Colab](docs/REMOTE.md).

## 📄 Ваши данные

В таблице должна быть **одна строка на измерение**:

| Столбец | Содержимое |
|---|---|
| `entity` | Участник, образец, прибор или другой измеряемый объект |
| `group` | Принадлежность к группе |
| `value` | Числовое значение измерения |
| `sequence` | Необязательный порядок измерений |

Основной режим предполагает независимость объектов между группами. Для повторных условий у одного участника нужна соответствующая модель повторных измерений, а не анализ независимых групп. Подробнее: [формат данных и примеры](docs/DATA_FORMAT.md).

## 📊 Как читать результат

Результаты объединяют сравнение метрик, оценки мощности и частоты ложных срабатываний, групповые сравнения и неопределённость. Итог может указывать на различие, приблизительную эквивалентность, недостаток данных или неприменимость метрики. Пустой список кандидатов и отсутствие оценки минимально обнаруживаемого эффекта — допустимые результаты.

Экспорт позволяет изучать данные вне приложения и сохранять использованные настройки. [Справочник отчётов](docs/OUTPUTS.md) · [Методы и ограничения](docs/METHODS.md).

## 🔒 Конфиденциальность

Для локального анализа не нужен аккаунт MVS; программа не отправляет телеметрию. При выборе Colab задание и его измерения обрабатываются сервисом Google. Перед загрузкой или публикацией ноутбука проверьте, не содержат ли данные чувствительную информацию.

## ❓ Частые вопросы

<details>
<summary>Нужно уметь программировать?</summary>

Нет. Основные действия — импорт, калибровка, анализ и экспорт — доступны в приложении Windows.
</details>

<details>
<summary>Программа найдёт метрику, которая всегда лучше остальных?</summary>

Нет. Результат зависит от данных, эффекта и предположений. MVS помогает увидеть эту зависимость, а не выбирать показатель только по привычке.
</details>

<details>
<summary>Можно обойтись без облака?</summary>

Да. Локальный анализ не требует Colab. Облачный запуск необязателен.
</details>

## 📚 Документация

[Данные](docs/DATA_FORMAT.md) · [Методы](docs/METHODS.md) · [Отчёты](docs/OUTPUTS.md) · [Colab](docs/REMOTE.md) · [Плагины](docs/PLUGINS.md) · [Проверки и ограничения](docs/VALIDATION.md)

## Лицензия

[MIT](LICENSE). Данные для цитирования: [CITATION.cff](CITATION.cff).

## Colab 1.4.0 — обновление подключения

Вместо вкладки используется **отдельное окно Google Colab**: калибровка, анализ, остановка, скачивание и прогресс. Оно открывается кнопкой «Запустить через Colab» на странице калибровки или анализа; повторное нажатие поднимает то же окно. Код можно открыть и скопировать повторно. Связь с закрытым блокнотом не считается постоянной; можно переподключить тот же блокнот, сохранив проверенную калибровку.

Обновите приложение **и блокнот** вместе. Инструкции: [Colab](docs/REMOTE.md), [текст релиза](.github/RELEASE_NOTES.md), [проверки и ограничения](docs/VALIDATION.md). Выбор среды и лимиты Google остаются в интерфейсе Colab.


### Исправления интерфейса без изменения версии

Подробности, ограничения проверки и сборка: [PATCH_NOTES_RU.md](PATCH_NOTES_RU.md).

Версия остаётся **1.4.0**, движок — **1.6.0**. Окно Colab независимо от страниц приложения. Выбор аппаратного ускорителя подтверждается в самом Colab; MVS показывает фактически обнаруженное оборудование, а не выдуманный список доступных ресурсов.
