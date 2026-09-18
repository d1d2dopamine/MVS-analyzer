# CLI, Python and Jupyter roadmap

Status: implementation in progress. The first interface-layer milestone is implemented in this repository: compiled Core boundary, CLI machine schema `mvs-cli-result/v1`, path-based Python API, local Python notebook and CI parity smoke. Later roadmap items remain explicitly tracked below.

## 1. Goal

MVS should become a statistical engine that can be used from several environments without duplicating the statistical implementation.

The intended interface stack is:

```text
                         MVS statistical engine
                                  |
                 +----------------+----------------+
                 |                |                |
                CLI            Python API        Desktop
                                  |
                               Jupyter
                                  |
                                Colab
```

The current repository already contains most of the scientific engine, a headless .NET CLI, desktop UI, notebooks, manifests, saved calibration, validation utilities and checkpoints. The work below turns those pieces into explicit public boundaries.

## 2. Design rules

1. Keep one statistical implementation. Python, Jupyter and the desktop must not contain independent copies of the MVS calculations.
2. Treat reproducibility as part of the API. Seeds, method versions, settings, hashes, diagnostics and manifests remain first-class outputs.
3. Separate human output from machine output. CLI text can be readable, while automation receives a versioned JSON contract.
4. Keep the command line scriptable. Exit codes, stdout, stderr and file locations must be predictable.
5. Make Python feel like Python. A Python user should work with objects, paths and DataFrames instead of assembling command strings.
6. Preserve scientific warnings and unavailable states. Interfaces must not silently convert a diagnostic, failed fit or unavailable result into an ordinary numeric value.
7. Add interface features only after numerical parity can be tested against the engine.
8. Do not expand the list of statistical methods just to make the package look larger. Reliability of the existing workflows has priority.

## 3. Part A: freeze the current scientific contract

Before changing project boundaries, record what the current engine does.

### Work

- Define a small set of canonical datasets for each workflow.
- Save expected manifests and important numerical outputs for those datasets.
- Record current exit codes and failure classes.
- Record calibration compatibility behavior and state schema rules.
- Record which fields are public output contracts and which are internal implementation details.
- Add parity fixtures for Windows and headless runs where both interfaces support the same calculation.
- Decide the tolerance policy for floating-point comparisons.

### Done when

A refactor of project structure can be checked against a known numerical baseline. A change that alters a scientific result must be intentional and visible in tests, method hashes or versioning.

## 4. Part B: create a real Core library boundary

The CLI currently compiles an explicit shared list of engine source files through `SharedSources.props`. This prevents statistical duplication, but it is not yet a public library boundary.

### Target

Create a platform-neutral .NET class library such as `MvsAnalyzer.Core` and reference it from the CLI and desktop projects.

### Work

- Move platform-neutral calculation and scientific infrastructure behind the Core project boundary.
- Keep WinForms, browser bridge code and platform-specific rendering outside Core.
- Replace `internal` entry points that need to be consumed by front ends with a small intentional public API.
- Avoid exposing every internal record as public API. Add stable request/result types at the boundary.
- Keep serialization schemas explicit and versioned.
- Keep existing scientific hashes and compatibility checks meaningful after the project move.
- Retain explicit dependencies. Do not let the Core project accidentally acquire UI dependencies.

### Done when

Desktop and CLI reference the same compiled Core assembly and numerical parity tests remain unchanged.

## 5. Part C: make the CLI a stable public interface

The existing CLI already provides the main headless workflows. The next step is API discipline rather than a rewrite.

### Command model

Keep the existing scientific verbs unless a real usability problem requires a breaking change:

```text
calibrate
analyze
variance
estimation
melsm
benchmark
resume
state-check
version
env
```

### Human mode

Human mode should provide concise progress, useful errors and clear paths to generated artifacts. Help should use consistent option names, examples and terminology across commands.

### Machine mode

Add a versioned machine-readable mode for every command, for example `--json` or an equivalent global option.

A successful machine response should be able to identify at least:

```text
schema version
status
command
run id
output directory
application version
engine version
formula or method identity
manifest path
important artifact paths
warnings or diagnostics
```

