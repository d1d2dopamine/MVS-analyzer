"""Independent checks of synthetic benchmark export provenance.

Pure corruption tests always run and never execute native code. Opt into checking
an already executed native run with MVS_BENCHMARK_EXPORT_RESULTS=/abs/report.json.
A supplied missing/invalid/empty report fails. Native evidence is synthetic export
engineering only, not statistical validation. Set MVS_BENCHMARK_EXPORT_NEGATIVE_DIR
to a new directory to retain rejected JSON fixtures alongside regression evidence.
"""
import copy
import csv
import io
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

TABLES = {
    "benchmark_report.md", "benchmark_summary.csv", "benchmark_replications.csv",
    "benchmark_replication_procedures.csv", "benchmark_replication_metrics.csv",
    "benchmark_metrics.csv", "benchmark_choices.csv", "benchmark_stability.csv",
    "benchmark_stability_replications.csv", "benchmark_verdicts.csv", "benchmark_protocol.txt",
    "benchmark_stability_method.txt",
}
BENCHMARK_FILES = TABLES | {"benchmark_manifest.json", "SHA256SUMS.txt"}
REQUIRED_CASES = {
    "benchmark_main_partial", "benchmark_main_foreign", "benchmark_main_clean", "benchmark_main_exit0",
    "resume_api_partial", "resume_api_foreign", "resume_api_provenance", "resume_api_clean",
    "resume_main_clean", "resume_main_exit0", "benchmark_api_first", "benchmark_api_manifest",
    "benchmark_api_checksum", "benchmark_api_before_throw", "benchmark_api_after_throw",
    "benchmark_api_start_throw", "resume_api_manifest_rewrite", "resume_api_checksum_rewrite",
    "resume_api_manifest_read", "resume_api_start_throw", "benchmark_legacy_parity",
    "resume_legacy_parity", "preoutput_failure", "benchmark_api_cancel_after_write",
    "resume_api_cancel_after_write", "benchmark_figure_parity",
    "corrected_tau_identity", "mixed_tau_preoutput",
}
PARITY_CASES = {"benchmark_legacy_parity", "resume_legacy_parity"}
SCOPE = "current_invocation_successful_writes"
# Round 42 extends the v1 engineering evidence contract; historical Round 38/39
# validators and reports remain in their original evidence, without relabeling.
PROTOCOL_HASH = "b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268"
METHOD_HASHES = {
    "kendall-tau-b-v2": "408d7cf64a8910cd90a423d7f995eaf756d1f687310cb7f1ea0ecf362b619a4f",
    "kendall-legacy-v1": "39169e17ca56ce431c5695a955d0593efa9df5ad5b8a8da1308d85cb2db77a89",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "Duplicate JSON key")
            obj[key] = value
        return obj
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def absolute(value, label):
    require(isinstance(value, str) and Path(value).is_absolute(), "Invalid absolute " + label)
    return Path(value)


def case_mode(case):
    if case in PARITY_CASES or case == "preoutput_failure":
        return case
    for prefix in ("benchmark_main_", "benchmark_api_", "resume_main_", "resume_api_"):
        if case.startswith(prefix):
            return case[len(prefix):]
    raise ValueError("Unknown case")


def expected_artifacts(case):
    mode = case_mode(case)
    if mode in {"first", "start_throw", "preoutput_failure"}:
        return set()
    if mode in {"partial", "before_throw", "after_throw", "cancel_after_write"}:
        return {"benchmark_report.md"}
    if mode == "manifest":
        return TABLES
    if mode in {"checksum", "provenance"}:
        return TABLES | {"benchmark_manifest.json"}
    if mode in {"manifest_rewrite", "manifest_read"}:
        return TABLES | {"backup_resume.json"}
    if mode == "checksum_rewrite":
        return TABLES | {"backup_resume.json", "benchmark_manifest.json"}
    return BENCHMARK_FILES | ({"backup_resume.json"} if case.startswith("resume_") else set())


