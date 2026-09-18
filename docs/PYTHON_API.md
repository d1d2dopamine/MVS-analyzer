# Python API

The Python package in `python/` is a thin client for the MVS CLI. Statistical algorithms remain in the .NET engine; Python does not contain an independent implementation.

## Install for development

```bash
python -m pip install -e ./python
export MVS_CLI=/absolute/path/to/mvs
```

You can also call `mvs.configure_engine("/absolute/path/to/mvs")`. If no explicit path is supplied, the package looks for `mvs` on `PATH`. Engine discovery never silently falls back to a different statistical implementation.

## Main workflow

```python
import mvs

calibration = mvs.calibrate(
    "examples/demo_three_groups.csv",
    scenario="variability",
    effect=1.15,
    repetitions=5000,
    seed=20260719,
)

result = mvs.analyze(
    "examples/demo_three_groups.csv",
    calibration=calibration,
)

print(result.output_directory)
print(result.manifest.data["engineVersion"])
rows = result.read_csv("results.csv")
```

Explicit `output=` paths are recommended for production pipelines. When omitted, the package creates a unique directory below `./mvs-output/`.

## Result objects

Public result types are `Calibration`, `AnalysisResult`, `VarianceResult`, `EstimationResult`, `MelsmResult` and `BenchmarkResult`. They expose the output directory, run ID, engine/application versions, manifest, diagnostics and artifact paths. `read_json()` and `read_csv()` read saved artifacts; `read_csv(..., dataframe=True)` uses pandas only when requested.

Exit code `2` is represented as a completed result by default for workflows where diagnostics are expected (`variance`, `estimation`, `melsm`, `benchmark`). Pass `allow_diagnostic=False` to raise `ScientificDiagnostic` instead. Exit code `1` maps invalid inputs to `InputError` when the CLI supplies a known input exception type, otherwise to `EngineError`.

## Supported input policy

The first API release is path-based. DataFrame input is intentionally not included yet because serialization, missing values, column names, numeric precision and hashing must be specified before a DataFrame can be treated as reproducible scientific input.
