"""Validate saved resume/output engineering evidence without launching native code.

Pure corruption tests always run. Set MVS_RESUME_OUTPUT_RESULTS to the actual
report.json produced by an explicitly executed ResumeOutputHarness to opt into
saved-native checks. A supplied missing or invalid report is a failure, not a
skip. These synthetic fixtures are not numerical or scientific validation.
"""
import copy
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest

try:  # Both unittest discovery and package-qualified invocation are supported.
    from .test_partial_output_contract import load_json, validate_partial
except ImportError:
    from test_partial_output_contract import load_json, validate_partial


REQUIRED_CASES = {
    "late_calibration", "first_write_failure", "second_write_failure",
    "state_reread_failure", "provenance_write_failure",
    "preoutput_validation_failure", "observer_start_throw_retry",
    "observer_before_throw_retry", "observer_after_throw_retry",
    "cancellation_before_output", "cancellation_after_write", "history_empty", "history_foreign",
    "history_current", "legacy_observer_disabled_parity", "human_cli_success",
    "machine_cli_success", "benchmark_validation_callbacks_absent",
}
BASELINE_CASES = {"baseline_late_calibration"}
FIXTURE_KINDS = {"analyze", "variance", "estimation", "melsm"}
OPTIONAL_CASES = {
    prefix + kind
    for prefix in ("exporter_manifest_", "legacy_disabled_")
    for kind in FIXTURE_KINDS
}
SUCCESS_ARTIFACTS = ["calibration_state.json", "calibration.csv", "calibration_tracks.csv", "backup_resume.json"]
PARTIAL_CASES = {
    "late_calibration": ["calibration_state.json", "calibration.csv"],
    "first_write_failure": [],
    "second_write_failure": ["calibration_state.json"],
    "state_reread_failure": [],
    "cancellation_after_write": ["calibration_state.json"],
    "provenance_write_failure": ["calibration_state.json", "calibration.csv",
                                 "calibration_tracks.csv"],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def absolute_path(value, label):
    require(isinstance(value, str) and bool(value) and Path(value).is_absolute(),
            f"Missing or invalid absolute {label}")
    return Path(value)


def validate_fixture_checks(checks):
    """Require unchanged source hashes and verify the retained source bytes."""
    require(isinstance(checks, list), "fixtureChecks must be an array")
    seen = set()
    for item in checks:
        require(isinstance(item, dict), "Invalid fixture check")
        path = absolute_path(item.get("path"), "fixture path")
        require(path.resolve() not in seen, "Duplicate fixture source path")
        seen.add(path.resolve())
        before, after = item.get("beforeSha256"), item.get("afterSha256")
        require(valid_sha256(before) and valid_sha256(after), "Invalid fixture source hash")
        require(before == after, "Fixture source was modified")
        require(path.is_file(), "Fixture source is absent or not a file")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == after,
                "Retained fixture source hash differs")
    return checks


def validate_report(report, report_path=None):
    """Validate report structure, case identity, and independently counted totals."""
    require(isinstance(report, dict), "Report must be an object")
    require(report.get("schema") == "mvs-resume-output-tests/v1", "Wrong report schema")
    require(type(report.get("baselineIncluded")) is bool, "Invalid baselineIncluded")
    root = absolute_path(report.get("evidenceRoot"), "evidenceRoot")
    if report_path is not None:
        require(root.resolve() == Path(report_path).resolve().parent,
                "evidenceRoot differs from report directory")
    cases = report.get("cases")
    require(isinstance(cases, list), "Missing cases array")
    by_id, passed, failed, directories = {}, 0, 0, set()
    for case in cases:
        require(isinstance(case, dict), "Invalid report case")
        case_id = case.get("id")
        require(isinstance(case_id, str) and case_id in REQUIRED_CASES | OPTIONAL_CASES | BASELINE_CASES,
                "Unexpected case ID")
        require(case_id not in by_id, "Duplicate case ID")
        by_id[case_id] = case
        directory = absolute_path(case.get("evidenceDirectory"), "case evidenceDirectory")
        require(directory.resolve().parent == root.resolve(),
                "Case evidence directory escapes evidenceRoot")
        require(directory.resolve() not in directories, "Duplicate case evidence directory")
        directories.add(directory.resolve())
        status = case.get("status")
        require(status in ("passed", "failed"), "Invalid case status")
        if status == "passed":
            passed += 1
            require("error" not in case, "Passed case contains failure evidence")
        else:
            failed += 1
            require(isinstance(case.get("error"), str) and bool(case["error"].strip()),
                    "Failed case lacks a nonempty failure string")
    require(REQUIRED_CASES <= set(by_id), "Missing required resume/output case")
    if "fixtureKinds" in report:
        kinds = report["fixtureKinds"]
        require(isinstance(kinds, list) and all(isinstance(kind, str) for kind in kinds),
                "Invalid fixtureKinds")
        require(len(kinds) == len(set(kinds)) and "calibrate" in kinds
                and set(kinds) <= FIXTURE_KINDS | {"calibrate"}, "Invalid or duplicate fixture kind")
        expected_extended = {prefix + kind for kind in set(kinds) - {"calibrate"}
                             for prefix in ("exporter_manifest_", "legacy_disabled_")}
        require(set(by_id) & OPTIONAL_CASES == expected_extended,
                "Extended cases disagree with supplied fixture kinds")
    expected_baseline = BASELINE_CASES if report["baselineIncluded"] else set()
    require(set(by_id) & BASELINE_CASES == expected_baseline,
            "Baseline cases disagree with baselineIncluded")
    for field, actual in (("passed", passed), ("failed", failed), ("total", len(cases))):
        require(type(report.get(field)) is int and report[field] == actual,
                f"Incorrect report {field} count")
    require("fixtureChecks" in report, "Missing immutable fixtureChecks")
    validate_fixture_checks(report["fixtureChecks"])
    return by_id


