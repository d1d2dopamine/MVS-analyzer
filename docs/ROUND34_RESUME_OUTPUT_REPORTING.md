# Round34: resumed-run partial output evidence

## Scope and preserved behavior

This stage extends the Round33 per-file error evidence to the nonbenchmark
branches of CLI `resume`: restored calibration, analysis, variance, estimation
and MELSM. The legacy `BackupRunner.Run` signature, including its optional
`russian` argument, remains the entrypoint for existing callers. A separate
internal observer entrypoint is used by CLI resume; it does not depend on CLI
classes and does not install a global factory or observer.

Observation starts immediately before the first output-file writer. Validation,
restore acquisition, directory creation, arithmetic and checkpoint publication
remain at their existing positions. State writes are recorded before the
unchanged state reread. Resume provenance still captures the original saved
UTC and retained-unit count before computation. The supplied document may be
mutated by normal checkpoint restoration, just as before; original input archive
bytes must be checked independently in tests.

Benchmark resume is deliberately excluded. Its writer tree, provenance update
and checksum refresh remain unchanged and unobserved. The archived desktop uses
the original observer-free entrypoint. No cancellation checks, retries, catches,
rollback, file cleanup, statistical calculations, cached-result rules or
arithmetic-environment history rules are added by this stage.

## Failure evidence

CLI resume uses the existing Round33 `partialOutput` contract. Only successfully
observed current-invocation writes that still verify are advertised. An attempted
failed target is uncertain, never a successful artifact. Old or injected files
are not adopted. An export failure remains exit 1/error and does not certify a
completed run. A backup identifier is not substituted for an unknown run ID.

This is point-in-time evidence, not multi-file transactionality or protection
against concurrent filesystem mutation. The existing restore scope must unwind
normally on write/observer failure so a later explicit restore is possible.

## Test and comparison interpretation

Genuine restore tests require backups enabled in an isolated directory. Setting
`MVS_DISABLE_BACKUPS=1` bypasses the pending restore before cached units are
consumed and would not test the intended lifecycle. Fresh decoded checkpoint
copies are used for independent invocations.

The comparison plan distinguishes an actually unfinished calibration checkpoint
from completed-result engineering checkpoints used to compare export behavior.
Completed-result cache replay does not constitute fresh numerical validation.
All original checkpoint hashes, failures and raw outcomes are retained.

The new measurement driver uses blocking child wait with an independent bounded
watchdog. Wall elapsed time is captured at wait return, before joining the
watchdog; output files are opened before the timer begins. This avoids the
previous driver's 50 ms exit-observation polling bias. Historical Round31/33
measurements remain unchanged and are not reinterpreted or replaced.

Executed counts, limitations and comparison results belong in the final Russian
report and `validation/round34-results.json`. Scientific NO-GO and the pending
actual Windows acceptance gate remain separate from this reliability change.

## Re-running the committed regressions

From a source checkout with .NET8 and Python3.12:

```sh
dotnet build MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release
dotnet run --project validation/resume_output_harness/ResumeOutputHarness.csproj -c Release -- --candidate "$PWD/MvsAnalyzer.Cli/bin/Release/net8.0/mvs.dll" --out "$PWD/artifacts/resume-output"
MVS_RESUME_OUTPUT_RESULTS="$PWD/artifacts/resume-output/report.json" python -m unittest discover -s validation -p 'test_resume_output_contract.py' -v
```

The output directory must be new. The bundled synthetic fixture ZIP is required
and copied beside the harness at build time. Candidate-only execution deliberately
omits the historical old-binary counterexample; its evidence validator reports
one baseline-only skip. Supplied missing/bad reports fail rather than skip. The
ordinary CLI CI runs this candidate path. No external evidence download is needed.

The comparison driver is a separate Linux engineering tool. Its archived plan
binds this measured environment's absolute paths; a new environment needs its own
pre-run plan, fixture identities and explicit `freeze --dotnet ...` host selection.
Use `--root` for the corresponding evidence directory, then `verify` to check
retained outcomes without launching native code. Never edit a frozen binding to
make modified results pass. The historical measured evidence remains immutable.
