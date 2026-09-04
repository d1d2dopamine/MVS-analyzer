# CLI and hosted notebooks

The Linux CLI is the same shared computational source without WinForms/drawing. See `mvs help` and README for summary, variance, estimation and MELSM commands. Model refits can require substantial CPU; no fixed runtime is promised.

CLI defaults do not silently load saved desktop settings. `--local-settings` is explicit. Use `--job path/to/job.json` (or its directory) for a schema-2 job; an omitted `--in` resolves relative to the job, not the working directory. Dataset hashes and import-profile compatibility are checked. Remote plugins are not installed automatically.

The three notebooks retain three executable cells. They download a **pinned release**, verify the asset checksum and engine version, then calculate/analyze/download. The default tag is `v1.4.0`; it must exist as a published release first. Before publication, supply `LOCAL_CLI` pointing to your own extracted Linux CI binary. There is no silent fallback to an older executable. Colab uploads and Kaggle input paths are explicit. Statistical parameters, including equivalence margin, belong in the calibration cell; the analysis cell restores the state.

Uploaded data leave your computer. Do not upload restricted or identifiable measurements without the required authorization. Downloading checksums from the same release helps detect accidental corruption, not a compromised publisher. The local program has no telemetry/account requirement, but browser links, binary downloads and notebook uploads use networks.

Exit codes: 0 completed; 1 invalid input/runtime error/cancellation; 2 numerical diagnostics or benchmark thresholds not satisfied. Code 2 can still leave useful diagnostic files; inspect them. `Ctrl+C` requests cooperative cancellation. Do not treat a partially written folder as a complete report.

Self-contained Linux ZIPs extracted on Unix may need `chmod +x mvs`. Windows release: `MVS_Analyzer_v1.4.0_win-x64.zip`; Linux: `MVS_Analyzer_v1.4.0_linux-x64-cli.zip`.
