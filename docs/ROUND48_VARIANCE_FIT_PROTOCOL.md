# Round 48: fixed Gaussian variance-fit numerical reference protocol

Status: FROZEN DESIGN, 2026-10-17. No reference optimization, candidate fitting, or inspection of candidate values is permitted until implementation review and the separate execution seal. The frozen artifacts may not be edited after outcomes are observed. Protocol identifier: `round48-variance-fit-v1`. Source inspected: Round47 `Core/VarianceAnalysis.cs`, `Core/NumericalMethods.cs`, `MvsAnalyzer.Core.Tests/ScientificChecks.cs`, and `docs/METHODS.md`. Implementation is planned in the separate Round48 source copy, without production-source changes.

## 1. Question and limits

Does the existing `VarianceAnalysis.Fit` numerically minimize its declared Gaussian independent-group random-intercept ML/REML objective on its declared finite variance box, for these literal deterministic examples? The experiment does not establish statistical coverage, bias, power, type-I error, global optimizer reliability for arbitrary data, or suitability of the Gaussian model for real observations. Scientific NO-GO and existing production activation decisions remain unchanged.

Exactly 20 scientific candidate Fit calls, nine independently optimized reference problems, and no simulated datasets, random seeds, bootstrap, power trial, candidate selection, or resampling. No production dependency is added. Constant-data rows are guard-contract checks, not usable estimates. Structural-invalid/cancellation tests, if implemented, must be labelled separate engineering checks and cannot silently enter these 20 rows. No execution of `VarianceAnalysis.Run`, `Generate`, or other stochastic workflow is allowed.

## 2. Literal fixtures and cases

The fixture root fields are exactly `schemaVersion`, `protocolId`, `status`, `scientificFitCallBudget`, `oracleProblemCount`, and `cases`. Draft status is `proposed`; change it to `frozen` only on explicit freeze, then hash the final bytes. Budgets must equal20 and9; at most10 clusters and40 observations occur in a case.

The accompanying `validation/variance-fit-fixtures-v1.json` is the shipped complete literal machine input (the pre-freeze external draft is `mvs-r48-variance-fixtures-proposed.json`): both raw values and sufficient summaries for every case, including affine variants. Cluster order and group order are fixed. All groups are independent; entity labels A/B are identifiers, not paired subjects. The native probe takes the literal summaries. The independent oracle constructs raw observation vectors and full covariance/design matrices from `values`; it must not call the native objective or use its sufficient-statistic objective implementation.

For raw-summary preflight, `count == values.length` exactly; means and within sums of squares agree to `1e-12 * max(1, abs(expected))`. All raw values and summaries must be finite. This is only fixture-integrity verification, never a replacement of literal summaries with recomputed values.

### B: balanced interior, existing ScientificChecks reproduced

Two groups, five clusters per group, four repeats each. Group 0 centers are 1,2,3,4,5; group 1 centers are 101,102,103,104,105. Every cluster has residual vector [-3,1,1,1], hence within sum of squares 12. Thus each group has W=60, centered sum of squared cluster means B=10, k=5, n=4, N_g=20. Arithmetic group means are 3 and103. Global centering mean is53 and global scale squared is2505. These are fixed arithmetic facts, not fitted outputs.

Unconstrained ML exact interior anchor: within variance4 and between variance1 in each group. REML anchor: within4, between1.5. The existing test has only the latter plus its ×1000 scaling case, with .003 absolute variance tolerance. Round48 adds independent likelihood and ML checks and retains that scaled REML example.

### Z: strict between-variance boundary

Two groups, five clusters per group, four repeats each. Group 0 centers [-.5,-.25,0,.25,.5]; group 1 has those centers +10. Each has residuals [-3,1,1,1] and within sum of squares12. Per group W=60 and B=.625. Exact nonnegative-variance ML solution: between0, within62.5/20=3.125; REML: between0, within62.5/19. Group means0 and10; global scale squared28.125. Both are strictly on the between-zero face, rather than an equality-threshold ambiguous toy.

These exact-zero values are analytic context. The primary reference and candidate comparison use the existing finite box, whose between floor is positive. A tiny positive estimate, or lack of the geometric AtBoundary flag when a likelihood-equivalent tiny positive value is returned, is not by itself an algorithm defect.

