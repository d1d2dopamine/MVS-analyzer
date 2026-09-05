# UI/Colab repair QA — app 1.4.0 / engine 1.6.0

Prepared as source for GitHub CI. **No .NET compilation/execution, C# test execution, WinForms launch, native Windows screenshot or live Colab run was performed here**, as requested. Static success is not a claim that the application builds or that scientific validation passed.

The previous source delivery's static checks did not detect the reported UI regression. This repair removes the nested auto-size cycle, restores result tab sizing and adds native Windows acceptance coverage rather than treating static checks as visual proof.

## Actually executed for this repair

- Python offline Colab regressions: explicit host/environment (a fake Python host, not .NET), completed-calibration reuse, mismatched metadata, failure/cancellation, diagnostic replay, normalized nested-result downloads, notebook URL detection, loopback code restrictions, strict JSON and safe ZIP/manifest paths.
- Static contracts: project/props/manifest/solution XML, exact compile-source paths, Python AST, two notebook structures and synchronized helper, engine/formula/protocol pins, versions, exact embedded portable source, original badge/image/plugin bytes and unchanged demo data.
- Limited C# lexical/structural checks over the final source tree. This is **not** a C# grammar parser, type checker or compiler.
- YAML parsing of all three workflows.
- Supplied Colab artwork cropped/resized from its alpha channel into 32/48/64/96/192-pixel assets. A light/dark icon composite was visually inspected; it was not a Windows app screenshot.
- ZIP integrity, one-root layout, required source/docs/notebooks/assets and byte equality with the final tree are verified during packaging.

## Written for CI / still requires target-environment execution

- Portable and desktop-linked C# regressions; Linux 150-replication save/replay and strict-output smoke.
- Windows geometry tests and PNGs for Guided/Expert, both languages/themes, multiple sizes, all pages and empty/populated core screens. Human screenshot and real-DPI review is mandatory.
- Live Colab build, browser permissions, pairing, three successive reassignments, completed-calibration disabling, custom import profiles, manual URL and ZIP fallback, restart/disconnection and benchmark diagnostics.

## Retained evidence and limitations

`reference_numerics_results.json` contains Python mathematical identity checks from the earlier preparation (quadrature moments and analytic/dense covariance agreement); those are not new C# runtime validation. Scientific model contracts remain unchanged by UI/Colab repairs. Native MELSM is experimental and not independently validated. Conditional power, approximate equivalence, selected-pair descriptions and editable local audit history retain their documented limits.

Do not publish a scientific or visual certification from this file. Run CI, inspect native layouts and diagnostics, then validate against independent implementations before substantive scientific use.