def validate_payload(payload, case, folder):
    require(isinstance(payload, dict), "Payload must be an object")
    mode = case_mode(case)
    completed = mode in {"clean", "foreign", "exit0"}
    code = 0 if mode == "exit0" else 2 if completed else 1
    require(payload.get("schemaVersion") == "mvs-cli-result/v1", "Wrong CLI schema")
    require(type(payload.get("exitCode")) is int and payload["exitCode"] == code, "Wrong exit code")
    require(payload.get("status") == {0: "completed", 1: "error", 2: "diagnostic"}[code], "Wrong status")
    require(payload.get("execution") == {"completed": completed, "outcome": {0: "completed", 1: "failed", 2: "completed_with_diagnostic"}[code]}, "Wrong execution outcome")
    readiness = payload.get("scientificReadiness", {})
    require(readiness.get("status") == "no_go" and readiness.get("scope") == "project_release_readiness"
            and readiness.get("independentConfirmatoryValidation") is False, "Scientific readiness changed")
    require((payload.get("error") is None) if completed else isinstance(payload.get("error"), dict), "Wrong error metadata")
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list), "Missing artifact list")
    if mode == "preoutput_failure":
        require(payload.get("outputDirectory") is None and payload.get("manifestPath") is None
                and artifacts == [] and "partialOutput" not in payload, "Pre-output failure claimed output")
        return
    require(absolute(payload.get("outputDirectory"), "output directory") == folder, "Wrong actual output directory")
    require(payload.get("artifactScope") == SCOPE, "Missing ownership scope")
    require(("partialOutput" in payload) is (not completed), "Wrong partialOutput presence")
    names, paths = set(), set()
    for item in artifacts:
        require(isinstance(item, dict), "Invalid artifact")
        name = item.get("name")
        require(isinstance(name, str) and name not in names, "Invalid or duplicate artifact name")
        names.add(name)
        path = absolute(item.get("path"), "artifact path")
        require(path.parent == folder and path.name == name and path not in paths, "Artifact path escapes ownership")
        paths.add(path)
        require(path.is_file(), "Artifact file is missing")
        require(type(item.get("sizeBytes")) is int and path.stat().st_size == item["sizeBytes"], "Artifact size differs")
        require(valid_hash(item.get("sha256")) and sha(path) == item["sha256"], "Artifact hash differs")
    require(names == expected_artifacts(case), "Artifact member set differs")
    require(payload.get("manifestPath") == (str(folder / "benchmark_manifest.json") if "benchmark_manifest.json" in names else None), "Manifest path claims an unverified file")
    if not completed:
        partial = payload["partialOutput"]
        require(isinstance(partial, dict) and partial.get("status") == "incomplete" and partial.get("scope") == SCOPE, "Wrong partial metadata")
        require(isinstance(partial.get("unverifiedPaths"), list), "Missing unverified paths")
        targets = {"partial": "benchmark_summary.csv", "before_throw": "benchmark_summary.csv",
                   "first": "benchmark_report.md", "manifest": "benchmark_manifest.json",
                   "manifest_rewrite": "benchmark_manifest.json", "checksum": "SHA256SUMS.txt",
                   "checksum_rewrite": "SHA256SUMS.txt", "provenance": "backup_resume.json"}
        target = targets.get(mode)
        require(partial.get("attemptedPath") == (str(folder / target) if target else None), "Wrong attempted path")
        expected_unverified = [str(folder / "benchmark_manifest.json")] if mode == "manifest_read" else []
        require(partial["unverifiedPaths"] == expected_unverified, "Wrong unverified paths")
        if case.startswith("resume_") and mode in {"provenance", "manifest_rewrite", "manifest_read"}:
            require((folder / "SHA256SUMS.txt").is_file() and "SHA256SUMS.txt" not in names,
                    "Stale initial checksum is claimed or original evidence was lost")
    else:
        validate_success_members(folder, case.startswith("resume_"))
    if mode == "foreign":
        for name in ("foreign-old-canary.txt", "foreign-nested/foreign-old-nested.txt"):
            require((folder / name).is_file(), "Unrelated canary was not retained on disk")


