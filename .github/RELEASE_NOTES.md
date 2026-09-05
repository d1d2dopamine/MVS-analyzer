# MVS Analyzer v1.4.0

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-x64-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/MVS_Analyzer_v1.4.0_win-x64.zip)

![Version](https://img.shields.io/badge/version-1.4.0-1f6feb?style=flat-square)
![Engine](https://img.shields.io/badge/engine-1.6.0-6f42c1?style=flat-square)
![.NET](https://img.shields.io/badge/.NET-8-512BD4?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

**Compare measurement metrics, preserve reproducible results, and choose where to run your calculations — on your Windows PC or in Google Colab.**

## Highlights

- Compare twelve summary metrics with calibration, uncertainty estimates and multiplicity-adjusted results.
- Explore within-entity variability and between-entity differences with separate simulation scenarios.
- Use optional variance-component analysis, known-truth estimation studies and experimental MELSM for repeated conditions.
- Save calibration profiles, CSV/JSON outputs, reports and integrity metadata.
- Control Colab jobs from a dedicated panel in the desktop application.

## A smoother Google Colab workflow

### One control panel

The **Google Colab** section brings the main actions together:

- **Calibrate** — prepare a calibration for the selected data and settings.
- **Analyze** — run the analysis using a matching calibration.
- **Download results** — request the complete results ZIP in the Colab browser.
- **Stop** — request cancellation and wait for the runtime to confirm it.
- **Connection code**, **Reconnect**, and **Open notebook** — recover the connection without hunting through old cells or creating another notebook.

The panel shows the current job state, runtime information and progress reported by the CLI. Preparation steps without numerical progress use an indeterminate indicator rather than an invented percentage.

### More reliable connections

- Stale connection states no longer leave the workflow permanently blocked after a notebook tab is closed. An unconfirmed connection expires after approximately 45 seconds without a valid status update.
- Forced notebook copying has been removed. The saved notebook address is retained independently of runtime availability, so the application can reopen the same notebook.
- The connection code can be reopened and copied again if its window was closed or the clipboard contents changed.
- Reconnecting revokes the old connection code while retaining verified calibration and received results.
- Repeated delivery of an already accepted command does not start a second calculation. Stale status messages and messages from another runtime are rejected.
- Result delivery is retried after temporary connection failures. Partial output is not treated as a completed result.

### Manual fallback remains available

If browser access to the local connection is blocked, save the job ZIP, upload it manually in Colab, and import the results ZIP back into MVS. Do not disable browser security to establish a connection.

When offline, MVS can also save the verified files it has already received. That archive is explicitly marked as a subset; additional tables and reports may still need to be downloaded from Colab.

## Getting started on Windows

1. Download **MVS_Analyzer_v1.4.0_win-x64.zip** using the button above.
2. Extract the archive and open **MVS_Analyzer.exe**.
3. Load your CSV/TSV file or try one of the included examples.
4. Calibrate, analyze and inspect the results locally, or choose **Run via Colab**.

**Requirements:** Windows 10/11, x64. The self-contained Windows release does not require a separate .NET installation. If Windows displays a warning for the unsigned application, verify the release checksum before running it.

## Connecting to Colab

1. Prepare a job in MVS and approve the transfer of its data and settings.
2. Open the matching notebook and select **Python 3 / CPU** in Colab's runtime settings.
3. Run the first cell, paste the connection code from MVS, and leave the cell running as the controller.
4. Use the desktop panel to calibrate, analyze and download results.

A running controller cell is not itself a running calculation. The other notebook cells remain available for manual operation after stopping the controller.

**Update the application and notebook together.** Existing Google Drive copies do not update automatically. Replace their cells with the current notebook or open the notebook included with this release. If reconnecting with a new code, enable `RESET_CONNECTION` before running the first cell again.

## Compatibility and important notes

- The application version remains **1.4.0**. The numerical engine is **1.6.0**, and the frozen formula identifier remains **MVS-1.4.0**.
- Compatible saved calibrations are reused only after checking the input data, settings, repetition count and integrity metadata.
- CPU/GPU selection, resource availability and quotas remain under Google's control. The application opens the notebook and explains the settings; it does not bypass Colab limits. This .NET engine does not use GPU/TPU acceleration.
- Removing forced copying cannot prevent Google from showing its own save/copy dialog when permissions or service requirements demand it.
- Losing the connection or choosing **Disconnect** does not prove that the cloud process has stopped. Use Colab directly when necessary, and download important results before resetting its runtime.
- Calibration and synthetic diagnostics are not independent scientific validation. MELSM remains experimental.

## Downloads and documentation

- [Windows x64 application](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/MVS_Analyzer_v1.4.0_win-x64.zip)
- [Linux x64 CLI](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/MVS_Analyzer_v1.4.0_linux-x64-cli.zip)
- [Source code](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/MVS_Analyzer_v1.4.0_source.zip)
- [SHA-256 checksums](https://github.com/d1d2dopamine/MVS-Analyzer/releases/download/v1.4.0/SHA256SUMS.txt)
- [Colab guide](https://github.com/d1d2dopamine/MVS-Analyzer/blob/main/docs/REMOTE.md)
- [Data format](https://github.com/d1d2dopamine/MVS-Analyzer/blob/main/docs/DATA_FORMAT.md)
- [Methods and interpretation](https://github.com/d1d2dopamine/MVS-Analyzer/blob/main/docs/METHODS.md)
