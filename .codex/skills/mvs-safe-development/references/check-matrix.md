# MVS verification matrix

Read live CI and scripts first; use this matrix to select evidence. Commands
below reflect the known source layout and must be verified in the current tree.
Do not install a compiler or dependencies merely for a read-only plan request.

## All edits

Run the change guard against the pre-edit snapshot. Review the full diff,
unexpected new/deleted files and applicable repository instructions. In Git,
run git diff --check and include both staged and unstaged work in review.
Do not claim source ZIP validation establishes runtime correctness.

## Documentation only

Check changed links, consistency with live definitions and exact diff scope.
Run source/documentation checks when their owning surface is affected.
Do not require a full scientific benchmark for an ordinary wording edit.

## Python validation tools

```bash
python -m pip install -r validation/requirements.txt
python -m unittest discover -s validation -p 'test_*.py' -v
python tools/check_source.py
```

Use independent numerical examples with stated expected values, boundary and
unavailable cases. Smoke-run the affected CLI script into a separate temporary
output folder. For simulation changes, record protocol/seed/denominator rules
and preserve historical reports. Match scientific settings when using SciPy or
another reference; numerical agreement does not prove population calibration.

## Python wrapper / CLI / export / persistence

```bash
PYTHONPATH=python/src python -m unittest discover -s python/tests -v
python tools/check_cli_contract.py
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release
```

Run the live CI publish/smoke/parity flow for actual CLI changes. Check with
tools/check_outputs.py, tools/check_cli_contract.py --artifacts and
tools/test_python_cli.py against the built CLI as appropriate. Test old-state
compatibility or explicit rejection of incompatible states. A fake-process
wrapper test cannot replace a real Core/CLI check.

## Statistical Core, metrics and benchmark

Run the native Core.Tests project, compile affected Core/CLI projects and run
small deterministic cases through the real interface. Add independent expected
values for ties, constants, near-zero scales, minima and failure paths.

Use archived benchmarks only as development evidence. For a method change,
include declared error-control tests under the relevant nulls and alternatives;
a global-null simulation alone cannot establish strong FWER for every procedure.
Full benchmarks require the live protocol and an appropriate simulation budget.
Do not use a tiny smoke run to make comparative power claims.

Static checks remain useful but limited:

```bash
python tools/check_csharp_structure.py
python validation/reference_numerics.py
```

If .NET is unavailable, state which native checks did not run. Do not translate
the algorithm to Python and call that a native test.

## Build, Colab payload and workflows

```bash
python tools/check_source.py
python tools/build_notebooks.py --check
python tools/test_backups.py
python tools/test_source.py
```

Run the owning builder for an authorized payload change, then its consistency
checks. Parse changed workflow YAML and embedded scripts; exercise failure paths.
Never let a shell wrapper swallow a failing child process.

## Source packaging

Check ZIP CRC/integrity, original-source completeness, expected changes and
protection of raw archives/assets. Preserve original source-controlled binaries
and schemas even if ordinary build outputs are excluded. Inspect new files for
caches, generated reports, credentials and task-baseline leakage.

## Skill maintenance

Run the skill-creator frontmatter validator and scripts/test_change_guard.py.
Check referenced resources and agent metadata. A skill-only change does not
require rebuilding the MVS application, which must remain untouched.
