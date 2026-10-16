# Round27: global rank experiment, development result

## Decision

The prespecified development advancement screen did **not pass**. All 1300 cases
completed, but the primary heavy-tail null produced 19/200 rejections (9.5%;
Wilson95% 6.1663–14.3602%). Its upper interval exceeds the frozen 10% eligibility
limit. This is **inconclusive**, not the protocol's material-inflation stop
(lower bound >7.5%). Three other null conditions were eligible. Power gains do not
override this null gate. `promising=false`, `pilotEvidenceOfImprovement=false`.
No production method or scientific NO-GO changed. No untouched evaluation data
were generated. This result does not prove a defective permutation test, and
also does not authorize declaring nominal5% control established.

## Complete fixed matrix

Counts are rejections/planned, no missing or unavailable cases.

| Condition | Shipped raw Bonferroni12 | Global candidate | Same-draw permutation Bonferroni12 | Fixed median | Fixed CV |
|---|---:|---:|---:|---:|---:|
| Heavy-tail null |7/200|19/200|6/200|16/200|16/200|
| Normal null |4/200|10/200|4/200|7/200|12/200|
| Heavy-tail10%contamination null |5/200|8/200|6/200|10/200|14/200|
| Voice lognormal null |2/200|9/200|4/200|7/200|7/200|
| Location×1.05 |35/250|79/250|43/250|112/250|22/250|
| Dispersion×1.30 |72/250|125/250|78/250|14/250|135/250|

Candidate null Wilson95% intervals respectively: [6.1663%,14.3602%],
[2.7383%,8.9578%], [2.0406%,7.6932%], [2.3853%,8.3297%]. Fixed median/CV are
prespecified single-statistic references, not an adaptive selection rule.

Paired candidate-minus-shipped power differences: +17.6 percentage points
(conservative marginal95% interval[10.7841,23.6721]) and +21.2pp
([13.9376,27.6056]). Discordances b/c=44/0 and53/0; one-sided exact McNemar
p=5.68434e-14 and1.11022e-16. Candidate-minus-permutation-Bonferroni differences
+14.4pp ([8.0504,20.1081]), +18.8pp ([11.8270,24.9914]); b/c=36/0 and47/0.
Four intervals are not simultaneous95% intervals. Reused-development comparisons
remain descriptive and cannot override the failed advancement screen.

## Engineering and provenance gates

Nine exact matrices cover987 observed assignments, including full orbits of
70/126/252, nontrivial equal rational scores with different tie variances,
constants, dependence, duplicates and reversal. Independent exact counts/order
matched;192 raw summary slots matched within prespecified2e-13 scalar tolerance;
four expected raw failures occurred at their specified stages. Nine Python oracle
tests, corruption/lifecycle tests and per-result envelope/hash/count validation
are supplied. Protocol, fixture and binary identities are in the gate manifests.

Complete archived replay1300/1300 matched all twelve shipped p-values, decisions
and seeds with zero mismatches. Actual replay14:41:37–14:44:16UTC (159s),
development14:44:50–14:47:45UTC (175s), 2026-10-16. Re-reading all saved files and
regenerating the report produced byte-identical JSON. Two workers, CPU affinity0–1,
999 shared uniform label draws per dataset, original20-minute/1GiB budgets.

The initial replay attempt was interrupted:288 completed,9 watchdog failures,
1003 not started. Missing Linux VmRSS during process exit was reproduced on147/150
short owned test processes. The driver now requires bounded confirmed exit rather
than treating absent live accounting as zero; native peak-memory checks and all
result validation remain mandatory. The full1300 replay was repeated under a new
source attestation; no selected subset replaced failures. Both attempts and the
seven deterministic lifecycle checks are retained. Fresh/saved result envelopes
also bind mode, coordinates, harness/core hashes and runtime8.0.31.

Literal oracle inputs and independent expected outputs preceded native comparison;
the consolidated freeze record was written during arithmetic preflight, about10s
after the first comparison started. Statistical specification was fixed before
scientific development generation. No stronger prospective-registration claim.
Local hashes cannot protect against a malicious machine owner rewriting history.

## Computational cost

Same pilot process/environment, shared preprocessing separately measured. Medians:
preprocessing39.779ms, shipped inference5.79155ms, candidate inference29.4011ms;
paired per-case totals including shared preprocessing45.95295ms versus70.27795ms.
The candidate is more expensive; this is not a speed improvement. Median native
process total86.0784ms/CPU80ms. Maximum native reported working set43,433,984bytes;
maximum sampled driver RSS49,688,576bytes. RSS sampling is a watchdog, not a hard
OS memory sandbox; process startup/reporting adds overhead outside inference.
All individual timings are retained, not just favorable samples.

## Scope, use and rollback

Normative settings: `ROUND27_GLOBAL_RANK_PROTOCOL.md` and
`validation/global-rank-development-v1.json`. The implementation is an isolated
net8.0 test harness in `validation/global_rank_experiment`, not linked into CLI
production inference. Build with `dotnet build validation/global_rank_experiment/GlobalRankExperiment.csproj -c Release`.
Run `python validation/run_global_rank_development.py --help` for explicit external
output/gate arguments. Execution requires matching locally built binary/source/
runtime attestations, not blindly trusting shipped evidence from another build.
The evidence archive contains every case and gate; use report JSON for complete
machine-readable fields. Exact oracle: `python validation/global_rank_reference.py --help`.

The candidate tests a maximum of marginal rank-location contrasts under entity
label exchangeability. It is not sensitive to every joint-distribution change,
does not identify latent components or individual metric discoveries, and does
not establish equivalence. Gains over permutation Bonferroni combine joint
calibration/dependence/discreteness effects. Real-world validation remains absent.

Delivery is cumulative25+26+27 PATCH over23/24 code, preserving README files.
Back up the source, verify manifest prior hashes, then apply. Round26 is rollback
for experimental files; deleting the newly added experiment is unnecessary to keep
production behavior unchanged. Round25/26 fixes remain separately documented.
Windows runtime acceptance of the Round26 repair is still pending owner rerun.
Next scientific action is a read-only audit of heavy-tail null exchangeability,
entity counts/filtering and implementation assumptions, followed by a separately
frozen diagnostic design if justified. No extra seeds/replications, threshold
changes or holdout consumption are authorized by this failed screen alone.

## Final regression checks

524 Python tests discovered:510 passed,14 actual-Windows-only checks skipped.
The actual Linux native MCP wire test passed. Isolated harness Release build
completed with zero warnings/errors; its binary hash remained unchanged.
The full158 native suite from Round25 was not repeated for this test-only stage.
All 92 inspected production/benchmark/history files match Round26 byte-for-byte.

## Independent terminal review

Independent re-analysis confirmed all1300 cases,15600 shipped p-values, saved
matrices, counts, intervals and provenance. No obvious exchangeability violation
was found in the primary null: all200 cases retain16+16 entities,40 measurements
each,1280 rows; both groups use the same law/floor and no outcome selection.
The concerning19/200 result therefore remains inconclusive under the frozen gate.
Ratios of timing medians are5.08× inference-only and1.53× including shared preparation.
Next authorized diagnostic is independent reconstruction of the SAME999 assignments
and exact tail counts for ALL200 primary-null cases, including nonrejections.
A separate plan must be frozen first; it creates no data, extra draws or holdout,
and cannot convert this pilot screen into a pass. Independent review artifacts
are included in the evidence archive.
