# Validation tools

This directory contains simulation inputs, reference scripts and machine-readable method/asset checks used by CI. Tests and synthetic data are not independent scientific certification.

- `method-hashes.json` pins the current formula and benchmark definitions.
- `protected-assets.json` checks local binary artwork and plugin packages; README badge text and markup are freely editable.
- `reference_numerics.py` checks mathematical identities in Python independently of the C# implementation.
- `make_datasets.py`, `dgp.py`, `reference_simulation.py` and `analyze_results.py` support the diagnostic workflow.

Generated reports belong in CI artifacts, not the application download. See `docs/VALIDATION.md` for interpretation limits.
