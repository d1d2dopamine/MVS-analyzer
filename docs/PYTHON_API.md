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

## Engine launch failures

`EngineNotFoundError`, `EngineError`, `InputError`, `EngineCompatibilityError` and
`ScientificDiagnostic` derive from `MvsError`. Missing engine targets, including a
file disappearing after discovery, raise `EngineNotFoundError`. Permission,
invalid-executable and other OS launch failures raise `EngineError`; malformed
UTF-8 child output also raises `EngineError`. The original exception is retained
as `__cause__`, and the message identifies the executable and requested command.
The wrapper does not silently switch engines or claim a scientific result after
a launch failure. This boundary does not convert every filesystem error from
independent result/artifact convenience methods into an engine error.

## Provenance warnings on completed results

A completed analysis can contain `result.diagnostics` with code
`journal_write_failed`: result artifacts were saved, but the local journal was not
updated. `allow_diagnostic=False` does not raise for this exit-0 warning; that option
controls exit-2 scientific diagnostics. Inspect warning codes even when the call
succeeds. The added message does not disclose the journal path. See
[round 20](ROUND20_JOURNAL_WARNING.md) for actual CLI/Python checks and limits.

### Inspecting a failed export

A validated native error response is available as `exc.result` on `InputError`
or `EngineError`; transport/handshake errors without such a response leave it
`None`. Exception classes and messages retain their existing meaning. Inspect
`exc.result.artifacts` and `exc.result.raw.get("partialOutput")` for incomplete
export evidence. This is a failed result, never a completed scientific analysis.
For failed results, `artifact(name)` only accepts explicitly listed artifacts;
`copy_to` refuses copying the directory, and `analyze` refuses a failed
`Calibration` object. These rules prevent accidental reuse of untouched stale
files from an overwrite directory. See
[Round33](ROUND33_PARTIAL_OUTPUT_REPORTING.md) for the exact scope and limits.
