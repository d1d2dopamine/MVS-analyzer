# Reproducibility and audit

MVS Analyzer treats a result as a claim, and a claim needs evidence that it was not quietly edited afterwards. Implementation: `RunAuditor.cs`.

- [What is hashed](#what-is-hashed)
- [The run journal](#the-run-journal)
- [Running an audit](#running-an-audit)
- [Audit codes](#audit-codes)
- [What hashing cannot prove](#what-hashing-cannot-prove)
- [Recommended workflow](#recommended-workflow)

---

## What is hashed

| Object | Where the hash lives |
|---|---|
| the **input dataset** | `run_manifest.json` → `inputData.sha256` |
| every **output file** in the run folder | `run_manifest.json` → `files[].sha256` |
| the **formula specification** | `run_manifest.json` → `formula.hash` |
| every installed **plugin package** | `package.sha256`, echoed into `plugins[]` |
| every **run**, chained | `%LocalAppData%\MVS_Analyzer\run_journal.jsonl` |

All SHA-256. Since 1.3.2, plugin text reports are written before the manifest, so they are inside `files[]` too.

---

## The run journal

`run_journal.jsonl` is append-only. One JSON object per line, and each line carries the SHA-256 of the **previous** line:

```jsonc
{ "runId": "...", "createdUtc": "...", "folder": "...", "inputSha256": "...",
  "formulaHash": "...", "engineVersion": "1.2.0", "candidateSet": ["median"],
  "prevHash": "3f0c..." }
```

Consequences, all intentional:

- deleting a line breaks every hash after it → `JOURNAL_BROKEN`;
- deleting a *run folder* while the journal remembers it → `RUN_HIDDEN`;
- running the same dataset repeatedly until a nice candidate set appears is visible as `CANDIDATE_SET_UNSTABLE`, because every attempt is in the journal.

The journal is local and per-machine. It is a record of what *this installation* did.

---

## Running an audit

**Audit** in the sidebar (`Ctrl`+`9`) → choose a folder → it walks the tree recursively and, for each run it finds:

1. re-reads `run_manifest.json`;
2. recomputes the SHA-256 of every listed file and compares;
3. compares `formula.hash` with the formula compiled into the running build;
4. compares `engineVersion`;
5. checks the input hash is present;
6. cross-checks the journal for hidden runs and chain integrity;
7. compares settings and candidate sets across runs on the same input hash.

The result is a table of findings with one code per problem, and a plain-language explanation for each.

---

## Audit codes

### `FILE_MODIFIED`

A file listed in the manifest no longer matches its hash. Somebody opened `results.csv` in Excel and saved it, or edited a number. **The run is no longer trustworthy** — re-run it.

### `FILE_MISSING`

A file listed in the manifest is gone. Often innocent (someone moved figures), sometimes not. The remaining files still verify individually.

### `FORMULA_CHANGED`

The manifest's `formula.hash` differs from the current build's. The numbers were produced by a different definition of the MVS Score. This is expected after upgrading across a formula version — for example `MVS-1.1.0` → `MVS-1.2.0` — and it is the reason the hash exists. **Do not compare those runs with new ones; repeat them.**

### `NO_INPUT_HASH`

A legacy run that predates input hashing. The outputs verify, but nothing ties them to a dataset. Re-run if the result matters.

### `ENGINE_DIFFERS`

Same formula string, different `engineVersion`. The computation may still have changed. Check [CHANGELOG.md](../CHANGELOG.md) for what moved between the two versions.

### `ORPHAN_RESULTS`

`results.csv` without a `run_manifest.json`. There is nothing to verify against — the numbers could come from anywhere. Treat as unverified.

### `SETTINGS_VARIED`

Several runs over the same input hash used different seeds, scenarios or effect multipliers. Legitimate during exploration; a red flag when only one of them is being reported. The audit lists the settings side by side so a reader can see the spread.

### `CANDIDATE_SET_UNSTABLE`

The same dataset produced different candidate sets across runs. Usually means the metrics sit near the thresholds and the dataset is not decisive. Report the instability rather than the run you liked.

### `RUN_HIDDEN`

The journal contains a run whose folder is no longer present. Deleting outputs is allowed; hiding them from a reader is what this code exists to prevent.

### `JOURNAL_BROKEN`

The hash chain does not verify: a line was edited, removed, or reordered. Everything before the break is still verifiable; everything after it is not.

---

## What hashing cannot prove

> [!IMPORTANT]
> **Integrity is not honesty.**

The audit catches edits, deletions and hidden runs **on this machine**. It cannot catch:

- somebody who starts from a clean installation on another computer and reports only the run they preferred;
- a dataset that was filtered before it ever reached the app;
- a well-formed run with a badly chosen equivalence margin;
- an import profile that mapped the wrong column, producing a perfectly verifiable answer to the wrong question.

The app states this in its own Help section rather than implying stronger guarantees. What the hashes give you is a *cheap, offline, verifiable* record — not proof of good faith.

---

## Recommended workflow

1. **Archive the input file** next to the run folder. `inputData.sha256` is only useful while the file exists.
2. **Do not open exports in Excel and save.** Copy the file first if you need to play with it.
3. **Audit before you publish**, ideally from a second machine, so the check is independent of the journal being audited.
4. **Quote `formula.hash` and `engineVersion`** in the methods section — those two strings let a reader reproduce the definition exactly.
5. **Report the instability**, not just the run: if `CANDIDATE_SET_UNSTABLE` appears, that is a finding about your data worth a sentence in the paper.
