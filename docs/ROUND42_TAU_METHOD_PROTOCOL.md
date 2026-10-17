# Round42: benchmark Kendall tau-b correction and compatibility

## Scope fixed before candidate checks

This stage corrects a demonstrated benchmark diagnostic defect. It does not change
production metric scores, p-values, family correction, calibration settings or
scientific thresholds. Tau enters benchmark hypothesis C and can therefore change
C and the overall benchmark verdict on **new** runs. No historical result is
recomputed or upgraded, and no new scientific dataset or random stream is used.

The Round41 source is the rollback baseline. Its joint-tie example [1,1,2]
compared with itself returns 2/3 rather than 1; constants return 0 instead of an
undefined coefficient. Subtraction and product arithmetic also fail for finite
extreme/subnormal values. The retained Round41 negative-control evidence remains
unchanged.

## Corrected definition

Validate equal lengths, at least two observations and finite entries. Compare
values directly, treating signed zero as equal. Count concordant C, discordant D,
exclusive ties T_a and T_b. A pair tied in both vectors contributes to none of
these counts. Return (C-D)/sqrt((C+D+T_a)(C+D+T_b)); a zero denominator is undefined.
No subtraction/product of input values is required. Undefined coefficients remain
nonfinite internally and are exported as JSON null / empty numeric CSV fields
with an explicit diagnostic reason.

## Version and restore contract

The original MVS-BENCH-1.2.0 specification/hash remains immutable. A separate
pinned tau-method specification/hash forms a mandatory composite comparability
identity with that protocol. The protocol hash alone does not establish identical
benchmark arithmetic. Exported manifests, report text, rich stability rows,
journal and figures identify corrected versus unversioned legacy provenance.

Fresh requests explicitly record the corrected method. Nullable appended metadata
is omitted when null, preserving historical and non-benchmark request bytes and
hashes. An otherwise supported old request without method metadata resumes using
the exact preserved legacy implementation; completed cached results retain their
stored values, verdicts and overall status. Legacy provenance stays unversioned,
not independently established by the current executable.

Unknown or contradictory request/result/split method identities fail before
opening or publishing a checkpoint and before returning a cached final result.
Corrected requests may not adopt untagged cached stability values. Opening a
legacy checkpoint does not upgrade its arithmetic identity.

The existing aggregation policy is retained: nonfinite tau splits are excluded
from tau and top-one denominators and count as failed/undefined. The correction
can cause all-tied splits previously treated as finite to become undefined. All
requested, usable and failed counts must remain visible; this is not permission
to select splits or improve an old median by filtering it again.

## Acceptance and comparison

1. Independent exact pair-count fixtures, exhaustive bounded small-array checks,
   secondary SciPy tau-b cross-check: joint and exclusive ties, reversal,
   constants, signed zero, extreme finite values, subnormals and invalid inputs.
2. Old negative controls retained against the exact legacy helper.
3. Historical/non-benchmark request serialization and hash parity; old completed
   export without numerical reevaluation; corrected and legacy resume dispatch;
   encoded checkpoint roundtrip; missing/unknown/mixed identities reject without
   mutating stored units or creating a successful publication.
4. Manifest, Markdown, CSV, journal and figure source paths use the same method
   identity. Undefined output is explicit. Non-stability decisions and archived
   evidence hashes remain unchanged.
5. Native regression suite, relevant Python/static/Colab/pin/layout checks,
   official embedded-source regeneration, and checks from the fresh full ZIP.

This is a correctness comparison on identical fixed inputs, not a performance or
power benchmark. No speed claim, scientific GO, unseen validation or Windows
runtime claim follows from it. Historical tau cannot be corrected without the
unretained split score vectors.
