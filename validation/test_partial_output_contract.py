"""Partial-output engineering contract checks; no native work at discovery.

Pure corruption tests always run. Set MVS_PARTIAL_OUTPUT_RESULTS to an actual
PartialOutputHarness report.json to enable saved-native-evidence checks. Build
and invoke the .NET harness explicitly with --candidate and --out; --baseline
is optional. Missing or malformed explicitly supplied evidence fails, never
silently skips. No numerical experiment or scientific validation is performed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest


REQUIRED_CASES = {
    "candidate_late_calibration", "current_files_only",
    "failed_rewrite_invalidates_previous_success", "mutation_omits_changed_file",
    "deletion_omits_deleted_file", "unreadable_omits_locked_file",
    "unreadable_at_capture_is_unverified", "reset_clears_partial_state",
    "disabled_tracking_has_no_emission", "cancellation_retains_successful_files",
    "preflight_failure_has_no_output_context", "success_payload_contract",
    "diagnostic_payload_has_no_partial_output", "exporter_manifest_write_failure",
}
BASELINE_CASES = {
    "baseline_late_calibration_counterexample", "success_payload_matches_baseline",
}


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON property: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique, parse_constant=invalid)


def validate_partial(payload, expected_names=None):
    """Check an actual error payload against its retained current-write files."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(payload.get("schemaVersion") == "mvs-cli-result/v1", "Wrong schema")
    require(payload.get("status") == "error" and payload.get("exitCode") == 1,
            "Partial output is not an error")
    require(payload.get("execution") == {"completed": False, "outcome": "failed"},
            "Partial output claims completion")
    folder_text = payload.get("outputDirectory")
    require(isinstance(folder_text, str) and Path(folder_text).is_absolute(),
            "Missing absolute outputDirectory")
    folder = Path(folder_text)
    require(folder.is_dir(), "Output directory is absent")
    partial = payload.get("partialOutput")
    require(isinstance(partial, dict), "Missing partialOutput")
    require(partial.get("status") == "incomplete" and
            partial.get("scope") == "current_invocation_successful_writes",
            "Incorrect partial scope/status")
    require("attemptedPath" in partial, "Missing attemptedPath")
    require(partial.get("attemptedPath") is None or
            isinstance(partial.get("attemptedPath"), str), "Invalid attemptedPath")
    unverified = partial.get("unverifiedPaths")
    require(isinstance(unverified, list) and all(isinstance(x, str) for x in unverified),
            "Missing or invalid unverifiedPaths")
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list), "Missing artifacts array")
    paths, names = set(), []
    for artifact in artifacts:
        require(isinstance(artifact, dict), "Invalid artifact")
        path_text, name = artifact.get("path"), artifact.get("name")
        require(isinstance(path_text, str) and isinstance(name, str), "Invalid artifact path/name")
        path = Path(path_text)
        require(path.is_absolute() and path.parent == folder and path.name == name,
                "Artifact path escapes output directory or name differs")
        require(path_text not in paths, "Duplicate artifact")
        paths.add(path_text)
        names.append(name)
        require(path.is_file(), "Reported artifact is absent or not a file")
        size = artifact.get("sizeBytes")
        require(type(size) is int and size >= 0 and path.stat().st_size == size,
                "Artifact size differs")
        digest = artifact.get("sha256")
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                "Invalid artifact hash")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                "Artifact hash differs")
    if expected_names is not None:
        require(sorted(names) == sorted(expected_names), "Unexpected current-write artifact names")
    manifest = payload.get("manifestPath")
    require(manifest is None or manifest in paths, "Unverified or stale manifest reported")
    require(not paths.intersection(unverified), "Unverified file also reported as verified")
    require(partial["attemptedPath"] not in paths, "Attempted failed write also reported as verified")
    return payload


class PartialPayloadCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.file = self.folder / "good.csv"
        self.file.write_bytes(b"ABCD")
        self.payload = {
            "schemaVersion": "mvs-cli-result/v1", "status": "error", "exitCode": 1,
            "execution": {"completed": False, "outcome": "failed"},
            "outputDirectory": str(self.folder), "manifestPath": None,
            "partialOutput": {"status": "incomplete",
                              "scope": "current_invocation_successful_writes",
                              "attemptedPath": None, "unverifiedPaths": []},
            "artifacts": [{"name": self.file.name, "path": str(self.file),
                           "sizeBytes": 4, "sha256": hashlib.sha256(b"ABCD").hexdigest()}],
        }

    def test_valid_actual_file_passes(self):
        validate_partial(self.payload, ["good.csv"])

    def test_empty_partial_output_can_describe_first_write_failure(self):
        self.payload["artifacts"] = []
        self.payload["partialOutput"]["attemptedPath"] = str(self.folder / "failed.csv")
        validate_partial(self.payload, [])

    def test_missing_output_directory_fails(self):
        self.payload["outputDirectory"] = None
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_false_completion_fails(self):
        self.payload["execution"]["completed"] = True
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_missing_partial_metadata_fails(self):
        del self.payload["partialOutput"]
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_missing_attempted_path_key_fails(self):
        del self.payload["partialOutput"]["attemptedPath"]
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_attempted_write_cannot_be_verified_artifact(self):
        self.payload["partialOutput"]["attemptedPath"] = str(self.file)
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_missing_retained_file_fails(self):
        self.file.unlink()
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_same_size_mutated_bytes_fail(self):
        self.file.write_bytes(b"WXYZ")
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_size_mismatch_fails(self):
        self.payload["artifacts"][0]["sizeBytes"] += 1
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_duplicate_artifact_fails(self):
        self.payload["artifacts"].append(copy.deepcopy(self.payload["artifacts"][0]))
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_artifact_name_path_mismatch_fails(self):
        self.payload["artifacts"][0]["name"] = "different.csv"
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_stale_manifest_reference_fails(self):
        stale = self.folder / "run_manifest.json"
        stale.write_text('{"runId":"old-run"}')
        self.payload["manifestPath"] = str(stale)
        with self.assertRaises(ValueError):
            validate_partial(self.payload)

    def test_unverified_file_cannot_be_verified_artifact(self):
        self.payload["partialOutput"]["unverifiedPaths"] = [str(self.file)]
        with self.assertRaises(ValueError):
            validate_partial(self.payload)


class SavedNativePartialOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report_path = os.environ.get("MVS_PARTIAL_OUTPUT_RESULTS")
        if not report_path:
            raise unittest.SkipTest("Set MVS_PARTIAL_OUTPUT_RESULTS to an explicitly executed native harness report.json; native work is never launched at discovery")
        cls.report_path = Path(report_path).resolve()
        cls.report = load_json(cls.report_path)
        cls.cases = {case["id"]: case for case in cls.report["cases"]}

    def payload(self, case_id):
        case = self.cases[case_id]
        self.assertEqual(case["status"], "passed", case)
        directory = Path(case["evidenceDirectory"])
        self.assertEqual(directory.parent.resolve(), self.report_path.parent)
        return load_json(directory / "stdout.json")

    def test_native_report_is_complete_and_passed(self):
        self.assertEqual(self.report["schema"], "mvs-partial-output-tests/v1")
        expected = REQUIRED_CASES | (BASELINE_CASES if self.report["baselineIncluded"] else set())
        self.assertEqual(set(self.cases), expected)
        self.assertEqual(len(self.report["cases"]), len(self.cases), "Duplicate case IDs")
        self.assertEqual(self.report["total"], len(expected))
        self.assertEqual(self.report["passed"], len(expected))
        self.assertEqual(self.report["failed"], 0)
        self.assertTrue(all(case["status"] == "passed" for case in self.cases.values()))
        provenance = load_json(self.report_path.parent / "provenance.json")
        self.assertTrue(provenance["backupDisabled"])
        self.assertEqual(provenance["schema"], "mvs-partial-output-provenance/v1")

    def test_actual_calibration_failure_retains_verified_bytes(self):
        payload = validate_partial(self.payload("candidate_late_calibration"), ["calibration.csv"])
        self.assertEqual(payload["error"]["type"], "IOException")
        self.assertEqual(Path(payload["partialOutput"]["attemptedPath"]).name, "calibration_tracks.csv")
        self.assertIsNone(payload["manifestPath"])
        if self.report["baselineIncluded"]:
            old = self.payload("baseline_late_calibration_counterexample")
            self.assertIsNone(old["outputDirectory"])
            self.assertEqual(old["artifacts"], [])
            old_dir = Path(self.cases["baseline_late_calibration_counterexample"]["evidenceDirectory"])
            self.assertEqual(payload["artifacts"][0]["sha256"], load_json(old_dir / "retained.json")["sha256"])

    def test_stale_and_failed_rewrite_paths_are_excluded(self):
        for case in ("current_files_only", "failed_rewrite_invalidates_previous_success"):
            with self.subTest(case=case):
                payload = validate_partial(self.payload(case), ["good.csv"])
                self.assertIsNone(payload["manifestPath"])
        self.assertIsNone(self.payload("current_files_only")["runId"])

    def test_changed_deleted_unreadable_files_are_disclosed(self):
        for case in ("mutation_omits_changed_file", "deletion_omits_deleted_file",
                     "unreadable_omits_locked_file", "unreadable_at_capture_is_unverified"):
            with self.subTest(case=case):
                payload = validate_partial(self.payload(case), ["good.csv"])
                self.assertEqual(len(payload["partialOutput"]["unverifiedPaths"]), 1)

    def test_reset_preflight_and_disabled_tracking_have_no_partial_output(self):
        for case in ("reset_clears_partial_state", "preflight_failure_has_no_output_context",
                     "disabled_tracking_has_no_emission"):
            with self.subTest(case=case):
                payload = self.payload(case)
                self.assertIsNone(payload["outputDirectory"])
                self.assertEqual(payload["artifacts"], [])
                self.assertNotIn("partialOutput", payload)

    def test_cancellation_keeps_error_and_retained_files(self):
        payload = validate_partial(self.payload("cancellation_retains_successful_files"), ["good.csv"])
        self.assertEqual(payload["error"]["type"], "OperationCanceledException")

    def test_real_exporter_manifest_failure_is_not_completed(self):
        payload = validate_partial(self.payload("exporter_manifest_write_failure"),
                                   ["results.csv", "metric_availability.csv", "results.json", "data_quality.csv"])
        self.assertIsNone(payload["manifestPath"])
        self.assertEqual(payload["runId"], "manifest-fixture")
        self.assertEqual(Path(payload["partialOutput"]["attemptedPath"]).name, "run_manifest.json")
        directory = Path(self.cases["exporter_manifest_write_failure"]["evidenceDirectory"])
        injection = load_json(directory / "exporter-injection.json")
        self.assertTrue(injection["injected"])
        self.assertEqual(injection["actualMethod"], "OutputExporter.Export")

    def test_success_and_diagnostic_keep_existing_contract(self):
        for case, status, code in (("success_payload_contract", "completed", 0),
                                   ("diagnostic_payload_has_no_partial_output", "diagnostic", 2)):
            with self.subTest(case=case):
                payload = self.payload(case)
                self.assertNotIn("partialOutput", payload)
                self.assertEqual(payload["status"], status)
                self.assertEqual(payload["exitCode"], code)
                self.assertTrue(payload["execution"]["completed"])
                self.assertIsNone(payload["error"])
                self.assertEqual(payload["scientificReadiness"]["status"], "no_go")
        if self.report["baselineIncluded"]:
            directory = Path(self.cases["success_payload_matches_baseline"]["evidenceDirectory"])
            self.assertEqual(self.payload("success_payload_matches_baseline"), load_json(directory / "baseline-stdout.json"))


if __name__ == "__main__":
    unittest.main()
