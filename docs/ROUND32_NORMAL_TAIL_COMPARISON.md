# Round32 isolated normal-tail experiment

Candidate outcome: **NO-GO**.
Scientific status: **NO-GO unchanged**. Production remains unchanged; this experiment cannot activate B.

## Fixed evidence

- Scalar inputs: 3173; domain specials: 8; actual native rank cases: 165.
- Candidate scalar failures: 170; rank failures: 0.
- Threshold B/reference-policy mismatches: 5 of 365.
- A/B changed decisions: 174; every change is retained in changed-decisions.json.
- Policy/mathematical rounding discrepancies: 1.
- Premature zeros: A=2108, B=0.
- Candidate monotonicity violations: 0.

## Candidate criteria

- FAIL: all_candidate_numeric_gates
- PASS: candidate_monotone_nonincreasing
- PASS: special_domain_and_underflow
- PASS: max_absolute_error_improved_at_least_10x
- PASS: all_A_premature_zeros_eliminated
- FAIL: all_threshold_B_decisions_match_policy
- PASS: native rank regression, strict end-to-end accuracy, declared policies, KW bitwise control and deterministic transformations.

## Central absolute error

- Maximum A error: 0.000000146296271663472992284573108908129162791222879855072589315781087201352448299060563484957652
- Maximum B error: 0.000000000000000102340420418716282624936025314113401127264455197646722542847103020336974966574240154900035
- Improvement factor: 1429506260.23339991188788833533613963752453285947726604205232079267142433179055111321000682

## Cost

Status: FAIL.
- PASS: publish_increment_lte_10MiB
- PASS: startup_median_budget
- PASS: startup_p95_budget
- FAIL: throughput_median_ratio_lte_1_25
- Publish increment: 1601241 bytes.
- Startup median A/B: 94.010421/98.078239 ms.
- Startup nearest-rank p95 A/B: 109.925479/108.619653 ms.
- Throughput median B / median A: 4.454184951.

Startup uses 30 fresh paired launches in alternating AB/BA order; first pair retained and excluded from n=29 summaries. Each of the separate 30 throughput pairs uses fresh processes, 100,000 warmup and 100,000 measured total calls. p95 uses nearest rank. These are warm-file-cache repeated launches, not a cold-start claim.

## Interpretation and retained failures

A invokes the actual private NormalCdf; native MW is called in both variants. B changes one final return expression in an external source copy. Native internal z is not observed. Exact-rank mathematical z and rounded independent z are distinct reference diagnostics; discrepancies never justify wider tolerances.

SciPy ordinary p and separate logsf diagnostics are retained independently. Direct logsf is not substituted for the strict log of returned p gate. High precision is independently saved at 100 and 200 decimal digits, with explicit nearest-even binary64 conversion. Maximum finite and +infinity are separate domain/underflow checks.

Signed zeros remain separate. Actual A zero values are preserved; exact-at-zero is a B acceptance criterion. Every threshold-neighborhood candidate decision is checked against the actual unchanged DecisionPolicy fed rounded H, including unchanged but incorrect A/B decisions.

Windows compatibility is UNVERIFIED. Publication measurements are for the isolated framework-dependent Release linux-x64 harness, not the Windows application. Numerical failure is an informative terminal outcome; no tuning, threshold changes or selective retries are authorized.

## Artifacts

- scalar-results.json and scalar-results.csv: every point, bits, H/S/native errors and failures.
- rank-results.json: every native MW/KW case, frozen regression and transformations.
- decisions.json and changed-decisions.json: raw/adjusted values, actual policies, mathematical decisions and classifications.
- cost-processes.json, cost-results.json and raw/: retained stdout/stderr, exits, timeouts, wall time and batch checksums.
- frozen-config.json: exact bindings, algorithms, versions and workload settings.

## Boundary interpretation

All five B/reference-policy discrepancies also occur in A; none is newly introduced relative to A. Four disagree with both the policy and mathematical reference. At alpha0.2, B agrees with the exact-real comparison, while correctly rounded H passed through the unchanged policy rounds the adjusted value to exactly0.2 and does not reject. The frozen target remains that policy, so the criterion still fails. All174 changed decisions improve agreement with the frozen reference.

The118 subnormal failures have high-precision probabilities approximately2.49e-310 to2.23e-308. Their largest absolute error is about5.02e-321 and largest relative error2.36e-13; they fail the deliberately strict8-minimum-subnormal-quanta criterion. Another52 points return the minimum positive binary64 when H rounds to zero. These counts are numerical edge-case tests, not counts of practical research mistakes. The mature library substantially outperforms the existing approximation on this fixed grid despite failing this exact replacement contract.

Production and scientific acceptance remain unchanged. The primitive throughput ratio is not an end-to-end MVS slowdown. Existing production tolerance2e-7 for MW fixtures was not overwritten or reinterpreted as the new experiment's much tighter criterion.

## Reproduction entrypoints

This is an optional isolated experiment, not a normal application startup step. Use Python3.12 and .NET8 as recorded. Install `validation/requirements-normal-tail-reference.txt` in a separate environment; production package requirements are unchanged. Existing validation CI additionally installs mpmath1.3.0 to execute the new helper tests.

Acquire official `MathNet.Numerics`5.0.0 from NuGet. Expected nupkg SHA256: `44724254ce8ec6ab8917b9f931b7bfa0d6ee7016e481ee942dc6c07333a0995a`. Its declared license is MIT; the versioned license is retained in the evidence archive. The dependency installer/binaries are not bundled.

From the source root, use the scripts' `--help` for complete required arguments:

1. `python validation/normal_tail_reference.py --help`: generates a new fixed-grid/reference directory; both original protocol and amendment SHA arguments are required. Protocol files are `docs/ROUND32_NORMAL_TAIL_PROTOCOL_ORIGINAL_RU.md` and `docs/ROUND32_NORMAL_TAIL_PROTOCOL_AMENDMENT.md`.
2. `python validation/prepare_normal_tail_native.py --source . --out ../normal-tail-native --package PATH_TO_VERIFIED_NUPKG --build --dotnet PATH_TO_DOTNET`: creates separate A/B copies and publishes the isolated harnesses. Never choose an existing output directory or replace installed CLI files.
3. `python validation/run_normal_tail_comparison.py prepare --help`: freezes a new config binding the actual new source/build/reference paths and runtime. Then `verify` checks its SHA without executing candidates.
4. `correctness --execute` runs the fixed comparisons; `cost --execute --exclusive-cpu-slot` runs the separately prespecified timing experiment. Read all retained outputs; a numerical failure is not an execution retry request. `analyze` rechecks saved evidence without launching native processes.

The delivered original frozen config contains the original machine paths and is provenance, not a portable execution config. Prepare a new config for a new machine; do not edit the original manifest to pretend the new execution is the historical one. The source32 production code equals the source31 experimental baseline; newly added diagnostic scripts/docs change the full-tree hash. Timing results naturally need not reproduce bitwise.

The ordinary regression suite does not download Math.NET or invoke experimental candidates. It runs synthetic helper/guard/aggregation tests. Actual Windows native runtime acceptance remains pending separately.

## Companion evidence

`MVS-analyzer-round32-normal-tail-evidence.zip`:8,948,441 bytes, SHA256`c2122916d2fef05d9904ca4d978b3c89c5692715c0788671a6e1caa425c2349b`. All fixed inputs/references, raw126process outputs, failed numerical criteria, timing observations and independent retained audit are included. Keep outside source control if desired; no build or CI dependency on this archive. Original frozen local paths are historical provenance, not portable execution paths. Local freeze is not external study registration or protection against machine-owner tampering.
