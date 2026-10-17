# Prospective adapter verification and literal cost probe

Protocol `MVS-PROSPECTIVE-ADAPTER-COST-1.0.0`, Round55. This bounded engineering experiment implements the fixed-fixture admission step specified in the prospective ADEMP design. It does not execute any of the 12,000 planned study cases. The immutable Round54 statistical design and historical result registries remain unchanged.

## Scope and implementation boundary

The isolated validation project links the unchanged Round50 harness source and references the actual production Core project. A narrowly named reflection bridge invokes only the existing `Fixture`, `Observer`, `Complete`, `Legacy`, `Encode`, and `Identity` helpers. This reuses the established fixture, recording checks, summary policy, and exact serialization without copying a statistical implementation. The private bridge is test infrastructure tied to source hashes, not a new public API; renamed or incompatible helpers must fail closed.

The new project retains the fourteen historical `source/` embedded provenance resources. Its own adapter source/project identities are separate, so the old identity helper's exact count is preserved. The adapter and Core DLLs, runtime, request bytes, build evidence, and host driver must be bound before calculation. Compiling a new adapter does not change production methods or their versions.

This release verifies a **fixed-fixture adapter**, not a general study executor. General arbitrary-input routing, complete outer-case failure classification, the planned generator, and final statistical report implementation still need independent verification. Resource eligibility from this probe cannot authorize the large simulation.

## Fixed work and explicit request

The request contract has thirteen exact fields, rejects duplicates/unknown keys, and is at most16KiB. Its canonical encoding is UTF-8 compact JSON with sorted keys and one terminal LF. The admitted SHA-256 is `6aed9dd4fb65af09414db6b245edfe29173b72521807fa3dafa4008ef396e440`.

- Fixture: unchanged Round50 deterministic `Fixture()`; two groups,16 entities per group,40 repeats,1280 formula-defined observations.
- Native seed52000000; evaluation repetitions100; reference replications199; both effect parameters2; alpha.05.
- One full variance call and one actual fixed12-summary calculation per fresh process.
- Native cancellation limit180 seconds; the overall engineering probe has a stricter shared300-second lifecycle budget plus at most10 seconds for cleanup.
- Backups disabled, no saved-state restoration or cache replay; each child has a one-CPU runtime cap and one selected permitted CPU affinity slot.

`identity` and `validate-only` modes cannot invoke the model. `engineering` requires the exact request hash and environment prerequisites before fixture materialization or computation. It accepts no user dataset. A complete success envelope is emitted only after full work, completeness validation, summary calculation, and serialization. Failures retain their phase, completed=false, exception type/message/stack/inner exception, and operation counts; partial traces do not become successful results.

The ordinary model call performs its internal parametric bootstrap/evaluation draws on the fixed seed. “No study data generated” refers to the absence of new outer benchmark datasets, not an assertion that the engine did no random computation.

## Schedule and preservation

There are exactly three sequential fresh processes followed by one batch of eight fresh processes, eleven calculation calls maximum. There are no replacements or retries. All paths, command identities, starts/exits, stdout/stderr bytes, native timing, and failures are retained. A failed sequential call halts before starting later work; failed parallel members are retained and the attempt cannot be eligible. The supplied protocol fixes limits before any call.

The driver uses blocking process completion with an independent deadline watchdog. Output files are opened before measured launch. The parallel lifecycle begins at first launch and ends after every child exits, including launch stagger. Timed-wait polling backoff must not contaminate wall-time measurements. Process groups are owned and cleaned up on failure; no unrelated process is terminated.

Aggregate RSS is sampled every50ms and bounded at2GiB, with native peak-working-set information reported separately. Sampling can miss a transient peak; this is not a kernel-enforced memory sandbox or proof that unsampled usage never exceeded the limit. Retained output has a20,000,000-byte admission cap checked by the sampled watchdog and final accounting. The sampler can observe an overshoot after it occurs; it is not an OS write quota. Overshoot must fail admission and preserve the tail rather than truncate it into an apparently complete stream. Unexplained resource-read, capture, provenance, or cleanup failure is a technical failure, not silently ignored missing telemetry.

## Exact adapter parity gate

Both retained Round50 literal cost calls are the reference. Their original harness file hash differs from the later linked harness because the later file added a study-worker entry and helper block. Removing exactly those additions reconstructs the historical file byte-for-byte; all linked fixture/recording/completeness/summary/encoding/identity helper bodies are unchanged. The thirteen other historical source resources and runtime identities are checked separately. Thus this is preserved-helper/output equivalence, not a claim that the whole historical harness file or its binary is identical. Before use, verify their pinned stdout and result hashes and agreement with each other. Each new call must match the old fixture digest, full report, full legacy result, and completeness summary exactly, including binary64 bit tokens. All1103 cached callback observations must match in original order and value, including convergence, finite status, and callback counts.

The only excluded fields are historical call ordinal in `payload.call` and the trace `call` tag. Timing, process identity and envelope provenance are validated separately, not compared as scientific values. No numeric tolerance, field dropping, favorable-call selection, or parser fallback is allowed. A mismatch stops the attempt and preserves its evidence.

Every call must satisfy the old `Complete` contract: expected keys, callbacks exactly once, required finite/converged fits, complete reference/evaluation/grid counts, normal begin/finish/dispose ownership, and zero restore hits. A cheap incomplete call cannot satisfy resource admission.

## Resource screen and interpretation

Let S be the maximum lifecycle wall time among three sequential calls, P the lifecycle wall time of the eight-call batch, and D the maximum retained bytes per call. The predeclared projections are:

    projected_wall_seconds = 2 * max(S,P) * 12000 / 8
    required_storage_bytes = 2 * D * 12000 + 1073741824

The wall projection must not exceed86400 seconds. Required storage must fit measured available storage, and all completeness, parity, telemetry and memory checks must succeed. Storage figures include raw call evidence and do not justify deleting failed cases or necessary source assets. Package copies and manifest overhead remain separately visible.

This is a conservative multiplier applied to one fixture, not a statistical confidence bound or a worst-case guarantee. Preserve all11 costs; no single favorable sample is substituted. The previous192-dataset study's linear reference remains41727.10178525085 seconds (11.59 hours) for12000 cases. Different observed datasets can require very different optimization work. A faster literal fixture neither refutes that historical reference nor proves that a real study will finish sooner. No general method-speedup claim is planned.

Even an eligible resource screen reports `science_execution_authorized=false`. Final study execution still requires the complete adapter/generator/report implementation, runtime and data provenance, review, and a separately frozen execution manifest. The existing planning tool must continue to report execution blocked.

## Verification before launch

1. Compile the test-only adapter; inspect actual Core/runtime/resource identities.
2. Verify valid request and malformed/duplicate/unknown/environment-failure cases without model calls.
3. Test driver corruption, missing/incomplete envelopes, callback drift, wrong exits, source/hash drift, write-once behavior, cleanup, resource failures and exact schedule arithmetic with synthetic test processes.
4. Independently review native source and driver, bind their final bytes, then run the single eleven-call attempt.
5. Independently audit retained results and report every failure and all costs. Do not rerun to rescue eligibility.

The full source archive contains the implementation, fixed protocol, and tests. Large raw evidence, if separate, is an optional companion explicitly identified in the source manifest; no CI check may depend on an inaccessible private attachment.
