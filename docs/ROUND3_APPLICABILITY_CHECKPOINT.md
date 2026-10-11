# Round 3: observed testability and metric diagnostics

Date: 2026-10-11. Starting source: `MVS-analyzer-round2-fixed.zip`, SHA-256
`32720016646b5826fbd5fd5a7d56e0b514cf5796529d198e866cdf256f3b4ffa`.
The owner reported that the preceding 1.6.1 GitHub build passed. This report does
not reinterpret that result as verification of the subsequent changes.

## Before and after

Before: `Results` required both `CalibrationRow.Applicable` and four finite
observed entity summaries per group. Complete or excessive simulation failure
could therefore suppress an otherwise testable observed contrast. The benchmark
registry-corrected shipped comparator had the same coupling.

After: observed tests depend on observed finite entity summaries alone. Calibration
availability, power and FPR remain diagnostics and recommendation inputs. A compatible
calibration file is still required by the CLI; calibration-free analysis is deferred.

For example, eight positive entities in each of two separated groups remain testable
even when all 100 calibration simulations fail after missingness drops all values.
The observed p-value and full-family adjustment remain available; calibration rates
remain null, all 100 failures remain recorded, and no candidate is fabricated.

## Scientific contract

- Independent unit: retained entity, with repeated observations used only to compute
  its summary. Metric-specific exclusions never turn measurement rows into entities.
- Observed eligibility: at least four finite metric values in every group. A nonfinite
  rank-test result remains unavailable rather than producing an effect/verdict.
- Null: equal entity-summary distributions across independent groups for each metric.
  The tests do not isolate a pure mean, variance or latent component difference.
- Tests: two-sided asymptotic Mann-Whitney with ties/continuity correction for two
  groups; asymptotic tie-corrected Kruskal-Wallis for three to ten; all ties give p=1.
- Decisions: fixed twelve-metric Bonferroni family, adjusted p=min(1,12p), difference
  when adjusted p<alpha. Unavailable metrics remain in the family and cannot reject.
- Calibration arithmetic, the legacy candidate gate, score formula MVS-1.4.0/hash,
  seeds, effect/equivalence intervals and all four staged metrics are unchanged.
- Existing approximate two-group equivalence concerns the declared Cliff's delta
  margin; it is not equality of distributions, spread or all effects. Multi-group
  selected-pair intervals remain descriptive. Non-rejection remains insufficient.

The null FPR allowance max(1.5 alpha/12, alpha/12+0.02) is a legacy diagnostic
heuristic, not a confirmatory significance threshold or proof of FWER. The 0.70
power bound and marginal Wilson-interval overlap recommendation rule are heuristics.
Finite-simulation intervals do not capture uncertainty in the empirical generator.

## Delivered changes

- R1-04: observed availability separated from calibration in Core and in the shipped
  benchmark comparator. Single-metric legacy gated comparators retain their gates.
- R1-06: result JSON adds `ObservedStatus`, `CalibrationApplicable`, `GroupAvailability`;
  result CSV appends two status columns; new `metric_availability.csv` exports every
  metric/group's retained, usable and excluded entity counts and exclusion reasons.
- Registry requirement checks now return explicit reasons without changing metric
  formulas or applicability requirements. Nonfinite computed summaries have a fallback
  reason even when their measurement requirements hold.
- Native regressions cover simulation failures, entity exclusions, exactly four usable
  entities, constant inputs, full-family adjustment, unchanged observed random streams,
  null handling, serialization and spreadsheet-safe CSV text.
- Artifact checks reconcile JSON/CSV counts, exclusions, statuses and adjustment;
  CLI/Python parity also compares the availability table exactly.
- Required embedded portable CLI source and generated Colab notebooks are rebuilt
  from the same source; the supplied safe-development skill is retained unchanged.

Counts refer to entities retained after input processing. They do not include entities
already removed during import. Exclusion reasons count one reason per excluded entity;
they describe failed metric requirements or nonfinite summaries, not causal diagnoses.

