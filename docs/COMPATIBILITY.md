# Interface compatibility

The public interfaces are versioned independently.

| Interface | Current identifier | Compatibility rule |
| --- | --- | --- |
| CLI release | `1.4.0` | Current archived release identifier; 1.5.0 development is CLI/Python-first. |
| Windows desktop | `1.4.0` | Frozen legacy interface. No longer built, released or used as a compatibility gate. |
| Scientific engine | `1.6.0` | Recorded in states and manifests. |
| Calibration state | `2` | Must satisfy the existing state compatibility checks. |
| Result/manifest files | `2` | Readers must validate schema and scientific identity. |
| CLI command contract | `mvs-cli` major `1` | Commands/options may grow additively. |
| CLI machine response | `mvs-cli-result/v1` | Python rejects unknown machine schemas. |
| Python package | `0.1.x` | Requires machine response `mvs-cli-result/v1`; package and CLI release versions need not match. |

Compatibility is established from explicit schemas, engine/formula identity and the existing state checks, not by assuming that equal package version strings imply equal calculations.
