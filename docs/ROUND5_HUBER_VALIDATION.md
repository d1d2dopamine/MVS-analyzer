# Round 5: native Huber convergence reproduction (R1-08)

Date: 2026-10-11. Starting source is the round-4 diagnostic ZIP, SHA-256
`0e5a26d07eb703e0032d7c79f8854415aacbd6700ce42df6309be072484553c6`.

## Acceptance and result

The plan's R1-08 acceptance criterion was to reproduce scale-dependent Huber
convergence in C# before activation. **Reproduction is complete; Huber numerical
accuracy is not validated and the implementation is not repaired in this stage.**
Two numerical defects are confirmed. The metric must stay staged until a scoped
repair passes these independent checks and the later activation criteria.

There are no production-method changes. Engine 1.6.2, application 1.4.0,
MVS-1.4.0 formula, MVS-BENCH-1.2.0, the active twelve metrics, calibration states,
Bonferroni and the four staged/active flags remain unchanged. No version bump is
needed for this validation-only checkpoint. No prior evidence was overwritten.

## Independent definition and precision budget

For finite binary64 input values, calculate sample median m and sample MAD;
s = 1.482602218505602 * MAD. For s > 0, solve

    sum clip((x_i - mu) / s, -1.345, 1.345) = 0.

If MAD is exactly zero, the reference returns m according to the project's
explicit fallback policy. That policy is not a claim that zero-scale Huber
inference is defined. Decimal80 arithmetic interprets each binary64 input exactly;
the solver uses monotone clipped-score bisection in coordinates centered at m and
scaled by s, not the production iteratively reweighted averaging algorithm.
Two asymmetric fixtures also have independently derived piecewise-linear roots.

The declared numerical acceptance tolerance is

    max(1e-10 * s, 4 * ulp(reference rounded to binary64)).

The second term allows final binary64 representation error under large translations;
it is not permission to accept a visibly different estimate. Translation examples
use exactly representable integer inputs. These are deterministic numerical
checks, not estimates of power, coverage or inferential validity.

## Reproduced defects

### H5-01: stopping tolerance depends on absolute units and offset

For x = [0, 1, 2, 7, 30], MAD=2 and s=2.965204437011204. Only the final observation
is clipped at the root, so the independent analytic result is
(10 + 1.345*s)/4 = 3.497049991945017345.

The native unscaled result agrees within the declared tolerance. For x*1e-13,
normalizing the native output back by 1e-13 gives 3.2630214000987954 instead of
3.497049991945017. The error is about 0.078925 fixed-MAD scale units.

Cause: the production convergence tolerance is
`1e-12 * max(1, abs(mu), scale)`. The absolute floor permits premature stopping for
small units; a large location offset similarly inflates the tolerance. Positive
rescaling or translation can therefore change the normalized numerical answer.

### H5-02: positive robust scale misclassified as zero

For x+3e12 the inputs remain exactly represented. The native output is
3000000000002, the sample median, instead of approximately
3000000000003.49705. Error ≈1.49705; allowed error is 0.001953125.
Replacing only the outlier 30 by 1e13 causes the same fallback despite MAD=2.

Cause: Huber reuses the relative-metric denominator threshold
`max(abs(x))*1e-12` to decide whether its MAD scale is zero. That threshold changes
with a common offset and with arbitrarily large outliers, although MAD does not.
This contradicts the fixed-MAD equation for these nonzero-scale cases.

### Unconfirmed limit

The production routine returns its current iterate after 100 iterations without
an explicit convergence status. This remains a review risk; this checkpoint does
not claim to have reproduced a separate iteration-limit failure.

## Deliverables and reproducibility

- `validation/huber-fixtures-v1.json`: 20 fixed cases, declared definition and tolerance
- `validation/huber-native-baseline-v1.json`: actual native results from this source,
  fixture SHA-256, Core assembly SHA-256, runtime and staged-family metadata
- `MvsAnalyzer.Core.Tests/HuberDiagnosticChecks.cs`: invokes the actual Core metric
- `validation/huber_reference.py`: independent reference/comparison tool
- `validation/test_huber_reference.py`: 12 reference/tool regression tests

Run native export and the accuracy comparison:

```bash
dotnet run --project MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj -c Release -- --export-huber-diagnostics validation/huber-fixtures-v1.json /tmp/huber-native.json
python validation/huber_reference.py --native /tmp/huber-native.json --out /tmp/huber-comparison.json
```