def validate_provenance(provenance):
    require(isinstance(provenance, dict), "Provenance must be an object")
    require(provenance.get("schema") == "mvs-resume-output-provenance/v1",
            "Wrong provenance schema")
    require(provenance.get("backupDisabled") is False,
            "Resume evidence must exercise enabled state/backup writes")
    # Do not accept a contradictory plural spelling as another source of truth.
    require("backupsDisabled" not in provenance, "Unexpected backupsDisabled field")
    purpose = provenance.get("purpose")
    require(isinstance(purpose, str) and "synthetic engineering fixtures only" in purpose.lower(),
            "Missing synthetic engineering fixture scope")
    candidate = provenance.get("candidate")
    require(isinstance(candidate, dict), "Missing candidate binary provenance")
    absolute_path(candidate.get("path"), "candidate path")
    require(valid_sha256(candidate.get("sha256")), "Invalid candidate binary hash")
    require(valid_sha256(candidate.get("coreSha256")), "Invalid candidate core hash")
    return provenance


def validate_machine_status(payload, status="error", exit_code=1):
    require(isinstance(payload, dict), "Machine payload must be an object")
    require(payload.get("schemaVersion") == "mvs-cli-result/v1", "Wrong machine schema")
    require(payload.get("status") == status and type(payload.get("exitCode")) is int
            and payload["exitCode"] == exit_code, "Incorrect machine status/exit")
    completed = exit_code in (0, 2)
    outcome = "completed" if exit_code == 0 else "completed_with_diagnostic" if exit_code == 2 else "failed"
    execution = payload.get("execution")
    require(isinstance(execution, dict) and execution.get("completed") is completed
            and execution.get("outcome") == outcome,
            "Incorrect execution completion metadata")
    readiness = payload.get("scientificReadiness")
    require(isinstance(readiness, dict) and readiness.get("status") == "no_go"
            and readiness.get("scope") == "project_release_readiness"
            and readiness.get("independentConfirmatoryValidation") is False,
            "Engineering fixture must not claim scientific readiness")
    require((payload.get("error") is None) if completed else isinstance(payload.get("error"), dict),
            "Incorrect machine error metadata")
    return payload


def validate_no_output(payload):
    validate_machine_status(payload)
    require(payload.get("outputDirectory") is None, "Pre-output failure claims output directory")
    require(payload.get("artifacts") == [], "Pre-output failure claims artifacts")
    require(payload.get("manifestPath") is None, "Pre-output failure claims manifest")
    require("partialOutput" not in payload, "Pre-output failure claims partial output")
    return payload


def validate_retained_files(folder, artifacts, expected_names=None, manifest=None):
    """Reuse the hash checker independently of the original payload's status."""
    return validate_partial({
        "schemaVersion": "mvs-cli-result/v1", "status": "error", "exitCode": 1,
        "execution": {"completed": False, "outcome": "failed"},
        "outputDirectory": str(folder), "manifestPath": manifest,
        "partialOutput": {"status": "incomplete", "scope": "current_invocation_successful_writes",
                          "attemptedPath": None, "unverifiedPaths": []},
        "artifacts": artifacts,
    }, expected_names)


def normalize_parity_json(name, value):
    """Mirror only the documented volatile timestamp/derived-hash exclusions."""
    value = copy.deepcopy(value)
    if name == "calibration_state.json":
        value.pop("CreatedUtc", None)
        value.pop("PayloadHash", None)
    elif name == "run_manifest.json":
        value.pop("created", None)
        value.pop("runId", None)
        for item in value.get("files", []):
            if item.get("FileName") == "calibration_state.json":
                item.pop("sha256", None)
                item.pop("SizeBytes", None)
    return value