def validate_success_members(folder, resume):
    manifest = load_json(folder / "benchmark_manifest.json")
    members = manifest.get("files")
    expected = TABLES | ({"backup_resume.json"} if resume else set())
    require(isinstance(members, list) and all(isinstance(n, str) for n in members)
            and len(members) == len(set(members)) and set(members) == expected, "Manifest membership differs")
    sums = (folder / "SHA256SUMS.txt").read_text().splitlines()
    seen = set()
    for line in sums:
        require(len(line) > 66 and valid_hash(line[:64]) and line[64:66] == "  ", "Invalid checksum line")
        name = line[66:]
        require(name not in seen and name in expected | {"benchmark_manifest.json"}, "Unexpected checksum member")
        seen.add(name)
        require(sha(folder / name) == line[:64], "Checksum differs from file bytes")
    require(seen == expected | {"benchmark_manifest.json"}, "Checksum membership differs")


def validate_report(report, report_path):
    require(isinstance(report, dict) and report.get("schema") == "mvs-benchmark-export-tests/v1", "Wrong report schema")
    require(report.get("baseline") is False, "Candidate evidence cannot be a baseline reproduction")
    root = absolute(report.get("evidenceRoot"), "evidence root")
    require(root.resolve() == Path(report_path).resolve().parent, "Evidence root differs from report location")
    require(report.get("scientificSimulations") == 0 and type(report.get("scientificSimulations")) is int
            and report.get("scientificReadiness") == "no_go", "Invalid engineering-only scope")
    cases = report.get("cases")
    require(isinstance(cases, list), "Missing cases")
    ids, directories, passed, failed = set(), set(), 0, 0
    for item in cases:
        require(isinstance(item, dict) and item.get("id") in REQUIRED_CASES and item["id"] not in ids, "Unknown or duplicate case")
        ids.add(item["id"])
        directory = absolute(item.get("evidenceDirectory"), "case directory")
        require(directory.parent == root and directory.name == item["id"] and directory not in directories, "Case directory escapes evidence root")
        directories.add(directory)
        require(item.get("status") in {"passed", "failed"}, "Unknown case status")
        if item["status"] == "passed":
            passed += 1
            require("error" not in item, "Passed case carries failure")
        else:
            failed += 1
            require(isinstance(item.get("error"), str) and item["error"].strip(), "Failed case lacks error")
    require(ids == REQUIRED_CASES, "Missing required cases")
    for key, actual in (("passed", passed), ("failed", failed), ("total", len(cases))):
        require(type(report.get(key)) is int and report[key] == actual, "Incorrect " + key + " total")
    require(failed == 0, "Native harness reported failures")
    checkpoint = absolute(report.get("fixture"), "checkpoint path")
    require(checkpoint.parent == root / "fixture" and checkpoint.is_file(), "Missing immutable checkpoint")
    require(valid_hash(report.get("fixtureSha256Before")) and report["fixtureSha256Before"] == report.get("fixtureSha256After")
            and sha(checkpoint) == report["fixtureSha256Before"], "Checkpoint changed")
    require(valid_hash(report.get("cachedOutcomeSha256")), "Missing cached outcome identity")
    return root


def validate_identity_metadata(manifest, method):
    require(method in METHOD_HASHES, "Unknown expected stability method")
    digest = METHOD_HASHES[method]
    key = f"{PROTOCOL_HASH}/{method}/{digest}"
    require(manifest.get("stabilityMethod") == method and manifest.get("stabilityMethodHash") == digest
            and manifest.get("comparabilityKey") == key, "Wrong exact stability/comparison identity")
    require(manifest.get("protocolHash") == manifest.get("protocolHashFrozen") == PROTOCOL_HASH
            and manifest.get("protocolUnchanged") is True, "Frozen protocol identity changed")
    require(manifest.get("stabilityMethodProvenance") == ("legacy_unversioned" if method == "kendall-legacy-v1" else "explicit_method_identity"), "Stability provenance overstated")
    return [method, digest, key]