### U: genuinely unbalanced raw covariance example

Group 0 clusters: [-4,-2]; [-1,0,1]; [0,1,2,3]; [3,4,5,6,7]. Group 1: [5,9,13]; [7,11]; [8,10,12,14,16]; [15,17,19,21]. There are28 observations, four clusters per group, and counts2,3,4,5 in different orders. Group-specific means and both variance components are fitted. No reference optimum is filled in before freeze.

### C: constant-data contract

Two groups, two clusters per group, two observations per cluster, every value7. Expected API result: means[7,7], both within and between arrays[0,0], NaN objective, `Converged=false`, `AtBoundary=true`, iterations0, and the requested method label. This is a refused/degenerate fit; it is never counted as an accurate statistical estimate or passed to the covariance reference optimizer.

### Exact 20-row manifest

1–6: B_ML, B_REML, Z_ML, Z_REML, U_ML, U_REML, all unconstrained.

7–9: U_ML_equalWithin, U_ML_equalBetween, U_ML_equalBoth.

10–17: unconstrained U, ML and REML each, transformed by y+32, 1000y, .001y, and −2y+7.

18: B_large_REML =1000B, unconstrained REML.

19–20: C_ML and C_REML, degenerate contract rows.

The first nine rows have independent optimization. The nine affine variants derive reference parameters exactly from the appropriate first-six result and receive independent dense-objective reevaluation; no new optimization is required. Global affine transformations preserve the normalized feasible box and normalized objective, with a possible sign reversal of centered data. Group-specific shifts are deliberately absent because they alter the global scale squared and the finite physical box.

## 3. Independent likelihood derivation and constants

Write s_g=within variance, t_g=between variance. Stack raw observations y, in fixed cluster order. Let X be the N×G group-indicator design, rankG. For a cluster of size n in group g its marginal covariance is V_i=s_g I_n+t_g 1_n1_n′; assemble V block diagonally. Use Cholesky factorization and solves, not an explicit determinant or numerical integration. Set A=V⁻¹, M=X′AX, beta=M⁻¹X′Ay, r=y−Xbeta, z=Ar, and P=A−AXM⁻¹X′A.

With the group-indicator convention fixed, full profiled ML NLL is

L_ML = .5 [N log(2π) + log|V| + r′Ar].

Full REML NLL is

L_REML = .5 [(N−G) log(2π) + log|V| + log|X′V⁻¹X| + r′Ar].

Some packages additionally subtract .5 log|X′X|. This protocol does not. Do not compare package likelihood numbers without removing their constants. ML and REML objectives are never compared against one another as if they were the same function.

Derivation of the sufficient-statistic identity, for auditing rather than implementing the independent optimizer: V_i has eigenvalue s_g on its n−1 within-cluster contrast directions and s_g+n t_g on its constant direction. Thus log|V_i|=(n−1)log(s_g)+log(s_g+n t_g), and its profiled quadratic contribution is W_i/s_g+(mean_i−beta_g)²/(t_g+s_g/n). X′V⁻¹X is diagonal with group sums of1/(t_g+s_g/n). This proves the scalar code and direct matrix expression target the same mathematical objective.

The implementation centers at a=mean(y) and scales by c²=mean((y−a)²), population denominator N. Construct normalized raw y*=(y−a)/c and optimize normalized variances s*=s/c²,t*=t/c². The returned native NLL omits constants and is on this normalized scale. Consequently:

F_native_ML = L_raw_ML − N/2 log(2π) − N/2 log(c²).

F_native_REML = L_raw_REML − (N−G)/2 log(2π) − (N−G)/2 log(c²).

Equivalently evaluate normalized dense V*, omit the appropriate normal constant, and include log|X′V*⁻¹X| only for REML. Output both this normalized objective and a reconstructed raw full NLL with the convention recorded. Raw NLL changes by N log|b| (ML) or (N−G)log|b| (REML) under y→a+b y; normalized NLL is invariant. Means transform a+b beta and variances by b².

## 4. Balanced analytic anchors and boundary interpretation

For k clusters with n repeats in one group, W=sum within sums of squares, B=sum(mean_i−mean_group)², d=k(n−1):

Interior ML: s=W/d, v=B/k, t=v−s/n.

Interior REML: s=W/d, v=B/(k−1), t=v−s/n.