The exporter completing successfully means the native values were collected.
**The accuracy checker currently returns exit 1: 9 of 20 cases fail, 11 pass.**
Exit 0 would mean all numerical cases passed; exit 2 means invalid data/provenance.
Do not suppress or relabel exit 1 as successful Huber validation. The default
unit suite can pass because it tests the diagnostic machinery and correctly
recognizes failures in the immutable recorded evidence, not because Huber is fixed.
Future repair must run the checker against a new native export rather than
replacing this historical baseline or loosening the tolerance.

## Fixed-grid result

| Case | Native result | Reference | Accuracy |
| --- | ---: | ---: | --- |
| scale_1e-14 | 3.2630214000987958e-14 | 3.4970499919450176e-14 | FAIL |
| scale_1e-13 | 3.2630214000987954e-13 | 3.4970499919450175e-13 | FAIL |
| scale_1e-10 | 3.4967450450003627e-10 | 3.4970499919450174e-10 | FAIL |
| scale_1e-06 | 3.4970499774114569e-06 | 3.4970499919450172e-06 | FAIL |
| scale_1.0 | 3.4970499919449924 | 3.4970499919450173 | pass |
| scale_1000000.0 | 3497049.991944992 | 3497049.9919450171 | pass |
| scale_1000000000000.0 | 3497049991944.9917 | 3497049991945.0176 | pass |
| shift_10000.0 | 10003.497049991925 | 10003.497049991945 | pass |
| shift_1000000000.0 | 1000000003.497039 | 1000000003.49705 | FAIL |
| shift_1000000000000.0 | 1000000000003.4886 | 1000000000003.4971 | FAIL |
| shift_3000000000000.0 | 3000000000002 | 3000000000003.4971 | FAIL |
| shift_-3000000000000.0 | -2999999999998 | -2999999999996.5029 | FAIL |
| extreme_positive_outlier | 2 | 3.4970499919450173 | FAIL |
| negative_reflection | -3.4970499919449924 | -3.4970499919450173 | pass |
| symmetric | 0 | 0 | pass |
| constant | 4 | 4 | pass |
| zero_mad_contamination | 1 | 1 | pass |
| two_values | 2 | 2 | pass |
| even_asymmetric | 2.5982299951670056 | 2.5982299951670105 | pass |
| permuted | 3.4970499919449924 | 3.4970499919450173 | pass |

## Checkpoint verification

- Native default regression suite: 97/97 passed; native export completed all 20
  cases and exactly reproduced the frozen output including assembly metadata.
- Huber numerical accuracy check: **FAIL, 9/20 cases**, exit 1; eleven controls
  pass. This failure is the finding, not a suppressed test or a repaired method.
- CI-style Python tests: 120/120 passed (72 validation, 4 wrapper, 17 backups,
  6 source, 21 round-2 checks); the supplied guard's own 30 tests also passed.
- Source, CLI contract, notebook/payload, 74-file C# structure, independent
  numerical identities and 53 frozen rank cases passed. Release CLI publication
  succeeded. This stage does not claim a new full benchmark.
- Broader archived UI/connection suites still fail their one pre-existing
  `HeadlessRun.cs` source pin each, as documented in round 4. The file is unchanged.
- Read-only independent review confirmed reference independence, precision-aware
  tolerance, exact native provenance and unchanged scientific scope.
- Final scope guard: PASS; three modified files, six added, no deletion or
  out-of-scope changes. Source ZIP keeps all 254 previous files plus six additions.
  Core, Benchmark, CLI, embedded payload, historical reports, existing scientific
  fixtures and hashes are byte-identical to round 4. Archive integrity verified.

## Next steps and boundaries

The complete MVS-BENCH-1.2.0 development baseline may proceed: Huber is absent
from its active twelve-metric registry, so these staged defects cannot affect
that run. Full benchmark results, including null/negative results and failures,
must be retained without changing settings to obtain a favorable outcome.

Before Huber activation, separately repair its convergence/zero-scale handling,
prove appropriate scale/translation behavior and independent root accuracy,
handle nonconvergence explicitly, and assess implementation identity/version
implications. Do not change the shared denominator policy of other metrics as
incidental cleanup. Holm/maxT and family-level inference retain their separate
acceptance gates. This source ZIP is not a release or a statistical certification.