def validate_csv_identity(text, identity):
    rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    require(bool(rows) and rows[0][-3:] == ["stability_method", "stability_method_hash", "comparability_key"], "Missing CSV identity columns")
    require(all(len(row) == len(rows[0]) and row[-3:] == identity for row in rows[1:]), "Wrong CSV logical-row identity")


def validate_export_identity(folder, method):
    manifest = load_json(folder / "benchmark_manifest.json")
    identity = validate_identity_metadata(manifest, method)
    require(sha(folder / "benchmark_protocol.txt") == PROTOCOL_HASH, "Frozen protocol bytes changed")
    for name in sorted(TABLES):
        if name.endswith(".csv"):
            with (folder / name).open(encoding="utf-8-sig", newline="") as stream:
                validate_csv_identity(stream.read(), identity)
    sidecar = (folder / "benchmark_stability_method.txt").read_text()
    markdown = (folder / "benchmark_report.md").read_text()
    require(all(part in sidecar for part in identity) and identity[0] in markdown and identity[2] in markdown, "Report/sidecar identity missing")
    if method == "kendall-legacy-v1":
        require("original executable identity was not recorded" in sidecar, "Legacy provenance overclaimed")


def validate_tau_case(directory, corrected):
    details = load_json(directory / "details.json")
    require(type(details.get("actualSimulations")) is int and details["actualSimulations"] == 0, "Tau fixture scope changed")
    if not corrected:
        require(details.get("callbacks") == 0 and type(details["callbacks"]) is int
                and details.get("outputCreated") is False and not (directory / "output").exists()
                and details.get("error") == details.get("legacyWrapperError") == "InvalidDataException", "Mixed provenance reached output")
        return
    folder = absolute(details.get("folder"), "corrected output folder")
    require(directory in folder.parents and details.get("cachedOutcomeUnchanged") is True, "Invalid corrected fixture boundary")
    validate_success_members(folder, True)
    validate_export_identity(folder, "kendall-tau-b-v2")
    before = load_json(directory / "document-before.json")
    after = load_json(directory / "document-after.json")
    require(set(before.get("Units", {})) == {"result"} and before["Units"] == after.get("Units"), "Cached units mutated")
    require(after.get("SavedUtc", "") >= before.get("SavedUtc", ""), "Save timestamp regressed")
    before.pop("SavedUtc"); after.pop("SavedUtc")
    require(before == after, "Document changed beyond save timestamp")
    outcome = before["Units"]["result"]
    require(outcome.get("StabilityMethod") == "kendall-tau-b-v2" and outcome.get("Overall") == "no-go"
            and outcome["Stability"]["Tau"] == [0.5] and outcome["Verdicts"][0]["Result"] == "fail", "Synthetic historical fields changed")
    manifest = load_json(folder / "benchmark_manifest.json")
    require(manifest["overall"] == "no-go" and manifest["stability"]["medianTau"] == .5, "Exported cached fields changed")
    journal = directory.parent / "isolation/MVS_APPDATA_ROOT/MVS_Analyzer/benchmark_journal.jsonl"
    entries = [json.loads(line) for line in journal.read_text().splitlines()]
    matches = [entry for entry in entries if entry.get("folder") == str(folder)]
    require(len(matches) == 1 and all(matches[0].get(key) == manifest[key] for key in ("stabilityMethod", "stabilityMethodHash", "comparabilityKey")), "Corrected journal identity differs")


