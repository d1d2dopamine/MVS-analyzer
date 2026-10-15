"""Real official-SDK stdio/wire tests; the dispatcher/child below are test doubles.

These checks establish MCP behavior, not native statistical correctness. Native
workflow/engine parity is covered separately by the workflow service tests.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SDK_AVAILABLE = importlib.util.find_spec("mcp") is not None
LINUX_SDK = SDK_AVAILABLE and sys.platform.startswith("linux")
SOURCE = Path(__file__).resolve().parents[1] / "src"
NAMES = {"register_protocol", "get_protocol", "run_analysis", "get_run", "read_artifact"}

# Runs the production adapter/official SDK in another process. Only the shared
# workflow service is substituted; this synthetic child is NOT the MVS engine.
FAKE_SERVER = r'''
import json, os, pathlib, subprocess, sys, time
import anyio
from mvs.mcp_server import READINESS, serve_stdio
root = pathlib.Path(sys.argv[1])
class Service:
    def dispatch(self, operation, params, cancel_event=None):
        with (root / "calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"operation": operation, "params": params}) + "\n")
        print("Python diagnostic, never JSON-RPC", flush=True)
        os.write(1, b"Descriptor diagnostic, never JSON-RPC\n")
        if params.get("run_id") == "throw":
            raise RuntimeError("private-path-that-must-not-be-returned")
        if operation == "run_analysis" and params["run_id"] == "slow":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            (root / "started").write_text(str(child.pid))
            try:
                while not cancel_event.wait(0.01):
                    pass
                (root / "cancelled").write_text("yes")
                # Visible stopping interval checks that the run slot remains held.
                time.sleep(0.3)
            finally:
                child.terminate()
                child.wait(timeout=2)
                (root / "reaped").write_text(str(child.returncode))
            return {"schemaVersion": "mvs-workflow-result/v1",
                    "execution": {"status": "cancelled", "nativeExitCode": None},
                    "scientificReadiness": READINESS, "data": None, "error": None}
        return {"schemaVersion": "mvs-workflow-result/v1",
                "execution": {"status": "completed", "nativeExitCode": 0},
                "scientificReadiness": READINESS,
                "data": {"operation": operation, "params": params}, "error": None}
anyio.run(serve_stdio, Service())
'''


def environment():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SOURCE) + os.pathsep + env.get("PYTHONPATH", "")
    return env


class Wire:
    """Small raw JSON-RPC client used to inspect exact official-server framing."""
    def __init__(self, root: Path, command=None):
        self.root = root
        self.stderr = (root / "stderr.txt").open("w+")
        self.proc = subprocess.Popen(
            command or [sys.executable, "-u", "-c", FAKE_SERVER, str(root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            env=environment(), text=True, bufsize=1,
        )
        self.next_id = 1

    def send(self, method, params=None, *, request_id=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            request_id = self.next_id if request_id is None else request_id
            self.next_id = max(self.next_id, request_id + 1)
            message["id"] = request_id
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        return request_id

    def receive(self, timeout=10):
        if not select.select([self.proc.stdout], [], [], timeout)[0]:
            raise AssertionError("Timed out waiting for MCP response")
        line = self.proc.stdout.readline()
        if not line:
            self.stderr.flush()
            raise AssertionError("MCP process closed stdout: " + (self.root / "stderr.txt").read_text())
        return json.loads(line)

    def request(self, method, params=None):
        request_id = self.send(method, params)
        response = self.receive()
        if response.get("id") != request_id:
            raise AssertionError(f"Unexpected response ID: {response}")
        return response

    def initialize(self, version="2025-11-25"):
        result = self.request("initialize", {
            "protocolVersion": version, "capabilities": {},
            "clientInfo": {"name": "mvs-wire-test", "version": "1.0"},
        })
        self.send("notifications/initialized", notification=True)
        return result

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})["result"]

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
            raise AssertionError("Adapter did not exit after stdin closed")
        finally:
            self.proc.stdout.close()
            self.stderr.close()


def wait_for(path: Path, timeout=5):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for fixture {path.name}")
        time.sleep(0.01)


@unittest.skipUnless(LINUX_SDK, "requires Linux and optional official MCP SDK")
class McpWireTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.wire = Wire(self.root)

    def tearDown(self):
        self.wire.close()
        self.temp.cleanup()

    def test_initialize_discovery_and_fixed_resource(self):
        reply = self.wire.initialize()["result"]
        self.assertEqual(reply["protocolVersion"], "2025-11-25")
        self.assertEqual(reply["serverInfo"]["name"], "mvs-workflow")
        listed = self.wire.request("tools/list")["result"]["tools"]
        self.assertEqual({tool["name"] for tool in listed}, NAMES)
        self.assertEqual(len(listed), 5)
        for tool in listed:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
        resources = self.wire.request("resources/list")["result"]["resources"]
        self.assertEqual([r["uri"] for r in resources], ["mvs://capabilities"])
        self.assertEqual(self.wire.request("resources/templates/list")["result"]["resourceTemplates"], [])
        data = self.wire.request("resources/read", {"uri": "mvs://capabilities"})
        resource = json.loads(data["result"]["contents"][0]["text"])
        self.assertEqual(resource["scientificReadiness"]["status"], "no_go")
        self.assertEqual(resource["transport"], "stdio")
        self.assertEqual(resource["supportedPlatform"], "linux")
        self.assertEqual(set(resource["operations"]), NAMES)
        self.assertIn("error", self.wire.request("resources/read", {"uri": "file:///etc/passwd"}))
        self.assertIn("error", self.wire.request("arbitrary/command", {"command": "true"}))

    def test_older_protocol_negotiates_with_official_sdk(self):
        reply = self.wire.initialize("2024-11-05")["result"]
        self.assertEqual(reply["protocolVersion"], "2024-11-05")
        self.assertEqual(len(self.wire.request("tools/list")["result"]["tools"]), 5)

    def test_five_tool_calls_and_stdout_isolation(self):
        self.wire.initialize()
        cases = {
            "register_protocol": {"protocol_id": "p1", "data": "data.csv", "calibration": "state.json",
                                  "prior_exposure": "unknown", "question": "Distributional difference?"},
            "get_protocol": {"protocol_id": "p1"},
            "run_analysis": {"run_id": "r1", "data": "data.csv", "calibration": "state.json"},
            "get_run": {"run_id": "r1"},
            "read_artifact": {"run_id": "r1", "name": "results.csv"},
        }
        for name, params in cases.items():
            result = self.wire.call(name, params)
            self.assertFalse(result["isError"])
            data = result["structuredContent"]
            self.assertEqual(data, json.loads(result["content"][0]["text"]))
            self.assertEqual(data["data"], {"operation": name, "params": params})
            self.assertEqual(data["execution"]["status"], "completed")
            self.assertEqual(data["scientificReadiness"]["scope"], "project_release_readiness")
            self.assertEqual(data["scientificReadiness"]["status"], "no_go")
        diagnostics = (self.root / "stderr.txt").read_text()
        self.assertIn("Python diagnostic", diagnostics)
        self.assertIn("Descriptor diagnostic", diagnostics)

    def test_unknown_and_malformed_parameters_never_dispatch(self):
        self.wire.initialize()
        cases = [
            ("execute", {"command": "echo forbidden"}),
            ("get_run", {"run_id": "r1", "path": "/etc/passwd"}),
            ("get_run", {"run_id": 5}),
            ("get_run", {"run_id": "../escape"}),
            ("get_run", {}),
            ("run_analysis", {"run_id": "r", "data": "d", "calibration": "c", "mode": "confirmatory"}),
            ("run_analysis", {"run_id": "r", "data": "d", "calibration": "c", "mode": "frozen"}),
            ("run_analysis", {"run_id": "r", "data": "d", "calibration": "c", "protocol_id": "p"}),
            ("run_analysis", {"run_id": "r", "data": "d", "calibration": "c", "allow_group_scoped_ids": "false"}),
            ("register_protocol", {"protocol_id": "p", "data": "d", "calibration": "c",
                                   "question": "q", "prior_exposure": "proven_unseen"}),
        ]
        for name, params in cases:
            result = self.wire.call(name, params)
            self.assertTrue(result["isError"])
            self.assertIn(result["structuredContent"]["error"]["code"], {"unknown_operation", "invalid_params"})
        self.assertFalse((self.root / "calls.jsonl").exists())

    def test_dispatch_exception_is_sanitized(self):
        self.wire.initialize()
        result = self.wire.call("get_run", {"run_id": "throw"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error"]["code"], "internal_error")
        self.assertNotIn("private-path", json.dumps(result))

    def test_sdk_cancellation_signals_and_reaps_before_slot_reuse(self):
        self.wire.initialize()
        run_id = self.wire.send("tools/call", {"name": "run_analysis", "arguments": {
            "run_id": "slow", "data": "d", "calibration": "c"}})
        wait_for(self.root / "started")
        busy = self.wire.call("run_analysis", {"run_id": "r2", "data": "d", "calibration": "c"})
        self.assertEqual(busy["structuredContent"]["error"]["code"], "busy")
        began = time.monotonic()
        self.wire.send("notifications/cancelled", {"requestId": run_id, "reason": "test cancellation"},
                       notification=True)
        cancelled = self.wire.receive()
        self.assertEqual(cancelled["id"], run_id)
        self.assertIn("error", cancelled)
        wait_for(self.root / "cancelled")
        stopping = self.wire.call("run_analysis", {"run_id": "r3", "data": "d", "calibration": "c"})
        self.assertEqual(stopping["structuredContent"]["error"]["code"], "busy")
        wait_for(self.root / "reaped")
        self.assertLess(time.monotonic() - began, 5)
        pid = int((self.root / "started").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        # Reaping precedes worker return; retry only until the slot-release edge.
        deadline = time.monotonic() + 2
        while True:
            result = self.wire.call("run_analysis", {"run_id": "after", "data": "d", "calibration": "c"})
            if not result["isError"]:
                break
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(result["structuredContent"]["execution"]["status"], "completed")

    def test_transport_close_also_cancels_and_reaps(self):
        self.wire.initialize()
        self.wire.send("tools/call", {"name": "run_analysis", "arguments": {
            "run_id": "slow", "data": "d", "calibration": "c"}})
        wait_for(self.root / "started")
        self.wire.proc.stdin.close()
        self.wire.proc.wait(timeout=6)
        self.assertEqual(self.wire.proc.returncode, 0)
        self.assertTrue((self.root / "cancelled").exists())
        self.assertTrue((self.root / "reaped").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.root / "started").read_text()), 0)


    def test_real_service_receives_sdk_cancellation_and_reaps_native_test_double(self):
        # This uses the production WorkflowService and adapter, with a deliberately
        # sleeping synthetic engine. It does not claim a statistical engine run.
        self.wire.close()
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "data.csv").write_text("entity,group,value\na,A,1\n")
        (inputs / "state.json").write_text("{}")
        marker = self.root / "native-pid"
        engine = self.root / "fake-native"
        engine.write_text(f"#!{sys.executable}\nimport os, pathlib, time\n"
                          f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
                          "time.sleep(60)\n")
        engine.chmod(0o700)
        self.wire = Wire(self.root, [sys.executable, "-u", "-m", "mvs.mcp_server",
            "--engine", str(engine), "--read-root", str(inputs),
            "--work-root", str(self.root / "work"), "--timeout-seconds", "30"])
        self.wire.initialize()
        request_id = self.wire.send("tools/call", {"name": "register_protocol", "arguments": {
            "protocol_id": "cancelled", "data": "data.csv", "calibration": "state.json",
            "question": "Test cancellation only", "prior_exposure": "unknown"}})
        wait_for(marker)
        pid = int(marker.read_text())
        self.wire.send("notifications/cancelled", {"requestId": request_id}, notification=True)
        self.assertEqual(self.wire.receive()["id"], request_id)
        deadline = time.monotonic() + 5
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            self.assertLess(time.monotonic(), deadline, "Production service failed to reap native test double")
            time.sleep(0.01)
        self.assertFalse((self.root / "work" / "protocols" / "cancelled.json").exists())
        self.assertEqual(len(self.wire.request("tools/list")["result"]["tools"]), 5)


    def test_invalid_startup_configuration_has_no_traceback_or_protocol_output(self):
        result = subprocess.run([sys.executable, "-m", "mvs.mcp_server",
            "--engine", str(self.root / "missing"), "--read-root", str(self.root),
            "--work-root", str(self.root / "work")], env=environment(),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("MVS MCP startup failed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_official_client_lifecycle_and_tool(self):
        # Use the official client too, independent of the raw inspection helper.
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def exercise():
            params = StdioServerParameters(command=sys.executable,
                args=["-u", "-c", FAKE_SERVER, str(self.root)], env=environment())
            with (self.root / "client-stderr.txt").open("w") as err:
                async with stdio_client(params, errlog=err) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        initialized = await session.initialize()
                        self.assertEqual(initialized.protocolVersion, "2025-11-25")
                        self.assertEqual({t.name for t in (await session.list_tools()).tools}, NAMES)
                        result = await session.call_tool("get_run", {"run_id": "official-client"})
                        self.assertFalse(result.isError)
                        self.assertEqual(result.structuredContent["scientificReadiness"]["status"], "no_go")
        anyio.run(exercise)


@unittest.skipUnless(LINUX_SDK and all(os.environ.get(key) for key in (
    "MVS_MCP_TEST_ENGINE", "MVS_MCP_TEST_DATA", "MVS_MCP_TEST_CALIBRATION")),
    "set MVS_MCP_TEST_ENGINE/DATA/CALIBRATION for actual native wire integration")
class McpNativeIntegrationTests(unittest.TestCase):
    def test_actual_native_exploratory_and_frozen_wire_round_trip(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "inputs"
            inputs.mkdir()
            shutil.copyfile(os.environ["MVS_MCP_TEST_DATA"], inputs / "data.csv")
            shutil.copyfile(os.environ["MVS_MCP_TEST_CALIBRATION"], inputs / "state.json")
            async def exercise():
                config = StdioServerParameters(command=sys.executable, args=["-m", "mvs.mcp_server",
                    "--engine", os.environ["MVS_MCP_TEST_ENGINE"], "--read-root", str(inputs),
                    "--work-root", str(root / "work"), "--timeout-seconds", "30"], env=environment())
                with (root / "stderr.txt").open("w") as err:
                    async with stdio_client(config, errlog=err) as (reader, writer):
                        async with ClientSession(reader, writer) as session:
                            await session.initialize()
                            async def call(name, params):
                                result = await session.call_tool(name, params)
                                self.assertFalse(result.isError, result.content)
                                self.assertEqual(result.structuredContent["scientificReadiness"]["status"], "no_go")
                                return result.structuredContent
                            common = {"data": "data.csv", "calibration": "state.json"}
                            protocol = await call("register_protocol", {**common, "protocol_id": "native-p1",
                                "prior_exposure": "previously_inspected", "question": "Existing native smoke fixture"})
                            self.assertEqual(await call("get_protocol", {"protocol_id": "native-p1"}), protocol)
                            for mode in ("exploratory", "frozen"):
                                params = {**common, "run_id": mode, "mode": mode}
                                if mode == "frozen":
                                    params["protocol_id"] = "native-p1"
                                run = await call("run_analysis", params)
                                self.assertEqual(run["execution"]["nativeExitCode"], 0)
                                self.assertFalse(run["data"]["confirmatoryCertified"])
                                self.assertEqual(await call("get_run", {"run_id": mode}), run)
                                self.assertEqual(await call("run_analysis", params), run)
                                artifact = await call("read_artifact", {"run_id": mode, "name": "results.csv"})
                                self.assertTrue(artifact["data"]["text"])
            anyio.run(exercise)


class OptionalDependencyTests(unittest.TestCase):
    def test_module_and_core_api_import_without_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-S", "-c", "import mvs; import mvs.mcp_server"],
            env=environment(), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


    def test_missing_sdk_explains_optional_install(self):
        result = subprocess.run([sys.executable, "-S", "-m", "mvs.mcp_server",
            "--engine", "unused", "--read-root", "unused", "--work-root", "unused"],
            env=environment(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("mvs-analyzer[mcp]", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_help_needs_no_sdk_and_only_configures_local_stdio(self):
        result = subprocess.run([sys.executable, "-S", "-m", "mvs.mcp_server", "--help"],
                                env=environment(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--read-root", result.stdout)
        self.assertIn("--work-root", result.stdout)
        self.assertNotIn("--host", result.stdout)
        self.assertNotIn("--port", result.stdout)


if __name__ == "__main__":
    unittest.main()