## Compatibility

Scientific engine advances from 1.6.1 to 1.6.2 to identify changed test eligibility.
Application 1.4.0, state/result/manifest schema 2, machine response v1, formula identity
and benchmark protocol MVS-BENCH-1.2.0 remain unchanged. Result additions are additive;
the changed meaning of `Applicable` is distinguished by engine identity.
Calibration-row serialization is unchanged. Existing strict state/backup identity
checks reject earlier engines; recompute old calibrations. `--force` cannot bypass this.

Only source byte pins for the five changed previously pinned scientific files are
revised, with original and pre-round-3 hashes retained. This records the authorized
behavior/export change; numerical reference fixtures, gates and protocol pins are
not relaxed. The pre-existing unrelated stale `HeadlessRun.cs` pin is not revised.

## Verification

Passed locally: all eleven independent/static stages in the existing validation
runner, including 86 Python regression tests (38 validation, 4 fake-process Python
wrapper, 21 parity/artifact/runner, 17 backup, 6 source tests), frozen SciPy rank
references, source/method contracts, C# structural checks, notebook/payload consistency
and independent mathematical identities. The runner returns 2/incomplete for this
Python-only run, rather than claiming native verification.

The official .NET 8 SDK 8.0.425 and runtime 8.0.31 were downloaded into a separate
scratch directory. The executable cannot initialize CoreCLR in this environment:
`Failed to create CoreCLR, HRESULT: 0x8007000E` (exit 137). The actual native test
command was attempted and failed before compilation/test execution. Thus C# build,
the four new native regressions, real CLI/Python parity and benchmark execution
remain unverified locally; the existing GitHub workflow runs the native/CLI checks.
The expected native suite now contains 92 checks, including the four new cases.

Additional legacy offline suites: UI checks 17/18, connection checks 47/48. Both
retain the same pre-existing stale `MvsAnalyzer.Cli/HeadlessRun.cs` source pin.
That file is unchanged from the starting archive; the stale pin is documented,
not weakened to turn unrelated historical checks green. The new source-pin entries
for Models/OutputExporter replace their earlier stale pins only because those files
are deliberately changed in this round, with the preceding bytes retained explicitly.

The scope guard passed against the pre-edit snapshot: 28 modified files, 3 added,
no deletions or out-of-scope changes. Source packaging checks verify ZIP integrity,
complete retention of original sources, and unchanged rank fixtures, numeric gates,
formula/protocol identity, historical benchmarks, previous round reports and skill.
These checks do not establish runtime validity or scientific performance.

No new power, FWER, interval-coverage or release-readiness claim is made.

## Deferred work

R1-07 per-replication benchmark diagnostics and R1-08 Huber convergence validation
remain separate tasks, as do Holm/maxT, staged metric activation and family-level
automatic inference. A short technical benchmark follows successful new native CI;
a full development baseline follows completion of benchmark diagnostics. Final
1.5 validation requires a separately frozen MVS-BENCH-2.0 protocol.

This delivery is a source ZIP for review/commit, not a compiled release.

## Краткое пояснение

Теперь возможность сравнить группы определяется пригодностью исходных данных
для конкретной метрики. Неудачная калибровка не отключает доступную проверку,
но её недоступные оценки не заменяются числами и не создают рекомендации.
Новая таблица показывает, сколько независимых объектов реально участвовало
и почему отдельные объекты не подошли для метрики. Повторные измерения
не считаются дополнительными независимыми объектами.

Перед использованием нового снимка пересчитайте калибровку движком 1.6.2.
После копирования архива в репозиторий GitHub CI должен проверить 92 нативных
регрессии и настоящий CLI/Python. Следующий рабочий блок — подробная диагностика
каждого повтора бенчмарка; затем можно запускать полный развивающий прогон.
Улучшение чувствительности пока не доказано новым бенчмарком.
