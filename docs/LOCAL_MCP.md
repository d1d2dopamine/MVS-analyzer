# Local stdio MCP (Linux and experimental Windows)

This is an optional adapter over the [same local workflow](WORKFLOW_PROTOCOL.md),
not a remote service. Windows support is implemented in Round23 but requires the
owner-run Windows validation gate before any verified-support claim. The only computation exposed is
native summary analysis with an existing calibration. The ordinary native CLI
continues to own statistical validation and calculations.

Install from the source root in a virtual environment:

```bash
python -m pip install './python[mcp]'
```

The optional dependency is pinned to the official Python SDK **mcp 1.30.0**.
The tested default protocol is **2025-11-25**; **2024-11-05** negotiation is also
covered. This is the official maintained v1 SDK line, not an implicit dependency
on whatever a future major SDK installs. Ordinary `import mvs` and workflow CLI
usage do not import or require the MCP SDK.

Configure the host to launch the installed `mvs-mcp` executable, with arguments:

```text
--engine /absolute/path/publish/cli/mvs
--read-root /absolute/mvs-inputs
--work-root /absolute/mvs-work
--timeout-seconds 120
```

Use a fresh empty work root disjoint from the read root. For a task-local .NET
installation the host must explicitly supply its trusted `DOTNET_ROOT` environment.
Only launch configuration chooses engine/root paths; tool arguments cannot replace
them. The stdio process opens no HTTP listener. There is no arbitrary shell tool,
arbitrary file resource, benchmark endpoint or automatic dataset upload.

Tools: `register_protocol`, `get_protocol`, `run_analysis`, `get_run`,
`read_artifact`. Their requests and result semantics are described in the shared
workflow document. Resource `mvs://capabilities` reports scope, limits and retained
scientific NO-GO; there are no resource templates that accept arbitrary paths.

The official SDK handles initialization, JSON-RPC framing, schema validation and
cancellation. Native workers are separate subprocesses. The adapter redirects
accidental stdout to stderr while preserving a dedicated protocol stream. Tool
calls are serialized; cancellation signals the worker and waits for cleanup before
releasing its slot. Malformed calls/unknown tools fail without dispatching an engine.
An MCP transport success or an execution exit 0 is not a scientific GO decision.

The server can expose files beneath the explicitly configured roots to the local
host through the whitelisted operations. Choose those directories narrowly. This
is an operator-controlled local integration, not an isolation boundary against
hostile software running as the same OS user. Host/client permission decisions and
external transfers remain the operator's responsibility; no external registrar or
complete-campaign assurance is provided.

Actual tests include official SDK client/server stdio exchange, native exploratory
and frozen runs, CLI/MCP returned-result parity, verified artifacts and cancellation.
Synthetic executable tests exercise malformed results and cancellation mechanics;
they are labeled separately from actual .NET statistical execution. Windows/macOS,
remote hosts and a production desktop-agent installation were not tested in the
Linux/cloud execution environment. See [Windows setup and pending runtime gate](ROUND23_WINDOWS_MCP.md).

Official references:
- [Python SDK v1.30.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.30.0)
- [Official v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/)
