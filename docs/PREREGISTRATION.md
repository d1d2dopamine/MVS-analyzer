# Declared protocol versus external preregistration

`Benchmark/BenchmarkProtocol.cs` records methods, comparisons, seeds and thresholds; a checksum pins that declaration. Changing it intentionally requires a new protocol version/hash. The current protocol is `MVS-BENCH-1.2.0` and is not comparable to old benchmark runs without re-running them.

A local file or checksum is **not external preregistration**. This package does not assert that a timestamped protocol was deposited before any outcome was observed. If that protection is needed, deposit the code revision, protocol, estimands, design matrix, failure rules and acceptance criteria in a trusted timestamped registry before running the confirmatory experiment. Keep raw failures and all planned conditions.

GUI project-mode labels are metadata, not a mechanism that makes an analysis confirmatory. Full-registry correction does not resolve unrecorded model selection, repeated inspection, changed outcomes or selective reporting.
