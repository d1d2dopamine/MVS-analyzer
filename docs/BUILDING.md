# Building and CI

Public application **1.4.0**, numerical engine **1.6.0**. This package is source, not a locally compiled binary. Desktop development requires Windows and the .NET 8 SDK; the portable CLI uses plain .NET 8. There are no third-party NuGet dependencies.

## Windows

```powershell
dotnet build MvsAnalyzer.csproj -c Release
dotnet run --project MvsAnalyzer.Tests/MvsAnalyzer.Tests.csproj -c Release
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
dotnet run --project MvsAnalyzer.Ui.Tests/MvsAnalyzer.Ui.Tests.csproj -c Release -- artifacts/ui-layout
.\build_release.bat
```

Review actual layout PNGs and the Windows checklist before releasing. Geometry assertions alone do not certify visual quality or real-monitor DPI transitions.

## CLI

```bash
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -o publish/cli -p:UseAppHost=false
dotnet publish/cli/mvs.dll calibrate --in examples/demo_three_groups.csv --out artifacts/calibration --repetitions 150 --seed 20260719
dotnet publish/cli/mvs.dll analyze --in examples/demo_three_groups.csv --calibration artifacts/calibration --out artifacts/analysis
python tools/check_outputs.py artifacts
```

For a private SDK installation, set `DOTNET_ROOT` / `DOTNET_ROOT_X64` and invoke the SDK's absolute `dotnet` path followed by the absolute `mvs.dll` path. The notebook does this instead of relying on an apphost to find a runtime.

## Derived assets

After editing shared/CLI source or the helper, regenerate and commit:

```bash
python tools/build_colab_payload.py
python tools/build_notebooks.py
python tools/check_source.py
python tools/check_csharp_structure.py
python tools/test_colab.py
```

The embedded payload contains exact portable source, not a silently substituted old release binary. `SharedSources.props` remains explicit. CI rejects stale payloads/notebooks; text line endings are pinned for identical source bytes on Windows and Linux. Commit the complete package to update the notebook opened from `main`.

CI includes portable/desktop regressions, Linux save/replay, and Windows layout screenshots. Release builds remain drafts until reviewed. No .NET compilation or execution was performed locally by the source-package author; actual versus pending checks are recorded in `validation/PACKAGE_QA.md`.
