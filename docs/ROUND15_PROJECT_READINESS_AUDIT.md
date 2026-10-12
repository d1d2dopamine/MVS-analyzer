# Round 15: Python launch errors and project readiness audit

## Outcome and acceptance boundary

This is a **development engineering checkpoint**, not a declaration that MVS 1.5
is scientifically ready or that the plan is finished. The maintained architecture
remains Python/notebooks → versioned CLI → one .NET statistical engine. Active
inference still uses the twelve legacy metrics and Bonferroni.

The audit is risk-based and evidence-backed across implementation, tests, result
validity, performance, errors and documentation. It does not imply exhaustive
verification of every possible dataset, platform or experimental model.

Readiness criteria are explicit:

1. **Supported engineering checkpoint:** builds and meaningful tests pass on the
   tested platform; known input-loss paths are repaired within stated filesystem
   bounds; engine/protocol/error identity is preserved; source and evidence are
   reproducibly packaged. Unexpected failures are not reported as successful runs.
2. **Method integration:** each newly activated estimator/correction has independent
   numerical checks, declared hypotheses/family/null/resampling/availability
   rules, and deliberate version/state/result compatibility treatment.
3. **Scientific release:** freeze the method and acceptance targets, then evaluate
   FWER, power, change-family identification/stability, uncertainty and determinism
   on unseen BENCH-2.0 conditions/seeds. Do not reuse development tuning outcomes
   as confirmatory validation or change a failed gate to obtain GO.

Criteria 2–3 are not met for the planned automatic family-level redesign.

## What was actually established

| Area | Evidence and current finding | Remaining boundary |
|---|---|---|
| Active implementation | Round-3 availability/calibration separation, subsequent native suites, canonical CLI/Python parity and unchanged pre-repair saved-state result bytes | Canonical three-group summary analysis only; full variance/estimation/MELSM cross-interface parity remains unverified |
| Numerical estimators | Rank reference: 53 frozen SciPy cases; staged Huber: original 20 plus expanded 136 independent checks pass after repair | Staged Huber is not activated; other proposed estimator/activation gates remain separate |
| Multiplicity | Internal Holm matches exhaustive closed-Bonferroni reference; full archived development vectors reconciled. Internal maxT matches 40 finite-matrix cases / 104 values | Neither is active; maxT has no validated production null generator or partial-null guarantee |
| Benchmark results | Full BENCH-1.2.0 development run completed all 5,490 work units; per-replication and aggregate diagnostics verified | Scientific NO-GO remains; development scenarios are already reused |
| Errors/data preservation | Round-13 actual CLI tests protect dataset/job/profile collisions, overwrite requirements and predictable target obstructions; global flags return structured errors | Preflight is not transactional, race-proof or universal filesystem-alias detection |
| Evidence/checkpoints | Historical verifier rejects fabricated/truncated evidence; checkpoint runner preserves inputs and validates completion; raw failures and null outcomes retained | Checksums prove supplied-byte consistency, not authenticity or every scientific verdict |
| Performance/resources | Full baseline completed in about 60.4 minutes using eight threads; independent full-vector Holm analysis took 68.622 seconds and about 126.5 MiB peak RSS | These are measured development workloads, not a broad scaling study or performance SLA |
| Interfaces/platforms | Linux native and actual Python/CLI tests, static notebook/payload consistency | Windows/macOS runtime, live Colab/desktop and external R/model validation were not executed here |
| Documentation | This checkpoint consolidates current state and gates; older round reports remain historical snapshots | A historical “not yet fixed” statement is not silently rewritten as current evidence |

### Scientific results are preserved, including negative findings

The full development baseline has A/D/E passing, B failing and C inconclusive.
The principal location multiplier 1.05 scenario detects 35/250 (14%) versus the
held-out oracle's 44.8%; dispersion multiplier 1.30 detects 72/250 (28.8%) versus
53.6%. Mean ranking concordance is about 0.7143 and top-1 agreement 22.5%. These
observations do not meet the desired power/stability redesign goals.

Full-vector Holm diagnostics have exactly the same any-rejection event as the
fixed-family Bonferroni comparator. More member discoveries include false-member
rejections in the primary null: 39 versus 48 rejected metric members, while the
18/1000 any-rejection count is identical. This is a useful constraint on design,
not evidence that Holm alone fixes global power or that every extra discovery is
beneficial. See rounds 6 and 12 for exact procedure labels and denominators.

The original Huber failures remain archived alongside the successful repair.
Failed/absent values are not removed to improve rates, and old scientific archives
are not overwritten by newer comparators.

## Bounded Python repair in this stage

The audit reproduced raw `PermissionError` from `Engine(non_executable_file)` and
`Engine(directory)`, bypassing the documented `MvsError` hierarchy. A controlled
child emitting invalid UTF-8 also leaked `UnicodeDecodeError` before JSON handling.

