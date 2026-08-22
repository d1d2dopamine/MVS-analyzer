# Plugins

Plugins extend MVS Analyzer with **data, never code**. Implementation: `PluginManager.cs` (install, verify, enable) and `PluginAssets.cs` (profiles, templates, rules, terms).

- [Package format](#package-format)
- [plugin.json](#pluginjson)
- [What a plugin can add](#what-a-plugin-can-add)
- [Security limits](#security-limits)
- [Installing and managing](#installing-and-managing)
- [Building a plugin](#building-a-plugin)
- [Bundled packs](#bundled-packs)

---

## Package format

A `.mvsplugin` file is a **ZIP archive with `plugin.json` at its root**. That is the entire format.

```text
MVS_Report_Pack_v1.0.0.mvsplugin
├─ plugin.json
├─ templates/
│  ├─ mvs_ranking.json
│  ├─ fpr_power_map.json
│  ├─ value_spread.json
│  └─ group_medians.json
└─ README.md
```

Installed into `%LocalAppData%\MVS_Analyzer\plugins\<plugin-id>\`, alongside:

| File | Purpose |
|---|---|
| `package.sha256` | hash of the installed package, recorded in every run manifest |
| `disabled.flag` | present when the plugin is switched off; the files stay on disk |

Installation is atomic: the package is unpacked to `<id>.installing` and renamed only after every check passes, so a rejected package cannot leave a half-installed plugin behind.

---

## plugin.json

```json
{
  "id": "mvs.lab.pack",
  "name": "MVS Lab Pack",
  "version": "1.0.0",
  "author": "d1d2dopamine",
  "type": "import-export",
  "minAppVersion": "1.2.0",
  "description": "Import profile for lab device exports, strict QC profile, RU summary report."
}
```

| Field | Required | Rules |
|---|---|---|
| `id` | ✅ | must match `^[a-z0-9][a-z0-9._-]{2,63}$`; also the folder name |
| `name` | ✅ | shown in the Plugins list |
| `version` | ✅ | semantic version of the pack |
| `type` | ✅ | `visualization` or `import-export` — anything else is rejected |
| `author` | — | free text |
| `minAppVersion` | — | refused if higher than the running engine |
| `description` | — | one line, shown under the name |

---

## What a plugin can add

### Figure templates — `templates/*.json`

```json
{
  "id": "mvs_ranking",
  "name": "MVS ranking",
  "chart": "bar",
  "source": "results",
  "x": "metric",
  "y": "mvs_score",
  "grouping": "candidate",
  "version": "1.0.0"
}
```

| Field | Allowed values |
|---|---|
| `chart` | `bar` · `scatter` · `histogram` · `line` · `box` |
| `source` | `results` · `calibration` · `participants` · `trials` |
| `x`, `y` | column names from that source |
| `grouping` | optional column used for colour/series |

Templates are declarative: the app renders them, the plugin never draws anything itself.

### Import profiles — `import-profiles/*.json`

Delimiter, decimal convention and column mapping for instruments that will not be renamed. See [DATA_FORMAT.md](DATA_FORMAT.md#import-profiles).

### Settings profiles — `settings-profiles/*.json`

Named presets (for example `strict-qc`: higher `minMeasurements`, tighter α, more repetitions) applied with one click and recorded in the manifest.

### Report templates — `report-templates/*.txt`

Plain-text templates with placeholders, rendered into `report_*.txt` inside the run folder. Since 1.3.2 they are written before the manifest, so they are hashed with everything else.

### Validation rules — `validation-rules/*.json`

Pre-run checks on the dataset, for example:

```json
{
  "rules": [
    { "id": "min-measurements-20", "type": "minMeasurements", "value": 20, "severity": "warning" },
    { "id": "group-size-15",       "type": "minEntitiesPerGroup", "value": 15, "severity": "warning" }
  ]
}
```

Rules warn; they never silently change the analysis.

### Terminology — `terms/*.json`

Domain wording for labels and reports (for example laboratory Russian instead of generic Russian).

---

## Security limits

Every package is treated as hostile input. Rejected at install time:

| Check | Limit |
|---|---|
| Executable extensions | `.dll .exe .bat .cmd .ps1 .vbs .js .hta .com .scr` |
| Path traversal | absolute paths and `..` segments; every entry must resolve inside the plugin folder |
| Entry count | max 2 000 |
| Unpacked size | max 64 MB |
| Manifest | `plugin.json` must exist at the root and parse |
| Id | must match the id pattern |
| Type | must be `visualization` or `import-export` |
| Version gate | `minAppVersion` above the running engine |

Rejections are reported with the offending entry name, and the run manifest records both the enabled plugin set and anything that was refused.

> [!WARNING]
> A plugin cannot execute code, but it can still mislead: a report template that omits `fpr_inflated`, or an import profile that maps the wrong column, produces a perfectly verifiable answer to the wrong question. Review packs you did not write.

---

## Installing and managing

**Plugins** in the sidebar → *Install* → pick a `.mvsplugin` file. From the same page you can enable, disable (`disabled.flag`, files kept) or remove a pack, and see its id, version, type and package hash.

Every run records the active plugin set, so a reader can tell which templates and profiles were in play.

---

## Building a plugin

1. Create a folder with `plugin.json` at its root.
2. Add `templates/`, `import-profiles/`, `settings-profiles/`, `report-templates/`, `validation-rules/`, `terms/` as needed.
3. Zip the **contents** of the folder — `plugin.json` must be at the archive root, not inside a subfolder.
4. Rename the archive to `<name>.mvsplugin`.
5. Install it and check the Plugins page reports the version and hash you expect.

```powershell
# from inside the plugin source folder
Compress-Archive -Path * -DestinationPath ..\My_Pack_v1.0.0.zip
Rename-Item ..\My_Pack_v1.0.0.zip ..\My_Pack_v1.0.0.mvsplugin
```

---

## Bundled packs

| Source | Id | Type | Contents |
|---|---|---|---|
| [`plugin-example-source`](../plugin-example-source) | `example.mvs.visualization` | visualization | one template (`publication_score`) — the minimal working example |
| [`plugin-report-pack-source`](../plugin-report-pack-source) | `mvs.report.pack` | visualization | four templates: MVS ranking, FPR × power map, value spread, group medians |
| [`plugin-lab-pack-source`](../plugin-lab-pack-source) | `mvs.lab.pack` | import-export | `lab-device` import profile, `strict-qc` settings, RU summary report, validation rules, lab terminology |
| [`plugin-stress-pack-source`](../plugin-stress-pack-source) | `mvs.stress.pack` | visualization | adversarial profiles and rules for hostile datasets (requires app ≥ 1.3.0) |

Two prebuilt packages are committed for convenience: `example-visualization.mvsplugin` and `MVS_Report_Pack_v1.0.0.mvsplugin`.
