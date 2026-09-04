# Audit and provenance

Input and artifact SHA-256 values identify bytes. Calibration additionally freezes scientific configuration and validates a semantic payload checksum before replay. Manifest path traversal is rejected; calibration state is listed before the manifest is finalized. Forced cross-dataset reuse records both hashes.

The local append journal uses a cross-process lock and chains entries. Write failures are surfaced instead of silently suppressed. The journal is a useful local consistency check, but a person controlling the directory can rewrite the chain, omit runs, delete records or replace the program. It does **not** prove absence of selective reporting, authenticity, scientific correctness or preregistration. Keep a trusted external copy/commit if stronger provenance is needed.

A historical formula mismatch is a compatibility warning, not automatically evidence of tampering. Compare a historical run against the source/method version that produced it. Model reports have model-specific configurations, not the summary score formula. Older audit views may describe a model-only report as lacking summary-calibration metadata; inspect its model report and checksum list directly.

Pseudonymization does not guarantee anonymization. Before sharing, inspect calibration-state dataset names, group names, free text and model random-effect exports. Hosted notebook uploads leave the local machine.
