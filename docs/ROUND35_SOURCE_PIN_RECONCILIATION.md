# Round35: reviewed historical source-pin reconciliation

## Defect and bounded repair

The older Colab connection suite stopped at an obsolete expected source hash
(47/48 tests), and the UI source-contract suite reported 17 subtest failures
(18 tests). The protected source had evolved through already delivered stages,
while the historical revision mapping stopped updating. The Round34 embedded
source-archive packaging defect was separate and already repaired; it remains
fixed here without regenerating or changing that asset.

This stage changes only validation tooling, an explicit review manifest, CI and
reports. Production source, numerical code, README, assets and both old manifests
are byte-identical to Round34. No new statistical experiment or C# runtime claim
is made. Scientific NO-GO and actual Windows acceptance requirements are unchanged.

## Contract

`tools/source_pins.py` resolves all three layers before returning any expected hash:

1. `validation/ui-patch-baseline.json`: original 30 anchors, unchanged.
2. `validation/checkpoint-source-baseline.json`: prior reviewed revisions, unchanged.
3. `validation/source-pin-revisions-v2.json`: 17 explicitly reviewed Round35 revisions.

The new manifest binds the exact raw bytes of both older manifests. Every new
entry carries its original anchor, previous effective expected hash, literal
reviewed current hash, stage/evidence references and provenance limitation. The
helper never computes expected hashes from live production sources. Consumers
still compare actual source bytes with those expectations.

All manifests/entries are validated before resolving even an untouched file.
Unknown/noncanonical/control-character paths, duplicate JSON keys, malformed
hashes, missing overlays, incorrect caller/original anchors and broken prior
revision chains fail with explicit exceptions. Python `-O` cannot remove these
checks. Tests pin the original manifest bytes, exact 17 revision paths and exact 4
historical-gap labels, so adding allowances or relabeling uncertainty requires
an explicit test/review change as well.

## Provenance and its limits

13 entries have recovered byte/diff traces from the **effective legacy expected
hash** to current source. This does not reconstruct or newly certify the original
UI-to-checkpoint revisions already recorded in the older manifests.

Four files have a bounded independent review of current behavior and retained
stage/hash anchors, but incomplete older transitions:

- `Infrastructure/CliArguments.cs`: current hash recorded in Round13 results;
  exact current bytes retained in the Round21 source archive. Older transition missing.
- `MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj`: current explicit net8 CLI file list
  retained in Round21; exact introducing stage is unproven.
- `MvsAnalyzer.Cli/HeadlessRun.cs`: preserve the unexplained 608db779→679369121
  interval documented in Rounds 4/8. Later Round13 metadata, Round20 source,
  Round25 import-boundary and Round33 output-observation changes are retained.
- `MvsAnalyzer.Cli/ScientificCommands.cs`: Round13 metadata matches retained
  Round21 bytes, with exact later Round25/Round33 diffs; older transition missing.

Current acceptance of these four files does **not** retroactively explain or
approve missing history. The independent semantic review covered current CLI
argument validation, project compile wiring, captured import identity, output
observation and diagnostic/error semantics. It did not establish scientific
validity, transactional output, resistance to malicious local owners or full
historical authorship. Detailed per-file anchors/diff hashes are retained in
`validation/round35-evidence.zip`; concise reasons are in the new manifest.

## Executed checks and reproducibility

The existing static CI now explicitly requires Node (rather than silently
skipping its browser-JavaScript test) and runs:

```sh
node --version
python tools/test_source_pins.py
python tools/test_colab_connection.py
python tools/test_ui_patch.py
```

Executed locally: 24/24 focused contract tests,48/48 Colab connection tests,
18/18 UI source tests, without skips. These simulate/check source and helper
behavior; they are not a live Google session or WinForms runtime test.

Negative tests cover changed revised and untouched sources, missing production
files, malformed unrelated entries, duplicates in every manifest, missing layers,
wrong chains/anchors, unknown and noncanonical paths, malformed hashes and optimized
Python. The old failure is retained, rather than replaced by only passing logs.
The exact `tools/check_source.py` command also remains required on a fresh source
ZIP extraction before delivery.

## Rollback and future changes

Restore full Round34 if needed. This restores old validation behavior, including
its known obsolete-pin failures; user data and native results are unaffected.
Do not edit old anchors or auto-refresh all hashes from the current checkout.
A future reviewed source change needs an explicit versioned revision with reason,
evidence and corresponding tests. A checksum is an integrity comparison, not
independent scientific review; an owner able to edit code and manifests can alter
both. No external signature or complete-run logging guarantee is implied.
