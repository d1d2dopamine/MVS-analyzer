"""Synthetic software fixtures only; no retained outcome or native execution."""
import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import benchmark_suite as suite


class RegistryFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "validation").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "code.py").write_text("# Synthetic software fixture\nvalue = 1\n", encoding="utf-8")
        self.evidence = {
            "passed": 4, "requested": 10, "rate": 0.4,
            "zero": 0, "false": False, "float_zero": 0.0,
            "label": "synthetic fixture", "nullable": None,
            "values": [1, {"a/b": {"~key": 2}}],
            "structured": {"zero": 0, "list": [False, 1.0]},
        }
        self.write_json("evidence.json", self.evidence)
        self.registry = {
            "schema_version": 1, "suite_id": "MVS-Benchmark-Suite", "suite_version": "1.0.0",
            "sources": [{"id": "methodology", "role": "Synthetic reference only",
                         "url": "https://www.nist.gov/itl/sed/statistical-reference-datasets"}],
            "nist_support": [{
                "operation": "Arithmetic mean", "status": "mapped_not_run",
                "source_url": "https://www.nist.gov/itl/sed/statistical-reference-datasets",
                "code_refs": [dict(self.reference("code.py"), lines=[1, 2])],
                "reason_ru": "Синтетическая карта, данные NIST не запускались.",
            }],
            "benchmarks": [{
                "id": "Synthetic-Numerical-Contract", "name_en": "Synthetic numerical contract",
                "version": "1.0.0", "category": "numerical_reference", "nature": "numerical_contract",
                "execution_status": "completed", "gate_status": "predeclared_numerical_pass",
                "retrospective_registration": True, "independent_scientific_validation": False,
                "ademp": {
                    "aims": "Exercise the registry checker with synthetic software fixtures.",
                    "data": "Hand-written software fixture; no scientific simulation.",
                    "estimands": "Exact fixture counts.", "truth": "Known synthetic fixture values.",
                    "methods": "Compare exact typed JSON values.",
                    "performance": "Exact fixture identity only.",
                },
                "methods": [{"id": "Synthetic-Checker", "version": "1.0.0"}],
                "identity": {
                    "protocol_id": "Synthetic-Protocol-1", "protocol_refs": [self.reference("evidence.json")],
                    "data_id": "Synthetic-Data-1", "data_hash": self.reference("evidence.json")["sha256"],
                    "data_limitations_ru": "Только синтетические программные данные.",
                },
                "uncertainty_ru": "Монте-Карло неопределённость не применима.",
                "failures_ru": "Отказы явно представлены только в программных тестах.",
                "stopping_ru": "Конечный набор программных примеров.",
                "comparability_ru": "Не сравнивать с научными испытаниями.",
                "conclusion_ru": "Проверяется программный контракт.",
                "observations": [{
                    "label_ru": "Синтетический счётчик", "reference": self.reference("evidence.json", "/passed"),
                    "value": 4, "unit": "count", "truth": "numerical", "denominator": 10,
                    "denominator_reference": self.reference("evidence.json", "/requested"),
                    "denominator_note_ru": "Десять запрошенных синтетических элементов, включая отказы.",
                    "interpretation_ru": "Только тестовое значение, не научный результат.",
                }],
            }],
        }
        # History is a separate retained snapshot; current checks may not omit it.
        self.historical_registry = copy.deepcopy(self.registry)
        historical_path, historical_table = suite.VERSION_PATHS[suite.HISTORICAL_VERSION]
        self.write_json(historical_path, self.historical_registry)
        (self.root / historical_table).write_text(suite.render_table(self.historical_registry), encoding="utf-8")
        self.registry["suite_version"] = suite.CURRENT_VERSION

    def write_json(self, path, value):
        (self.root / path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def reference(self, path, pointer=None):
        value = {"path": path, "sha256": hashlib.sha256((self.root / path).read_bytes()).hexdigest()}
        if pointer is not None:
            value["pointer"] = pointer
        return value

    @property
    def benchmark(self):
        return self.registry["benchmarks"][0]

    @property
    def observation(self):
        return self.benchmark["observations"][0]

    def validate(self):
        return suite.validate_registry(self.root, self.registry)

    def prepare_disk(self):
        self.write_json(suite.REGISTRY_PATH, self.registry)
        (self.root / suite.TABLE_PATH).write_text(suite.render_table(self.registry), encoding="utf-8")

    def add_nist_execution(self, passed=True):
        names = [f"SyntheticCase{index}" for index in range(9)]
        self.nist_result = {
            "schema": "mvs-nist-study-result/v1", "protocolId": suite.NIST_BENCHMARK_ID,
            "executionStatus": "completed", "numericalContractPassed": passed,
            "results": [{"id": name, "primary": {
                "mean": {"passed": passed if index == 0 else True},
                "standardDeviation": {"passed": True}}} for index, name in enumerate(names)],
        }
        self.write_json(suite.NIST_PROTOCOL_PATH, {
            "schema": "mvs-nist-univariate-protocol/v1", "id": suite.NIST_BENCHMARK_ID,
            "datasetNames": names,
        })
        self.write_json(suite.NIST_RESULTS_PATH, self.nist_result)
        self.registry["nist_support"][0]["status"] = "executed_numerical"
        nist = copy.deepcopy(self.benchmark)
        nist.update(id=suite.NIST_BENCHMARK_ID, name_en="Synthetic NIST numerical contract",
                    gate_status="predeclared_numerical_pass" if passed else "predeclared_numerical_fail")
        nist["identity"].update(protocol_id=suite.NIST_BENCHMARK_ID, protocol_refs=[
            self.reference(suite.NIST_PROTOCOL_PATH), self.reference(suite.NIST_RESULTS_PATH)])
        nist["observations"] = []
        for index in range(9):
            for operation in ("mean", "standardDeviation"):
                observation = copy.deepcopy(self.observation)
                observation.update(
                    label_ru=f"Синтетический результат {index} {operation}",
                    reference=self.reference(suite.NIST_RESULTS_PATH, f"/results/{index}/primary/{operation}/passed"),
                    value=self.nist_result["results"][index]["primary"][operation]["passed"],
                    unit="diagnostic", denominator=None, denominator_reference=None)
                nist["observations"].append(observation)
        self.registry["benchmarks"].append(nist)
        return nist

    def test_valid_registry_and_exact_deterministic_render(self):
        self.assertIs(self.validate(), self.registry)
        self.assertEqual(suite.render_table(self.registry), suite.render_table(copy.deepcopy(self.registry)))
        self.prepare_disk()
        self.assertEqual(suite.check_or_write(self.root), self.registry)
        rendered = suite.render_table(self.registry)
        for text in ("Общего балла нет", "mapped_not_run", "SHA-256", "/passed", "Численные эталоны"):
            self.assertIn(text, rendered)
        self.assertTrue(rendered.endswith("\n"))
        self.assertFalse(rendered.endswith("\n\n"))

    def test_changed_source_bytes_fail(self):
        (self.root / "evidence.json").write_text('{"passed": 4}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.validate()

    def test_altered_observation_hash_fails(self):
        self.observation["reference"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.validate()

    def test_altered_protocol_hash_fails(self):
        self.benchmark["identity"]["protocol_refs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.validate()

    def test_altered_value_and_pointer_fail(self):
        self.observation["value"] = 5
        with self.assertRaisesRegex(ValueError, "typed value mismatch"):
            self.validate()
        self.observation["value"] = 4
        for pointer in ("/requested", "/absent", "passed", "/values/01", "/values/-1", "/values/9", "/passed/x", "/bad~2"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                self.observation["reference"]["pointer"] = pointer
                self.validate()

    def test_invalid_denominators_fail(self):
        for denominator in (None, 0, -1, False, True, 10.0, "10", 3):
            with self.subTest(denominator=denominator), self.assertRaises(ValueError):
                self.observation["denominator"] = denominator
                self.validate()

    def test_plausible_but_altered_denominator_fails(self):
        self.observation["denominator"] = 11
        with self.assertRaisesRegex(ValueError, "typed denominator mismatch"):
            self.validate()
        self.observation["denominator"] = 10
        self.observation["denominator_reference"]["pointer"] = "/passed"
        with self.assertRaisesRegex(ValueError, "typed denominator mismatch"):
            self.validate()

    def test_denominator_requires_exact_typed_reference_or_explicit_absence(self):
        self.observation["denominator_reference"] = None
        with self.assertRaises(ValueError):
            self.validate()
        self.observation.update(unit="diagnostic", denominator=None)
        self.validate()
        self.observation["denominator_reference"] = self.reference("evidence.json", "/requested")
        with self.assertRaisesRegex(ValueError, "null denominator"):
            self.validate()

    def test_missing_or_empty_required_metadata_fails(self):
        original = copy.deepcopy(self.registry)
        mutations = [
            lambda: self.benchmark["ademp"].pop("truth"),
            lambda: self.benchmark["ademp"].__setitem__("truth", " "),
            lambda: self.benchmark.pop("uncertainty_ru"),
            lambda: self.benchmark.__setitem__("uncertainty_ru", ""),
            lambda: self.benchmark.pop("failures_ru"),
            lambda: self.benchmark.__setitem__("failures_ru", ""),
            lambda: self.observation.pop("denominator"),
            lambda: self.observation.pop("denominator_reference"),
            lambda: self.observation.pop("truth"),
            lambda: self.observation.__setitem__("denominator_note_ru", ""),
        ]
        for index, mutate in enumerate(mutations):
            self.registry = copy.deepcopy(original)
            mutate()
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                self.validate()

    def test_unknown_keys_and_statuses_fail(self):
        original = copy.deepcopy(self.registry)
        mutations = [
            lambda: self.registry.__setitem__("aggregate_score", 100),
            lambda: self.benchmark.__setitem__("scientific_pass", True),
            lambda: self.benchmark.__setitem__("execution_status", "passed"),
            lambda: self.benchmark.__setitem__("gate_status", "scientifically_validated"),
            lambda: self.benchmark.__setitem__("category", "unseen_validation"),
            lambda: self.observation.__setitem__("truth", "unknown"),
            lambda: self.observation.__setitem__("truth", None),
            lambda: self.observation.__setitem__("unit", "percent"),
            lambda: self.registry["nist_support"][0].__setitem__("status", "certified_pass"),
        ]
        for index, mutate in enumerate(mutations):
            self.registry = copy.deepcopy(original)
            mutate()
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                self.validate()

    def test_suite_identity_and_boolean_types_are_strict(self):
        for key, value in (("schema_version", True), ("schema_version", 1.0),
                           ("schema_version", 2), ("suite_id", "Other"), ("suite_version", "2.0.0")):
            registry = copy.deepcopy(self.registry)
            registry[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                suite.validate_registry(self.root, registry)
        for key, value in (("retrospective_registration", 1), ("retrospective_registration", False),
                           ("independent_scientific_validation", 0), ("independent_scientific_validation", True)):
            registry = copy.deepcopy(self.registry)
            registry["benchmarks"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                suite.validate_registry(self.root, registry)

    def test_claim_category_and_gate_mismatch_fails(self):
        self.benchmark["category"] = "development_simulation"
        with self.assertRaisesRegex(ValueError, "category/nature"):
            self.validate()
        self.benchmark["nature"] = "historical_development"
        with self.assertRaisesRegex(ValueError, "numerical gate"):
            self.validate()
        self.benchmark["gate_status"] = "historical_no_go"
        self.validate()
        self.benchmark["category"] = "computational_audit"
        self.benchmark["nature"] = "computational_audit"
        with self.assertRaisesRegex(ValueError, "historical gate category"):
            self.validate()

    def test_numerical_candidate_failure_preserves_nonvalidation(self):
        self.benchmark["gate_status"] = "candidate_no_go"
        self.validate()
        self.benchmark["independent_scientific_validation"] = True
        with self.assertRaisesRegex(ValueError, "not independent scientific validation"):
            self.validate()

    def test_duplicate_identifiers_fail(self):
        for key in ("sources", "benchmarks", "nist_support"):
            registry = copy.deepcopy(self.registry)
            registry[key].append(copy.deepcopy(registry[key][0]))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "duplicate"):
                suite.validate_registry(self.root, registry)
        for key in ("methods", "observations"):
            registry = copy.deepcopy(self.registry)
            entries = registry["benchmarks"][0][key]
            entries.append(copy.deepcopy(entries[0]))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "duplicate"):
                suite.validate_registry(self.root, registry)

    def test_unsafe_paths_fail_even_when_the_file_could_exist(self):
        for path in ("../evidence.json", "/tmp/evidence.json", "validation/../evidence.json",
                     "./evidence.json", "evidence.json/", "validation//evidence.json",
                     r"..\evidence.json", "C:/evidence.json", "https://example.org/x", ""):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.observation["reference"]["path"] = path
                self.validate()

    def test_symlink_escape_fails_for_inputs_and_output(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "outside.json"
            external.write_text(json.dumps(self.evidence), encoding="utf-8")
            link = self.root / "escaped.json"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are not available in this environment")
            self.observation["reference"] = self.reference("escaped.json", "/passed")
            with self.assertRaisesRegex(ValueError, "escapes root"):
                self.validate()
            self.observation["reference"] = self.reference("evidence.json", "/passed")
            self.write_json(suite.REGISTRY_PATH, self.registry)
            output = Path(outside) / "outside.md"
            (self.root / suite.TABLE_PATH).symlink_to(output)
            with self.assertRaisesRegex(ValueError, "escapes root"):
                suite.check_or_write(self.root, write=True)
            self.assertFalse(output.exists())

    def test_zero_false_and_float_zero_are_distinct(self):
        self.observation.update(unit="diagnostic", denominator=None, denominator_reference=None)
        for pointer, actual, wrong in (("/zero", 0, False), ("/false", False, 0),
                                       ("/float_zero", 0.0, 0), ("/zero", 0, 0.0)):
            self.observation["reference"]["pointer"] = pointer
            self.observation["value"] = actual
            self.validate()
            self.observation["value"] = wrong
            with self.subTest(pointer=pointer), self.assertRaisesRegex(ValueError, "typed value mismatch"):
                self.validate()

    def test_nested_typed_values_and_null(self):
        self.observation.update(unit="diagnostic", denominator=None, denominator_reference=None)
        self.observation["reference"]["pointer"] = "/structured"
        self.observation["value"] = copy.deepcopy(self.evidence["structured"])
        self.validate()
        self.observation["value"]["list"][0] = 0
        with self.assertRaisesRegex(ValueError, "typed value mismatch"):
            self.validate()
        self.observation["reference"]["pointer"] = "/nullable"
        self.observation["value"] = None
        self.validate()

    def test_nonfinite_values_fail_recursively(self):
        for value in (math.nan, math.inf, -math.inf, {"nested": [math.inf]}):
            self.observation["value"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "nonfinite"):
                self.validate()

    def test_source_json_rejects_nonfinite_and_duplicate_keys(self):
        for content in ('{"passed":NaN}', '{"passed":Infinity}', '{"passed":1e999}',
                        '{"passed":4,"passed":4}'):
            (self.root / "evidence.json").write_text(content, encoding="utf-8")
            self.benchmark["identity"]["protocol_refs"] = [self.reference("evidence.json")]
            self.observation["reference"] = self.reference("evidence.json", "/passed")
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.validate()

    def test_not_run_cannot_carry_results_or_gate_pass(self):
        self.benchmark["execution_status"] = "not_run"
        with self.assertRaises(ValueError):
            self.validate()
        self.benchmark["gate_status"] = "not_assessed"
        with self.assertRaisesRegex(ValueError, "not_run"):
            self.validate()
        self.benchmark["observations"] = []
        self.validate()
        self.benchmark["execution_status"] = "completed"
        with self.assertRaisesRegex(ValueError, "requires observations"):
            self.validate()

    def test_nist_mapping_requires_pinned_code_and_valid_lines(self):
        mapping = self.registry["nist_support"][0]
        original = copy.deepcopy(mapping["code_refs"])
        mapping["code_refs"] = []
        with self.assertRaisesRegex(ValueError, "requires local code"):
            self.validate()
        mapping["status"] = "unsupported"
        self.validate()
        mapping["status"] = "mapped_not_run"
        for lines in ([0, 2], [True, 2], [1, 3], [2, 1], [1], "1-2"):
            mapping["code_refs"] = copy.deepcopy(original)
            mapping["code_refs"][0]["lines"] = lines
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.validate()

    def test_malformed_hash_and_external_url_fail(self):
        for value in ("A" * 64, "0" * 63, None, 123):
            registry = copy.deepcopy(self.registry)
            registry["benchmarks"][0]["identity"]["data_hash"] = value
            if value is None:
                suite.validate_registry(self.root, registry)
            else:
                with self.subTest(hash=value), self.assertRaises(ValueError):
                    suite.validate_registry(self.root, registry)
        for url in ("file:///tmp/data", "https://", "https://user:password@example.org", "https://example.org/ a"):
            self.registry["sources"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.validate()

    def test_rate_requires_real_number_and_positive_denominator(self):
        self.observation.update(unit="rate", value=0.4)
        self.observation["reference"]["pointer"] = "/rate"
        self.validate()
        for value in (True, -0.1, 1.1, "0.4"):
            self.observation["value"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate()
        self.observation["value"] = 0.4
        self.observation["denominator"] = None
        with self.assertRaises(ValueError):
            self.validate()

    def test_text_unit_requires_nonempty_text(self):
        self.observation.update(unit="text", value="synthetic fixture", denominator=None, denominator_reference=None)
        self.observation["reference"]["pointer"] = "/label"
        self.validate()
        self.observation["value"] = 4
        with self.assertRaises(ValueError):
            self.validate()

    def test_markdown_escapes_retained_text(self):
        self.benchmark["conclusion_ru"] = "pipe|newline\n<script> & `tick` \\ end"
        self.validate()
        rendered = suite.render_table(self.registry)
        self.assertIn("pipe&#124;newline<br>&lt;script&gt; &amp; &#96;tick&#96; &#92; end", rendered)
        self.assertNotIn("<script>", rendered)

    def test_stale_table_fails_without_rewriting(self):
        self.prepare_disk()
        path = self.root / suite.TABLE_PATH
        path.write_text("outdated table\n", encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Stale rendered table"):
            suite.check_or_write(self.root)
        self.assertEqual(path.read_bytes(), before)
        suite.check_or_write(self.root, write=True)
        self.assertEqual(path.read_text(encoding="utf-8"), suite.render_table(self.registry))

    def test_missing_table_and_explicit_write(self):
        self.write_json(suite.REGISTRY_PATH, self.registry)
        with self.assertRaises(OSError):
            suite.check_or_write(self.root)
        suite.check_or_write(self.root, write=True)
        suite.check_or_write(self.root)

    def test_failed_validation_never_writes_table(self):
        self.prepare_disk()
        path = self.root / suite.TABLE_PATH
        original = path.read_bytes()
        self.observation["value"] = 5
        self.write_json(suite.REGISTRY_PATH, self.registry)
        with self.assertRaises(ValueError):
            suite.check_or_write(self.root, write=True)
        self.assertEqual(path.read_bytes(), original)

    def test_cli_default_check_and_explicit_modes(self):
        self.prepare_disk()
        script = str(Path(suite.__file__).resolve())
        for mode in ([], ["--check"], ["--write"]):
            result = subprocess.run([sys.executable, script, "--root", str(self.root)] + mode,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no scientific execution", result.stdout)
        (self.root / suite.TABLE_PATH).write_text("old", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = suite.main(["--root", str(self.root)])
        self.assertEqual(status, 1)
        self.assertIn("Stale rendered table", stderr.getvalue())
        self.assertEqual((self.root / suite.TABLE_PATH).read_text(encoding="utf-8"), "old")

    def test_historical_renderer_is_byte_identical_to_frozen_fixture(self):
        # Derived once from the retained Round52 renderer, not from the new branch.
        historical_bytes = suite.render_table(self.historical_registry).encode("utf-8")
        self.assertEqual(hashlib.sha256(historical_bytes).hexdigest(),
                         "6c6eeb3ac0a2c3044fc1f5b2c4c941a9cfa816e828a8a2cbaf07606ba5d4dfa6")
        self.assertNotIn(b"Round53", historical_bytes)
        current = suite.render_table(self.registry)
        self.assertIn("2026-10-17, Round53", current)
        self.assertIn(suite.REGISTRY_PATH, current)
        self.assertIn("версия 1.1.0", current)

    def test_explicit_history_check_needs_no_current_snapshot(self):
        self.assertFalse((self.root / suite.REGISTRY_PATH).exists())
        self.assertEqual(suite.check_or_write(self.root, version="1.0.0"), self.historical_registry)
        self.assertEqual(suite.load_registry(self.root, version="1.0.0"), self.historical_registry)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(suite.main(["--root", str(self.root), "--version", "1.0.0"]), 0)

    def test_default_requires_current_snapshot_without_fallback(self):
        with self.assertRaises(OSError):
            suite.check_or_write(self.root)
        with self.assertRaises(OSError):
            suite.load_registry(self.root)

    def test_current_check_and_write_require_both_historical_files(self):
        self.prepare_disk()
        for historical_path in suite.VERSION_PATHS["1.0.0"]:
            path = self.root / historical_path
            original = path.read_bytes()
            path.unlink()
            current_before = (self.root / suite.TABLE_PATH).read_bytes()
            try:
                for write in (False, True):
                    with self.subTest(path=historical_path, write=write), self.assertRaises(OSError):
                        suite.check_or_write(self.root, write=write)
                    self.assertEqual((self.root / suite.TABLE_PATH).read_bytes(), current_before)
            finally:
                path.write_bytes(original)

    def test_stale_history_blocks_current_write_without_repairing_history(self):
        self.prepare_disk()
        _, historical_table = suite.VERSION_PATHS["1.0.0"]
        path = self.root / historical_table
        path.write_text("Changed historical view\n", encoding="utf-8")
        current_before = (self.root / suite.TABLE_PATH).read_bytes()
        with self.assertRaisesRegex(ValueError, "historical view must be preserved"):
            suite.check_or_write(self.root, write=True)
        self.assertEqual(path.read_text(encoding="utf-8"), "Changed historical view\n")
        self.assertEqual((self.root / suite.TABLE_PATH).read_bytes(), current_before)

    def test_explicit_historical_write_is_refused_and_current_write_preserves_history(self):
        self.prepare_disk()
        before = {path: (self.root / path).read_bytes() for path in suite.VERSION_PATHS["1.0.0"]}
        with self.assertRaisesRegex(ValueError, "immutable"):
            suite.check_or_write(self.root, version="1.0.0", write=True)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(suite.main(["--root", str(self.root), "--version", "1.0.0", "--write"]), 1)
        suite.check_or_write(self.root, write=True)
        for path, original in before.items():
            self.assertEqual((self.root / path).read_bytes(), original)

    def test_version_path_mislabels_and_unknown_versions_fail(self):
        self.prepare_disk()
        self.write_json(suite.REGISTRY_PATH, self.historical_registry)
        with self.assertRaisesRegex(ValueError, "version/path mismatch"):
            suite.load_registry(self.root)
        self.prepare_disk()
        historical_path, _ = suite.VERSION_PATHS["1.0.0"]
        self.write_json(historical_path, self.registry)
        with self.assertRaisesRegex(ValueError, "version/path mismatch"):
            suite.check_or_write(self.root)
        for version in ("1.2.0", "latest", None, True):
            with self.subTest(version=version), self.assertRaises(ValueError):
                suite.load_registry(self.root, version=version)
        with self.assertRaisesRegex(ValueError, "version/path mismatch"):
            suite.validate_registry(self.root, self.registry, expected_version="1.0.0")

    def test_executed_nist_requires_identified_benchmark(self):
        self.registry["nist_support"][0]["status"] = "executed_numerical"
        with self.assertRaisesRegex(ValueError, "identified NIST benchmark"):
            self.validate()

    def test_nist_execution_and_failure_gate_are_rejected_by_historical_schema(self):
        self.add_nist_execution(passed=False)
        self.validate()
        historical = copy.deepcopy(self.registry)
        historical["suite_version"] = "1.0.0"
        with self.assertRaisesRegex(ValueError, "NIST status"):
            suite.validate_registry(self.root, historical)
        historical["nist_support"][0]["status"] = "mapped_not_run"
        with self.assertRaisesRegex(ValueError, "gate_status"):
            suite.validate_registry(self.root, historical)
        historical["benchmarks"][-1]["gate_status"] = "candidate_no_go"
        with self.assertRaisesRegex(ValueError, "unavailable in historical"):
            suite.validate_registry(self.root, historical)

    def test_nist_success_and_failed_predeclared_gate_remain_distinct(self):
        nist = self.add_nist_execution(passed=False)
        self.validate()
        for wrong_gate in ("candidate_no_go", "predeclared_numerical_pass", "descriptive_only"):
            nist["gate_status"] = wrong_gate
            with self.subTest(gate=wrong_gate), self.assertRaisesRegex(ValueError, "gate disagrees"):
                self.validate()
        self.registry["benchmarks"].pop()
        nist = self.add_nist_execution(passed=True)
        self.validate()
        nist["gate_status"] = "predeclared_numerical_fail"
        with self.assertRaisesRegex(ValueError, "gate disagrees"):
            self.validate()

    def test_nist_requires_pinned_protocol_results_and_observation_coverage(self):
        nist = self.add_nist_execution()
        original = copy.deepcopy(nist)
        for missing_path in (suite.NIST_PROTOCOL_PATH, suite.NIST_RESULTS_PATH):
            nist["identity"]["protocol_refs"] = [ref for ref in original["identity"]["protocol_refs"]
                                                  if ref["path"] != missing_path]
            with self.subTest(path=missing_path), self.assertRaisesRegex(ValueError, "pinned protocol and results"):
                self.validate()
        nist["identity"]["protocol_refs"] = copy.deepcopy(original["identity"]["protocol_refs"])
        nist["observations"] = [copy.deepcopy(self.observation)]
        with self.assertRaisesRegex(ValueError, "source-bound results observations"):
            self.validate()
        nist["observations"] = copy.deepcopy(original["observations"][:-1])
        with self.assertRaisesRegex(ValueError, "all 18"):
            self.validate()
        # Eighteen observations from seventeen distinct operation branches still fail.
        duplicate = copy.deepcopy(nist["observations"][0])
        duplicate["label_ru"] = "Другой ярлык той же операции"
        nist["observations"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "all 18"):
            self.validate()

    def test_nist_result_schema_identity_and_completion_are_required(self):
        nist = self.add_nist_execution()
        original_result = copy.deepcopy(self.nist_result)
        for field, value in (("schema", "unrelated/v1"), ("protocolId", "Wrong-Protocol"),
                             ("executionStatus", "technical_failure"), ("numericalContractPassed", 1)):
            result = copy.deepcopy(original_result)
            result[field] = value
            self.write_json(suite.NIST_RESULTS_PATH, result)
            nist["identity"]["protocol_refs"][-1] = self.reference(suite.NIST_RESULTS_PATH)
            for observation in nist["observations"]:
                observation["reference"] = self.reference(suite.NIST_RESULTS_PATH, observation["reference"]["pointer"])
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate()

    def test_nist_entry_requires_numerical_category_and_complete_execution(self):
        nist = self.add_nist_execution()
        nist.update(category="engineering_contract", nature="engineering_contract", gate_status="descriptive_only")
        with self.assertRaisesRegex(ValueError, "completed versioned numerical_reference"):
            self.validate()
        nist.update(category="numerical_reference", nature="numerical_contract",
                    execution_status="technical_failure_with_supplemental_audit")
        with self.assertRaisesRegex(ValueError, "completed versioned numerical_reference"):
            self.validate()

    def test_predeclared_numerical_fail_is_version_and_category_bounded(self):
        self.benchmark["gate_status"] = "predeclared_numerical_fail"
        self.validate()
        self.benchmark.update(category="engineering_contract", nature="engineering_contract")
        with self.assertRaisesRegex(ValueError, "numerical gate"):
            self.validate()
        self.benchmark.update(category="numerical_reference", nature="numerical_contract",
                              execution_status="technical_failure_with_supplemental_audit")
        with self.assertRaisesRegex(ValueError, "numerical gate"):
            self.validate()


class PointerTests(unittest.TestCase):
    def test_rfc6901_escaping_empty_key_and_document_root(self):
        document = {"": 1, "a/b": {"~key": [0, False]}, "~1": 2}
        self.assertIs(suite.json_pointer(document, ""), document)
        self.assertEqual(suite.json_pointer(document, "/"), 1)
        self.assertIs(suite.json_pointer(document, "/a~1b/~0key/1"), False)
        self.assertEqual(suite.json_pointer(document, "/~01"), 2)

    def test_typed_equality_is_recursive(self):
        self.assertTrue(suite.typed_equal({"x": [0, False, 0.0]}, {"x": [0, False, 0.0]}))
        self.assertFalse(suite.typed_equal({"x": [0]}, {"x": [False]}))
        self.assertFalse(suite.typed_equal({"x": 1}, {"x": 1.0}))
        self.assertFalse(suite.typed_equal({"x": 1}, {"y": 1}))


if __name__ == "__main__":
    unittest.main()
