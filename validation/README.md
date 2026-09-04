# Validation material

`PACKAGE_QA.md` records checks actually run while preparing the source package. The C# programs have not been compiled/executed during preparation. `method-hashes.json` pins the current declarations. `reference_numerics.py` checks mathematical identities independently in Python; this is not a C# runtime test.

The other `reference_*` scripts, tables and figures were supplied with the historical development snapshot. They are retained, not republished as engine-1.6.0 validation. Their scores, correction policies and metric registry may be obsolete. See docs/VALIDATION.md for an independent validation plan and remaining acceptance gates.
