"""Current-invocation output provenance contract, with no native work at discovery.

Pure corruption tests always run. Set MVS_OVERWRITE_OUTPUT_RESULTS to an actual
OverwriteOutputHarness report.json to inspect explicitly executed native evidence.
Missing/invalid supplied evidence fails rather than skipping. The tiny native
fixtures check engineering behavior, not numerical or scientific adequacy.
"""
import copy
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest

try:
    from .test_partial_output_contract import load_json, validate_partial
except ImportError:
    from test_partial_output_contract import load_json, validate_partial

SCOPE = "current_invocation_successful_writes"
SCIENTIFIC_FILES = {
    "estimation": {"estimation_report.json", "estimation_performance.csv", "estimation_draws.csv"},
    "variance": {"variance_report.json", "variance_components.csv", "variance_tests.csv"},
    "melsm": {"melsm_report.json", "melsm_parameters.csv", "melsm_random_effects.csv"},
}
CANARIES = {"stale_previous_report.txt", "old_scientific_result.csv", "benchmark_manifest.json", "nested/keep.txt"}
REQUIRED_CASES = {
    "candidate_estimation_overwrite", "candidate_variance_overwrite", "candidate_melsm_overwrite",
    "human_estimation_manifest", "tracked_success_stale_no_manifest", "tracked_diagnostic_stale_no_manifest",
    "tracked_partial_stale_no_manifest", "tracked_current_manifest_run_id", "tracked_explicit_run_id",
    "tracked_empty_success", "tracked_changed_file", "tracked_deleted_file", "tracked_unreadable_file",
    "tracked_changed_manifest", "tracked_deleted_manifest", "tracked_failed_rewrite",
    "reset_clears_tracked_context", "untracked_legacy_benchmark_success", "untracked_legacy_benchmark_diagnostic",
}
BASELINE_CASES = {"baseline_estimation_counterexample", "baseline_tracked_stale_manifest_counterexample"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def absolute(value, label):
    require(isinstance(value, str) and bool(value) and Path(value).is_absolute(), f"Invalid {label}")
    return Path(value)


def validate_status(payload, code):
    require(isinstance(payload, dict), "Payload is not an object")
    require(payload.get("schemaVersion") == "mvs-cli-result/v1", "Wrong schema")
    require(type(payload.get("exitCode")) is int and payload["exitCode"] == code, "Native exit differs")
    require(payload.get("status") == {0: "completed", 1: "error", 2: "diagnostic"}[code], "Status differs")
    require(payload.get("execution") == {
        "completed": code in (0, 2),
        "outcome": {0: "completed", 1: "failed", 2: "completed_with_diagnostic"}[code]}, "Execution status differs")
    readiness = payload.get("scientificReadiness")
    require(isinstance(readiness, dict) and readiness.get("status") == "no_go", "Scientific no_go changed")
    if code in (0, 2):
        require(payload.get("error") is None and "error" in payload, "Completed payload has error")
        require("partialOutput" not in payload, "Completed result contains partialOutput")
    else:
        require(isinstance(payload.get("error"), dict), "Error metadata missing")
    return payload


def validate_payload(payload, expected_names, code=0, tracked=True):
    validate_status(payload, code)
    if tracked:
        require(payload.get("artifactScope") == SCOPE, "Current-invocation marker missing/invalid")
    else:
        require("artifactScope" not in payload, "Untracked result falsely claims current writes")
    folder = absolute(payload.get("outputDirectory"), "outputDirectory")
    require(folder.is_dir(), "Missing output folder")
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list), "Missing artifacts")
    names, paths = [], set()
    for artifact in artifacts:
        require(isinstance(artifact, dict), "Invalid artifact")
        path = absolute(artifact.get("path"), "artifact path")
        name = artifact.get("name")
        require(isinstance(name, str) and path.name == name and path.parent == folder,
                "Artifact path/name escaped output directory")
        require(path not in paths, "Duplicate artifact")
        paths.add(path)
        names.append(name)
        require(path.is_file(), "Retained artifact is absent")
        require(type(artifact.get("sizeBytes")) is int and artifact["sizeBytes"] == path.stat().st_size,
                "Artifact size differs")
        require(valid_hash(artifact.get("sha256")) and artifact["sha256"] == digest(path), "Artifact hash differs")
    require(sorted(names) == sorted(expected_names), "Stale or missing current artifact")
    require("manifestPath" in payload and "runId" in payload, "Identity fields missing")
    manifest_text = payload["manifestPath"]
    if manifest_text is not None:
        manifest_path = absolute(manifest_text, "manifestPath")
        require(manifest_path in paths and manifest_path.name in ("run_manifest.json", "benchmark_manifest.json"),
                "Unverified/stale manifest supplied identity")
    if code == 1:
        validate_partial(payload, expected_names)
    return payload


