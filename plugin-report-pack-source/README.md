# MVS Report Pack 1.0.0

Пакет шаблонов визуализации для MVS Analyzer 1.1.0 и выше · `mvs.report.pack` · тип `visualization`

> Visualization template pack for MVS Analyzer 1.1.0+. English documentation: [`../docs/PLUGINS.md`](../docs/PLUGINS.md).

## Установка

1. **Плагины** → «Установить пакет» → выбрать [`MVS_Report_Pack_v1.0.0.mvsplugin`](../MVS_Report_Pack_v1.0.0.mvsplugin)
2. **Графики** → в списке появятся четыре пункта «Плагин: …»
3. Отметить нужные, сохранить выбор, запустить анализ с включёнными графиками

## Состав

| Файл | Что рисует | Тип | Источник |
|---|---|---|---|
| `templates/mvs_ranking.json` | MVS Score по всем метрикам | `bar` | `results` |
| `templates/fpr_power_map.json` | диаграмма рассеяния FPR / мощность | `scatter` | `calibration` |
| `templates/value_spread.json` | гистограмма измерений | `histogram` | `trials` |
| `templates/group_medians.json` | сравнение групп | `bar` | `results` |

## Важно

- **Имя файла шаблона — это его идентификатор в программе.** Поле `"id"` внутри JSON для поиска не используется; здесь они совпадают.
- Пакет не содержит исполняемых файлов и не меняет формулу MVS.
- Хеш установленного пакета попадает в `run_manifest.json` — читатель видит, какие шаблоны были активны.

## Пересборка пакета

```powershell
# из этой папки: plugin.json должен оказаться В КОРНЕ архива
Compress-Archive -Path * -DestinationPath ..\MVS_Report_Pack_v1.0.0.zip -Force
Rename-Item ..\MVS_Report_Pack_v1.0.0.zip ..\MVS_Report_Pack_v1.0.0.mvsplugin
```

Формат `.mvsplugin`, ограничения безопасности и поля шаблонов описаны в [`../docs/PLUGINS.md`](../docs/PLUGINS.md).
