# Security policy

## Threat model in one paragraph

MVS Analyzer is an offline desktop application. It has no server, no accounts, no telemetry and no network code. The realistic attack surface is therefore local: **files you open** (CSV/TSV datasets) and **packages you install** (`.mvsplugin` archives), plus the integrity guarantees the app claims about its own run folders.

## Supported versions

| Version | Supported |
|---|---|
| 1.3.x | ✅ fixes are released here |
| 1.2.x and older | ❌ please upgrade; the formula and engine changed |

## Reporting a vulnerability

Please **do not open a public issue** for anything that could be exploited.

1. Use GitHub → **Security** → *Report a vulnerability* (private advisory) on this repository.
2. Include: the app version and `engineVersion` from `run_manifest.json`, a minimal reproducer (dataset or plugin package), what you expected, and what happened.
3. You will get a first response within **7 days**. Fixes for confirmed issues are released as a patch version with a changelog entry that credits you unless you prefer otherwise.

Please do not send datasets containing personal or confidential measurements. Reduce the reproducer to synthetic values first — the bug almost always survives that.

## What the app already defends against

**Plugin packages** (`PluginManager.Install`) are treated as hostile input:

- `plugin.json` must exist at the archive root and declare an id matching `^[a-z0-9][a-z0-9._-]{2,63}$`;
- only `visualization` and `import-export` types are accepted;
- executable payloads are rejected outright: `.dll .exe .bat .cmd .ps1 .vbs .js .hta .com .scr`;
- absolute paths and `../` traversal are rejected; every entry is resolved and verified to stay inside the plugin folder;
- zip-bomb limits: max 2000 entries and 64 MB unpacked;
- `minAppVersion` above the running engine is refused;
- the package SHA-256 is stored next to the installed files and recorded in every run manifest;
- installation is atomic (`*.installing` → rename), so a failed install cannot leave a half-written plugin behind.

**Datasets** are parsed with a hand-written reader: no formula evaluation, no macro execution, no external references. Values outside the configured min/max range are dropped rather than trusted.

**Run integrity** is provided by SHA-256 over the input file and every output file, plus a hash-chained journal (`run_journal.jsonl`).

## What it explicitly does *not* defend against

- **Hashes prove integrity, not honesty.** They detect edits, deletions and hidden runs on this machine. They cannot detect somebody who re-runs everything in a clean copy elsewhere and reports only the run they liked.
- **Plugins are data, but data can still mislead.** A malicious pack cannot execute code, yet it can ship a misleading report template or an import profile that silently maps the wrong column. Review packs you did not build.
- **Local file system trust.** Anyone with write access to `%LocalAppData%\MVS_Analyzer\` can delete the journal. The audit will report `JOURNAL_BROKEN` or `RUN_HIDDEN`, but it cannot restore it.
- **Not a medical or safety device.** No conclusion from this tool should be the sole basis of a clinical, industrial or safety-critical decision.

## Hardening tips for shared machines

- Keep run folders on a share that only the analyst can write to, and audit them from a second machine.
- Enable **Settings → Anonymous reports** (default) so exported identifiers are pseudonymized.
- Archive the input dataset next to the run folder — `inputData.sha256` is only useful if the file still exists.