The repair keeps existing exception classes and discovery semantics. Missing
resolution/launch targets map to `EngineNotFoundError`; other resolution/launch
OS errors and invalid child UTF-8 map to `EngineError`. Exceptions retain their
underlying cause and identify the executable/command. Structured CLI input errors,
scientific diagnostics, process/status agreement and successful responses retain
their existing behavior. No dependency, timeout policy or schema redesign is added.

Risk is limited to Python exception classification around process launch/I/O. The
round-14 source ZIP is the rollback point. No native source, method identity,
calibration, payload, historical result or scientific gate changes in round 15.

## Open issues, ordered by consequence

### Decisions and independent scientific validation required

- Define what an automatic “location”, “within variability” or “between
  heterogeneity” result claims. A distributional difference in summaries does not
  isolate one data-generating component. A joint-distribution omnibus claim and
  a pure-component claim require different hypotheses and validation.
- Specify fixed statistics/orientations and a valid common entity-level reference
  mechanism, including partial-null behavior. Do not permute repeated rows as if
  they were independent entities or generate each metric's draw independently.
- Decide failure/availability handling without shrinking the predeclared family,
  across-family correction, uncertainty and the relationship between exploratory
  calibration and confirmatory inference.
- Only then freeze activation/version/cache/result changes and the unseen
  BENCH-2.0 protocol with prespecified FWER/power/family-stability criteria.

A useful next proposal is a **global joint-distribution development comparator**
under explicit entity-label exchangeability, retaining Bonferroni/Holm comparators
and treating family descriptors as descriptive. That would be narrower than the
planned pure-component interpretation and must not be silently substituted for
it. If pure-component claims remain the target, the next stage is their model/null
specification and independent partial-null simulation design, before activation.
Step-down maxT does not remove these requirements.

### Operational/coverage limits retained explicitly

- Unexpected mid-write failures can leave partial generations. Preflight prevents
  known predictable obstructions but is not multi-file transactional output;
  complete partial-artifact error reporting remains a separate improvement.
- Symbolic-link protection does not cover bind-mount aliases, all case-folded
  Linux filesystems, every Unix special-file type or concurrent mutation. No
  security/filesystem settings were changed to test these cases.
- Release workflow audit found omitted linked checkpoint/method documentation
  in binary bundles and newer oracle/safety checks missing from release gates.
  These require a separate local packaging/workflow repair; no release was run.
- `help --json` still returns human usage, and version/env retain their existing
  unknown/duplicate-option policy. These documented gaps are not scientific exits.
- Retired UI/desktop-Colab checks pin stale historical HeadlessRun bytes. Those
  pins were not weakened, and they are outside the maintained CLI/Python CI target.
- Experimental variance/MELSM implementation tests do not substitute for external
  model validation. No new independent R comparison was run.
- The best-supported historical engine-1.6.0 producing revision was identified,
  but original Actions artifact access requires authentication. Public metadata
  and committed archive equality do not close source/build/output binding. No
  alternative credential path or unpublished Git operation was used.

## Verification record for round 15

Only executed results are added below. Round-14 native evidence remains distinct
from checks rerun for this Python-only change.

### Executed results

- **22/22 new Python error-boundary tests PASS**, including real OS non-executable,
  directory, exec-format, disappearance and permission-loss cases; actual child
  UTF-8 failures; and portable mocked errno cases. Positive child handshakes in
  these unit tests use an explicitly synthetic protocol peer, not the native
  statistical engine.
- **341/341 current Python tests PASS**: 17 backup, 6 source, 40 historical
  verifier, 34 checkpoint runner, 26 API, 21 round-2 and 197 validation-tool tests.
  Existing 53 SciPy rank-reference cases pass as part of this check run.
- Actual compiled CLI plus current Python wrapper: canonical summary-analysis
  scientific-field/CSV/manifest/state parity PASS; output/contract checks PASS.
  Two actual native negative cases (missing dataset and malformed global flag)
  still map to Python InputError.
- Source identities/links, CLI contract, notebooks and unchanged embedded source
  payload: PASS. Final scope and ZIP integrity/source-preservation checks: PASS.
- Native source is byte-identical to round 14. Its tested Linux CLI binary was
  reused for the actual cross-interface checks. The 135-test native suite and
  native maxT/Huber exporters were not redundantly rerun for this Python/docs-only
  patch; their recorded evidence remains in the corresponding checkpoints.

The front-door validation summary now links current evidence and explicitly
corrects the retired loopback-test claim. Full variance/estimation/MELSM numerical
cross-interface parity is not claimed. No external CI, release, tag, commit,
publication, live notebook session or new full benchmark was performed.

The remaining scientific design choices are queued; safe independent release
packaging/gate consistency work can proceed without choosing a scientific claim.
