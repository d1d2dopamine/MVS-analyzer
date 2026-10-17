# MVS development status after the Round40 checkpoint

This reconciles the older V1_5_PLAN with completed work; it does not silently
replace its scientific release criteria.

## Closed engineering or bounded mathematical milestones

- Registry metadata and staged metric implementations; observed availability separated
  from calibration; per-replication benchmark diagnostics; staged Huber numerical repair.
- Full engine1.6.2 development baseline:5,490 units, zero execution failures,
  scientific NO-GO retained.
- Internal Holm and maxT arithmetic and independent reference checks. Neither
  arithmetic implementation alone establishes a deployable inferential procedure.
- Exact input snapshot provenance for active headless paths; run-recording seam;
  same-scope restore repair and conservative optimizer-cache environment handling.
- Partial/current-run export provenance through direct and resumed benchmark paths;
  source/payload/pin checks and recoverable root-layout migration.
- Actual owner Windows Server2022/2025 acceptance at commit
  b60824dc618b6f8cb5e1b14becadb6ef5acdafe4:193 native checks and21 Win32 checks per
  runner, zero skips, native/exploratory/frozen/MCP evidence. Uploaded archive hashes
  matched public Actions artifact digests; saved output parity was independently
  checked. This closes the earlier CI runtime gate for that version.
- Round40 improves failure diagnostics; its later diagnostic workflow edits still
  require their own CI run. Personal Windows11 smoke remains separate and does
  not block independent scientific development.

## Retained negative or inconclusive findings

- Baseline power14.0%/28.8% versus held-out diagnostic oracle44.8%/53.6%;
  top-one agreement22.5%. These are development observations, not universal targets.
- R27 global max-rank candidate has better observed power but failed its frozen
  primary-null screening gate. R28 verified the same saved calculations; this did
  not repair the scientific gate. No activation or extra samples to rescue it.
- R32 direct Math.NET tail substitution failed its frozen acceptance conditions.
  This does not mean mature libraries are generally inferior; no production
  replacement was made.

## Active scientific sequence

1. Round41: explain retained power/selection behaviour using fixed family scopes,
   absolute versus relative spread, and honest agreement/coarsening diagnostics.
   Build a test-only comparable implementation, retain every condition and baseline.
2. Act on a concrete numerical/measurement defect if the diagnosis independently
   reproduces one; preserve old evidence and version any changed scientific meaning.
3. Assess further candidate procedures only against an explicit question, null,
   family and evidence budget. Focused selection must precede new analysis data.
   A family descriptor is not isolated-component identification.
4. Candidate-set stability requires paired calibration evidence that the old120
   splits did not retain. Any replay needs its own frozen purpose and budget;
   changing the reported statistic is not a substitute.
5. Only after a method/claim is fixed may an untouched BENCH-2.0 validation protocol
   be frozen. Existing development data cannot certify release readiness.

Full ZIPs are checkpoints, not automatic project completion. Continue useful
authorized work until a concrete scientific/owner decision, unavailable evidence,
or execution limit blocks it; do not manufacture activity or rerun failed
experiments with friendlier seeds or thresholds.
