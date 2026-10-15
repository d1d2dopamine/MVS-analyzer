# MVS Analyzer Python API

This package is a thin interface to the MVS statistical engine. It does **not** reimplement the statistical methods in Python.

A compatible `mvs` CLI must be installed or configured with `MVS_CLI=/path/to/mvs`.

## Optional local workflow and MCP (Linux / experimental Windows)

The ordinary `mvs.Engine` API is unchanged. Install this source package to add
`mvs-workflow`; use the optional `mcp` extra for `mvs-mcp` (official SDK 1.30.0).
These entry points call one application service and the same native engine. They
support summary analysis with an existing calibration on Linux and experimental
Windows 10+ x64/local NTFS. Actual Windows runtime verification is pending the
owner-run gate in [Round23](../docs/ROUND23_WINDOWS_MCP.md); no automatic confirmatory inference is provided. Frozen local records are
not external preregistration, and project scientific NO-GO is always disclosed.
See [workflow quickstart](../docs/WORKFLOW_PROTOCOL.md) and
[MCP configuration](../docs/LOCAL_MCP.md) for exact root, request and trust limits.
