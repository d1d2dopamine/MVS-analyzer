# Run via Colab

**Run via Colab / Запустить через Colab** is beside Calibration, Run, variance components, estimation studies, MELSM and the synthetic benchmark, not in Settings. Kaggle is not an active workflow.

## Use

1. Load measurements and select the operation/settings in MVS. Click the Colab button and approve transfer of that selected job.
2. A confirmed live, paired MVS notebook is reopened. Otherwise Colab opens a repository notebook with a fresh-copy request; Google may require sign-in and saving the copy.
3. Run cell 1. On the first connection, paste the code copied by MVS into the hidden input prompt. Keep MVS open and allow browser local-network permission when requested. MVS never asks for a Google password or API secret.
4. Cell 1 prepares/calibrates, cell 2 analyzes, cell 3 downloads a ZIP. Additional methods are prepared in cell 1 and executed in cell 2.
5. A validated completed calibration is cached and reused, not rerun. Its button is disabled for the same input/settings/repetition count. Analysis remains available. For another assigned job in the same notebook, rerun its first cell.

Job identity includes input bytes, statistical/preprocessing settings, repetition count, method/options and this repair revision. An incompatible calibration is not silently reused. Existing completed output is not overwritten.

## What active means

The kernel must answer a recent heartbeat. A button click, an open browser tab or a remembered URL is not proof of a live runtime or completion. MVS tracks paired MVS jobs; it cannot enumerate all notebooks in a Google account. Restarting the desktop requires a new local pairing; validated saved calibration is retained.

Notebook-address detection is best-effort. If it fails, the notebook shows a **Notebook URL** input: paste its saved `https://colab.research.google.com/drive/...` address. The notebook does not need to be public.

## Manual fallback

Browser policy may block Colab-to-localhost access. The desktop's connection dialog shows the generated job ZIP path. Leave the notebook connection prompt empty and upload this ZIP manually. Download the finished results ZIP and choose **Import Colab result** in MVS, with matching data/settings loaded. Manual exchange cannot promise automatic live-state detection.

For standalone work, an empty connection prompt accepts CSV/TSV or the selected synthetic benchmark/estimation defaults. Independent-group IDs need the appropriate acknowledgment; repeated subjects across conditions belong in MELSM.

## Runtime-discovery correction

The supplied log's exit **131 / libhostfxr.so not found** followed a successful build. Its apphost did not discover the SDK/runtime installed privately under `/content/dotnet` with `--no-path`.

The notebook sets `DOTNET_ROOT`, `DOTNET_ROOT_X64`, and `PATH`, publishes with `UseAppHost=false`, and invokes the explicit **`/content/dotnet/dotnet <absolute-mvs.dll-path> ...`** host. It checks application/engine/repair revision. Desktop jobs contain their exact CLI source and import profile; standalone jobs print the selected repository commit. Only use source/job archives you trust.

## Integrity and privacy

- Calibration completion requires the native checksum/method/input validator, not just a status flag. Result import checks dataset/settings/repetition identity, output checksum and the complete metric registry.
- Nested analysis output is normalized to `analysis/` in downloads. Benchmarks use their own manifest and SHA256SUMS, including nested figure paths.
- Diagnostic exit 2 remains a diagnostic/failure status on replay. Partial output is not a completed run.
- The local bridge is loopback-only, origin-checked, token-scoped and size-limited; it exposes no shell, general file browser or public relay.
- Job ZIPs contain original measurements. Results ZIPs exclude input/source/connection tokens, but reports may still be sensitive. Pseudonyms do not guarantee anonymity.
- Notebook output saving is disabled in the shipped metadata. Clear outputs and inspect notebooks before sharing. Never share a connection code while the app is running.
- Google controls runtime availability, CPU quota and session duration; none are guaranteed by MVS.

Offline orchestration tests were run. Live Windows/Colab pairing was not executed during source preparation; see the target-environment checklist.
