# Round 12: post-hoc internal Holm development diagnostics

Date: 2026-10-11 UTC. Input: the immutable, completed round-6 engine-1.6.2
MVS-BENCH-1.2.0 full development run. This is **derived development evidence**,
not a new benchmark run, unseen validation or an activated inference method.

## Result

Actual internal native Bonferroni/Holm outputs were checked against the independent
exhaustive closed-intersection reference for **5,370 full-family vectors and
128,880 adjusted values**. All arithmetic and legacy/family decision checks passed.
All twenty condition/phase groups retain exactly the same any-rejection count.

| Condition | Replications | Any rejection, both methods | Bonferroni member discoveries | Holm member discoveries |
| --- | ---: | ---: | ---: | ---: |
| Primary null | 1,000 | 18 | 39 | 48 |
| Location x1.05 | 250 | 35 | 162 | 169 |
| Location x1.10 | 250 | 190 | 923 | 949 |
| Location x1.20 | 250 | 250 | 1,329 | 1,369 |
| Dispersion x1.30 | 250 | 72 | 277 | 318 |

Holm adds member discoveries only after the first rejection. Across the 5,250 main
replications from heterogeneous conditions, it adds 163 member discoveries in 105
replications. This is a descriptive count, **not a pooled power/FWER estimate**.
Under the primary null, all additional member rejections are false discoveries;
the family-level event still affects the same 18 replications. More member
rejections are therefore not automatically a scientific benefit.

Location x1.05 any-detection stays 14.0%; dispersion x1.30 stays 28.8%. The frozen
benchmark's **NO-GO remains unchanged**. No verdict was recomputed or relabelled.
These corrections concern the raw fixed twelve-metric family, not calibration
selection gates or equivalence intervals. Historical procedure labels are retained.

## Evidence and preservation

The new archive is separate:
`benchmark_history/holm-development-diagnostics-round12/`.
It contains the prepared full-vector fixtures, actual native output, independent
comparison, condition/phase CSV, detailed per-metric diagnostics, provenance and
checksums. Original benchmark files are pinned by their exact hashes and remain
byte-for-byte unchanged. Native fixture SHA-256:
`29b117854746aec9f8219773eafccd6b48471a6c1b8779448a9845df1f894d18`.

The native export used the verified round-10 Core assembly, SHA-256
`23fda6adf0a605b614839f6f79fd7bbd911f947644e95c7e9ebf7541d06de5be`,
whose relevant source is unchanged here. No native source or public inference
path changed in this stage. Both replay phases remain distinct 60-replication
sets, not pooled as independent scientific evidence. All 5,370 actual replications
were completed/retained; excluded replications and unavailable metric slots were
zero in this particular run.

The tool preserves failed/unknown/missing diagnostic rows if supplied; they do
not silently become analyzed discoveries. Fixed twelve-member vectors retain
null slots rather than shrinking the family. Incomplete evidence yields an
explicit incomplete outcome, never a complete accuracy pass. Output directories
and analysis files cannot be overwritten by the tool.

## Checks actually performed

- Source identity, thirteen raw-file/checksum hashes, frozen settings/budgets and
  round-4 per-replication reconciliation checked before preparation and analysis.
- Actual native exporter executed on all 5,370 prepared cases; fixture, runtime,
  engine/family and actual Core binary hashes verified.
- Exhaustive independent comparison checked every adjusted p-value and rejection
  vector. Native Bonferroni was also checked against raw metric decisions and
  recorded Bonferroni/registry-corrected procedure decisions on these exact data.
- Same any-rejection event and Bonferroni-discovery subset of Holm verified for
  every case. No disagreement or omitted phase was found.
- **34 new synthetic regression tests** cover unavailable values, ties, additional
  discoveries, failures/missing diagnostics, phases, malformed/duplicate rows,
  tampering/provenance and overwrite protection. Fake native documents in these
  tests are explicitly synthetic and are not the archived native evidence.
- Existing validation tests plus new tests: 159/159 passed. Full CI-style Python
  suite: 281/281 passed. Source/CLI contracts, notebook/payload consistency,
  pre-edit scope guard and ZIP integrity/completeness passed.

The independent full comparison took approximately **68.6 seconds** wall time,
68.4 user-CPU seconds and 129,488 KiB peak resident memory in this execution.
That is an operational observation for the diagnostic checker, not a controlled
production speed claim. An optional timing wrapper was unavailable initially
(exit 127); native export had completed, analysis had not started, and its evidence
was retained. Python timing/resource collection then measured the actual analysis.

No full benchmark, remote CI or new native regression suite was run. Round 10's
113/113 native suite and real CLI/Python parity remain the latest such evidence;
this stage's native claim is specifically the newly executed exporter.

## Risk, rollback and remaining gates

Risk is misinterpreting post-hoc member counts as a new scientific success. The
report therefore retains source identity, original NO-GO, each phase/denominator,
and the distinction between arithmetic correctness and inferential validity.
Rollback is the complete round-11 ZIP; no state migration or method switch occurs.

Holm's strong FWER result requires valid marginal p-values; this diagnostic does
not resolve small-sample rank-test approximation limits. Fixed-family Holm and
Bonferroni have the same first-rejection event, so Holm alone cannot close this
benchmark's global power gap. maxT needs declared joint-null/resampling assumptions,
and family-level claims still need explicit null meanings and cross-family rules.
The reused BENCH-1.2.0 run cannot serve as unseen release validation.