def validate_saved_report(path):
    report = load_json(path)
    root = validate_report(report, path)
    provenance = load_json(root / "provenance.json")
    require(provenance.get("schema") == "mvs-benchmark-export-provenance/v1" and provenance.get("baseline") is False
            and provenance.get("backupDisabled") is False and "synthetic engineering fixtures only" in provenance.get("purpose", "").lower(), "Invalid native provenance")
    for field in ("binarySha256", "coreSha256", "harnessSha256"):
        require(valid_hash(provenance.get(field)), "Missing binary provenance")
    source = load_json(root / "fixture" / "backup.json")
    require(source.get("CalculationComplete") is True and set(source.get("Units", {})) == {"result"}, "Fixture is not a completed cached result")
    require(source["Units"]["result"].get("Conditions") == [] and source["Units"]["result"].get("Overall") == "no-go", "Fixture is not the empty synthetic no-go outcome")
    for case in sorted(REQUIRED_CASES):
        directory = root / case
        if case in {"corrected_tau_identity", "mixed_tau_preoutput"}:
            validate_tau_case(directory, case == "corrected_tau_identity")
            continue
        if case == "benchmark_figure_parity":
            validate_figure_case(directory)
            continue
        if case in PARITY_CASES:
            parity = load_json(directory / "parity.json")
            files = parity.get("files")
            require(isinstance(files, list) and len(files) == len(expected_artifacts(case)), "Missing parity file checks")
            require({f["name"] for f in files} == expected_artifacts(case), "Parity omitted files")
            for item in files:
                require(item["legacySha256"] == item["observedSha256"] == sha(item["legacy"]) == sha(item["observed"]), "Legacy exact-byte parity failed")
            continue
        details = load_json(directory / "details.json")
        require(details.get("actualSimulations") == 0, "Case scope changed")
        folder = None if case == "preoutput_failure" else absolute(details.get("folder"), "case output folder")
        if folder is not None:
            require(directory in folder.parents, "Output folder escapes case evidence")
            require(details.get("sourceFixtureUnchanged") is True, "Case changed input fixture")
        validate_payload(load_json(directory / "stdout.json"), case, folder)
        if folder is not None and case_mode(case) in {"clean", "foreign", "exit0"}:
            validate_export_identity(folder, "kendall-legacy-v1")
        if case == "preoutput_failure":
            require(details.get("callbacks") == 0, "Pre-output validation called observer")
            continue
        boundary = load_json(directory / "boundary.json")
        if "_main_" in case:
            require(boundary.get("actualCliMain") is True, "Main evidence is a substituted API call")
        else:
            require(boundary.get("actualCliMain") is False and boundary.get("starts") == 1, "Observer did not start exactly once")
            events = boundary.get("events")
            require(isinstance(events, list) and events[0].get("kind") == "start" and events[0].get("path") == str(folder), "Wrong observer start folder")
            require(all(p.get("fraction") in (0, .99, .995) for p in boundary.get("progress", [])), "Unexpected computational progress")
            if case.endswith("cancel_after_write"):
                require(boundary.get("errorType") == "OperationCanceledException", "Cancellation exception was lost")
            if case == "resume_api_clean":
                require(len(events) == 36, "Missing clean resume observer events")
    return report