Use these only if t>0. If the unconstrained t is negative, the exact nonnegative-model boundary optimum is t=0 and s=(W+nB)/(kn) for ML or (W+nB)/(kn−1) for REML. Simply truncating negative t while keeping s=W/d is not the boundary optimum. These formulas sum independently over groups for the unconstrained B/Z rows.

The actual code restricts every distinct normalized log variance to [−23,8], giving physical box [c²e⁻²³,c²e⁸]. Its global `AtBoundary` flag is true when any fitted log parameter is strictly within1e−4 of either endpoint. This is a geometric numerical flag, not a hypothesis test or proof of zero. No within-zero fixture is included: zero within sum of squares with distinct cluster centers can make likelihood unbounded as s→0 and would require a different estimability discussion.

For Z, evaluate the analytic exact-zero NLL, the feasible point(s=s_zero,t=c²e⁻²³), and the independently optimized finite-box solution. Their relation must be L_exact_zero ≤ L_box ≤ L_feasible_point up to1e−8 normalized NLL. Report the exact-to-box gap. Require finite-box within estimates agree with the exact-zero within anchor within1e−6 × group raw variance scale; means within1e−8 × group raw SD. This is an anchor check only; native acceptance uses the finite-box reference and absolute boundary tolerance below.

## 5. Reference computation, conditioning, and frozen optimization budget

Installed reference packages checked without fitting: NumPy2.3.5, SciPy1.17.0, and mpmath available. Record actual versions, Python/platform/BLAS details and source/fixture/protocol hashes at execution. No package installation is required. Use SciPy L-BFGS-B, not a reimplementation of the production Nelder–Mead optimizer.

Distinct coordinates are ordered [within coordinates, between coordinates]; shared-variance models have one coordinate for the shared component. Build dense derivative matrices from I_n or1_n1_n′ blocks and sum affected blocks for shared coordinates. For a log parameter θ with Vθ=dV/dθ:

ML gradient =.5 tr(A Vθ) − .5 z′Vθz.

REML gradient =.5 tr(P Vθ) − .5 z′Vθz.

Compute these from raw covariance linear algebra, not by differentiating the production scalar formula. A single oracle call returns both objective and gradient.

For each of the nine reference problems, enumerate every subset of distinct between coordinates fixed at log floor−23, including the empty subset. For every face use exactly two starts, BEFORE setting that face's fixed coordinates: start1 has normalized within=.1 and between=.1; start2 has within=1 and between=.01. Preserve this order. All other coordinates are bounded [−23,8]. These counts are 6 free models×4 faces×2 starts + one equalWithin model×4×2 + equalBetween×2×2 + equalBoth×2×2 =64 optimizer attempts. All64 are run if the oracle remains valid and resource caps permit; no new starts or retries are selected after seeing values.

Fixed options: method L-BFGS-B, analytic Jacobian, ftol1e−14, gtol1e−9, maxiter1000, maxfun1500, maxls40. Enforce1500 objective/gradient evaluations per attempt in a wrapper as well as via options. At most96,000 such evaluations total. At most128 high-precision covariance evaluations (including preflight and accepted-point audits), all within a180-second monotonic wall-clock cap for the entire reference stage. These are deterministic numerical iterations, not random sampling. The maximum raw covariance matrix is40×40; individual blocks are at most5×5. BLAS is single-threaded. Timeouts or evaluation caps end the reference stage with `oracle_inconclusive`, preserve all work, and do not authorize candidate fitting.

Conditioning: theoretical block eigenvalues give full κ₂(V)=max_i(s_i+n_i t_i)/min_i(s_i). Compute this before factorization. Do not silently add a ridge, truncate eigenvalues, or replace an unreliable trial by an artificial objective. For κ₂>1e8, evaluate the same direct covariance likelihood and derivatives with mpmath at60 decimal digits, using dense per-cluster blocks and exact group-indicator projection. Convert only final objective/gradient to binary64 for SciPy. Any nonfinite result, factorization failure, exhausted high-precision budget, or failed identity is an oracle failure/inconclusive result, not a candidate failure. Accepted optima themselves must have κ₂≤1e8 and relative solve residual ≤1e−10. Define the latter for every solve Vx=b as ||Vx−b||∞/(||V||∞||x||∞+||b||∞), with zero-over-zero defined as0.

