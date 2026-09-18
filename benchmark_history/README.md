# Benchmark archive

This directory stores immutable benchmark outputs used in MVS development and validation.

Each run lives in a versioned folder. The folder name should identify the software version, scientific engine, and benchmark protocol. Raw benchmark files are copied here without editing. Human-readable comparisons belong in `docs/BENCHMARK_HISTORY.md`.

The archive exists so that later releases can be compared with the actual earlier results rather than with remembered headline numbers. Direct numerical comparisons require compatible protocol definitions and settings; `docs/BENCHMARK_HISTORY.md` records when that condition is and is not satisfied.
