# Round 1 validation tools checkpoint

Date: 2026-10-10. Source snapshot: b2037d4cf07ef22172e5aff7603a499ab046f85e
(the user-provided ZIP). This delivery is a source archive ready for review and
commit; it is not a compiled application release.

## Delivered scope

- R1-02: manifest-aware score reproduction, explicit historical formula mode,
  average-rank Spearman and Kendall tau-b, undefined constant-rank diagnostics.
- R1-03: independent twelve-metric definitions, floor trimming, per-entity
  geometric availability, guarded absolute relative denominators.
- Additional reference-tool fixes: tied Mann-Whitney ranks/variance; separate
  entity exclusions per replication; unconditional rejection and availability
  rates; fixed twelve-test Bonferroni diagnostics.
- 25 regression tests, usage documentation and CI integration. CI also runs the
  score checker against real CLI exports and fails if no exports are present.

Application 1.4.0, engine 1.6.0 and formula MVS-1.4.0 are unchanged. The reference
simulation protocol advances to MVS-REFERENCE-2 because its definitions and
reporting have changed. It must not be treated as interchangeable with historical
ten-metric reference reports.

## Verification

The following local checks passed with Python 3.12.14 and NumPy 2.3.5:

```bash
python -m unittest discover -s validation -p 'test_*.py' -v
PYTHONPATH=python/src python -m unittest discover -s python/tests -v
python tools/test_backups.py
python tools/test_source.py
python tools/check_source.py
python tools/check_cli_contract.py
python tools/check_csharp_structure.py
python tools/build_notebooks.py --check
python validation/reference_numerics.py
```

The unit suites contain 25 new diagnostic tests, 4 existing Python-wrapper tests,
17 backup tests and 6 source/documentation tests. New fixtures include formula
reproduction, invalid/unknown metadata, CSV identity, tied/constant ranks,
trim-floor boundaries, near-zero denominators, individual geometric availability,
known asymptotic Mann-Whitney values and insufficient usable entities.

Both reference grids were smoke-run separately, and random tied/continuous
Mann-Whitney cases were compared against SciPy's declared asymptotic settings.
These are implementation checks, not new scientific performance claims.

Workflow YAML and its embedded Python score-check step were parsed locally.
The full GitHub Actions jobs were not run here.

## Unexecuted native checks

.NET is unavailable in the preparation environment. C# compilation, native
Core.Tests, real CLI parity and real exported-score reproduction are therefore
not claimed. Existing CI retains native build/tests and adds exported-score
checks so this limitation is visible and testable after pushing.

Static structural and contract checks do not establish compilation or
statistical validity. The Python wrapper tests use a fake CLI process.

## Next tasks

1. R1-01: build Core/CLI with .NET 8, run native tests and real CLI parity.
2. R1-04: separate observed-test applicability from calibration availability,
   preserving the fixed twelve-test family and reviewing schema compatibility.
3. R1-05: independently validate native Mann-Whitney/Kruskal-Wallis numerical
   results and small-sample limitations; this delivery fixes only the Python
   reference implementation.
4. R1-06: export metric-specific sample sizes and unavailability reasons; clarify
   diagnostic null tolerances, recommendation heuristics and equivalence scope.
5. R1-07: add per-replication selection/failure diagnostics to the benchmark.
6. R1-08: reproduce Huber scale-dependent convergence in C# before activating it.

Holm, maxT, activation of the four staged metrics and interval-coverage studies
remain separate tasks. Power improvements or a significant p-value are not
completion criteria for this checkpoint.

## Archive and commit

The original C# sources, embedded Colab payload, method hashes and benchmark
history are retained byte-for-byte. Generated reports, bytecode caches, build
outputs and local analysis helpers are excluded from the source ZIP.

Copy the contents of the archive's MVS-analyzer-main directory into the existing
checkout, inspect the diff and commit the nine changed/added files. The archive
does not contain Git history.

Suggested commit message: `fix: align independent MVS validation tools with current formula and registry`.

See [Validation tools](../validation/README.md) for commands and changed behaviour.
