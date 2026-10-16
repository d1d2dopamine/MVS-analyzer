# Round28: independent reconstruction of existing primary-null assignments

## Result and preserved decision

All **200/200** existing primary-null cases passed independent reconstruction:
199,800 original label assignments, all label-stream SHA256 digests, observed exact
rank scores, twelve marginal and max-adjusted tail counts, global counts,
p-values and decisions agreed. There were zero missing or mismatching cases.
The original 19 rejections and181 nonrejections are unchanged.

This does not turn Round27's inconclusive null screen into a pass. It rules out
a reproduced disagreement in the independently checked PRNG/shuffle/rank/tail path
for these inputs; it does not establish population error control, exclude every
implementation defect or prove the19/200 outcome was just chance. No new data,
seeds, extra label draws or reserved evaluation cases were generated.

## Why this check was needed

Round27 increased development power but primary heavy-tail null rejection was
19/200, with Wilson95% interval6.17–14.36%, failing the frozen eligibility screen.
Independent source review found no obvious exchangeability violation: both groups
used the same laws/floor and all200 datasets retained16+16 entities with40
measurements each. The remaining bounded implementation question was whether the
actual sampled label stream and exact tails matched an independent implementation.

## Independent implementation

`validation/replay_primary_rank_draws.py` uses Python standard library only. It
reimplements SplitMix64/xoshiro256**, uint64 wraparound, rejection-unbiased bounded
sampling and fresh-identity Fisher–Yates. It does not call native code or the data
generator. Midranks come from direct below/equal counts rather than the native
sort-and-tie-block implementation. Exact integer cross-products determine inclusive
tails, including rational ties. It checks saved matrices, identities, coordinate
seeds and binary/source provenance against the original pinned run/checkpoint.

The frozen plan is `validation/round28-diagnostic-plan.json`, SHA256
`0de2f785f341f15a8de9bb7caebccf1d9eed9f0df3dd81d07113c2cf30cf1118`.
It pins report/run/checkpoint and all200 original JSON hashes. All200 cases are
included, not only the19 rejected cases. Final program/test hashes were recorded
before full reconstruction. An initial10-test log is retained; final source has12
synthetic tests, also independently rerun successfully. Additional tests were
completed before execution; no implementation change followed observed results.

## Execution and limits

Linux Python3.12.14, one process, CPU affinity0–1, 600-second wall bound,
1GiB address-space limit. Actual elapsed16.1629seconds, maximum process RSS14,336KiB
(14MiB). This is diagnostic replay cost, not production inference performance.
All200 per-case reconstruction/comparison records and the full denominator are
retained. A mismatch would stop with the reconstructed values and explicit
failed/not-started lists; none occurred. The Linux resource controls are not a
claim of Windows support for this optional diagnostic.

## Reproduction and rollback

Extract `validation/round27-evidence.zip` to an external directory so its
`mvs-r27-development` folder contains the original saved case files. From source:

```
python validation/replay_primary_rank_draws.py \
  --inputs /absolute/path/mvs-r27-development \
  --plan validation/round28-diagnostic-plan.json \
  --plan-sha256 0de2f785f341f15a8de9bb7caebccf1d9eed9f0df3dd81d07113c2cf30cf1118 \
  --out /absolute/fresh/output-directory
```

The script requires Linux resource/affinity APIs and the CPU0–1 permitted set.
Do not silently relax a failed environment constraint. The source used by the
original experiment must match recorded hashes. Output is fresh and external;
original input evidence is never rewritten. Tests:
`python -m unittest discover -s validation -p test_replay_primary_rank_draws.py -v`.

This cumulative25+26+27+28 PATCH preserves README files and production source.
Round27 is the rollback checkpoint. The diagnostic adds no production dependency,
public API or statistical activation. Existing Windows repair acceptance remains
pending real owner-run checks. The next useful work is an independently scoped
architecture boundary improvement; no additional statistical sample is authorized
by this successful reconstruction.

Final regression suite: all282 validation tests passed, including the12 new
synthetic checks. The broader524-test Python suite was passed in Round27
(510pass/14Windows-only skips) and was not repeated here. Independent terminal
review verified every output/input pair and all bound hashes with zero mismatch.
