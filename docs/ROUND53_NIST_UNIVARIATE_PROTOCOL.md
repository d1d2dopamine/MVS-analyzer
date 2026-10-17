# MVS-NUM-NIST-UNIVARIATE-1.0.0: fixed numerical-reference protocol

## Status, aim and scope

This protocol is written before native evaluation of the selected NIST values. It evaluates the current, unchanged MVS arithmetic-mean and sample-standard-deviation entry points against all nine datasets in the official StRD univariate index. It does not evaluate p-values, statistical power, coverage, route selection, or the applicability of a Gaussian variance model. It does not confer NIST certification on MVS.

Primary sources: [NIST univariate index](https://www.itl.nist.gov/div898/strd/univ/homepage.html), [instructions](https://www.itl.nist.gov/div898/strd/general/howto.html), [certification methodology](https://www.itl.nist.gov/div898/strd/univ/certmethdef/pidigits.html), and the exact dataset URLs in the source manifest. This numerical track implements the numerical-reference layer defined by `docs/BENCHMARK_SUITE.md`; it is not a new simulation study. ADEMP fields are specified below with non-applicable dimensions explicit.

## Aims, data, estimands, methods and performance

**Aim.** Quantify reproducible numerical agreement of two existing operations across the complete published univariate collection, including its higher-difficulty cancellation examples. No dataset is selected or removed in response to MVS output.

**Data.** PiDigits (5000), Lottery (218), Lew (200), Mavro (50), Michelso (100), NumAcc1 (3), NumAcc2 (1001), NumAcc3 (1001), NumAcc4 (1001):8574 observations total. Preserve original response bytes, line ranges, URLs, decimal tokens, declared counts, certified fields and exactness markers. Hash original bytes before parsing. No filtering, imputation, standardization, rescaling, order changes or entity restructuring is allowed. PiDigits provenance metadata differs between index and file description; retain both descriptions rather than resolve that historical label by inference.

**Estimands.** For each supplied finite vector x of length n,

\[
\bar x=\frac1n\sum_i x_i,\qquad s=\sqrt{\frac{\sum_i(x_i-\bar x)^2}{n-1}}.
\]

The intended calculation is the sample SD, not the population denominator n or the standard error of a mean. No inferential null hypothesis or statistical error family is tested. All 18 numerical comparisons are required; a suite-level contract pass is their conjunction.

**Methods.** Invoke `MetricRegistry.Compute("mean", values)` and `MetricRegistry.Compute("standard_deviation", values)` through a test-only friend assembly referencing unchanged Core. The adapter parses decimal tokens once to invariant-culture binary64, preserves order and returns every consumed bit pattern. It does not copy the algorithms. Original source/DLL hashes, runtime and architecture are frozen before execution. Windows behavior is not established by this Linux run.

**Reference.** NIST reports multiple-precision calculations using decimal inputs exactly, rounded to 15 significant digits for the five observed-data tables; NumAcc1–4 explicitly mark mean and SD exact. The independent reference uses exact rational decimal values to compute mean and variance. For a rounded certified value c with half-unit q in its last published decimal place, verify mean in [c−q,c+q], and sample variance in [max(0,c−q)^2,(c+q)^2] for SD. For explicitly exact fields q=0. Certificate mismatch is a reference-integrity failure and blocks candidate comparison. Decimal means/square roots at precision100 and200 must agree within 10^−90 max(1,|reference200|); disagreement blocks evaluation. These displays are diagnostics, not the certificate or primary pass/fail oracle.

Also compute reference moments of the exact binary64 inputs, represented as rational numbers. These diagnose conversion error separately from algorithmic error. They cannot replace the published NIST field in the primary gate or excuse a failure after outputs are observed.

## Frozen accuracy contract

All18 published mean/SD fields are nonzero. Let c be the exact rational value of the published decimal and v the exact rational value reconstructed from the native result's binary64 bits. The primary project gate is

\[
|v-c|\le |c|/10^{10}.
\]

Evaluate this inequality exactly with integers/rationals. This is a uniform relative-error target of 10^−10, chosen before evaluation to require roughly ten decimal digits while leaving several digits below the 15-digit published reference precision. It is an MVS numerical contract, not a tolerance prescribed by NIST. There is no absolute-error floor, reference-interval enlargement, fitted tolerance, or substitution of a binary-input reference. Conditioning and input representation may cause a genuine failure of this target; report that failure and its diagnostic decomposition rather than changing the target.

Report absolute error, relative error and descriptive LRE=−log10(relative error), plus decimal-input and binary-input reference discrepancies. An exact match has an explicit exact-match state; do not emit log(0), infinity or a fabricated finite digit count. If a selected certified field unexpectedly equals zero, stop before evaluation and resolve the protocol rather than invent a denominator. Synthetic zero-mean fixtures have a separate exact expected-value check and do not alter the18-row contract.

## Execution, failures and reproducibility

No RNG, simulation replications or bootstrap sampling is used; Monte Carlo standard errors and sampling confidence intervals are not applicable. Dataset source precision and arithmetic/input-conditioning limits are relevant uncertainty sources. No claim of general software correctness beyond these operations and fixed vectors is made.

Before native evaluation, freeze original files/manifest, protocol, adapter/reference source and tests, input envelope, compiled DLL hashes and runtime. Require independent review and passing synthetic parser/arithmetic/provenance tests. Retain all attempted process output and nonzero exits. Run the nine datasets in one native process; hard native-process timeout120s, input cap16MiB, at most12cases/10000values percase/20000total values. The planned NIST input has nine cases and8574 values. No child process is launched by the adapter. Separate deterministic malformed-input and toy-vector checks may run up to20 native invocations total, with a cumulative120s wall budget; no rerun of NIST outcomes to select a preferred result.

Native execution success is separate from numerical-contract success. A numerical failure is an informative terminal result, retained per row with no algorithm correction in this stage. Malformed input, missing source identity, count/bit mismatch, nonfinite output, reference-integrity failure or provenance drift causes a technical failure; never convert it to an ordinary numerical failure or omit it from the requested denominator. Any justified technical continuation receives a distinct attempt identity and retains the original failure.

Wall time is a bounded execution diagnostic only. No throughput or before/after performance claim is planned; build time, process startup and output serialization are not comparable to an isolated arithmetic microbenchmark.

## Registration and reporting

The machine protocol and input manifest are source-archive assets under `validation/`; the standalone runtime bundle intentionally excludes validation tooling. Report all18 rows, all9 dataset difficulties and all failures. Preserve MVS Benchmark Suite1.0.0 as the historical registry snapshot; this separately versioned numerical study does not rewrite its earlier mapped-not-run state. Scientific NO-GO and previous failed development candidates remain unchanged.
