"""Round36 current-invocation artifact boundaries; synthetic protocol evidence."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mvs.engine import Engine, EngineCompatibilityError, EngineError, InputError, _result_from_payload
from mvs.models import AnalysisResult, Artifact, BaseResult, Calibration


SCOPE = "current_invocation_successful_writes"


def record(path):
    return Artifact(path.name, path, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def payload(output, artifacts, **extra):
    return {"schemaVersion": "mvs-cli-result/v1", "command": "analyze", "status": "completed",
            "exitCode": 0, "engineVersion": "synthetic", "applicationVersion": "synthetic",
            "cliProtocol": {"name": "mvs-cli", "major": 1}, "outputDirectory": str(output),
            "artifactScope": SCOPE,
            "artifacts": [{"name": a.name, "path": str(a.path), "sizeBytes": a.size_bytes,
                           "sha256": a.sha256} for a in artifacts], **extra}


class ArtifactScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "output"
        self.output.mkdir()
        self.current = self.output / "results.csv"
        self.current.write_bytes(b"metric,value\nmean,2\n")
        self.item = record(self.current)
        self.stale = self.output / "stale.json"
        self.stale.write_bytes(b'{"stale":true}')
        self.input = self.output / "input.csv"
        self.input.write_bytes(b"private,input\n1,2\n")
        (self.output / "old-subdirectory").mkdir()
        (self.output / "old-subdirectory/private.txt").write_bytes(b"old")
        self.outside = self.root / "outside.txt"
        self.outside.write_bytes(b"outside secret")
        self.result = BaseResult("analyze", "completed", 0, self.output, None, "synthetic", "synthetic",
                                 None, (self.item,), raw={"artifactScope": SCOPE})

    def assert_rejected_without_destination(self, result, exception=ValueError):
        target = self.root / "absent-parent" / "copy"
        with self.assertRaises(exception):
            result.copy_to(target)
        self.assertFalse(target.parent.exists())

    def test_completed_and_diagnostic_lookup_never_fall_back_to_stale_or_input_files(self):
        for status, code in [("completed", 0), ("diagnostic", 2)]:
            result = replace(self.result, status=status, exit_code=code)
            with self.subTest(status=status):
                self.assertEqual(result.artifact("results.csv"), self.current)
                self.assertEqual(result.read_csv("results.csv"), [{"metric": "mean", "value": "2"}])
                for name in ["stale.json", "input.csv", "old-subdirectory", str(self.current),
                             "../outside.txt", str(self.outside)]:
                    with self.subTest(name=name), self.assertRaises(FileNotFoundError):
                        result.artifact(name)

    def test_completed_and_diagnostic_copy_only_current_listed_files(self):
        for status, code in [("completed", 0), ("diagnostic", 2)]:
            result = replace(self.result, status=status, exit_code=code)
            target = self.root / status / "copy"
            with self.subTest(status=status):
                self.assertEqual(result.copy_to(target), target)
                self.assertEqual([p.name for p in target.iterdir()], ["results.csv"])
                self.assertEqual((target / "results.csv").read_bytes(), self.current.read_bytes())
                self.assertEqual(self.input.read_bytes(), b"private,input\n1,2\n")

    def test_empty_scoped_list_copies_empty_directory_without_enumeration(self):
        result = replace(self.result, artifacts=())
        with self.assertRaises(FileNotFoundError):
            result.artifact("results.csv")
        target = self.root / "empty"
        result.copy_to(target)
        self.assertEqual(list(target.iterdir()), [])

    def test_failed_scoped_result_keeps_explicit_partial_lookup_and_refuses_copy(self):
        result = replace(self.result, status="error", exit_code=1)
        self.assertEqual(result.artifact("results.csv"), self.current)
        result.verify_artifacts()
        with self.assertRaises(FileNotFoundError):
            result.artifact("stale.json")
        with self.assertRaisesRegex(ValueError, "incomplete output"):
            result.copy_to(self.root / "failed")
        self.assertFalse((self.root / "failed").exists())

    def test_unmarked_results_keep_legacy_lookup_and_recursive_copy(self):
        result = replace(self.result, raw={})
        self.assertEqual(result.artifact("stale.json"), self.stale)
        target = self.root / "legacy"
        result.copy_to(target)
        self.assertEqual((target / "input.csv").read_bytes(), self.input.read_bytes())
        self.assertEqual((target / "old-subdirectory/private.txt").read_bytes(), b"old")
        failed = replace(result, status="error", exit_code=1)
        self.assertEqual(failed.artifact("results.csv"), self.current)
        with self.assertRaises(FileNotFoundError):
            failed.artifact("stale.json")
        self.assert_rejected_without_destination(failed)

    def test_unknown_or_invalid_scope_never_falls_back(self):
        for value in [None, "", "directory_snapshot", False, 1, [], {}, [SCOPE]]:
            result = replace(self.result, raw={"artifactScope": value})
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Unsupported artifact scope"):
                    result.artifact("results.csv")
                with self.assertRaises(ValueError):
                    result.verify_artifacts()
                self.assert_rejected_without_destination(result)

    def test_duplicate_names_fail_closed_including_case_collisions(self):
        upper = self.output / "RESULTS.CSV"
        upper.write_bytes(self.current.read_bytes())
        for other in [self.item, record(upper)]:
            result = replace(self.result, artifacts=(self.item, other))
            with self.subTest(name=other.name):
                with self.assertRaisesRegex(ValueError, "Duplicate"):
                    result.artifact("results.csv")
                self.assert_rejected_without_destination(result)

    def test_unsafe_names_fail_closed_before_read_or_destination_creation(self):
        names = ["", ".", "..", "../outside.txt", "nested/file", "nested\\file", "/outside.txt",
                 "C:outside", "file\x00", "file\n", "file\x7f", "file.", "file ", "a?b", "a*b",
                 "a<b", "a>b", 'a"b', "a|b", "CON", "nul.txt", "COM1.log", "LPT9", None, 42]
        for name in names:
            result = replace(self.result, artifacts=(replace(self.item, name=name),))
            with self.subTest(name=name), patch("pathlib.Path.open") as opened:
                self.assert_rejected_without_destination(result)
                opened.assert_not_called()

    def test_outside_nested_mismatched_and_traversing_paths_are_rejected(self):
        candidates = [self.outside, self.stale, self.output / "nested/results.csv",
                      self.output / "../output/results.csv", Path("results.csv")]
        for path in candidates:
            result = replace(self.result, artifacts=(replace(self.item, path=path),))
            with self.subTest(path=path), patch("pathlib.Path.open") as opened:
                self.assert_rejected_without_destination(result)
                with self.assertRaises(ValueError):
                    result.artifact("results.csv")
                opened.assert_not_called()

    def test_invalid_root_is_rejected(self):
        for output in [None, Path("output"), self.root / "../output", self.current]:
            result = replace(self.result, output_directory=output)
            with self.subTest(output=output):
                self.assert_rejected_without_destination(result, (ValueError, FileNotFoundError))

    def test_missing_file_is_rejected_before_destination_creation(self):
        self.current.unlink()
        self.assert_rejected_without_destination(self.result, FileNotFoundError)

    def test_nonregular_listed_file_is_rejected_without_reading(self):
        self.current.unlink()
        self.current.mkdir()
        with patch("pathlib.Path.open") as opened:
            self.assert_rejected_without_destination(self.result)
            opened.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_fifo_is_rejected_without_opening_or_blocking(self):
        self.current.unlink()
        os.mkfifo(self.current)
        with patch("pathlib.Path.open") as opened:
            self.assert_rejected_without_destination(self.result)
            opened.assert_not_called()

    def test_symlink_to_inside_or_outside_is_rejected_without_reading(self):
        self.current.unlink()
        for target in [self.stale, self.outside]:
            try:
                self.current.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
            with self.subTest(target=target), patch("pathlib.Path.open") as opened:
                self.assert_rejected_without_destination(self.result)
                opened.assert_not_called()
            self.current.unlink()

    def test_symlink_output_directory_is_rejected(self):
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.output, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        result = replace(self.result, output_directory=alias,
                         artifacts=(replace(self.item, path=alias / self.item.name),))
        self.assert_rejected_without_destination(result)

    def test_symlink_ancestor_cannot_redirect_an_otherwise_regular_output(self):
        alias = self.root / "parent-alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        output = alias / "output"
        result = replace(self.result, output_directory=output,
                         artifacts=(replace(self.item, path=output / self.item.name),))
        with patch("pathlib.Path.open") as opened:
            self.assert_rejected_without_destination(result)
            with self.assertRaises(ValueError):
                result.artifact("results.csv")
            opened.assert_not_called()

    def test_symlink_destination_ancestor_is_rejected_before_creation(self):
        alias = self.root / "target-alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        with self.assertRaises(ValueError):
            self.result.copy_to(alias / "new-parent" / "copy")
        self.assertFalse((self.root / "new-parent").exists())

    def test_unlisted_symlink_and_directory_do_not_enter_copy(self):
        try:
            (self.output / "private-link").symlink_to(self.outside)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        target = self.root / "copy"
        self.result.copy_to(target)
        self.assertEqual([p.name for p in target.iterdir()], ["results.csv"])

    def test_changed_size_or_same_size_content_is_rejected(self):
        for content in [b"different size", b"x" * self.item.size_bytes]:
            self.current.write_bytes(content)
            with self.subTest(content=content):
                self.assert_rejected_without_destination(self.result)
                with self.assertRaises(ValueError):
                    self.result.verify_artifacts()
                with self.assertRaises(ValueError):
                    self.result.artifact("results.csv")

    def test_missing_or_malformed_identity_is_rejected(self):
        changes = [{"size_bytes": None}, {"size_bytes": True}, {"size_bytes": -1}, {"size_bytes": 20.0},
                   {"sha256": None}, {"sha256": ""}, {"sha256": "g" * 64}, {"sha256": 42},
                   {"sha256": "0" * 63}]
        for change in changes:
            with self.subTest(change=change):
                self.assert_rejected_without_destination(replace(self.result, artifacts=(replace(self.item, **change),)))

    def test_uppercase_checksum_is_accepted(self):
        result = replace(self.result, artifacts=(replace(self.item, sha256=self.item.sha256.upper()),))
        self.assertEqual(result.artifact("results.csv"), self.current)
        result.copy_to(self.root / "upper")

    def test_all_files_are_preflighted_before_destination_creation(self):
        changed = record(self.stale)
        self.stale.write_bytes(b"changed")
        self.assert_rejected_without_destination(replace(self.result, artifacts=(self.item, changed)))

    def test_destination_and_dangling_symlink_are_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        (target / "keep.txt").write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            self.result.copy_to(target)
        self.assertEqual((target / "keep.txt").read_bytes(), b"keep")
        link = self.root / "dangling"
        try:
            link.symlink_to(self.root / "absent")
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        with self.assertRaises(FileExistsError):
            self.result.copy_to(link)
        self.assertTrue(link.is_symlink())

    def test_manifest_must_be_listed_and_match_declared_path(self):
        manifest = self.output / "run_manifest.json"
        manifest.write_bytes(b'{"runId":"current"}')
        result = replace(self.result, manifest_path=manifest)
        with self.assertRaises(FileNotFoundError):
            _ = result.manifest
        result = replace(result, artifacts=(*result.artifacts, record(manifest)))
        self.assertEqual(result.manifest.data, {"runId": "current"})
        outside_manifest = self.root / manifest.name
        outside_manifest.write_bytes(b'{"runId":"outside"}')
        with self.assertRaisesRegex(ValueError, "Manifest path"):
            _ = replace(result, manifest_path=outside_manifest).manifest

    def test_calibration_state_lookup_obeys_scoped_list(self):
        state = self.output / "calibration_state.json"
        state.write_bytes(b"{}")
        calibration = Calibration(**self.result.__dict__)
        with self.assertRaises(FileNotFoundError):
            _ = calibration.state_path
        calibration = replace(calibration, artifacts=(record(state),))
        self.assertEqual(calibration.state_path, state)

    def test_analyze_rejects_unlisted_missing_changed_or_unknown_scope_calibration_without_launch(self):
        state = self.output / "calibration_state.json"
        state.write_bytes(b"{}")
        state_artifact = record(state)
        calibration = replace(Calibration(**self.result.__dict__), command="calibrate")
        engine = object.__new__(Engine)
        engine.executable = "synthetic-cli"
        cases = [
            ("unlisted", calibration, lambda: None),
            ("unknown_scope", replace(calibration, raw={"artifactScope": "all_files"}), lambda: None),
            ("changed", replace(calibration, artifacts=(state_artifact,)), lambda: state.write_bytes(b"[]")),
            ("missing", replace(calibration, artifacts=(state_artifact,)), state.unlink),
        ]
        for name, result, mutate in cases:
            mutate()
            with self.subTest(name=name), patch("mvs.engine.subprocess.run") as run:
                with self.assertRaisesRegex(InputError, "invalid scoped calibration state") as caught:
                    engine.analyze("input.csv", calibration=result, output=self.root / "analysis")
                self.assertIs(caught.exception.result, result)
                run.assert_not_called()
                self.assertFalse((self.root / "analysis").exists())

    def test_analyze_uses_verified_state_file_for_scoped_calibration_and_legacy_directory_otherwise(self):
        state = self.output / "calibration_state.json"
        state.write_bytes(b"{}")
        calibration = replace(Calibration(**self.result.__dict__), command="calibrate", artifacts=(record(state),))
        engine = object.__new__(Engine)
        engine.executable = "synthetic-cli"
        response = subprocess.CompletedProcess([], 0, json.dumps(payload(self.output, (self.item,))), "")
        cases = [(calibration, state),
                 (replace(calibration, status="diagnostic", exit_code=2), state),
                 (replace(calibration, raw={}), self.output)]
        for result, expected in cases:
            with self.subTest(raw=result.raw, status=result.status):
                with patch("mvs.engine.subprocess.run", return_value=response) as run:
                    engine.analyze("input.csv", calibration=result, output=self.root / "analysis")
                args = run.call_args.args[0]
                self.assertEqual(args[args.index("--calibration") + 1], str(expected))

    def test_copy_error_propagates_and_may_leave_documented_partial_destination(self):
        result = replace(self.result, artifacts=(self.item, record(self.stale)))
        target = self.root / "partial-copy"
        real_copy = shutil.copy2
        count = 0

        def copy(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic disk failure")
            return real_copy(*args, **kwargs)

        with patch("mvs.models.shutil.copy2", side_effect=copy):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                result.copy_to(target)
        self.assertEqual((target / "results.csv").read_bytes(), self.current.read_bytes())
        self.assertFalse((target / "stale.json").exists())
        self.assertIn("not a transaction", BaseResult.copy_to.__doc__)

    def test_corruption_during_copy_is_not_reported_as_success(self):
        real_copy = shutil.copy2

        def corrupt(source, target, **kwargs):
            result = real_copy(source, target, **kwargs)
            Path(target).write_bytes(b"x" * self.item.size_bytes)
            return result

        with patch("mvs.models.shutil.copy2", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.result.copy_to(self.root / "corrupted")

    def test_parser_preserves_scope_raw_and_typed_artifact_identity(self):
        data = payload(self.output, (self.item,))
        result = _result_from_payload(data, AnalysisResult)
        self.assertEqual(result.raw, data)
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.artifacts, (self.item,))
        self.assertEqual(result.artifact("results.csv"), self.current)
        with self.assertRaises(FileNotFoundError):
            result.artifact("stale.json")

    def test_parser_rejects_unknown_or_invalid_marker(self):
        for scope in [None, "", "all_files", 1, True, [], {}]:
            with self.subTest(scope=scope), self.assertRaises(EngineCompatibilityError):
                _result_from_payload(payload(self.output, (self.item,), artifactScope=scope), BaseResult)

    def test_parser_never_silently_skips_or_coerces_scoped_records(self):
        data = payload(self.output, (self.item,))
        valid = data["artifacts"][0]
        records = [None, {}, "invalid", [None], [valid, None], [{}],
                   [valid | {"name": 42}], [valid | {"path": None}], [valid | {"path": 42}],
                   [valid | {"path": ""}], [valid | {"sizeBytes": True}], [valid | {"sha256": None}],
                   [valid | {"name": "../escape"}]]
        for artifacts in records:
            with self.subTest(artifacts=artifacts), self.assertRaises(EngineCompatibilityError):
                _result_from_payload(data | {"artifacts": artifacts}, BaseResult)
        missing = dict(data)
        del missing["artifacts"]
        with self.assertRaises(EngineCompatibilityError):
            _result_from_payload(missing, BaseResult)

    def test_unmarked_parser_preserves_old_permissive_artifact_handling(self):
        data = payload(self.output, (self.item,))
        del data["artifactScope"]
        data["artifacts"].extend([None, {}])
        result = _result_from_payload(data, BaseResult)
        self.assertNotIn("artifactScope", result.raw)
        self.assertEqual(result.artifacts, (self.item,))
        self.assertEqual(result.artifact("stale.json"), self.stale)

    def test_engine_completed_diagnostic_and_error_paths_preserve_scope(self):
        cli = self.root / "synthetic-cli"
        cli.write_text("fixture", encoding="utf-8")
        identity = payload(self.output, (), command="version")
        del identity["artifactScope"]
        with patch("mvs.engine.subprocess.run", return_value=subprocess.CompletedProcess([], 0, json.dumps(identity), "")):
            engine = Engine(cli)
        for status, code in [("completed", 0), ("diagnostic", 2), ("error", 1)]:
            data = payload(self.output, (self.item,), status=status, exitCode=code,
                           error={"type": "IOException", "message": "synthetic failure"})
            process = subprocess.CompletedProcess([], code, json.dumps(data), "")
            with self.subTest(status=status), patch("mvs.engine.subprocess.run", return_value=process):
                if code == 1:
                    with self.assertRaises(EngineError) as caught:
                        engine.analyze("input.csv", calibration="state.json", output=self.output)
                    result = caught.exception.result
                else:
                    result = engine.analyze("input.csv", calibration="state.json", output=self.output,
                                            allow_diagnostic=True)
                self.assertEqual(result.raw["artifactScope"], SCOPE)
                self.assertEqual(result.artifact("results.csv"), self.current)
                with self.assertRaises(FileNotFoundError):
                    result.artifact("stale.json")


if __name__ == "__main__":
    unittest.main()