Fixed high-condition preflight: n=2,3,4,5; normalized s=e⁻²³,t=.1; raw y=[0,1,…,n−1] with one intercept. Evaluate60-digit dense V and compare its determinant and profiled quadratic to the exact constant-direction/contrast eigenidentity, to scaled error1e−40. Record binary64 discrepancies at those deliberately ill-conditioned points diagnostically; do not require binary64/mp60 agreement there. These four points are reference-engine checks, not added candidate fixtures or optimization problems. Also audit every selected accepted reference point in60 digits: normalized NLL agreement ≤1e−8 absolute and log-coordinate gradient agreement ≤1e−8 absolute. Count every audit within the128 limit and180 seconds.

Reference certification: the two starts on the selected winning face must both complete successfully and agree in normalized NLL within1e−8, means within1e−7 times group raw SD, and positive interior variance coordinates within1e−6 relative plus1e−9 times group raw variance. Each selected point must satisfy projected log-gradient infinity norm≤1e−6. Additionally inspect linear normalized-variance scores, especially fixed between-floor coordinates: let score=.5 trace_term−.5 quadratic_term; tolerance is1e−6[1+.5|trace_term|+.5|quadratic_term|]. At a lower bound, score must be≥−tolerance; at an upper bound≤tolerance; in the interior its absolute value must be≤tolerance. Classify a coordinate within1e−6 log distance as at its bound for this check. A tiny log-gradient alone cannot certify a between-floor solution, since multiplying the linear score by e⁻²³ can hide an inward direction of descent.

Select the lowest certified objective. It must be no greater than every finite feasible recorded attempt endpoint plus1e−8, including unsuccessful or uncertified endpoints; otherwise the reference is `oracle_inconclusive`, because an unsuccessful attempt can still supply a better feasible point. Objectives within1e−8 are tied; prefer the face fixing the greatest number of between coordinates at the floor, then ascending bitmask of fixed coordinates, then start1. No discarded or unsuccessful attempt is omitted from the reference report. Certification is a bounded multi-start agreement/KKT check, not a theorem of global optimality. B interior anchors must also agree with the analytic parameters to relative1e−6 plus1e−9 times group raw variance, means within1e−8 times group raw SD, and objective within1e−8. Z has the separate finite-floor anchor in section4. If any required reference problem fails certification, stop before native fits and report the blocker; changes require a new reviewed version, never relaxed post hoc gates.

## 6. Frozen native acceptance gates

For each group define H_g as the population raw observation variance within that group, centered at that group's raw mean. It is positive for all regular fixtures and invariant to group offset; it scales by b² under affine transformation. Let c² be the global normalization scale.

For every regular row:

- Exactly one native Fit call with the frozen flags. Require returned method ML/REML correct, `Converged=true`, finite objective/means/variances, correctly sized arrays, and all variances positive and inside the normalized log box within1e−10 endpoint roundoff. A `Converged=false` result is a failed diagnostic even if point estimates happen to be close; preserve its values and do not retry the candidate.
- Mean absolute error ≤2e−4 sqrt(H_g)+1e−10 max(1,abs(reference mean)).
- For positive interior variance components, absolute error ≤5e−4 abs(reference component)+1e−7 H_g.
- For reference between components whose log is within1e−6 of the lower bound, use absolute error ≤max(5c²e⁻²³,1e−6 H_g), never relative error against zero/floor. Report the exact native floor-distance and tiny-positive value.
- Reevaluate dense normalized NLL at native returned variances with GLS means. Absolute discrepancy from native reported NLL ≤2e−8(1+abs(reference NLL)). Independently compare returned means with these GLS means under the same mean tolerance. This separates an objective/formula mismatch from optimization error.
- Native normalized NLL minus reference normalized NLL must lie in [−1e−7,2e−5]. A native objective lower than the reference by more than1e−7 is `oracle_or_protocol_inconclusive` pending investigation, not evidence of native superiority or a passing candidate. No finite-box result is judged against an unconstrained exact-zero optimum as though the domains were equal.
- Reconstruct log coordinates from returned physical variances and c². `AtBoundary` must match the source criterion (<1e−4 distance) unless a reconstructed distance is within1e−8 of that threshold; in that explicitly predeclared roundoff band report `boundary_flag_threshold_ambiguous`. A mathematically boundary reference does not force `AtBoundary=true` if the returned tiny positive component remains outside that geometric band and meets the parameter/objective gates.
- For equalWithin/equalBetween rows, shared returned components must be bitwise equal across groups, as the source computes the same transformed parameter for each group.