def validate_manifest(folder, expected_names):
    folder = Path(folder)
    manifest = load_json(folder / "run_manifest.json")
    require(isinstance(manifest, dict) and isinstance(manifest.get("files"), list), "Missing manifest file list")
    require(isinstance(manifest.get("runId"), str) and bool(manifest["runId"]), "Missing manifest run ID")
    names = []
    for item in manifest["files"]:
        require(isinstance(item, dict), "Invalid manifest entry")
        name = item.get("FileName")
        require(isinstance(name, str) and Path(name).name == name and name not in (".", ".."), "Unsafe manifest filename")
        path = folder / name
        require(path.is_file(), "Manifest names absent file")
        require(type(item.get("SizeBytes")) is int and item["SizeBytes"] == path.stat().st_size, "Manifest size differs")
        require(valid_hash(item.get("sha256")) and item["sha256"] == digest(path), "Manifest hash differs")
        names.append(name)
    require(len(names) == len(set(names)), "Duplicate manifest entry")
    require(sorted(names) == sorted(expected_names), "Manifest contains stale or missing files")
    return manifest


def normalize_manifest(manifest):
    value = copy.deepcopy(manifest)
    value.pop("created", None)
    value.pop("runId", None)
    return value


def validate_checks(checks, folder=None):
    require(isinstance(checks, list) and bool(checks), "No immutable checks")
    seen = set()
    for item in checks:
        require(isinstance(item, dict), "Invalid immutable check")
        path = absolute(item.get("path"), "retained path")
        require(path not in seen, "Duplicate immutable check")
        seen.add(path)
        before, after = item.get("beforeSha256"), item.get("afterSha256")
        require(valid_hash(before) and before == after, "Old canary/source changed")
        require(path.is_file() and digest(path) == after, "Retained old canary/source differs")
        if "sizeBytes" in item:
            require(type(item["sizeBytes"]) is int and path.stat().st_size == item["sizeBytes"], "Retained canary size differs")
    if folder is not None:
        expected = {Path(folder) / name for name in CANARIES}
        require(seen == expected, "Required old canaries not all checked")
    return checks


def validate_report(report, report_path=None):
    require(isinstance(report, dict) and report.get("schema") == "mvs-overwrite-output-tests/v1", "Wrong report schema")
    require(type(report.get("baselineIncluded")) is bool, "Invalid baseline flag")
    root = absolute(report.get("evidenceRoot"), "evidenceRoot")
    if report_path is not None:
        require(root.resolve() == Path(report_path).resolve().parent, "Evidence root mismatch")
    cases = report.get("cases")
    require(isinstance(cases, list), "Missing cases")
    by_id, directories = {}, set()
    for case in cases:
        require(isinstance(case, dict), "Invalid case")
        key = case.get("id")
        require(isinstance(key, str) and key in REQUIRED_CASES | BASELINE_CASES, "Unknown case")
        require(key not in by_id, "Duplicate case ID")
        directory = absolute(case.get("evidenceDirectory"), "evidenceDirectory")
        require(directory.resolve() == (root / key).resolve() and directory not in directories, "Case path differs/duplicates/escapes root")
        directories.add(directory)
        require(case.get("status") in ("passed", "failed"), "Invalid case status")
        require(type(case.get("elapsedSeconds")) in (int, float) and case["elapsedSeconds"] >= 0, "Invalid elapsed time")
        if case["status"] == "failed":
            require(isinstance(case.get("error"), str) and bool(case["error"]), "Failed case has no error")
        else:
            require("error" not in case, "Passed case contains error")
        by_id[key] = case
    expected = REQUIRED_CASES | (BASELINE_CASES if report["baselineIncluded"] else set())
    require(set(by_id) == expected, "Case set does not match required/baseline cases")
    for key, actual in (("total", len(cases)), ("passed", sum(c["status"] == "passed" for c in cases)), ("failed", sum(c["status"] == "failed" for c in cases))):
        require(type(report.get(key)) is int and report[key] == actual, "Incorrect report count: " + key)
    return by_id


class OverwriteOutputCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.file = self.folder / "good.csv"
        self.file.write_bytes(b"ABCD")
        self.payload = {
            "schemaVersion": "mvs-cli-result/v1", "status": "completed", "exitCode": 0,
            "execution": {"completed": True, "outcome": "completed"},
            "scientificReadiness": {"status": "no_go"}, "artifactScope": SCOPE,
            "outputDirectory": str(self.folder), "manifestPath": None, "runId": None, "error": None,
            "artifacts": [{"name": "good.csv", "path": str(self.file), "sizeBytes": 4, "sha256": digest(self.file)}],
        }
        self.manifest = {"runId": "current", "created": "volatile", "files": [
            {"FileName": "good.csv", "SizeBytes": 4, "sha256": digest(self.file)}]}
        self.check = {"path": str(self.file), "beforeSha256": digest(self.file), "afterSha256": digest(self.file), "sizeBytes": 4}
        self.report = {"schema": "mvs-overwrite-output-tests/v1", "evidenceRoot": str(self.folder), "baselineIncluded": False,
                       "passed": len(REQUIRED_CASES), "failed": 0, "total": len(REQUIRED_CASES),
                       "cases": [{"id": key, "status": "passed", "evidenceDirectory": str(self.folder / key), "elapsedSeconds": 0} for key in sorted(REQUIRED_CASES)]}

    def test_valid_current_artifact(self):
        validate_payload(self.payload, ["good.csv"])

    def test_empty_current_artifacts_allowed(self):
        self.payload["artifacts"] = []
        validate_payload(self.payload, [])

    def test_missing_marker_rejected(self):
        del self.payload["artifactScope"]
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_wrong_marker_rejected(self):
        self.payload["artifactScope"] = "all_files_in_folder"
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_untracked_marker_rejected(self):
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"], tracked=False)

    def test_untracked_legacy_without_marker_accepted(self):
        del self.payload["artifactScope"]
        validate_payload(self.payload, ["good.csv"], tracked=False)

    def test_stale_artifact_rejected(self):
        with self.assertRaises(ValueError): validate_payload(self.payload, [])

    def test_stale_manifest_identity_rejected(self):
        stale = self.folder / "run_manifest.json"
        stale.write_text('{"runId":"stale"}')
        self.payload["manifestPath"] = str(stale)
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_duplicate_artifact_rejected(self):
        self.payload["artifacts"] *= 2
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv", "good.csv"])

    def test_mutated_same_size_artifact_rejected(self):
        self.file.write_bytes(b"WXYZ")
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_deleted_artifact_rejected(self):
        self.file.unlink()
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_artifact_size_mismatch_rejected(self):
        self.payload["artifacts"][0]["sizeBytes"] = 5
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_artifact_path_escape_rejected(self):
        self.payload["outputDirectory"] = str(self.folder / "other")
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_completed_partial_output_rejected(self):
        self.payload["partialOutput"] = {}
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def test_exit_two_is_diagnostic_completed(self):
        self.payload.update(status="diagnostic", exitCode=2, execution={"completed": True, "outcome": "completed_with_diagnostic"})
        validate_payload(self.payload, ["good.csv"], code=2)

    def test_relabelled_exit_two_rejected(self):
        self.payload["exitCode"] = 2
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"], code=2)

    def test_scientific_readiness_not_promoted(self):
        self.payload["scientificReadiness"]["status"] = "go"
        with self.assertRaises(ValueError): validate_payload(self.payload, ["good.csv"])

    def save_manifest(self):
        import json
        (self.folder / "run_manifest.json").write_text(json.dumps(self.manifest))

    def test_valid_manifest(self):
        self.save_manifest()
        validate_manifest(self.folder, ["good.csv"])

    def test_stale_manifest_entry_rejected(self):
        self.save_manifest()
        with self.assertRaises(ValueError): validate_manifest(self.folder, [])

    def test_mutated_manifest_file_rejected(self):
        self.save_manifest()
        self.file.write_bytes(b"WXYZ")
        with self.assertRaises(ValueError): validate_manifest(self.folder, ["good.csv"])

    def test_duplicate_manifest_entry_rejected(self):
        self.manifest["files"] *= 2
        self.save_manifest()
        with self.assertRaises(ValueError): validate_manifest(self.folder, ["good.csv", "good.csv"])

    def test_unsafe_manifest_entry_rejected(self):
        self.manifest["files"][0]["FileName"] = "../good.csv"
        self.save_manifest()
        with self.assertRaises(ValueError): validate_manifest(self.folder, ["../good.csv"])

    def test_normalization_only_ignores_clock_and_run_id(self):
        self.manifest["scientificValue"] = 1.25
        expected = copy.deepcopy(self.manifest)
        del expected["created"], expected["runId"]
        self.assertEqual(normalize_manifest(self.manifest), expected)
        self.assertIn("created", self.manifest)
        changed = copy.deepcopy(self.manifest)
        changed["scientificValue"] = 2.5
        self.assertNotEqual(normalize_manifest(changed), expected)

    def test_immutable_source_hashes_verified(self):
        validate_checks([self.check])
        self.file.write_bytes(b"WXYZ")
        with self.assertRaises(ValueError): validate_checks([self.check])

    def test_canary_deletion_rejected(self):
        self.file.unlink()
        with self.assertRaises(ValueError): validate_checks([self.check])

    def test_claimed_canary_change_rejected(self):
        self.check["beforeSha256"] = "a" * 64
        with self.assertRaises(ValueError): validate_checks([self.check])

    def test_valid_report(self):
        validate_report(self.report)

    def test_report_missing_case_rejected(self):
        self.report["cases"].pop()
        with self.assertRaises(ValueError): validate_report(self.report)

    def test_report_duplicate_case_rejected(self):
        self.report["cases"].append(copy.deepcopy(self.report["cases"][0]))
        with self.assertRaises(ValueError): validate_report(self.report)

    def test_report_forged_totals_rejected(self):
        self.report["passed"] += 1
        with self.assertRaises(ValueError): validate_report(self.report)

    def test_report_escaping_case_path_rejected(self):
        self.report["cases"][0]["evidenceDirectory"] = str(self.folder.parent)
        with self.assertRaises(ValueError): validate_report(self.report)

    def test_report_false_baseline_claim_rejected(self):
        self.report["baselineIncluded"] = True
        with self.assertRaises(ValueError): validate_report(self.report)


class SavedNativeOverwriteOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied = os.environ.get("MVS_OVERWRITE_OUTPUT_RESULTS")
        if not supplied:
            raise unittest.SkipTest("Set MVS_OVERWRITE_OUTPUT_RESULTS to explicitly executed harness report.json; discovery never launches native work")
        cls.report_path = Path(supplied).resolve()
        cls.report = load_json(cls.report_path)
        cls.cases = validate_report(cls.report, cls.report_path)

    def directory(self, case_id):
        case = self.cases[case_id]
        self.assertEqual(case["status"], "passed", case)
        return Path(case["evidenceDirectory"])

    def evidence(self, case_id, name="stdout.json"):
        return load_json(self.directory(case_id) / name)

    def test_report_complete_all_passed_and_provenance_bound(self):
        self.assertEqual(self.report["failed"], 0)
        self.assertEqual(self.report["passed"], len(self.cases))
        provenance = load_json(self.report_path.parent / "provenance.json")
        self.assertEqual(provenance["schema"], "mvs-overwrite-output-provenance/v1")
        self.assertIs(provenance["backupDisabled"], True)
        self.assertIs(provenance["benchmarkModelExecuted"], False)
        self.assertIn("synthetic engineering fixtures only", provenance["purpose"].lower())
        self.assertTrue(valid_hash(provenance["harnessSha256"]))
        for label in ("candidate", "baseline"):
            item = provenance[label]
            if item is None:
                self.assertEqual(label, "baseline")
                self.assertFalse(self.report["baselineIncluded"])
                continue
            binary = absolute(item["path"], label)
            self.assertEqual(item["sha256"], digest(binary))
            self.assertEqual(item["coreSha256"], digest(binary.parent / "MvsAnalyzer.Core.dll"))

    def assert_scientific_pair(self, case_id, kind, expect_bug=False):
        directory = self.directory(case_id)
        details = self.evidence(case_id, "details.json")
        self.assertEqual(details["kind"], kind)
        self.assertIs(details["expectBug"], expect_bug)
        self.assertIs(details["actualProcesses"], True)
        expected = SCIENTIFIC_FILES[kind]
        self.assertEqual(set(details["expectedScientificFiles"]), expected)
        manifests = {}
        for side in ("clean", "contaminated"):
            output = directory / side / "output"
            self.assertEqual(details[side], str(output))
            invocation = load_json(directory / side / "invocation.json")
            self.assertIs(invocation["actualProcess"], True)
            self.assertIs(invocation["machine"], True)
            self.assertIs(invocation["timedOut"], False)
            self.assertEqual(invocation["exitCode"], details["nativeExitCode"])
            self.assertIn(invocation["exitCode"], (0, 2))
            self.assertIn("--overwrite", invocation["arguments"])
            extras = {name for name in CANARIES if "/" not in name} if expect_bug and side == "contaminated" else set()
            payload = validate_payload(load_json(directory / side / "stdout.json"), expected | {"run_manifest.json"} | extras,
                                       code=invocation["exitCode"], tracked=not expect_bug)
            manifest = validate_manifest(output, expected | extras)
            manifests[side] = manifest
            self.assertEqual(payload["manifestPath"], str(output / "run_manifest.json"))
            self.assertEqual(payload["runId"], manifest["runId"])
            self.assertNotEqual(payload["runId"], "stale-run")
        validate_checks(details["canaries"], directory / "contaminated" / "output")
        validate_checks([details["input"]])
        self.assertNotEqual(details["oldManifestSha256"], digest(directory / "contaminated" / "output" / "run_manifest.json"))
        self.assertEqual(len(details["scientificParity"]), len(expected))
        self.assertEqual({item["name"] for item in details["scientificParity"]}, expected)
        for item in details["scientificParity"]:
            self.assertEqual(item["cleanSha256"], item["contaminatedSha256"])
            for side, key in (("clean", "cleanSha256"), ("contaminated", "contaminatedSha256")):
                self.assertEqual(item[key], digest(directory / side / "output" / item["name"]))
        equal = normalize_manifest(manifests["clean"]) == normalize_manifest(manifests["contaminated"])
        self.assertEqual(equal, not expect_bug)
        self.assertEqual(details["manifestNormalizedEqual"], equal)

    def test_actual_three_scientific_commands_clean_dirty_current_only(self):
        for kind in SCIENTIFIC_FILES:
            with self.subTest(kind=kind): self.assert_scientific_pair("candidate_" + kind + "_overwrite", kind)

    def test_actual_melsm_diagnostic_native_exit_two_preserved(self):
        details = self.evidence("candidate_melsm_overwrite", "details.json")
        self.assertEqual(details["nativeExitCode"], 2, "Capped MELSM fixture must exercise actual diagnostic exit 2")

    def test_human_mode_uses_same_exact_manifest_and_scientific_bytes(self):
        directory = self.directory("human_estimation_manifest")
        details = self.evidence("human_estimation_manifest", "details.json")
        invocation = self.evidence("human_estimation_manifest", "invocation.json")
        self.assertIs(invocation["actualProcess"], True)
        self.assertIs(invocation["machine"], False)
        self.assertIs(invocation["timedOut"], False)
        self.assertEqual(invocation["exitCode"], details["nativeExitCode"])
        output = directory / "output"
        validate_manifest(output, SCIENTIFIC_FILES["estimation"])
        validate_checks(details["canaries"], output)
        clean = self.directory("candidate_estimation_overwrite") / "clean" / "output"
        self.assertEqual(details["scientificParityWith"], str(clean))
        for name in SCIENTIFIC_FILES["estimation"]:
            self.assertEqual((output / name).read_bytes(), (clean / name).read_bytes())
        text = (directory / "human-stdout.txt").read_text(encoding="utf-8-sig")
        self.assertIn("Known-truth estimation report saved: " + str(output), text)
        self.assertNotIn("mvs-cli-result/v1", text)

    def test_stale_manifest_run_id_absent_on_success_diagnostic_and_partial(self):
        for label, code in (("success", 0), ("diagnostic", 2), ("partial", 1)):
            case = "tracked_" + label + "_stale_no_manifest"
            with self.subTest(case=case):
                payload = validate_payload(self.evidence(case), ["good.csv"], code=code)
                self.assertIsNone(payload["manifestPath"])
                self.assertIsNone(payload["runId"])
                details = self.evidence(case, "details.json")
                folder = Path(payload["outputDirectory"])
                validate_checks(details["canaries"], folder)
                self.assertEqual(details["ignoredManifestSha256"], digest(folder / "run_manifest.json"))
                self.assertEqual(load_json(folder / "run_manifest.json")["runId"], "stale-run")

    def test_current_manifest_binding_and_explicit_precedence(self):
        for case, run_id in (("tracked_current_manifest_run_id", "current-manifest-run"), ("tracked_explicit_run_id", "explicit-current-run")):
            with self.subTest(case=case):
                payload = validate_payload(self.evidence(case), ["good.csv", "run_manifest.json"])
                self.assertEqual(payload["runId"], run_id)
                self.assertEqual(payload["manifestPath"], str(Path(payload["outputDirectory"]) / "run_manifest.json"))

    def test_empty_tracked_output_does_not_fall_back_to_directory_listing(self):
        payload = validate_payload(self.evidence("tracked_empty_success"), [])
        self.assertIsNone(payload["manifestPath"])
        self.assertIsNone(payload["runId"])

    def test_changed_deleted_locked_and_failed_rewrite_are_omitted(self):
        for case in ("tracked_changed_file", "tracked_deleted_file", "tracked_unreadable_file", "tracked_changed_manifest", "tracked_deleted_manifest", "tracked_failed_rewrite"):
            with self.subTest(case=case):
                payload = validate_payload(self.evidence(case), ["good.csv"])
                self.assertIsNone(payload["manifestPath"])
                self.assertIsNone(payload["runId"])
                if case == "tracked_failed_rewrite":
                    self.assertTrue((Path(payload["outputDirectory"]) / "rewrite.csv").is_file())
                    continue
                details = self.evidence(case, "details.json")
                self.assertIs(details["mutationWasFixtureInjected"], True)
                path = Path(details["path"])
                self.assertEqual(path.exists(), details["existsAfter"])
                if details["action"] == "delete":
                    self.assertFalse(path.exists())
                    self.assertIsNone(details["afterSha256"])
                else:
                    self.assertEqual(details["afterSha256"], digest(path))
                    self.assertEqual(details["beforeSha256"] == details["afterSha256"], details["action"] == "lock")

    def test_reset_drops_previous_invocation_identity(self):
        payload = validate_status(self.evidence("reset_clears_tracked_context"), 0)
        self.assertNotIn("artifactScope", payload)
        self.assertEqual(payload["artifacts"], [])
        for key in ("outputDirectory", "manifestPath", "runId"):
            self.assertIsNone(payload[key])

    def test_untracked_benchmark_compatibility_is_explicitly_bounded(self):
        for label, code in (("success", 0), ("diagnostic", 2)):
            case = "untracked_legacy_benchmark_" + label
            with self.subTest(case=case):
                payload = validate_payload(self.evidence(case), ["benchmark.csv", "benchmark_manifest.json", "old.csv"], code=code, tracked=False)
                self.assertEqual(payload["command"], "benchmark")
                self.assertEqual(payload["runId"], "legacy-benchmark-run")
                details = self.evidence(case, "details.json")
                self.assertIs(details["benchmarkModelExecuted"], False)
                self.assertIs(details["writeTrackingStarted"], False)
                self.assertIn("Protocol-only", details["scope"])
                if self.report["baselineIncluded"]:
                    self.assertIs(details["baselinePayloadEqual"], True)
                    self.assertEqual(payload, self.evidence(case, "baseline-stdout.json"))
                else:
                    self.assertIsNone(details["baselinePayloadEqual"])

    def test_baseline_counterexamples_and_cross_version_scientific_parity(self):
        if not self.report["baselineIncluded"]:
            self.skipTest("No baseline supplied to explicit native run")
        self.assert_scientific_pair("baseline_estimation_counterexample", "estimation", expect_bug=True)
        old = self.directory("baseline_estimation_counterexample") / "clean" / "output"
        new = self.directory("candidate_estimation_overwrite") / "clean" / "output"
        for name in SCIENTIFIC_FILES["estimation"]:
            self.assertEqual((old / name).read_bytes(), (new / name).read_bytes(), name)
        payload = self.evidence("baseline_tracked_stale_manifest_counterexample")
        self.assertNotIn("artifactScope", payload)
        self.assertEqual(payload["runId"], "stale-run")
        self.assertEqual(Path(payload["manifestPath"]).name, "run_manifest.json")
        self.assertIn("stale_previous_report.txt", [item["name"] for item in payload["artifacts"]])


class CiEvidenceRoutingTests(unittest.TestCase):
    def test_negative_fixtures_are_outside_canonical_recursive_scan_and_uploaded(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for name in ("partial-output", "resume-output", "overwrite-output"):
            self.assertNotIn("$PWD/artifacts/" + name, workflow)
            self.assertIn("$PWD/regression-evidence/" + name, workflow)
        self.assertIn("python tools/check_outputs.py artifacts", workflow)
        self.assertIn("python tools/check_cli_contract.py --artifacts artifacts", workflow)
        self.assertIn("            regression-evidence/\n", workflow)


if __name__ == "__main__":
    unittest.main()
