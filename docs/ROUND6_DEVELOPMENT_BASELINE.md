# Round 6: complete engine 1.6.2 development baseline

Date: 2026-10-11 UTC. Source ZIP: `MVS-analyzer-round5-huber-validation.zip`,
SHA-256 `ba95a9b5b9dfb6dccafdffb0b4140e09d343358e6f1a61d1b1c923247d881431`.

## Result

**The full benchmark completed. Its scientific verdict is NO-GO.** No settings,
thresholds, seeds or failed observations were changed to improve that verdict.
This stage archives evidence; it changes no production source or statistical method.

- Engine 1.6.2; application 1.4.0; formula MVS-1.4.0
- Frozen protocol MVS-BENCH-1.2.0, hash
  `b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268`
- Full profile; seed 20260904; eight workers; synthetic data only
- Primary 1,000; grid 250/condition; calibration 1,000; stability 120; replay 60/pass
- 5,490/5,490 work units completed; zero condition-replication or stability failures
- Start 20:12:14 UTC, command finish 21:12:40 UTC; native compute duration
  3,625 seconds, command wall time approximately 3,626 seconds
- .NET SDK 8.0.425/runtime 8.0.31, Linux X64

The result directory's generated date uses the machine's local clock and says
2026-10-12; the UTC manifest timestamps and dates above describe the same run.

## Main observations

| Quantity | Current result | Previous engine 1.6.0 |
| --- | ---: | ---: |
| Null false-positive rate, cherry-pick | 17.8% | 17.8% |
| Null false-positive rate, registry-corrected MVS | 1.8% | 1.8% |
| Location x1.05 power, registry-corrected MVS | 14.0% | 14.0% |
| Location x1.05 held-out oracle | 44.8% | 44.8% |
| Dispersion x1.30 power, registry-corrected MVS | 28.8% | 28.8% |
| Dispersion x1.30 held-out oracle | 53.6% | 53.6% |
| Median ranking Kendall tau | 0.714260 | 0.714260 |
| Top-1 stability agreement | 22.5% | 22.5% |

Frozen verdicts: A pass, B fail, C inconclusive, D pass, E pass. B's worst
power loss is 30.8 percentage points versus the held-out oracle; the declared
failure threshold is above 15 points. No scientific performance improvement is
claimed. The legacy report's “two-track” wording denotes its registry-corrected
comparator; its historical names/questions are preserved, not reinterpreted.

All six historical data/protocol files (summary, metrics, choices, stability,
verdicts and protocol text) are **byte-identical** to the engine-1.6.0 archive.
All nineteen condition decision digests also match. This is an observed result
for this fixed development protocol/seed, not proof that all inputs or boundary
cases behave identically between engine versions. Software metadata, dates,
duration and diagnostic artifacts appropriately differ.

The older run took 117 minutes on four threads. This run's eight-thread timing
is an operational observation, not a controlled claim of software speedup.

## Archived evidence

[Raw run and evidence](../benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0/)
contains all thirteen original generated files without modification, plus:

- `execution.json`: command, source ZIP hash, assembly hashes, timestamps and host
- `console.log`: actual native output, including the NO-GO result
- `diagnostic_verification.json`: independent per-replication reconciliation
- `verification.json`: identity, checksums, counts, rates, intervals and replay checks
- `historical_comparison.json`: explicit cross-version comparison
- `checkpoint.zip`: completed portable checkpoint archive
- `failed_attempt1.json`: preserved initial launcher-error evidence

The first attempt mistakenly supplied a descriptive `MVS_BACKUP_JOB` value where
the backup format requires an empty or hexadecimal identifier. It stopped during
pilot preparation with no committed outer replications. The corrected launcher
omitted that optional tag and reran the same scientific configuration. This was
an execution-configuration correction; no computed condition result was discarded.

Checkpoints were written by the existing engine throughout the run. The successful
run did not need resumption. The included completed checkpoint permits inspection
or re-export using the matching source; previous stage-native tests separately
cover resumed versus uninterrupted calculations.

## Checks actually performed

- Expected engine/formula/protocol, fixed hash, profile, seed, worker count and
  simulation budgets verified against the actual final manifest.
- All twelve `SHA256SUMS.txt` entries verified against their original bytes.
- 5,370 replication rows, 42,960 procedure rows, 64,440 metric rows and 120 split
  rows reconciled with the old aggregate reports. Missing diagnostics: zero.
- Requested/completed/failure counts, choices, raw/family decisions, unavailable
  semantics and stability positions verified by the independent round-4 checker.
- Conditional rates, standard errors, Wilson intervals, metric/choice rates and
  stability median/quartile/agreement independently recomputed in Python.
- Both replay passes completed without failures; all rich replication, procedure
  and metric diagnostics match exactly, beyond the legacy decision-only digest.
- Cross-version data/protocol byte equality and all nineteen digest equalities
  verified. The old archive was not rewritten.

Independent read-only review confirmed these checks separately, including all
152 summary rows. The completed checkpoint contains 5,495 cached entries:
four pilots, 5,370 replications, 120 splits and the final result. Both embedded
backup archives pass CRC/inner SHA checks. The current CLI decoded and validated
their identity/request hashes via a read-only missing-output probe; actual
resume/re-export of this completed run was not performed and is not claimed.

Source/CLI/notebook/method contracts and archive scope/integrity checks passed.
No C# or Python implementation changed in this stage; the preceding source's
97 native and 120 Python regression results remain the applicable software
checkpoint, rather than being represented as newly rerun tests. New work here
is the actual full native benchmark and independent artifact verification.
All 260 prior source files are retained, with old raw history unchanged.

Reproduce the computational run with the matching source and .NET 8:

```bash
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -o publish/cli
# Do not set MVS_DISABLE_BACKUPS=1; leave optional MVS_BACKUP_JOB unset.
MVS_BACKUP_DIR=/path/to/backups dotnet publish/cli/mvs.dll benchmark --profile full --seed 20260904 --threads 8 --out /path/to/results
python validation/check_benchmark_diagnostics.py /path/to/results/MVS_Benchmark_run
# In that original result folder:
sha256sum -c SHA256SUMS.txt
```

The native benchmark's exit code 2 is a completed scientific NO-GO. It must not
be swallowed or relabelled GO, but it is distinct from execution failure (exit 1).
The existing paper-specific verifier still pins historical engine 1.6.0; this
new engine-1.6.2 development run was checked explicitly against its own declared
identity rather than weakening that historical gate.

## Readiness and next gates

This closes the planned full development baseline. It does not close MVS 1.5 or
make the project scientifically release-ready. The demonstrated remaining power
and selection-stability gaps are retained as development targets.

A safe next checkpoint is an independently tested internal Holm vector comparator,
with Bonferroni still the default, all twelve hypotheses retained and unavailable
hypotheses unable to reject. For a fixed family, Holm and Bonferroni have the same
“at least one rejection” event; global-any power improvement is therefore not a
valid acceptance target for that arithmetic-only checkpoint.

Public/default method changes require explicit method/cache/persistence identity
and unchanged legacy parity. MaxT requires a frozen statistic/resampling/missingness
specification, defensible exchangeability/partial-null error-control conditions,
and independent validation. Family-level claims need declared null meanings and
cross-family multiplicity. Huber's two confirmed numerical defects still block
its activation. None of those dependent scientific gates is silently resolved here.
Final evaluation needs a separately frozen unseen MVS-BENCH-2.0. A passing software
suite and a completed development benchmark are not substitutes for that evidence.
