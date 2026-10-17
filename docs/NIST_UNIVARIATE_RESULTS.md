# NIST Univariate Numerical Results: MVS-NUM-NIST-UNIVARIATE-1.0.0

Fixed Linux/.NET8.0.31 build, unchanged MVS production implementation. All nine original NIST datasets and18 requested mean/sample-SD comparisons completed. Primary contract: exact rational relative error≤10^−10 against the published certified decimal. No tolerance was revised after outcomes.

**Outcome:16/18 numerical rows pass;2 fail.** All9 means pass. SampleSD fails for NumAcc3 and NumAcc4. This is a failure of the predeclared decimal-reference numerical target, not a scientific false-positive or power measurement.

| Dataset | Difficulty | n | Operation | Certified value | Native value | Relative error | Primary gate |
|---|---|---:|---|---:|---:|---:|---|
| PiDigits | Lower | 5000 | mean | 4.53480000000000 | 4.5348 | 6.173455E-17 | PASS |
| PiDigits | Lower | 5000 | standardDeviation | 2.86733906028871 | 2.8673390602887063 | 1.279358E-15 | PASS |
| Lottery | Lower | 218 | mean | 518.958715596330 | 518.9587155963303 | 5.926528E-16 | PASS |
| Lottery | Lower | 218 | standardDeviation | 291.699727470969 | 291.69972747096904 | 1.279154E-16 | PASS |
| Lew | Lower | 200 | mean | -177.435000000000 | -177.435 | 1.281448E-17 | PASS |
| Lew | Lower | 200 | standardDeviation | 277.332168044316 | 277.3321680443162 | 6.373119E-16 | PASS |
| Mavro | Lower | 50 | mean | 2.00185600000000 | 2.001856 | 3.986708E-17 | PASS |
| Mavro | Lower | 50 | standardDeviation | 0.000429123454003053 | 0.0004291234540030854 | 7.550699E-14 | PASS |
| Michelso | Lower | 100 | mean | 299.852400000000 | 299.85239999999993 | 2.271823E-16 | PASS |
| Michelso | Lower | 100 | standardDeviation | 0.0790105478190518 | 0.07901054781905065 | 1.459088E-14 | PASS |
| NumAcc1 | Lower | 3 | mean | 10000002 | 10000002 | 0.000000E+6 | PASS |
| NumAcc1 | Lower | 3 | standardDeviation | 1 | 1 | 0.000000E+6 | PASS |
| NumAcc2 | Average | 1001 | mean | 1.2 | 1.1999999999999889 | 9.288866E-15 | PASS |
| NumAcc2 | Average | 1001 | standardDeviation | 0.1 | 0.10000000000000026 | 2.553513E-15 | PASS |
| NumAcc3 | Average | 1001 | mean | 1000000.2 | 1000000.1999999994 | 6.286426E-16 | PASS |
| NumAcc3 | Average | 1001 | standardDeviation | 0.1 | 0.10000000003492503 | 3.492503E-10 | FAIL |
| NumAcc4 | Higher | 1001 | mean | 10000000.2 | 10000000.200000098 | 9.797513E-15 | PASS |
| NumAcc4 | Higher | 1001 | standardDeviation | 0.1 | 0.10000000055884095 | 5.588410E-9 | FAIL |

## Conditioning and error decomposition

Primary comparisons use exact published decimal references. Native operations consume binary64 values, whose exact bit patterns were retained and checked for all8574 inputs. Independent rational moments separate decimal-to-binary conversion effects from computation on the consumed values. For SD, decimal square roots are precision-qualified displays; exact rational comparisons decide the primary gate. Signed differences decompose total error; absolute values are not generally additive.

| Dataset / sampleSD | Total signed error against certified decimal | Input-representation contribution | Algorithm error against exact binary64-input reference |
|---|---:|---:|---:|
| NumAcc3 | 3.492502676E-11 | 3.492459655E-11 | 4.302114051E-16 |
| NumAcc4 | 5.588409513E-10 | 5.587935448E-10 | 4.740651882E-14 |

The two failed rows are dominated by the representation change before the arithmetic operation. Their algorithm-relative errors against the exact consumed binary64 inputs are approximately4.30×10^−15 and4.74×10^−13. This does not reclassify either primary failure. Replacing an arithmetic routine cannot recover arbitrary decimal information already lost on conversion to binary64. A different input-precision contract would be a separately specified method/interface change.

## Integrity, cost and limits

All19 prescribed toy/malformed native preflight cases completed with expected statuses; smoke wall1.824380s. The single NIST process/evidence validation took0.170766s; aggregate1.995146s within the120s cap. The actual remaining NIST timeout was118.175620s. These are bounded wall diagnostics, not comparative throughput measurements.

Exact decimal mean/variance agreed with all certified rounded intervals or explicit exact fields. Precision100/200 diagnostics passed. Source/input/binary hashes were checked before and after execution. No missing rows, nonfinite results, timeout, replacement dataset or native retry occurred. Scientific NO-GO is unchanged; no NIST endorsement, general numerical guarantee or new statistical validation is claimed.

Primary sources and byte identities are preserved in the source-archive file `validation/nist-univariate-inputs.json`. Raw process output, exact rational errors, reference calculations and the freeze manifest are supplied in the separate Round53 evidence archive; validation programs and original nine data files are included in full source. The standalone runtime bundle omits validation assets.

[Official NIST dataset index](https://www.itl.nist.gov/div898/strd/univ/homepage.html), [certification methodology](https://www.itl.nist.gov/div898/strd/univ/certmethdef/pidigits.html), [NIST limitations](https://www.itl.nist.gov/div898/strd/general/faq.html).

## Independent retained-evidence audit

An independent implementation, without importing the evaluated reference/driver modules, reproduced all18 exact gates. It manually decoded8574 binary64 values, verified nearest-even conversion using adjacent-float midpoints, recomputed decimal/binary moments by sum and sum-of-squares, and checked72 diagnostic groups with300-digit direct-root calculations. All60 source pins,4 binary pins and57 preflight files matched. It confirmed16/18, retaining both original failures; no native rerun was performed.
