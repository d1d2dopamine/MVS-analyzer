# Paper benchmark run

This workflow is for the benchmark used in the MVS methods manuscript. It runs the existing frozen benchmark protocol rather than defining a new one.

The fixed settings are:

- profile: `full`;
- seed: `20260904`;
- protocol: `MVS-BENCH-1.2.0`;
- expected application: `1.4.0`;
- expected scientific engine: `1.6.0`.

The workflow uses the portable checkpoint support already present in MVS. A GitHub-hosted job runs for about 5 hours 17 minutes, sends an interrupt, saves the latest completed computational units, and the next job resumes them. Up to six compute chunks are chained automatically. The statistical protocol, random seed, simulation budgets, thresholds, and decision rules are unchanged.

## Run it

1. Push these files to GitHub.
2. Open **Actions**.
3. Choose **MVS paper benchmark - full**.
4. Click **Run workflow**.
5. Leave it alone. The browser does not need to stay open.

When the run finishes, download the artifact named:

`mvs-paper-benchmark-full-seed-20260904`

The final job verifies the protocol version and hash, application/engine versions, seed, full profile, and output checksums. A scientific `no-go` result is accepted as a completed benchmark. It is not treated as a failed GitHub job.

If the final job says that six chunks were insufficient, keep `paper-benchmark-state-6`. It contains the latest portable checkpoint. Do not restart the benchmark from zero or change the seed. Add another resume chunk to the workflow or continue that checkpoint with `mvs resume`.

## What this does not do

The workflow does not split one simulation condition across different machines and then merge statistics. That would require a new distributed reduction layer and its own validation. This version uses MVS's existing checkpoint/resume path, so completed outer replications are reused exactly as the application already supports.

It also does not add real-data plasmodes. The paper benchmark described here is the frozen synthetic benchmark unless a real-data folder is deliberately supplied in a separate analysis.
