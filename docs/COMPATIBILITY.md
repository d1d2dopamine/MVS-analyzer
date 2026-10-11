# Interface compatibility

The public interfaces are versioned independently.

| Interface | Current identifier | Compatibility rule |
| --- | --- | --- |
| CLI release | `1.4.0` | Current archived release identifier; 1.5.0 development is CLI/Python-first. |
| Windows desktop | `1.4.0` | Frozen legacy interface. No longer built, released or used as a compatibility gate. |
| Scientific engine | `1.6.2` | Observed availability is independent of calibration. Recompute states/backups from earlier engines. |
| Calibration state | `2` | Must satisfy the existing state compatibility checks. |
| Result/manifest files | `2` | Readers must validate schema and scientific identity. |
| CLI command contract | `mvs-cli` major `1` | Commands/options may grow additively. |
| CLI machine response | `mvs-cli-result/v1` | Python rejects unknown machine schemas. |
| Python package | `0.1.x` | Requires machine response `mvs-cli-result/v1`; package and CLI release versions need not match. |

Compatibility is established from explicit schemas, engine/formula identity and the existing state checks, not by assuming that equal package version strings imply equal calculations.

Engine 1.6.2 adds `ObservedStatus`, `CalibrationApplicable` and `GroupAvailability`
to result rows, appends two CSV status columns, and adds `metric_availability.csv`.
Result/manifest schema 2 and machine response v1 are retained for these additive
fields. The existing `Applicable` field now describes observed testability alone;
engine identity prevents silently interpreting an earlier result with this meaning.
Calibration row serialization is unchanged, including its legacy `Applicable` field.
`--force` still cannot bypass scientific engine/formula compatibility.
