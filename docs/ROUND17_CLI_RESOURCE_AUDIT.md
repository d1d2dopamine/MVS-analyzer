# Round 17: bounded CLI resource and cancellation audit

## Scope and rollback

This checkpoint runs one frozen, serial Linux resource profile of the maintained
CLI calibration/analysis path and one deliberate cancellation probe. It is an
engineering observation, not a scientific benchmark, performance SLA, stability
estimate, or model validation. The twelve active metrics, Bonferroni correction,
engine 1.6.2, saved-state identity and historical evidence are unchanged.

The round-16 complete source ZIP is the rollback point. This stage changes only
an isolated diagnostic runner, its protocol/tests, new evidence and documentation.
It does not change native execution, Python API behavior or production defaults.
The existing round-14 compiled native binary is reused; binary/source identity is
recorded rather than claiming a new build.

## Frozen experiment and resource limits

The protocol is `validation/cli-resource-profile-v1.json`, written before the
run. Three independent groups contain respectively 4, 20 and 100 entities per
group, with 6, 20 and 50 repeated measurements per entity: 72, 1,200 and 15,000
rows. Synthetic generation is deterministic and retains original input bytes.
Each size receives one fresh 100-replication calibration and one analysis.
This smoke calibration budget is deliberately unsuitable for inferential claims.

Children run serially with affinity restricted to two available CPUs, a sampled
768 MiB resident-memory watchdog, and declared wall-time limits. The watchdog is
not a hard memory reservation; peak RSS and process CPU time are recorded from
Linux process accounting. The shared host is also running unrelated work, so
elapsed times describe these observations rather than controlled speed rankings.
Larger cases are skipped after a limiting failure rather than repeatedly retried.

One separate middle-size calibration requests 100,000 replications and receives
SIGINT after one second if it is still running. The intended outcome is a
structured cancellation, exit 1 and no completed calibration state. A bounded
shutdown timeout prevents a hung child from continuing indefinitely; any forced
termination is retained as a failure. Backups are disabled in task-local output,
so this probe makes no claim about checkpoint/resume after cancellation.

## Executed evidence

The single actual run started **2026-10-11 22:54:27 UTC** and completed
**22:54:46 UTC**. All seven cases passed their operational/output checks; no case
was skipped or retried, and no watchdog, timeout or forced termination occurred.
Child affinity was `[0, 1]`; parent affinity, inputs, protocol, runner and binary
identities remained unchanged.

| Case | Wall seconds | Process CPU seconds | Peak RSS MiB | Exit |
|---|---:|---:|---:|---:|
| 72-row calibration | 0.811 | 0.873 | 46.9 | 0 |
| 72-row analysis | 0.305 | 0.226 | 52.3 | 0 |
| 1,200-row calibration | 2.633 | 2.755 | 53.9 | 0 |
| 1,200-row analysis | 0.305 | 0.251 | 54.8 | 0 |
| Deliberate middle-size cancellation | 1.064 | 1.178 | 59.0 | 1 |
| 15,000-row calibration | 13.515 | 13.660 | 68.6 | 0 |
| 15,000-row analysis | 0.507 | 0.447 | 66.6 | 0 |

The cancellation emitted one structured `OperationCanceledException`, no completed
state/manifest and no claimed result artifacts. Observed signal-to-reap latency
was 0.0506 seconds, at approximately 50 ms polling resolution. This is one observed
cooperative cancellation, not a bound for all phases or workloads.

The compact summary is `validation/cli-resource-profile-round17.json`. The nested
`validation/cli-resource-profile-round17.zip` contains 69 raw evidence files,
including inputs, frozen protocol/runner, stdout/stderr, process samples and all
result artifacts. CRC and every inventory hash were verified. Its SHA-256 is
`5bb8567466d0835844e7dbac7981b7bec5575c55bf4c60d4920cced5aefad722`.
The frozen protocol SHA-256 is
`9f616a8ad788f0caf43a929faa48c90f319de48bee6832bc5b2129d9edf6a10b`.

The runner verifies machine status/exit agreement, artifact hashes/sizes, input
identity, twelve metric slots, Bonferroni adjusted p-values and preservation of
saved calibration bytes in analysis. These consistency checks do not independently
validate every scientific quantity. Timing includes startup, I/O and measurement
overhead; a fresh process does not mean a cold filesystem cache.

### Verification record

- **18/18 new pure/mock runner-control tests PASS**; they do not launch the CLI
  or rerun the profile. The actual seven invocations are separate evidence.
- Source identities/links, machine contract, notebook/payload checks and **34/34
  release-bundle tests PASS**, including copying the current source documentation
  with a synthetic nonexecuted CLI sentinel.
- All **88 native source/project files** are byte-identical to the tested round-14
  source. The existing native binary was reused. No rebuild, redundant native
  suite, full scientific benchmark or remote workflow was executed this stage.
- Existing output checks validated **12 JSON documents, six states and three
  manifests**. Final scope and nested evidence checks PASS; complete source ZIP
  integrity and preservation are separately verified at packaging. Earlier 375-test Python and 135-test native results remain historical
  evidence from their respective checkpoints, not tests relabeled as rerun here.

## Readiness and remaining decisions

The full BENCH-1.2.0 development result remains **NO-GO**: power fails and stability
is inconclusive. Resource observations cannot change those scientific outcomes.
The project is a tested development checkpoint, not a finished 1.5.0 release.

The remaining dependent scientific decisions are:

1. Define whether each automatic family finding is a distributional difference
   in entity summaries or an isolated location/variance-component claim.
2. Freeze the statistics, direction, joint entity-level null mechanism and
   assumptions supporting complete-null and partial-null control. A finite-matrix
   maxT implementation alone supplies none of these assumptions.
3. Specify unavailable/failure handling, across-family correction and how
   exploratory calibration relates to confirmatory decisions; preserve actual
   denominators and negative results.
4. Then define activation, version/state/result compatibility and an unseen
   BENCH-2.0 protocol with prespecified error, power and stability targets.

Further unused estimator or resampling scaffolding would not close these gates.
A proposed global exchangeable entity-distribution comparator would be a narrower
claim than pure component identification; it must not silently replace the goal.
Step-down arithmetic and additional runs on the already-used development protocol
are not substitutes for the missing scientific specification.

Safe independent work still has concrete possible value: full scientific-field
CLI/Python parity for the existing variance, estimation and experimental MELSM
interfaces would close an interface-coverage gap without changing the model.
It would not establish external model validity. Unexpected mid-write failures and
transactional multi-file output also remain a separate, larger operational design
issue; current preflight protection is not an atomic commit protocol.

Other honest limits persist: original historical Actions artifact retrieval needs
authentication; Windows/macOS/live Colab and independent external model checks
were not performed here; retired desktop hash pins remain unchanged. No commit,
remote workflow, release, tag or publication is part of this checkpoint.
