# Round 11: historical paper source provenance

Audit date: 2026-10-11 UTC. This checkpoint records public provenance evidence;
it changes no implementation, workflow, historical gate or archived result.

## Finding

The best-supported source candidate is
**561442711faa0bf69dc766f61d89869ce683af0e**. The
[successful historical paper run](https://github.com/d1d2dopamine/MVS-analyzer/actions/runs/35388409546)
explicitly identifies that commit. Its
[first benchmark job](https://github.com/d1d2dopamine/MVS-analyzer/actions/runs/35388409546/job/105740768659)
ran the benchmark step from **2026-09-18T19:53:35Z to 21:50:35Z**, exactly matching
the archived manifest's start and finish. This is strong supporting evidence for
the source candidate; timestamp agreement alone does not bind output bytes.

Downloaded source constants at that immutable commit pass the existing static
historical preflight. App 1.4.0, engine 1.6.0, formula MVS-1.4.0 and frozen
MVS-BENCH-1.2.0 specifications match, including both complete SHA-256 hashes.
The checked file URLs/hashes and public run/job/artifact metadata are retained in
`validation/historical-paper-provenance/`.

The historical archive first appeared in
[commit f085a40e9a349dcfb00a76a648c0110571f81491](https://github.com/d1d2dopamine/MVS-analyzer/tree/f085a40e9a349dcfb00a76a648c0110571f81491/benchmark_history/1.4.0-engine-1.6.0-MVS-BENCH-1.2.0).
All **nine files** fetched from that commit are byte-identical to the frozen local
archive. The comparison and checksum records are retained. No archive was modified.

## Why the release tag is not enough

The [v1.4.0 release](https://github.com/d1d2dopamine/MVS-analyzer/releases/tag/v1.4.0)
points to **79cf6d535a5b26bd2359d685a2111414c30fa3c5**, eight commits before the
workflow source. Its declared identities also pass the static preflight, but
[numerical and benchmark implementation files changed between those commits](https://github.com/d1d2dopamine/MVS-analyzer/compare/79cf6d535a5b26bd2359d685a2111414c30fa3c5...561442711faa0bf69dc766f61d89869ce683af0e).
The historical archive was absent at the release commit. Matching version strings
and specification hashes therefore do not establish identical source/builds.
Do not substitute the release tag as the proven historical producer.

## Exact remaining gap

Public metadata links artifact **10569962325**, named
`mvs-paper-benchmark-full-seed-20260904`, to that run/source commit. It reports
203,551 bytes and archive SHA-256
`499e12e3bc4c28b6d1ff03905fe34710453636f0b5f5c3d19479e26f4b954fa0`.
At audit time it was not expired; recorded expiry is **2026-12-17T19:53:08Z**.
[Artifact metadata](https://api.github.com/repos/d1d2dopamine/MVS-analyzer/actions/artifacts/10569962325)
was publicly readable, but downloading its contents returned **401 Requires
authentication**. No credentials were supplied and no alternate access route was
attempted.

Completing the run-to-output link needs authorized retrieval of that exact artifact
(or its original user-provided download), verification against the public digest,
inspection of original chunk provenance, and byte comparison of its result folder
against the committed archive. Only that dependent provenance check is blocked;
other development work can proceed. No authentication or persistent access is
required merely to read the public evidence already retained here.

Even a matching original artifact would not substitute for a controlled historical
reproduction or establish scientific correctness. No historical build or benchmark
replay was executed in this audit. The complete source/build/output binding remains
explicitly **unverified**. The current workflow's historical gate remains unchanged.

## Checks and rollback

- Actual downloaded constant files passed the static parser; no downloaded code ran.
- Public run success/source identity, exact step timestamps and artifact run/source
  metadata were cross-checked independently against the saved manifest.
- Nine committed archive file hashes were independently checked against local bytes.
- Retained evidence JSON was parsed and checksummed; source/CLI metadata checks,
  the existing forty verifier tests, scope guard and ZIP integrity passed.
- Native tests and real CLI parity were not rerun for this evidence/documentation
  checkpoint. Round 10 remains the latest native evidence.

Risk is limited to documentation/evidence interpretation. Rollback is the round-10
ZIP; this stage has no data/state migration or runtime effect. The scientific
NO-GO, staged metrics and maxT/family-level readiness gates remain unchanged.
