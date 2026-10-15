"""Optional, local stdio MCP adapter for the bounded MVS workflow service.

The official MCP SDK owns framing, initialization and request cancellation.
This module never assembles engine commands or exposes an HTTP transport. Install
``mvs-analyzer[mcp]`` to enable it; ordinary Python API use does not import MCP.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import threading
from typing import Any, Protocol


CAPABILITY_URI = "mvs://capabilities"
READINESS = {
    "scope": "project_release_readiness",
    "status": "no_go",
    "basis": "MVS-BENCH-1.2.0 development",
    "independentConfirmatoryValidation": False,
}


class WorkflowDispatcher(Protocol):
    def dispatch(
        self, operation: str, params: dict[str, Any],
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]: ...


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


_TEXT = {"type": "string", "minLength": 1, "maxLength": 4096}
_ID = {"type": "string", "minLength": 1, "maxLength": 64,
       "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"}
_GROUP_IDS = {"type": "boolean", "default": False}
TOOL_SCHEMAS = {
    "register_protocol": _schema({
        "protocol_id": _ID, "data": _TEXT, "calibration": _TEXT,
        "prior_exposure": {"type": "string", "enum": [
            "unknown", "previously_inspected", "not_inspected_declared"]},
        "question": {"type": "string", "minLength": 1, "maxLength": 2000},
        "parent_protocol_id": _ID,
        "allow_group_scoped_ids": _GROUP_IDS,
    }, ["protocol_id", "data", "calibration", "prior_exposure", "question"]),
    "get_protocol": _schema({"protocol_id": _ID}, ["protocol_id"]),
    "run_analysis": _schema({
        "run_id": _ID, "data": _TEXT, "calibration": _TEXT,
        "mode": {"type": "string", "enum": ["exploratory", "frozen"],
                 "default": "exploratory"},
        "protocol_id": _ID, "allow_group_scoped_ids": _GROUP_IDS,
    }, ["run_id", "data", "calibration"]),
    "get_run": _schema({"run_id": _ID}, ["run_id"]),
    "read_artifact": _schema({"run_id": _ID, "name": _TEXT}, ["run_id", "name"]),
}
TOOL_SCHEMAS["run_analysis"]["allOf"] = [{
    "if": {"properties": {"mode": {"const": "frozen"}}, "required": ["mode"]},
    "then": {"required": ["protocol_id"]},
    "else": {"not": {"required": ["protocol_id"]}},
}]
_DESCRIPTIONS = {
    "register_protocol": "Register a local immutable protocol; prior exposure is a declaration, not proof.",
    "get_protocol": "Read a registered protocol by its ID.",
    "run_analysis": "Run bounded native analysis from read-root-relative inputs; scientific readiness remains NO-GO.",
    "get_run": "Read a recorded local run by its ID.",
    "read_artifact": "Read a bounded, hash-checked text artifact belonging to a recorded run.",
}


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "schemaVersion": "mvs-workflow-result/v1",
        "execution": {"status": "error", "nativeExitCode": None, "outcome": "error"},
        "scientificReadiness": dict(READINESS),
        "data": None,
        "error": {"code": code, "message": message},
    }


def create_server(service: WorkflowDispatcher):
    """Create an official SDK Server with an injectable shared service.

    Cancellation waits for WorkflowService's bounded terminate/kill/reap path.
    The worker is never abandoned, including when the client closes transport.
    """
    try:
        import anyio
        import jsonschema
        from mcp import types
        from mcp.server.lowlevel import Server
        from mcp.server.lowlevel.helper_types import ReadResourceContents
    except ImportError as exc:
        raise RuntimeError("Install the optional dependency: pip install 'mvs-analyzer[mcp]'") from exc

    server = Server("mvs-workflow", version="0.1.0", instructions=(
        "Local Linux / experimental Windows NTFS workflow. Execution completion is separate from scientific "
        "readiness, which remains project_release_readiness/no_go. Inputs are relative "
        "to the operator-configured read root. No remote service or arbitrary commands."
    ))
    # Reject additional concurrent native runs rather than grow an unbounded queue.
    run_slot = threading.Lock()

    @server.list_tools()
    async def list_tools():
        return [types.Tool(
            name=name, description=_DESCRIPTIONS[name], inputSchema=schema,
            annotations=types.ToolAnnotations(
                readOnlyHint=name in {"get_protocol", "get_run", "read_artifact"},
                destructiveHint=False, openWorldHint=False,
            ),
        ) for name, schema in TOOL_SCHEMAS.items()]

    async def dispatch(operation: str, params: dict[str, Any]) -> dict[str, Any]:
        cancel_event = threading.Event()
        finished = anyio.Event()
        outcome: dict[str, Any] = {}

        async def worker():
            # The SDK cancels a request scope for notifications/cancelled and on
            # transport close. Shield only the worker; the waiting handler must
            # receive cancellation in order to set the service's native signal.
            with anyio.CancelScope(shield=True):
                try:
                    outcome["result"] = await anyio.to_thread.run_sync(
                        functools.partial(service.dispatch, operation, params,
                                          cancel_event=cancel_event),
                        abandon_on_cancel=False,
                    )
                except Exception:
                    # Do not leak internal paths, native stderr or exception text.
                    outcome["result"] = _error("internal_error", "Workflow service failed.")
                finally:
                    finished.set()

        async with anyio.create_task_group() as group:
            group.start_soon(worker)
            try:
                await finished.wait()
            except anyio.get_cancelled_exc_class():
                cancel_event.set()
                with anyio.CancelScope(shield=True):
                    await finished.wait()
                raise
        return outcome["result"]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]):
        # Use the published strict schemas but return the common workflow error
        # envelope even for malformed calls. The SDK still owns wire validation.
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            result = _error("unknown_operation", "Unknown workflow operation.")
        else:
            try:
                jsonschema.validate(arguments, schema)
            except jsonschema.ValidationError:
                result = _error("invalid_params", "Arguments do not match the tool schema.")
            else:
                acquired = name != "run_analysis" or run_slot.acquire(blocking=False)
                if not acquired:
                    result = _error("busy", "Another native analysis is still running or stopping.")
                else:
                    try:
                        result = await dispatch(name, arguments)
                    finally:
                        if name == "run_analysis":
                            run_slot.release()
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, allow_nan=False))],
            structuredContent=result,
            isError=result.get("execution", {}).get("status") != "completed",
        )

    @server.list_resources()
    async def list_resources():
        return [types.Resource(uri=CAPABILITY_URI, name="MVS local workflow capabilities",
                               description="Fixed local capabilities and scientific release readiness.",
                               mimeType="application/json")]

    @server.list_resource_templates()
    async def list_resource_templates():
        return []

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) != CAPABILITY_URI:
            raise ValueError("Unknown resource; only mvs://capabilities is available.")
        return [ReadResourceContents(content=json.dumps({
            "schemaVersion": "mvs-workflow-capabilities/v1",
            "transport": "stdio", "supportedPlatform": "windows" if sys.platform == "win32" else "linux",
            "platformValidation": "experimental_requires_owner_windows_ci" if sys.platform == "win32" else "linux_verified_round22",
            "operations": list(TOOL_SCHEMAS),
            "scientificReadiness": dict(READINESS),
            "concurrentNativeRuns": 1,
            "cancellation": "cooperative event, then bounded native terminate/kill/reap; no abandoned workers",
            "paths": "operator-configured local roots; no arbitrary path resources",
        }), mime_type="application/json")]

    return server


async def serve_stdio(service: WorkflowDispatcher) -> None:
    """Serve one local connection; reserve stdout exclusively for SDK JSON-RPC."""
    import anyio
    from mcp.server.stdio import stdio_server

    server = create_server(service)
    # v1 SDK takes explicit streams. Give it a private stdout descriptor and
    # redirect fd 1 itself, so both Python prints and inherited native stdout
    # are diagnostics on stderr rather than corrupting the protocol channel.
    sys.stdout.flush()
    protocol_fd = os.dup(sys.stdout.fileno())
    try:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        with os.fdopen(protocol_fd, "w", encoding="utf-8", closefd=False) as wire:
            async with stdio_server(stdout=anyio.wrap_file(wire)) as (reader, writer):
                await server.run(reader, writer, server.create_initialization_options())
    finally:
        sys.stdout.flush()
        os.dup2(protocol_fd, sys.stdout.fileno())
        os.close(protocol_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local MVS MCP server (stdio only).")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--read-root", required=True)
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        import anyio
        import mcp  # Check the optional SDK before creating a workspace.
        from mvs.workflow import WorkflowService, WorkflowError
        service = WorkflowService(engine=args.engine, read_root=args.read_root,
                                  work_root=args.work_root, timeout_seconds=args.timeout_seconds)
        anyio.run(serve_stdio, service)
    except ImportError:
        print("Install the optional dependency: pip install 'mvs-analyzer[mcp]'", file=sys.stderr)
        return 1
    except (WorkflowError, RuntimeError, ValueError, OSError) as exc:
        print(f"MVS MCP startup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