Affine rows must satisfy the corresponding transformed reference parameter gates and normalized objective gate; additionally compare their normalized NLL to the source row within4e−5, and their means/variances back-transformed to the original units under twice the per-row parameter tolerance. Reconstructed raw full NLL must have the section3 ML/REML log-unit shift within4e−5. No group-specific translation test is implied.

Constrained-fit nesting uses U's four ML models only, all with identical X and normalization. Require F_free≤F_equalWithin, F_free≤F_equalBetween, F_equalWithin≤F_both, F_equalBetween≤F_both, each with5e−6 native numerical slack (the free-vs-null LR therefore cannot be less than−1e−5). Reference nesting slack is1e−8. Compute raw untruncated LR=2(F_restricted−F_free) for the three restrictions and compare native/reference LR to1e−4 absolute; report any negative value, do not silently clip it in the diagnostic. Neither equalWithin nor equalBetween is nested in the other. These are optimization nesting checks, not inferential p-values.

Constant rows must match section2, with explicit nonfinite classification for objective rather than numeric zero. They contribute to guard-contract pass/fail separately from the18 numerical fit rows. All20 rows must be retained, including failures; no substitution, extra seeds, aggregate success percentage, or selective rerun is permitted.

## 7. Stage order and deliverables

1. Review this text, literal JSON, native probe design, and reference implementation without calling any optimizer or native Fit. Freeze their hashes in an external pre-execution record. Existing code/tests may be inspected; new optima must not be inspected.
2. Execute reference self-checks, nine frozen optimizations, high-precision audits, analytic anchors and nesting. Save a complete machine-readable reference report with every attempt, reason/status, call counts, durations and hashes. If oracle certification fails, stop before candidate evaluation.
3. Only after valid reference results are persisted, invoke the native probe once on the complete20-row manifest. Preserve exact source/build identity, input hash, raw outputs, values, numeric classes, convergence and boundary diagnostics. One result per row, no candidate retries.
4. Run the prespecified comparison; write machine-readable pass/fail/inconclusive details and a concise human report. State numerical scope and all caveats; no production activation follows from a pass.

The native output shape is coordinated with the native harness worker; it must preserve case id, flags, literal input identity, finite arrays plus explicit numeric classification/bit patterns, objective classification, method, convergence, boundary flag, iteration count and exceptions. The fixture schema is fixed by the accompanying JSON and should not be changed by a test runner. Atomic evidence persistence and source/fixture/protocol hashes are required, but a generic runner framework is out of scope.

## 8. Build-versus-buy decision and primary references

Buy/reuse mature NumPy/SciPy matrix factorization and bounded optimization in validation; add only a small transparent model-specific wrapper and the raw covariance/design matrices. Use the already installed mpmath only as a high-precision reference audit/fallback. Do not add a production statistics package, replace the production estimator, or reimplement generic optimization. Off-the-shelf MixedLM alone is not an exact drop-in comparison for both group-specific residual variances and each independent equality restriction, and package REML constants/parameter profiling vary. Direct V/X likelihood plus analytic anchors gives an auditable same-model comparison without relying on those defaults.

Primary documentation consulted:

- SciPy L-BFGS-B options, projected-gradient stopping and evaluation budgets: https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html . The live documentation may be newer than installed1.17.0; record and use the installed version's supported options.
- SciPy Cholesky/solve API and positive-definite covariance requirements: https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.cho_factor.html . Use only the selected triangle; no interpretation of an uninitialized triangle.
- statsmodels official mixed-linear-model source describes marginal covariance scale·I+ZΨZ′, GLS profiling, ML/REML and its Lindstrom–Bates implementation references: https://www.statsmodels.org/stable/_modules/statsmodels/regression/mixed_linear_model.html . It is model/convention context, not the numerical oracle.

The equations and analytic fixture anchors above are explicit independent derivations for this protocol. The reference matrix engine, its conditioning checks, and the finite-box distinction are the evidence; no package name by itself proves correctness.
