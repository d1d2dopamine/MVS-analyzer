# Round 8: paper benchmark evidence audit

Date: 2026-10-11 UTC. Starting checkpoint: round 7 internal Holm.

## Reproduced defects

1. The historical paper verifier accepted a directory with only an identity/verdict
   manifest and an empty `SHA256SUMS.txt`, with **no result files**. The fabricated
   manifest declared `overall: go`; the checker exited zero and printed verified.
   It trusted the optional manifest `files` array, which could be omitted.
2. Starting from the real historical archive, removing the manifest's checksum
   entry, changing primary replications from 1000 to 1, and clearing `conditions`
   still passed. Manifest integrity and full completion were not required.
3. The paper workflow built the current engine 1.6.2, but its final historical
   verifier requires engine 1.6.0. A run could expend its entire compute budget
   only to fail the identity check. The current full development archive reproduces
   that mismatch; the historical archive passes the original verifier.

These are artifact/workflow correctness defects, independent of whether a valid
scientific verdict is go or no-go. No historical result is rewritten or relabelled.

## Scope, risk and rollback

The change is limited to the historical verifier and adversarial tests, an early
workflow source-identity check, CI test invocation and documentation. It changes
no native code, statistical method, benchmark settings, archived evidence, saved
state, engine identity or embedded payload. Rollback is the complete round-7 ZIP.

The historical target remains app 1.4.0 / engine 1.6.0, full MVS-BENCH-1.2.0,
seed 20260904. The current checkout is deliberately refused before compute. No
verified historical source commit was found in the inspected archive; that
reproduction target must be established rather than guessed. The engine-1.6.2
development baseline remains a separate completed NO-GO run.

## Implemented checks and actual verification

The verifier now requires the seven historical output artifacts and checksummed
manifest, strict finite/unique-key JSON, safe regular-file paths, valid unique
checksum entries, frozen protocol text/formula identity, simulation budgets and
all nineteen declared synthetic conditions. It reconciles summary/metric/choice
counts and rates, stability CSV/summary and verdict/overall consistency. Optional
resume provenance must be declared, checksummed and use the same arithmetic
identity. Source preflight checks the declared app/engine/formula/protocol before
setup/build/compute; it does not authenticate a historical revision.

- **40/40 new adversarial verifier regressions passed.** They cover the reproduced
  empty-artifact acceptance, omitted manifest checksum, changed/truncated budgets,
  malformed JSON, duplicate/unsafe checksum paths, altered files, identity mismatch,
  inconsistent tables and resume provenance.
- The real historical engine-1.6.0 NO-GO archive passes without modification.
  Current engine-1.6.2 archive and source preflight correctly reject that historical
  target. These are expected identity rejections, not a scientific failure of a
  new run.
- Failure-preservation fixtures pass: one failed replication, all 1000 primary
  replications failed with blank rates, all 120 stability splits failed, and failed
  replay. Full completed-plus-failed accounting is required; zero failures is not
  an invented acceptance gate.
- Existing CI-style Python suites rerun: 134/134 passed. Together with the new
  verifier suite, 174/174 passed. Source/CLI metadata, notebook consistency and
  unchanged embedded payload checks passed. Shell/workflow entry was reviewed;
  remote GitHub Actions was not executed.
- Final change guard and ZIP integrity/source completeness checked. Both historical
  and new development benchmark archives are byte-preserved.

Native build/104-test suite and real CLI/Python parity were not redundantly rerun
for this Python/workflow-only stage; their round-7 results remain the most recent
native evidence. No full benchmark or historical reproduction was run here.

Checksums and self-consistency do not authenticate adversarially rewritten evidence.
The historical format does not expose enough raw information to independently
recompute every scientific verdict (notably held-out-oracle power comparisons).
The verifier therefore reports integrity/completeness, not scientific certification.

## Remaining audit findings and readiness criteria

The two legacy UI/Colab connection tests still pin older `HeadlessRun.cs` bytes
(expected SHA starting `608db779`, actual `679369121`). Actual bytes match both the
user-supplied round-3 ZIP and embedded source payload. This establishes stability
since the input, not correctness of the uninspected older change; the hashes were
not silently blessed to obtain a green suite.

The chunk shell runner separately needs safe destination/input-path validation:
its current reset deletes the requested state/work directories before checking
whether they overlap incoming evidence. Its pass-through branch also labels any
found manifest complete before final verification. A disposable temporary-directory reproduction with incoming equal to state
confirmed that the synthetic evidence marker was deleted before the later Git
error (exit 128). No user evidence was touched. These are follow-on engineering
defects, not repaired by changing scientific acceptance criteria.

Project readiness is explicitly split:

- Engineering readiness: meaningful tests for maintained CLI/Python paths,
  independent numerical comparisons, correct unavailable/error semantics, immutable
  evidence and reliable verification/checkpoint handling, honest documentation,
  measured resource behavior, reproducible source packaging.
- Method readiness: all activated estimators independently validated; correction
  family and valid test assumptions declared; observable methods identified in
  results, caches and saved states; unavailable cases do not shrink the family.
- Scientific release readiness: target family claims and thresholds defined, then
  behavior frozen and evaluated on an independent MVS-BENCH-2.0 design with unseen
  seeds and broader conditions. Assess FWER, power, family identification/stability,
  uncertainty and determinism. Reused development scenarios are not unseen evidence.

Current work does not meet the scientific release gate. Full BENCH-1.2.0 remains
NO-GO, Huber remains staged with reproduced defects, internal Holm is unused, and
maxT/family-level interpretation still needs declared assumptions. Safe independent
engineering and staged numerical repairs can continue while those decisions remain
queued. No full benchmark rerun is justified for this verifier-only patch.