Progress belongs on stderr or is disabled in machine mode. stdout should remain parseable.

### Exit codes

Keep the current distinction as a starting point:

```text
0  completed
1  input, runtime or cancellation failure
2  scientific or numerical diagnostic that requires inspection
```

If more codes are introduced, document them as a stable contract and map them to Python exceptions or result states.

### Additional CLI work

- Consistent `--help` for the root command and every subcommand.
- `--version` or equivalent behavior that works with common CLI conventions while preserving the existing `version` command if compatibility requires it.
- A quiet/non-interactive mode for pipelines.
- Stable overwrite behavior.
- Explicit output-directory rules.
- Shell completion only after the option surface is stable.
- No hidden dependency on desktop settings unless a user explicitly opts into them.

### Done when

The CLI can be used safely from shell scripts, CI, HPC schedulers and Python without parsing prose.

## 6. Part D: Python package

Python should expose a native-feeling API while delegating statistics to the MVS engine.

### First implementation strategy

Start with a Python package that controls the stable CLI or another narrow Core bridge. Do not port the statistical algorithms to NumPy/SciPy.

This gives two useful properties:

- one source of statistical truth;
- a Python API that can evolve without forcing the scientific implementation to be rewritten.

An in-process .NET bridge can be evaluated later if startup cost becomes a measured problem. It should not be chosen only because it appears more elegant.

### Proposed user-facing shape

The exact names should be finalized during API design, but the package should support workflows similar to:

```python
import mvs

calibration = mvs.calibrate(
    "data.csv",
    scenario="variability",
    effect=1.15,
    repetitions=5000,
    seed=20260719,
)

result = mvs.analyze(
    "data.csv",
    calibration=calibration,
)
```

Python should return structured result objects rather than raw stdout.

### Python objects

Candidate public objects include:

```text
Calibration
AnalysisResult
VarianceResult
EstimationResult
MelsmResult
RunManifest
Diagnostic
MvsError
InputError
EngineError
ScientificDiagnostic
```

Result objects should expose artifact paths and structured data. Where pandas is available, tabular outputs can have explicit DataFrame conversion methods rather than making pandas a mandatory dependency for every installation.

### Input policy

Support paths first. Add DataFrame input after defining how temporary serialization, missing values, column names, numeric precision and input hashing should behave. The conversion must be reproducible and visible to the user.

### Engine discovery

The package needs a predictable way to find a compatible MVS engine. Possible stages:

1. use an explicitly configured CLI path;
2. discover an installed `mvs` executable;
3. optionally distribute platform-specific engine binaries with Python wheels after packaging and release size are understood.

Do not silently use an arbitrary incompatible executable found on the system.

### Done when

A Python script can perform the main workflows, receive typed results, inspect diagnostics and save the same scientific artifacts as the CLI.

## 7. Part E: Jupyter API

Jupyter should become a normal consumer of the Python package rather than a separate statistical implementation.

### Work

- Add notebook-friendly representations for result objects.
- Display summary tables without hiding the saved raw artifacts.
- Make long calculations show progress without corrupting notebook output.
- Provide explicit save/export methods.
- Keep seed, calibration and engine identity visible.
- Build one small teaching notebook for each major workflow instead of one notebook that demonstrates every feature at once.

### Existing Colab bridge

The desktop-to-Colab controller has additional responsibilities such as connection ownership, job exchange and download handling. Keep that transport logic separate from the public Python statistics API.

The long-term direction is:

```text
Python package = scientific user API
Colab controller = optional transport/session layer
```

### Done when

The same Python code runs in a local notebook and in Colab, with environment-specific setup kept outside the analysis code.

## 8. Part F: packaging and installation

A research tool loses much of the benefit of a CLI/Python interface if installation is fragile.

### CLI releases

Plan release artifacts for the operating systems that pass the project test suite. A self-contained executable is useful for users who do not want to install the .NET runtime. A framework-dependent build can remain available for smaller downloads and development.

Potential distribution channels can be evaluated after release automation is stable:

- GitHub release archives;
- `dotnet tool` packaging if the command model fits it;
- package managers only when maintenance cost is justified.

