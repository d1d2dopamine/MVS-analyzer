# Round30: conservative restored simplex arithmetic provenance

## Verified numerical defect and repair

A backup can be published with the current environment appended before saved
simplex objective values have been reevaluated. A subsequent process restores
that file, sees the current environment last, and trusts stale values. A bounded
one-dimensional quadratic fixture demonstrated value−999 and zero objective calls
where reevaluation requires value1. This also occurs after successful Begin then
process exit before optimization, not only a failed collection ZIP publication.

The repair trusts restored simplex values only if their document's original
history is **nonempty and every entry equals the current environment**. Any foreign
history forces reevaluation on every resume. Restored empty history remains empty
when published, so opening it cannot falsely turn unknown origin into trusted
current origin across a second process. New fresh sessions still record current
normally. No sentinel, schema field, request hash, RNG or checkpoint key changes.

The necessary tradeoff is conservative repeated objective evaluation. A cache with
foreign/unknown history does not become trusted merely because an earlier resume
might already have refreshed some units. The format has no per-unit arithmetic
origin proof. For an n-dimensional restored simplex this path evaluates n+1 saved
points before normal iteration. Fresh sessions and all-current histories retain
the existing fast path. This is narrower than equivalence of all cross-environment
scientific results; completed fit/result cache shortcuts remain unchanged.

## Frozen checks and actual process boundary

Plan: `validation/round30-provenance-plan.json`, SHA256
`a69a71b81ad7b5ca98091faa2d50092b0e6af6ca9ef3fc1769b1eafeceb1c1dc`.
Baseline is Round29; its same-live-scope retry repair remains intact.

25 new native cases plus six Round29 cases cover foreign/mixed/reversed/unknown/
current/repeated-current histories; direct and three repeated disk reloads;
successful Begin and late collection ZIP failure; callback exception/cancellation;
precancelled optimizer token; fresh-session control; three converged-simplex cases.
Baseline29 fails13 and passes18. Candidate30 passes31/31, independently repeated.

A separate console harness actually launches a producer process that publishes a
checkpoint then calls Environment.Exit without disposing its session, followed by
separate consumer processes. This models the publication-before-reevaluation window;
it is **not an OS forced-kill test**. Foreign/unknown/current × normal/late failure,
three reloads, baseline/fixed:36 restart observations. Thirty additional cold
microcase observations use five paired AB/BA/AB/BA/AB orders per history. All66
observations and108 child invocations passed their prespecified expectations.
The baseline's stale-value failures are intentional negative controls, not hidden.

The producer/consumer journal fsync-retains commands, stdout/stderr, exit codes and
decoded pairs before assertions. Source/test/plan hashes were frozen before runs.
No new scientific datasets, permutation samples or heldout data were generated.

## Cost and interpretation

In the one-dimensional fixture, corrected foreign/unknown resumes require exactly
two objective evaluations; same-current resumes require zero in both versions.
The same-current result and all returned optimizer fields remain exact. Foreign/
unknown values deliberately change from the known stale−999 to correct1.

Median Minimize-only elapsed milliseconds (five observations per cell):

| History | Baseline29 | Fixed30 | Baseline/fixed objective calls |
|---|---:|---:|---:|
| Foreign |8.9963|8.6371|0 / 2|
| Unknown |7.9128|8.2368|0 / 2|
| All current |8.0146|8.1258|0 / 0|

Allocated bytes were30,344 in every cell. Timers exclude backup IO/build, but
include cold method/JIT effects; these tiny timings are descriptive, not a speed
comparison or deployment guarantee. The baseline foreign/unknown calculations are
incorrect controls, not acceptable faster alternatives. Real expensive objective
functions incur their actual n+1-call cost on each uncertain resume.

## Compatibility, remaining boundaries and deployment

Portable backup schema1 and implementation identity remain unchanged. Empty
histories were already accepted; consumers were inspected and do not index an
empty list unconditionally. BackupRunner reports an aggregate identity for such
history; it is not relabeled as a verified current origin. Foreign history remains
visible. Old executables retain the unsafe last-entry assumption: use a rebuilt
current engine to obtain this repair, not just updated source or Python wrapper.

Only simplex objective cache trust and initial backup retry handling change in
combined29/30. This does not promise atomic rollback of all checkpoint/collection
files, automatic retries, objective cancellation latency, real Windows acceptance,
or validity of the experimental global-rank method. The Round27 null screen and
NO-GO remain unchanged. Runtime checks here are Linux; the separate Round26 Windows
repair still requires owner-run acceptance.

Delivery is cumulative25–30 PATCH; README files are preserved. Back up the project,
check acceptable prior SHA256 values in the manifest and apply, then rebuild CLI
and reinstall any packaged engine. Round28 is the last delivered rollback; internal
Round29 records the intermediate same-scope-only repair. No backup conversion or
original evidence rewriting is required. Broader per-run recording architecture
and mature numerical-library evaluation remain separate future work.

## Final regression result

Full native suite189/189 passed. Python536 discovered:522 passed,14
actual-Windows-only checks skipped; actual newly rebuilt Linux CLI/MCP wire
passed. CLI and targeted Release builds had zero warnings/errors. No Windows
runtime or fresh scientific benchmark is claimed.