def validate_figure_case(directory):
    details = load_json(directory / "details.json")
    folder = absolute(details.get("folder"), "figure output folder")
    require(directory in folder.parents and details.get("starts") == 1 and details.get("actualSimulations") == 0
            and details.get("sourceFixtureUnchanged") is True, "Invalid returned-figure boundary")
    payload = load_json(directory / "stdout.json")
    require(payload.get("status") == "diagnostic" and payload.get("exitCode") == 2
            and payload.get("execution") == {"completed": True, "outcome": "completed_with_diagnostic"}
            and payload.get("artifactScope") == SCOPE and "partialOutput" not in payload
            and payload.get("scientificReadiness", {}).get("status") == "no_go", "Invalid figure machine result")
    require(payload.get("outputDirectory") == str(folder) and payload.get("manifestPath") == str(folder / "benchmark_manifest.json"), "Wrong figure directory/manifest")
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 15
            and {item["name"] for item in artifacts} == BENCHMARK_FILES | {"returned-fixture.svg"}, "Returned-figure artifacts differ")
    for item in artifacts:
        path = folder / ("figures/returned-fixture.svg" if item["name"] == "returned-fixture.svg" else item["name"])
        require(item["path"] == str(path) and item["sizeBytes"] == path.stat().st_size and item["sha256"] == sha(path), "Returned figure bytes differ")
    validate_export_identity(folder, "kendall-legacy-v1")
    members = TABLES | {"figures/returned-fixture.svg"}
    manifest = load_json(folder / "benchmark_manifest.json")
    require(set(manifest.get("files", [])) == members and len(manifest["files"]) == len(members), "Figure manifest membership differs")
    sums = (folder / "SHA256SUMS.txt").read_text().splitlines()
    require(len(sums) == 14 and {line[66:] for line in sums} == members | {"benchmark_manifest.json"}, "Figure checksum members differ")
    for line in sums:
        require(line[64:66] == "  " and sha(folder / line[66:]) == line[:64], "Figure checksum differs")
    require((folder / "figures/unreturned-canary.txt").is_file(), "Unreturned renderer file was lost")
    events = details.get("events")
    require(isinstance(events, list) and len(events) == 29 and events[0] == {"path": str(folder / "figures/returned-fixture.svg"), "completed": True}, "Returned figure was not observed")
    parity = load_json(directory / "parity.json")
    expected = BENCHMARK_FILES | {"figures/returned-fixture.svg"}
    require(len(parity.get("files", [])) == len(expected) and {item["name"] for item in parity["files"]} == expected, "Figure parity omitted files")
    for item in parity["files"]:
        require(item["legacySha256"] == item["observedSha256"] == sha(item["legacy"]) == sha(item["observed"]), "Figure wrapper parity failed")


class BenchmarkExportCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "output"
        self.folder.mkdir()
        path = self.folder / "benchmark_report.md"
        path.write_text("Synthetic report only\n")
        self.payload = {
            "schemaVersion": "mvs-cli-result/v1", "status": "error", "exitCode": 1,
            "execution": {"completed": False, "outcome": "failed"},
            "scientificReadiness": {"scope": "project_release_readiness", "status": "no_go", "independentConfirmatoryValidation": False},
            "error": {"type": "IOException", "message": "Synthetic failure"},
            "outputDirectory": str(self.folder), "artifactScope": SCOPE, "manifestPath": None,
            "artifacts": [{"name": path.name, "path": str(path), "sizeBytes": path.stat().st_size, "sha256": sha(path)}],
            "partialOutput": {"status": "incomplete", "scope": SCOPE, "attemptedPath": str(self.folder / "benchmark_summary.csv"), "unverifiedPaths": []},
        }
        checkpoint = self.root / "fixture" / "synthetic.mvsbackup"
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(b"synthetic checker-only archive fixture")
        self.report = {"schema": "mvs-benchmark-export-tests/v1", "baseline": False, "evidenceRoot": str(self.root),
                       "scientificSimulations": 0, "scientificReadiness": "no_go", "passed": len(REQUIRED_CASES), "failed": 0,
                       "total": len(REQUIRED_CASES), "cases": [{"id": case, "status": "passed", "evidenceDirectory": str(self.root / case)} for case in sorted(REQUIRED_CASES)],
                       "fixture": str(checkpoint), "fixtureSha256Before": sha(checkpoint), "fixtureSha256After": sha(checkpoint), "cachedOutcomeSha256": "a" * 64}

    def reject(self, value, validator):
        with self.assertRaises((ValueError, OSError)) as caught:
            validator(value)
        target = os.environ.get("MVS_BENCHMARK_EXPORT_NEGATIVE_DIR")
        if target:
            directory = Path(target)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (self.id().rsplit(".", 1)[-1] + ".json")
            with path.open("x") as stream:
                json.dump({"schema": "mvs-benchmark-export-negative/v1", "test": self.id(), "expectedRejection": str(caught.exception), "fixture": value,
                           "scope": "Pure validator corruption fixture; referenced temporary paths are intentionally not native evidence."}, stream, indent=2)

    def reject_payload(self):
        self.reject(self.payload, lambda p: validate_payload(p, "benchmark_main_partial", self.folder))

    def test_valid_partial(self):
        validate_payload(self.payload, "benchmark_main_partial", self.folder)

    def test_wrong_hash(self):
        self.payload["artifacts"][0]["sha256"] = "0" * 64
        self.reject_payload()

    def test_wrong_size(self):
        self.payload["artifacts"][0]["sizeBytes"] += 1
        self.reject_payload()

    def test_duplicate_artifact(self):
        self.payload["artifacts"].append(copy.deepcopy(self.payload["artifacts"][0]))
        self.reject_payload()

    def test_foreign_artifact(self):
        foreign = self.folder / "foreign-old-canary.txt"
        foreign.write_text("foreign")
        self.payload["artifacts"].append({"name": foreign.name, "path": str(foreign), "sizeBytes": foreign.stat().st_size, "sha256": sha(foreign)})
        self.reject_payload()

    def test_false_completion(self):
        self.payload["execution"]["completed"] = True
        self.reject_payload()

    def test_false_readiness(self):
        self.payload["scientificReadiness"]["status"] = "go"
        self.reject_payload()

    def test_wrong_attempted_path(self):
        self.payload["partialOutput"]["attemptedPath"] = None
        self.reject_payload()

    def test_stale_manifest_claim(self):
        self.payload["manifestPath"] = str(self.folder / "benchmark_manifest.json")
        self.reject_payload()

    def test_missing_ownership(self):
        self.payload.pop("artifactScope")
        self.reject_payload()

    def test_valid_report_structure(self):
        validate_report(self.report, self.root / "report.json")

    def test_zero_native_cases(self):
        self.report.update(cases=[], total=0, passed=0)
        self.reject(self.report, lambda p: validate_report(p, self.root / "report.json"))

    def test_duplicate_case(self):
        self.report["cases"][1] = copy.deepcopy(self.report["cases"][0])
        self.reject(self.report, lambda p: validate_report(p, self.root / "report.json"))

    def test_wrong_totals(self):
        self.report["passed"] += 1
        self.reject(self.report, lambda p: validate_report(p, self.root / "report.json"))

    def test_checkpoint_changed(self):
        Path(self.report["fixture"]).write_bytes(b"changed")
        self.reject(self.report, lambda p: validate_report(p, self.root / "report.json"))

    def test_baseline_rejected_as_fixed(self):
        self.report["baseline"] = True
        self.reject(self.report, lambda p: validate_report(p, self.root / "report.json"))

    def test_malformed_checksum_members(self):
        for name in TABLES:
            (self.folder / name).write_text("Synthetic file\n")
        (self.folder / "benchmark_manifest.json").write_text(json.dumps({"files": sorted(TABLES)}))
        names = TABLES | {"benchmark_manifest.json"}
        (self.folder / "SHA256SUMS.txt").write_text("".join(f"{sha(self.folder / n)}  {n}\n" for n in sorted(names)))
        validate_success_members(self.folder, False)
        foreign = self.folder / "foreign-old-canary.txt"
        foreign.write_text("foreign")
        with (self.folder / "SHA256SUMS.txt").open("a") as stream:
            stream.write(f"{sha(foreign)}  {foreign.name}\n")
        self.reject({"sums": (self.folder / "SHA256SUMS.txt").read_text()}, lambda _: validate_success_members(self.folder, False))

    def test_duplicate_manifest_members(self):
        (self.folder / "benchmark_manifest.json").write_text(json.dumps({"files": sorted(TABLES) + ["benchmark_report.md"]}))
        self.reject(load_json(self.folder / "benchmark_manifest.json"), lambda _: validate_success_members(self.folder, False))


class TauIdentityCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.method = "kendall-tau-b-v2"
        self.identity = [self.method, METHOD_HASHES[self.method], f"{PROTOCOL_HASH}/{self.method}/{METHOD_HASHES[self.method]}"]
        self.manifest = dict(zip(("stabilityMethod", "stabilityMethodHash", "comparabilityKey"), self.identity))
        self.manifest.update(protocolHash=PROTOCOL_HASH, protocolHashFrozen=PROTOCOL_HASH, protocolUnchanged=True, stabilityMethodProvenance="explicit_method_identity")

    def test_valid_current_and_legacy_identity(self):
        validate_identity_metadata(self.manifest, self.method)
        legacy = "kendall-legacy-v1"
        self.manifest.update(stabilityMethod=legacy, stabilityMethodHash=METHOD_HASHES[legacy], comparabilityKey=f"{PROTOCOL_HASH}/{legacy}/{METHOD_HASHES[legacy]}", stabilityMethodProvenance="legacy_unversioned")
        validate_identity_metadata(self.manifest, legacy)

    def test_identity_corruption_rejected(self):
        for field in self.manifest:
            with self.subTest(field=field):
                damaged = dict(self.manifest)
                damaged[field] = False if field == "protocolUnchanged" else "wrong"
                with self.assertRaises(ValueError):
                    validate_identity_metadata(damaged, self.method)

    def csv_fixture(self):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["tau", "reason", "stability_method", "stability_method_hash", "comparability_key"])
        writer.writerow(["", 'undefined, "ties"\r\nretained reason', *self.identity])
        writer.writerow(["0.5", "", *self.identity])
        return stream.getvalue()

    def test_quoted_newline_and_empty_tables(self):
        validate_csv_identity(self.csv_fixture(), self.identity)
        validate_csv_identity(self.csv_fixture().splitlines()[0] + "\n", self.identity)

    def test_each_logical_row_identity_checked(self):
        rows = list(csv.reader(io.StringIO(self.csv_fixture(), newline="")))
        for row_index in (0, 1, 2):
            with self.subTest(row=row_index):
                damaged = copy.deepcopy(rows)
                damaged[row_index][-1] = "wrong"
                stream = io.StringIO(newline="")
                csv.writer(stream).writerows(damaged)
                with self.assertRaises(ValueError):
                    validate_csv_identity(stream.getvalue(), self.identity)

    def test_mixed_provenance_requires_zero_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            details = {"actualSimulations": 0, "callbacks": 0, "outputCreated": False,
                       "error": "InvalidDataException", "legacyWrapperError": "InvalidDataException"}
            path = folder / "details.json"
            path.write_text(json.dumps(details))
            validate_tau_case(folder, False)
            for key, value in (("callbacks", 1), ("outputCreated", True), ("error", "IOException"), ("legacyWrapperError", None)):
                with self.subTest(key=key):
                    path.write_text(json.dumps(dict(details, **{key: value})))
                    with self.assertRaises(ValueError):
                        validate_tau_case(folder, False)
            path.write_text(json.dumps(details))
            (folder / "output").mkdir()
            with self.assertRaises(ValueError):
                validate_tau_case(folder, False)


class SavedBenchmarkExportEvidenceTests(unittest.TestCase):
    def test_saved_native_evidence(self):
        value = os.environ.get("MVS_BENCHMARK_EXPORT_RESULTS")
        if value is None:
            self.skipTest("Set MVS_BENCHMARK_EXPORT_RESULTS after explicitly running the synthetic native harness")
        require(bool(value.strip()), "MVS_BENCHMARK_EXPORT_RESULTS is empty")
        validate_saved_report(value)


if __name__ == "__main__":
    unittest.main()
