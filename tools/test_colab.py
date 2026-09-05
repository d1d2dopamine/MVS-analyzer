#!/usr/bin/env python3
"""Offline regression tests for the Python Colab transport/orchestration, not .NET execution."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mvs_colab", ROOT / "notebooks/mvs_colab.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ColabTests(unittest.TestCase):
    def test_explicit_host_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            host = Path(sys.executable).resolve()
            dll = base / "mvs.dll"
            dll.write_text('import json,os,sys\nprint(json.dumps({"argv":sys.argv[1:],"root":os.environ["DOTNET_ROOT"],"x64":os.environ["DOTNET_ROOT_X64"]}))\n', encoding="utf-8")
            command = m.cli_command(host, dll, "version")
            self.assertEqual(command[:2], [str(host), str(dll)])
            answer = json.loads(subprocess.check_output(command, env=m.dotnet_environment(host), text=True))
            self.assertEqual(answer["argv"], ["version"])
            self.assertEqual(answer["root"], str(host.parent))
            self.assertEqual(answer["x64"], str(host.parent))

    def test_zip_traversal(self):
        for name in ("../bad", "/tmp/bad", "C:/bad", "a\\b"):
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(name, "bad")
            archive.seek(0)
            with tempfile.TemporaryDirectory() as target, self.assertRaises(ValueError):
                m.safe_extract(archive, target)

    def test_zip_size_and_symlink(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("large", "a" * 50)
        archive.seek(0)
        with tempfile.TemporaryDirectory() as target, self.assertRaises(ValueError):
            m.safe_extract(archive, target, max_bytes=10)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            z.writestr(info, "../../bad")
        archive.seek(0)
        with tempfile.TemporaryDirectory() as target, self.assertRaises(ValueError):
            m.safe_extract(archive, target)

    def test_normal_archive(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Core/example.cs", "source")
        archive.seek(0)
        with tempfile.TemporaryDirectory() as target:
            m.safe_extract(archive, target)
            self.assertEqual((Path(target) / "Core/example.cs").read_text(), "source")

    def test_case_insensitive_fields(self):
        self.assertEqual(m.ci({"DatasetHash": "abc"}, "datasetHash"), "abc")

    def test_notebook_url_detection(self):
        payload = json.dumps([{"path": "/fileId=abcdefghij0123456789", "name": "MVS.ipynb"}]).encode()
        urls = []
        def request(url, **kwargs):
            urls.append(url)
            return io.BytesIO(payload)
        with patch.object(m.urllib.request, "urlopen", request):
            self.assertEqual(m.notebook_url(), "https://colab.research.google.com/drive/abcdefghij0123456789")
        self.assertTrue(urls[0].startswith("http://"))
        self.assertNotIn("{", urls[0])

    def test_notebook_url_unavailable_is_not_invented(self):
        with patch.object(m.urllib.request, "urlopen", side_effect=OSError("blocked")):
            self.assertEqual(m.notebook_url(), "")

    def test_strict_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.json"
            path.write_text('{"x":NaN}')
            with self.assertRaises(ValueError):
                m.strict_json(path)

    def fixture(self, directory):
        workspace = m.Workspace.__new__(m.Workspace)
        workspace.root = Path(directory)
        workspace.folder = workspace.root / "job"
        workspace.folder.mkdir()
        workspace.plan = {"Key": "a" * 64, "DatasetHash": "b" * 64, "SettingsHash": "c" * 64, "Repetitions": 150, "Kind": "standard", "Revision": m.REVISION}
        workspace.connection = ""
        workspace.epoch = "test-epoch-123"
        workspace.url = ""
        workspace.sequence = 0
        workspace.command_id = ""
        workspace.controls_ready = False
        workspace.percent = None
        workspace.message = ""
        workspace.runtime_label = "Python test · CPU"
        workspace._monitor = None
        workspace._files_pending = False
        workspace.last_notice = ""
        workspace.phase = "ready"
        workspace.input = workspace.folder / "data.csv"
        workspace.input.write_text("input")
        workspace.state_path.parent.mkdir()
        state = {"SchemaVersion": 2, "AppVersion": m.APP_VERSION, "EngineVersion": m.ENGINE_VERSION, "FormulaHash": m.FORMULA_HASH,
                 "DatasetHash": "b" * 64, "SettingsHash": "c" * 64, "Repetitions": 150, "Rows": [{} for _ in range(12)], "PayloadHash": "d" * 64}
        workspace.state_path.write_text(json.dumps(state))
        return workspace, state

    def test_calibration_matches_exact_job(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, state = self.fixture(directory)
            self.assertTrue(workspace.has_calibration())
            for key, value in [("DatasetHash", "e" * 64), ("SettingsHash", "f" * 64), ("Repetitions", 151), ("EngineVersion", "old"), ("PayloadHash", "")]:
                bad = dict(state); bad[key] = value
                workspace.state_path.write_text(json.dumps(bad))
                self.assertFalse(workspace.has_calibration(), key)

    def test_completed_calibration_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            calls = []
            workspace.refresh = lambda: None
            workspace.native_state_check = lambda: calls.append("state-check")
            workspace.send = lambda **kwargs: calls.append("status")
            workspace.run_process = lambda *args, **kwargs: self.fail("A completed calibration was re-executed")
            with contextlib.redirect_stdout(io.StringIO()):
                workspace.calibrate()
                workspace.calibrate()
            self.assertEqual(calls.count("state-check"), 2)
            self.assertEqual(workspace.phase, "calibrated")

    def test_nested_analysis_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(m.find_run_folder(root))
            folder = root / "MVS_2026_test"
            folder.mkdir()
            (folder / "results.json").write_text('{"rows":[]}')
            manifest = {"files": [{"FileName": "results.json", "sha256": m.sha(folder / "results.json")}], "inputData": {"sha256": "correct"}}
            (folder / "run_manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(m.find_run_folder(root), folder)
            m.validate_manifest(folder, "correct")
            with self.assertRaises(ValueError):
                m.validate_manifest(folder, "wrong")
            (folder / "results.json").write_text("tampered")
            with self.assertRaises(ValueError):
                m.validate_manifest(folder, "correct")

    def test_benchmark_manifest_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "benchmark_run"
            root.mkdir()
            (root / "figures").mkdir()
            (root / "figures/a.svg").write_text("<svg/>")
            (root / "benchmark_manifest.json").write_text('{"files":["figures/a.svg"]}')
            (root / "SHA256SUMS.txt").write_text(m.sha(root / "benchmark_manifest.json") + "  benchmark_manifest.json\n" + m.sha(root / "figures/a.svg") + "  figures/a.svg\n")
            self.assertEqual(m.find_run_folder(Path(directory)), root)
            m.validate_manifest(root)

    def test_connection_code_is_loopback_only(self):
        # Validation runs before evaluating browser JavaScript.
        fake_output = type("Output", (), {"eval_js": staticmethod(lambda script, **kwargs: {"ok": True, "value": {}})})
        fake_colab = type("Colab", (), {"output": fake_output})
        with patch.dict(sys.modules, {"google.colab": fake_colab}):
            for base in ("https://example.com", "http://0.0.0.0:80/v1/" + "a" * 64, "http://127.0.0.1:80/v1/short"):
                with self.assertRaises(ValueError):
                    m.browser_request(base, "request")
            self.assertEqual(m.browser_request("http://127.0.0.1:8123/v1/" + "a" * 64, "request"), {})


    def test_calibration_failures_do_not_complete(self):
        for error, expected in [(RuntimeError("failed"), "failed"), (KeyboardInterrupt(), "cancelled")]:
            with tempfile.TemporaryDirectory() as directory:
                workspace, _ = self.fixture(directory)
                workspace.state_path.unlink()
                workspace.job = {}
                workspace.dotnet = Path(directory) / "fake-host"
                workspace.dll = Path(directory) / "mvs.dll"
                workspace.refresh = lambda: None
                workspace.send = lambda **kwargs: None
                def fail(*args, **kwargs):
                    raise error
                workspace.run_process = fail
                with self.assertRaises(type(error)):
                    workspace.calibrate()
                self.assertEqual(workspace.phase, expected)
                self.assertFalse(workspace.has_calibration())

    def test_diagnostic_is_not_success_on_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.plan["Kind"] = "melsm"
            workspace.refresh = lambda: None
            workspace.send = lambda **kwargs: None
            folder = workspace.folder / "melsm"
            folder.mkdir()
            (folder / "run_manifest.json").write_text(json.dumps({"files": [], "inputData": {"sha256": "b" * 64}}))
            (folder / "completion.json").write_text('{"exitCode":2}')
            with contextlib.redirect_stdout(io.StringIO()):
                workspace.analyze()
            self.assertEqual(workspace.phase, "failed")

    def test_download_normalizes_nested_results_and_excludes_input(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            folder = workspace.folder / "analysis/nested-run"
            folder.mkdir(parents=True)
            (folder / "results.json").write_text('{"rows":[]}')
            (folder / "run_manifest.json").write_text(json.dumps({"files": [{"fileName": "results.json", "sha256": m.sha(folder / "results.json")}],
                "inputData": {"sha256": "b" * 64}, "calibration": {"settingsHash": "c" * 64}}))
            workspace.native_state_check = lambda: None
            workspace.send = lambda **kwargs: None
            downloaded = []
            fake_files = type("Files", (), {"download": staticmethod(downloaded.append)})
            fake_colab = type("Colab", (), {"files": fake_files})
            with patch.dict(sys.modules, {"google.colab": fake_colab}):
                archive = workspace.download()
            with zipfile.ZipFile(archive) as z:
                self.assertIn("analysis/results.json", z.namelist())
                self.assertIn("analysis/run_manifest.json", z.namelist())
                self.assertIn("calibration/calibration_state.json", z.namelist())
                self.assertNotIn("data.csv", z.namelist())
                self.assertFalse(any("nested-run" in name for name in z.namelist()))
            self.assertEqual(downloaded, [str(archive)])

    def test_manifest_cannot_escape_run_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("../outside", "C:/outside", "/tmp/outside", "a\\b"):
                with self.assertRaises(ValueError):
                    m.output_path(directory, name)

    def test_native_check_receives_profile_and_exact_job(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.dotnet = Path(directory) / "fake-host"
            workspace.dll = Path(directory) / "mvs.dll"
            (workspace.folder / "job.json").write_text('{}')
            calls = []
            workspace.run_process = lambda command: calls.append(command)
            workspace.native_state_check()
            command = calls[0]
            self.assertIn("--job", command)
            self.assertIn("--normalize", command)
            self.assertEqual(command[command.index("--settings-hash") + 1], m.ci(workspace.plan, "SettingsHash"))
            self.assertEqual(command[command.index("--repetitions") + 1], str(m.ci(workspace.plan, "Repetitions")))

    def test_legacy_metadata_is_verified_before_python_identity_check(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, state = self.fixture(directory)
            expected = m.ci(workspace.plan, "SettingsHash")
            state["SettingsHash"] = "legacy-windows-fingerprint"
            workspace.state_path.write_text(json.dumps(state))
            self.assertFalse(workspace.has_calibration())
            calls = []
            def native_migration():
                calls.append("native-verified-first")
                state["SettingsHash"] = expected
                workspace.state_path.write_text(json.dumps(state))
            workspace.native_state_check = native_migration
            workspace.prepare_calibration()
            self.assertEqual(calls, ["native-verified-first"])
            self.assertTrue(workspace.has_calibration())
            self.assertEqual(workspace.phase, "calibrated")

    def test_failed_native_checksum_is_never_marked_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.phase = "preparing"
            before = workspace.state_path.read_bytes()
            def fail():
                raise RuntimeError("checksum mismatch")
            workspace.native_state_check = fail
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                workspace.prepare_calibration()
            self.assertEqual(workspace.state_path.read_bytes(), before)
            self.assertNotEqual(workspace.phase, "calibrated")

    def test_new_job_without_state_does_not_invoke_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.state_path.unlink()
            workspace.native_state_check = lambda: self.fail("no state to validate")
            workspace.prepare_calibration()
            self.assertEqual(workspace.phase, "ready")

if __name__ == "__main__":
    unittest.main(verbosity=2)