def validate_benchmark_exclusion(details):
    require(isinstance(details, dict), "Missing benchmark exclusion details")
    require(type(details.get("observerCalls")) is int and details["observerCalls"] == 0,
            "Benchmark validation invoked output callbacks")
    require(details.get("benchmarkModelExecuted") is False,
            "Benchmark evidence must remain a pre-model validation fixture")
    scope = details.get("scope")
    require(isinstance(scope, str) and "pre-model" in scope.lower()
            and "outside" in scope.lower(), "Missing benchmark support boundary")
    for key in ("benchmarkPartialOutputSupported", "benchmarkPartialSupport",
                "benchmarkPartialOutputSupport"):
        if key in details:
            require(details[key] is False, "Benchmark partial support is not established")
    return details


class ResumeReportCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.report = {
            "schema": "mvs-resume-output-tests/v1", "passed": len(REQUIRED_CASES),
            "failed": 0, "total": len(REQUIRED_CASES), "baselineIncluded": False,
            "evidenceRoot": str(self.root), "fixtureChecks": [],
            "cases": [{"id": key, "status": "passed", "evidenceDirectory": str(self.root / key)}
                      for key in sorted(REQUIRED_CASES)],
        }
        self.provenance = {
            "schema": "mvs-resume-output-provenance/v1", "backupDisabled": False,
            "purpose": "Synthetic engineering fixtures only; no numerical experiment or scientific validation.",
            "candidate": {"path": str(self.root / "mvs.dll"), "sha256": "a" * 64,
                          "coreSha256": "b" * 64},
        }

    def test_complete_report_and_provenance_pass(self):
        validate_report(self.report, self.root / "report.json")
        validate_provenance(self.provenance)

    def test_duplicate_ids_fail_even_when_counts_are_adjusted(self):
        self.report["cases"].append(copy.deepcopy(self.report["cases"][0]))
        self.report["passed"] += 1
        self.report["total"] += 1
        with self.assertRaisesRegex(ValueError, "Duplicate case ID"):
            validate_report(self.report)

    def test_incorrect_counts_fail(self):
        for key in ("passed", "failed", "total"):
            with self.subTest(field=key):
                bad = copy.deepcopy(self.report)
                bad[key] += 1
                with self.assertRaises(ValueError):
                    validate_report(bad)

    def test_boolean_counts_are_not_integers(self):
        self.report["failed"] = False
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_missing_required_case_fails(self):
        self.report["cases"].pop()
        self.report["total"] -= 1
        self.report["passed"] -= 1
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_unknown_case_with_recognized_prefix_fails(self):
        self.report["cases"].append({"id": "exporter_manifest_benchmark", "status": "passed",
                                     "evidenceDirectory": str(self.root / "unsupported")})
        self.report["passed"] += 1
        self.report["total"] += 1
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_recognized_optional_cases_pass(self):
        for key in sorted(OPTIONAL_CASES):
            self.report["cases"].append({"id": key, "status": "passed",
                                         "evidenceDirectory": str(self.root / key)})
        self.report["passed"] += len(OPTIONAL_CASES)
        self.report["total"] += len(OPTIONAL_CASES)
        validate_report(self.report)

    def test_declared_fixture_kinds_require_both_extended_cases(self):
        self.report["fixtureKinds"] = ["calibrate", "analyze"]
        with self.assertRaises(ValueError):
            validate_report(self.report)
        for key in ("exporter_manifest_analyze", "legacy_disabled_analyze"):
            self.report["cases"].append({"id": key, "status": "passed",
                                         "evidenceDirectory": str(self.root / key)})
        self.report["passed"] += 2
        self.report["total"] += 2
        validate_report(self.report)

    def test_duplicate_fixture_kinds_fail(self):
        self.report["fixtureKinds"] = ["calibrate", "calibrate"]
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_failed_case_requires_nonempty_error(self):
        self.report["cases"][0]["status"] = "failed"
        self.report["passed"] -= 1
        self.report["failed"] += 1
        for value in (None, "", "  ", {}, False):
            with self.subTest(failure=value):
                self.report["cases"][0]["error"] = value
                with self.assertRaises(ValueError):
                    validate_report(self.report)
        self.report["cases"][0]["error"] = "Injected failure retained for diagnosis"
        validate_report(self.report)

    def test_failed_status_cannot_hide_in_passed_counts(self):
        self.report["cases"][0].update(status="failed", error="Native fixture failed")
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_passed_case_cannot_contain_error(self):
        self.report["cases"][0]["error"] = "Native fixture failed"
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_case_evidence_cannot_escape_root(self):
        self.report["cases"][0]["evidenceDirectory"] = str(self.root.parent / "elsewhere")
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_case_evidence_cannot_alias_another_case(self):
        self.report["cases"][1]["evidenceDirectory"] = self.report["cases"][0]["evidenceDirectory"]
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_report_location_must_match_evidence_root(self):
        with self.assertRaises(ValueError):
            validate_report(self.report, self.root / "elsewhere" / "report.json")

    def test_baseline_flag_requires_counterexample_case(self):
        self.report["baselineIncluded"] = True
        with self.assertRaises(ValueError):
            validate_report(self.report)
        self.report["cases"].append({"id": "baseline_late_calibration", "status": "passed",
                                     "evidenceDirectory": str(self.root / "baseline_late_calibration")})
        self.report["passed"] += 1
        self.report["total"] += 1
        validate_report(self.report)
        self.report["baselineIncluded"] = False
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_missing_fixture_checks_fails(self):
        del self.report["fixtureChecks"]
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_invalid_baseline_flag_fails(self):
        self.report["baselineIncluded"] = "false"
        with self.assertRaises(ValueError):
            validate_report(self.report)

    def test_backups_must_be_enabled(self):
        for value in (True, None, 0, "false"):
            with self.subTest(backupDisabled=value):
                self.provenance["backupDisabled"] = value
                with self.assertRaises(ValueError):
                    validate_provenance(self.provenance)

    def test_plural_backups_disabled_cannot_hide_the_contract(self):
        self.provenance["backupsDisabled"] = True
        with self.assertRaises(ValueError):
            validate_provenance(self.provenance)

    def test_missing_backup_flag_fails(self):
        del self.provenance["backupDisabled"]
        with self.assertRaises(ValueError):
            validate_provenance(self.provenance)

    def test_missing_or_invalid_binary_hash_fails(self):
        for field in ("sha256", "coreSha256"):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.provenance)
                bad["candidate"][field] = "not a hash"
                with self.assertRaises(ValueError):
                    validate_provenance(bad)

    def test_scientific_validation_purpose_is_not_fixture_scope(self):
        self.provenance["purpose"] = "Scientific validation"
        with self.assertRaises(ValueError):
            validate_provenance(self.provenance)

    def test_duplicate_json_properties_fail(self):
        path = self.root / "bad.json"
        path.write_text('{"failed":0,"failed":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_json(path)

    def test_nonfinite_json_fails(self):
        path = self.root / "bad.json"
        path.write_text('{"failed":NaN}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_json(path)

    def fixture_check(self):
        path = self.root / "fixture.csv"
        path.write_bytes(b"synthetic fixture\n")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": str(path), "beforeSha256": digest, "afterSha256": digest}

    def test_unchanged_fixture_source_is_verified(self):
        self.report["fixtureChecks"] = [self.fixture_check()]
        validate_report(self.report)

    def test_changed_source_hash_fails(self):
        item = self.fixture_check()
        item["afterSha256"] = "0" * 64
        self.report["fixtureChecks"] = [item]
        with self.assertRaisesRegex(ValueError, "Fixture source was modified"):
            validate_report(self.report)

    def test_same_size_source_mutation_fails(self):
        item = self.fixture_check()
        path = Path(item["path"])
        path.write_bytes(b"X" * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, "Retained fixture source hash differs"):
            validate_fixture_checks([item])

    def test_missing_fixture_source_fails(self):
        item = self.fixture_check()
        Path(item["path"]).unlink()
        with self.assertRaises(ValueError):
            validate_fixture_checks([item])

    def test_duplicate_fixture_source_fails(self):
        item = self.fixture_check()
        with self.assertRaises(ValueError):
            validate_fixture_checks([item, copy.deepcopy(item)])


class ResumeMachinePayloadCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "schemaVersion": "mvs-cli-result/v1", "status": "error", "exitCode": 1,
            "execution": {"completed": False, "outcome": "failed"},
            "scientificReadiness": {"status": "no_go", "scope": "project_release_readiness",
                                    "independentConfirmatoryValidation": False},
            "error": {"type": "OperationCanceledException", "message": "Synthetic cancellation"},
            "outputDirectory": None, "manifestPath": None, "artifacts": [],
        }

    def test_valid_preoutput_error_passes(self):
        validate_no_output(self.payload)

    def test_false_scientific_readiness_fails(self):
        self.payload["scientificReadiness"]["status"] = "go"
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)

    def test_false_confirmatory_validation_fails(self):
        self.payload["scientificReadiness"]["independentConfirmatoryValidation"] = True
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)

    def test_scientific_readiness_scope_cannot_be_a_run_verdict(self):
        self.payload["scientificReadiness"]["scope"] = "per_run_hypothesis_verdict"
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)

    def test_false_completion_fails(self):
        self.payload["execution"]["completed"] = True
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)

    def test_numeric_completion_is_not_boolean(self):
        self.payload["execution"]["completed"] = 0
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)

    def test_preoutput_partial_context_fails(self):
        self.payload["partialOutput"] = {"status": "incomplete"}
        with self.assertRaises(ValueError):
            validate_no_output(self.payload)

    def test_error_without_error_metadata_fails(self):
        self.payload["error"] = None
        with self.assertRaises(ValueError):
            validate_machine_status(self.payload)


class ResumeSupportingEvidenceCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = {"observerCalls": 0, "benchmarkModelExecuted": False,
                          "scope": "Missing-profile pre-model branch only. Full benchmark behavior is outside this seam."}

    def test_benchmark_exclusion_passes(self):
        validate_benchmark_exclusion(self.benchmark)

    def test_benchmark_callback_claim_fails(self):
        self.benchmark["observerCalls"] = 1
        with self.assertRaises(ValueError):
            validate_benchmark_exclusion(self.benchmark)

    def test_false_benchmark_model_execution_claim_fails(self):
        self.benchmark["benchmarkModelExecuted"] = True
        with self.assertRaises(ValueError):
            validate_benchmark_exclusion(self.benchmark)

    def test_benchmark_partial_support_claim_fails(self):
        self.benchmark["benchmarkPartialOutputSupported"] = True
        with self.assertRaises(ValueError):
            validate_benchmark_exclusion(self.benchmark)

    def test_benchmark_boundary_must_be_disclosed(self):
        self.benchmark["scope"] = "All benchmark output behavior is supported"
        with self.assertRaises(ValueError):
            validate_benchmark_exclusion(self.benchmark)

    def test_normalization_preserves_scientific_values(self):
        state = {"CreatedUtc": "volatile", "PayloadHash": "derived", "Seed": 54,
                 "Calibration": [{"Estimate": 1.5}], "EnvironmentHash": "kept"}
        normalized = normalize_parity_json("calibration_state.json", state)
        self.assertEqual(normalized, {"Seed": 54, "Calibration": [{"Estimate": 1.5}],
                                      "EnvironmentHash": "kept"})
        self.assertIn("CreatedUtc", state, "Normalization must not mutate evidence")
        changed = copy.deepcopy(state)
        changed["Calibration"][0]["Estimate"] = 2.5
        self.assertNotEqual(normalized, normalize_parity_json("calibration_state.json", changed))

    def test_manifest_normalization_only_excludes_state_derived_fields(self):
        manifest = {"created": "volatile", "runId": "volatile", "formulaHash": "kept",
                    "files": [{"FileName": "calibration_state.json", "sha256": "derived", "SizeBytes": 5},
                              {"FileName": "results.csv", "sha256": "kept", "SizeBytes": 10}]}
        self.assertEqual(normalize_parity_json("run_manifest.json", manifest), {
            "formulaHash": "kept", "files": [{"FileName": "calibration_state.json"},
            {"FileName": "results.csv", "sha256": "kept", "SizeBytes": 10}]})


class SavedNativeResumeOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied = os.environ.get("MVS_RESUME_OUTPUT_RESULTS")
        if not supplied:
            raise unittest.SkipTest("Set MVS_RESUME_OUTPUT_RESULTS to an explicitly executed native harness report.json; discovery never launches native work")
        cls.report_path = Path(supplied).resolve()
        cls.report = load_json(cls.report_path)
        cls.cases = validate_report(cls.report, cls.report_path)
        cls.provenance = validate_provenance(load_json(cls.report_path.parent / "provenance.json"))

    def evidence(self, case_id, filename="stdout.json"):
        case = self.cases[case_id]
        self.assertEqual(case["status"], "passed", case)
        directory = Path(case["evidenceDirectory"])
        self.assertTrue(directory.is_dir(), f"Missing case evidence directory: {case_id}")
        return load_json(directory / filename)

    def test_native_report_is_complete_and_passed(self):
        self.assertTrue(REQUIRED_CASES <= set(self.cases))
        expected_baseline = BASELINE_CASES if self.report["baselineIncluded"] else set()
        self.assertEqual(set(self.cases) - OPTIONAL_CASES, REQUIRED_CASES | expected_baseline)
        self.assertEqual(self.report["passed"], len(self.cases))
        self.assertEqual(self.report["failed"], 0)
        self.assertTrue(all(case["status"] == "passed" for case in self.cases.values()))
        validate_fixture_checks(self.report["fixtureChecks"])
        fixtures = load_json(self.report_path.parent / "fixtures" / "manifest.json")
        expected_sources = {fixtures["partial"], *fixtures["completed"].values()}
        expected_sources.update(str(self.directory("history_" + variant) / "source.mvsbackup")
                                for variant in ("empty", "foreign", "current"))
        self.assertEqual({item["path"] for item in self.report["fixtureChecks"]}, expected_sources)
        self.assertEqual(set(fixtures["completed"]), set(self.report["fixtureKinds"]))

    def directory(self, case_id):
        return Path(self.cases[case_id]["evidenceDirectory"])

    def restored_folder(self, directory):
        folders = [path for path in (directory / "output").glob("MVS_restored_*") if path.is_dir()]
        self.assertEqual(len(folders), 1, f"Expected one restored output in {directory}")
        return folders[0]

    def assert_events(self, directory, folder, completed_names, attempted_name=None):
        expected = [{"kind": "start", "path": str(folder)}]
        for name in completed_names:
            expected.extend([{"kind": "before", "path": str(folder / name)},
                             {"kind": "after", "path": str(folder / name)}])
        if attempted_name is not None:
            expected.append({"kind": "before", "path": str(folder / attempted_name)})
        self.assertEqual(load_json(directory / "events.json"), expected)

    def test_partial_failures_retain_only_verified_current_bytes(self):
        attempted = {"late_calibration": "calibration_tracks.csv",
                     "first_write_failure": "calibration_state.json",
                     "second_write_failure": "calibration.csv",
                     "provenance_write_failure": "backup_resume.json"}
        for case_id, expected_names in PARTIAL_CASES.items():
            with self.subTest(case=case_id):
                payload = self.evidence(case_id)
                validate_machine_status(payload)
                self.assertEqual(payload["command"], "resume")
                validate_partial(payload, expected_names)
                self.assertIsNone(payload["manifestPath"])
                details = self.evidence(case_id, "details.json")
                folder = Path(payload["outputDirectory"])
                if case_id in attempted:
                    target = attempted[case_id]
                    self.assertEqual(payload["error"]["type"], "IOException")
                    self.assertEqual(payload["partialOutput"]["attemptedPath"], str(folder / target))
                    self.assertEqual(payload["partialOutput"]["unverifiedPaths"], [])
                    self.assertIs(details["injected"], True)
                    self.assertEqual(details["target"], target)
                    self.assertEqual(sorted(details["expectedArtifacts"]), sorted(expected_names))
                    self.assert_events(self.directory(case_id), folder, expected_names, target)
                elif case_id == "state_reread_failure":
                    self.assertEqual(payload["error"]["type"], "InvalidDataException")
                    self.assertIsNone(payload["partialOutput"]["attemptedPath"])
                    self.assertEqual(payload["partialOutput"]["unverifiedPaths"],
                                     [str(folder / "calibration_state.json")])
                    self.assertIs(details["corrupted"], True)
                    self.assertIs(details["actualReread"], True)
                    self.assertEqual(details["verifiedArtifacts"], 0)
                    self.assertEqual(load_json(folder / "calibration_state.json"), {})
                    self.assert_events(self.directory(case_id), folder, ["calibration_state.json"])
                else:
                    self.assertEqual(payload["error"]["type"], "OperationCanceledException")
                    self.assertIsNone(payload["partialOutput"]["attemptedPath"])
                    self.assertEqual(payload["partialOutput"]["unverifiedPaths"], [])
                    self.assertIs(details["cancellationPropagated"], True)
                    self.assertIs(details["retainedState"], True)
                    self.assert_events(self.directory(case_id), folder, expected_names)
        late = self.evidence("late_calibration", "details.json")
        self.assertIs(late["wasRestored"], True)
        self.assertIs(late["originalCachedUnit"], True)

    def test_preoutput_failures_have_no_partial_context(self):
        for case_id in ("preoutput_validation_failure", "cancellation_before_output"):
            with self.subTest(case=case_id):
                payload = validate_no_output(self.evidence(case_id))
                details = self.evidence(case_id, "details.json")
                self.assertEqual(details["observerCalls"], 0)
                self.assertEqual(self.evidence(case_id, "events.json"), [])
                if case_id == "cancellation_before_output":
                    self.assertEqual(payload["error"]["type"], "OperationCanceledException")
                    self.assertIs(details["cancellationPropagated"], True)
                    self.assertIs(details["retrySucceeded"], True)
                    retry = self.directory(case_id) / "retry"
                    self.assert_events(retry, self.restored_folder(retry), SUCCESS_ARTIFACTS)
                else:
                    self.assertEqual(payload["error"]["type"], "InvalidDataException")
                    self.assertIs(details["validationRejected"], True)
                    self.assertIs(details["outputFolderCreated"], False)
                    self.assertFalse((self.directory(case_id) / "output").exists())

    def test_observer_exceptions_preserve_original_error_and_allow_retry(self):
        for stage in ("start", "before", "after"):
            case_id = "observer_" + stage + "_throw_retry"
            with self.subTest(stage=stage):
                details = self.evidence(case_id, "details.json")
                self.assertEqual(details["stage"], stage)
                self.assertIs(details["originalExceptionPreserved"], True)
                self.assertIs(details["retrySucceeded"], True)
                expected = ["calibration_state.json"] if stage == "after" else []
                self.assertEqual(details["completedFilesBeforeFailure"], expected)
                payload = validate_machine_status(self.evidence(case_id))
                validate_partial(payload, expected)
                self.assertEqual(payload["error"]["type"], "IOException")
                self.assertEqual(payload["error"]["message"],
                                 f"Intentional synchronous observer {stage} failure.")
                folder = Path(payload["outputDirectory"])
                self.assert_events(self.directory(case_id), folder, expected,
                                   "calibration_state.json" if stage == "before" else None)
                self.assertEqual(payload["partialOutput"]["attemptedPath"],
                                 str(folder / "calibration_state.json") if stage == "before" else None)
                self.assertEqual(payload["partialOutput"]["unverifiedPaths"], [])
                retry = self.directory(case_id) / "retry"
                retry_folder = self.restored_folder(retry)
                self.assert_events(retry, retry_folder, SUCCESS_ARTIFACTS)
                self.assertEqual(sorted(path.name for path in retry_folder.iterdir()),
                                 sorted(SUCCESS_ARTIFACTS))

    def test_history_and_pre_resume_provenance_are_retained(self):
        current = self.evidence("machine_cli_success")["executionEnvironment"]["fingerprint"]
        self.assertTrue(valid_sha256(current))
        for variant in ("empty", "foreign", "current"):
            case_id = "history_" + variant
            with self.subTest(variant=variant):
                details = self.evidence(case_id, "details.json")
                self.assertEqual(details["variant"], variant)
                self.assertIs(details["sourceUnchanged"], True)
                before = [] if variant == "empty" else ["a" * 64] if variant == "foreign" else [current]
                after = [] if variant == "empty" else ["a" * 64, current] if variant == "foreign" else [current]
                self.assertEqual(details["beforeHistory"], before)
                self.assertEqual(details["afterHistory"], after)
                folder = self.restored_folder(self.directory(case_id))
                provenance = load_json(folder / "backup_resume.json")
                self.assertEqual(provenance["environments"], after)
                self.assertIs(type(details["retainedUnits"]), int)
                self.assertGreaterEqual(details["retainedUnits"], 0)
                self.assertEqual(provenance["retainedUnits"], details["retainedUnits"])
                self.assertEqual(datetime.fromisoformat(provenance["resumedFromUtc"]),
                                 datetime.fromisoformat(details["resumedFromUtc"]))
                self.assert_events(self.directory(case_id), folder, SUCCESS_ARTIFACTS)
                source = str(self.directory(case_id) / "source.mvsbackup")
                self.assertIn(source, [item["path"] for item in self.report["fixtureChecks"]])

    def test_legacy_and_disabled_observers_preserve_artifacts(self):
        case_ids = ["legacy_observer_disabled_parity"] + sorted(
            key for key in self.cases if key.startswith("legacy_disabled_"))
        for case_id in case_ids:
            with self.subTest(case=case_id):
                details = self.evidence(case_id, "details.json")
                kind = "calibrate" if case_id == "legacy_observer_disabled_parity" else case_id.removeprefix("legacy_disabled_")
                self.assertEqual(details["kind"], kind)
                self.assertIs(details["legacySucceeded"], True)
                self.assertIs(details["disabledSucceeded"], True)
                self.assertIs(type(details["exitCode"]), int)
                self.assertIn(details["exitCode"], (0, 2))
                first, second = self.directory(case_id) / "legacy", self.directory(case_id) / "disabled"
                left, right = self.restored_folder(first), self.restored_folder(second)
                self.assertEqual(load_json(first / "events.json"), [])
                self.assertEqual(load_json(second / "events.json"), [])
                names = sorted(path.name for path in left.iterdir())
                self.assertEqual(names, sorted(path.name for path in right.iterdir()))
                self.assertEqual(names, sorted(details["artifacts"]))
                self.assertTrue(names, "Parity needs actual retained output")
                for name in names:
                    if name in ("calibration_state.json", "run_manifest.json"):
                        self.assertEqual(normalize_parity_json(name, load_json(left / name)),
                                         normalize_parity_json(name, load_json(right / name)))
                    else:
                        self.assertEqual((left / name).read_bytes(), (right / name).read_bytes(), name)

    def test_machine_and_human_success_keep_existing_contracts(self):
        payload = validate_machine_status(self.evidence("machine_cli_success"), "completed", 0)
        self.assertEqual(payload["command"], "resume")
        self.assertNotIn("partialOutput", payload)
        validate_retained_files(payload["outputDirectory"], payload["artifacts"],
                                SUCCESS_ARTIFACTS, payload["manifestPath"])
        self.assertIsNone(payload["manifestPath"])
        for case_id, machine in (("machine_cli_success", True), ("human_cli_success", False)):
            with self.subTest(case=case_id):
                details = self.evidence(case_id, "details.json")
                self.assertIs(details["actualMainInvoked"], True)
                self.assertIs(details["machine"], machine)
                self.assertIs(details["backupsEnabled"], True)
                self.assertEqual(details["exitCode"], 0)
        human = (self.directory("human_cli_success") / "human-stdout.txt").read_text(encoding="utf-8-sig")
        self.assertTrue(human.startswith("Resumed result saved: "))
        self.assertNotIn("schemaVersion", human)
        folder = self.restored_folder(self.directory("human_cli_success"))
        self.assertIn(str(folder), human)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), sorted(SUCCESS_ARTIFACTS))

    def test_benchmark_validation_does_not_claim_partial_output_support(self):
        payload = validate_no_output(self.evidence("benchmark_validation_callbacks_absent"))
        self.assertEqual(payload["error"]["type"], "InvalidDataException")
        self.assertEqual(payload["error"]["message"], "Missing benchmark profile.")
        self.assertEqual(self.evidence("benchmark_validation_callbacks_absent", "events.json"), [])
        validate_benchmark_exclusion(self.evidence("benchmark_validation_callbacks_absent", "details.json"))
        for data in (self.report, self.provenance, payload):
            for key in ("benchmarkPartialOutputSupported", "benchmarkPartialSupport",
                        "benchmarkPartialOutputSupport"):
                if key in data:
                    self.assertIs(data[key], False, "Benchmark partial output is outside the supported boundary")

    def test_extended_exporter_manifest_failures_verify_retained_files(self):
        for case_id in sorted(key for key in self.cases if key.startswith("exporter_manifest_")):
            with self.subTest(case=case_id):
                details = self.evidence(case_id, "details.json")
                kind = case_id.removeprefix("exporter_manifest_")
                self.assertEqual(details["kind"], kind)
                self.assertIs(details["injected"], True)
                self.assertEqual(details["actualMethod"], "OutputExporter.Export" if kind == "analyze" else "ScientificTables.WriteManifest")
                payload = validate_machine_status(self.evidence(case_id))
                validate_partial(payload, details["expectedArtifacts"])
                self.assertEqual(payload["error"]["type"], "IOException")
                self.assertTrue(payload["artifacts"], "Manifest failure must retain the earlier exporter writes")
                self.assertIsNone(payload["manifestPath"])
                folder = Path(payload["outputDirectory"])
                self.assertEqual(payload["partialOutput"]["attemptedPath"], str(folder / "run_manifest.json"))
                self.assertEqual(payload["partialOutput"]["unverifiedPaths"], [])
                self.assertNotIn("run_manifest.json", details["expectedArtifacts"])
                self.assertIn("backup_resume.json", details["expectedArtifacts"])
                self.assertEqual(sorted(path.name for path in folder.iterdir() if path.is_file()),
                                 sorted(details["expectedArtifacts"]))
                events = self.evidence(case_id, "events.json")
                before = [Path(item["path"]).name for item in events if item["kind"] == "before"]
                after = [Path(item["path"]).name for item in events if item["kind"] == "after"]
                self.assertEqual(before, after + ["run_manifest.json"])
                self.assertEqual(sorted(after), sorted(details["expectedArtifacts"]))
                self.assert_events(self.directory(case_id), folder, after, "run_manifest.json")

    def test_baseline_counterexample_retains_bytes_without_partial_metadata(self):
        if not self.report["baselineIncluded"]:
            self.skipTest("No baseline binary supplied to explicit native execution")
        payload = validate_no_output(self.evidence("baseline_late_calibration"))
        self.assertEqual(payload["error"]["type"], "IOException")
        details = self.evidence("baseline_late_calibration", "details.json")
        self.assertIs(details["injected"], True)
        folder = self.restored_folder(self.directory("baseline_late_calibration"))
        artifacts = [dict(item, name=Path(item["path"]).name) for item in details["retained"]]
        validate_retained_files(folder, artifacts, ["calibration_state.json", "calibration.csv"])


if __name__ == "__main__":
    unittest.main()