### Python releases

Publish the Python package only after engine discovery and compatibility checks are deterministic.

A minimal first release can require a compatible `mvs` CLI. Later, platform-specific wheels may bundle the engine if that produces a better installation experience without making updates or security fixes harder.

### Version compatibility

Do not require Python package version, application version and engine version to be identical. Instead, define a compatibility matrix and let the package query the engine manifest before running a job.

### Done when

A new user can install the supported CLI/Python combination from documented steps and verify it with one version command and one small example dataset.

## 9. Part G: documentation and examples

Documentation should be organized around user tasks rather than front-end implementation details.

### Documentation set

- Installation.
- Data model and assumptions.
- CLI reference.
- Python API reference.
- Jupyter quick start.
- Reproducibility and manifests.
- Statistical methods and limitations.
- Migration and compatibility.
- Troubleshooting.

### Examples

Keep examples small enough to run quickly. Each example should state whether the data are synthetic, what question is being asked and which result should be inspected.

Avoid examples that imply scientific validation from successful software execution.

## 10. Part H: parity and release gates

Every public interface should be tested against the same canonical cases.

### Required parity checks

For the same input, settings, seed and engine version:

- CLI and Python produce the same manifest-level scientific identity;
- numerical tables agree within declared tolerance;
- unavailable values and diagnostic statuses agree exactly;
- failed runs map to the intended error class;
- calibration compatibility behavior is identical;
- output artifact hashes agree when byte-for-byte identity is expected;
- any expected platform-specific difference is documented.

### Release gate

Do not publish a Python release if it passes its own wrapper tests but fails cross-interface parity against the engine.

## 11. Suggested implementation sequence

This order keeps each change reviewable and avoids mixing packaging, statistical refactors and user-facing API changes in one step. Completed items are marked here so the roadmap remains an implementation tracker rather than a historical wish list.

1. [~] Add golden datasets and parity baselines for the current CLI. Canonical calibrate/analyze cases are gated; broader numerical baselines remain.
2. [x] Define the machine-readable command result schema.
3. [x] Add complete machine mode to the current CLI.
4. [x] Extract `MvsAnalyzer.Core` without changing scientific behavior.
5. [x] Switch desktop and CLI to the Core project reference.
6. [~] Stabilize CLI help, errors, stdout/stderr and exit-code documentation. Machine streams/errors are stable; per-subcommand help can still be refined.
7. [x] Create a small Python package that discovers and verifies the CLI.
8. [x] Add Python result objects and artifact readers.
9. [x] Add path-based `calibrate` and `analyze` APIs.
10. [x] Add `variance`, `estimation`, `melsm` and benchmark APIs.
11. Add DataFrame input with a documented serialization policy.
12. [~] Add Jupyter representations and concise notebooks. A local quick-start exists; richer representations and per-workflow notebooks remain.
13. [x] Automate cross-platform CLI and Python packaging. Release automation builds the existing Windows/Linux CLI artifacts and a pure-Python wheel after parity gates.
14. [x] Publish an interface compatibility matrix and migration policy.

## 12. What is deliberately out of scope for this roadmap

- Rewriting the MVS statistical algorithms in Python.
- Replacing the desktop application only because CLI/Python exist.
- Adding many new statistical tests before the current interfaces are stable.
- Making GPU support a priority without a workload that benefits from it.
- Treating a notebook as the only reproducible record of a run. Saved manifests and artifacts remain authoritative.
- Hiding failed fits, unavailable metrics or simulation uncertainty to make the API look simpler.

## 13. First release target for the new interface layer

The first useful milestone is smaller than a complete Python ecosystem. It should provide:

- a real Core project boundary;
- a stable CLI with machine-readable responses;
- documented stdout, stderr and exit-code behavior;
- a Python package that can run `calibrate` and `analyze` through a verified engine;
- typed access to results and diagnostics;
- one local Jupyter example;
- parity tests proving that CLI and Python are using the same scientific engine.

Once that milestone is reliable, additional workflows and distribution conveniences can be added without changing the statistical core.
