"""Pure mutation fixtures for scientific output comparison; no native execution."""
import copy
import csv
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# The validation module and executable intentionally share a basename. Give the
# executable its own import identity so unittest discovery cannot import itself.
SPEC = importlib.util.spec_from_file_location(
    "mvs_scientific_cli_parity_tool", ROOT / "tools" / "test_scientific_cli_parity.py"
)
parity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = parity
SPEC.loader.exec_module(parity)


VALIDATION_ERRORS = (AssertionError, ValueError)


class StrictJsonTests(unittest.TestCase):
    def test_preserves_nested_finite_types_and_large_integer_precision(self):
        result = parity.strict_json(
            '{"count":9007199254740993,"nested":[1.25,true,false,null,"001"]}'
        )
        self.assertEqual(result["count"], 9007199254740993)
        self.assertIs(type(result["count"]), int)
        self.assertEqual(result["nested"], [1.25, True, False, None, "001"])
        self.assertIs(type(result["nested"][0]), float)

    def test_rejects_malformed_or_additional_output(self):
        for text in ("", "{", '{"a":}', '{"a":1,}', "{} {}", "progress\n{}", "{}\ntrailer"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parity.strict_json(text)

    def test_rejects_duplicate_keys_at_any_depth(self):
        for text in (
            '{"a":1,"a":2}',
            '{"groups":[{"count":4,"count":5}]}',
            '{"a":1,"\\u0061":2}',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parity.strict_json(text)

    def test_rejects_nonfinite_literals_and_exponent_overflow(self):
        for number in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            for text in (number, '{"nested":[{"estimate":' + number + "}]}"):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    parity.strict_json(text)

    def test_strings_that_resemble_nonfinite_literals_remain_strings(self):
        self.assertEqual(parity.strict_json('["NaN","Infinity","1e999"]'),
                         ["NaN", "Infinity", "1e999"])


class CompareValueTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "EngineVersion": "fixture-engine",
            "Status": "diagnostic",
            "Converged": False,
            "Iterations": 1000000000000,
            "Parameters": [
                {"Name": "location", "Estimate": 2.5, "Low": None,
                 "Diagnostics": {"Curve": [0.1, 0.25, 0.75]}},
                {"Name": "scale", "Estimate": 0.5, "Low": 0.125,
                 "Diagnostics": {"Curve": []}},
            ],
        }

    def test_identical_nested_report_passes(self):
        parity.compare_value(self.report, copy.deepcopy(self.report))

    def test_nested_floats_within_default_tolerance_pass(self):
        altered = copy.deepcopy(self.report)
        altered["Parameters"][0]["Estimate"] += 1e-11
        altered["Parameters"][0]["Diagnostics"]["Curve"][0] += 1e-13
        parity.compare_value(self.report, altered)
        parity.compare_value(0.0, 5e-13)
        parity.compare_value(1e8, 1e8 + 0.005)

    def test_nested_scientific_float_change_fails(self):
        altered = copy.deepcopy(self.report)
        altered["Parameters"][0]["Diagnostics"]["Curve"][1] += 0.01
        with self.assertRaises(VALIDATION_ERRORS):
            parity.compare_value(self.report, altered)

    def test_explicit_tolerances_are_honored(self):
        parity.compare_value(0.0, 0.005, absolute=0.01, relative=0.0)
        parity.compare_value(100.0, 100.5, absolute=0.0, relative=0.01)
        for expected, actual in ((0.0, 0.005), (100.0, 100.5)):
            with self.subTest(expected=expected), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(expected, actual, absolute=0.0, relative=0.0)

    def test_large_integer_counts_are_exact_even_with_float_tolerance(self):
        altered = copy.deepcopy(self.report)
        altered["Iterations"] += 1
        with self.assertRaises(VALIDATION_ERRORS):
            parity.compare_value(self.report, altered)
        with self.assertRaises(VALIDATION_ERRORS):
            parity.compare_value(9007199254740992, 9007199254740993)

    def test_integer_bool_and_null_types_cannot_coerce_each_other(self):
        for expected, actual in ((1, True), (True, 1), (False, 0),
                                 (None, 0), (None, ""), (None, "null")):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(expected, actual)

    def test_integral_float_representation_is_exact_not_tolerant(self):
        # JSON loses the source engine's declared double type. Equivalent
        # integral representations may agree, but count values remain exact.
        parity.compare_value(4, 4.0)
        parity.compare_value(4.0, 4)
        for expected, actual in ((4, 4.00000000001), (4.00000000001, 4),
                                 (9007199254740993, 9007199254740992.0)):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(expected, actual)

    def test_status_identity_boolean_and_null_changes_fail(self):
        mutations = (
            ("Status", "completed"),
            ("EngineVersion", "different-engine"),
            ("Converged", True),
        )
        for key, value in mutations:
            altered = copy.deepcopy(self.report)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(self.report, altered)
        altered = copy.deepcopy(self.report)
        altered["Parameters"][0]["Low"] = 0.0
        with self.assertRaises(VALIDATION_ERRORS):
            parity.compare_value(self.report, altered)

    def test_numeric_looking_identifiers_compare_as_strings(self):
        with self.assertRaises(VALIDATION_ERRORS):
            parity.compare_value({"Entity": "0007"}, {"Entity": "7"})

    def test_missing_extra_and_reordered_array_entries_fail(self):
        for rows in (self.report["Parameters"][:1],
                     self.report["Parameters"] + [self.report["Parameters"][0]],
                     list(reversed(self.report["Parameters"]))):
            altered = copy.deepcopy(self.report)
            altered["Parameters"] = rows
            with self.subTest(rows=rows), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(self.report, altered)

    def test_missing_extra_and_renamed_object_keys_fail(self):
        mutations = []
        missing = copy.deepcopy(self.report)
        del missing["Parameters"][0]["Low"]
        mutations.append(missing)
        extra = copy.deepcopy(self.report)
        extra["Parameters"][0]["Unexpected"] = None
        mutations.append(extra)
        renamed = copy.deepcopy(self.report)
        renamed["Parameters"][0]["Lower"] = renamed["Parameters"][0].pop("Low")
        mutations.append(renamed)
        for altered in mutations:
            with self.subTest(altered=altered), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(self.report, altered)

    def test_direct_nonfinite_floats_are_rejected_on_either_side(self):
        for bad in (float("nan"), float("inf"), -float("inf")):
            for expected, actual in ((bad, bad), (0.0, bad), (bad, 0.0)):
                with self.subTest(expected=expected, actual=actual), self.assertRaises(VALIDATION_ERRORS):
                    parity.compare_value(expected, actual)


class ScientificManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "created": "2026-10-01T01:00:00Z",
            "runId": "first-run",
            "files": [{"FileName": "report.json", "SizeBytes": 10, "sha256": "a" * 64}],
            "engineVersion": "fixture-engine",
            "inputData": {"file": "fixture.csv", "sha256": "b" * 64},
            "configuration": {"Seed": 7, "Repetitions": 100, "created": "scientific-value",
                              "runId": "nested-identity", "files": ["nested-scientific-file"]},
            "executionEnvironment": {"fingerprint": "same-environment"},
            "warnings": ["diagnostic retained"],
        }

    def test_excludes_only_three_root_operational_keys_without_mutating_input(self):
        before = copy.deepcopy(self.manifest)
        expected = {key: value for key, value in self.manifest.items()
                    if key not in {"created", "runId", "files"}}
        self.assertEqual(parity.scientific_manifest(self.manifest), expected)
        self.assertEqual(self.manifest, before)

    def test_operational_differences_do_not_change_scientific_comparison(self):
        altered = copy.deepcopy(self.manifest)
        altered.update(created="2026-10-02T02:00:00Z", runId="second-run",
                       files=[{"FileName": "report.json", "SizeBytes": 20, "sha256": "c" * 64}])
        parity.compare_value(parity.scientific_manifest(self.manifest), parity.scientific_manifest(altered))

    def test_nested_names_matching_operational_keys_are_scientific(self):
        for key, value in (("created", "changed"), ("runId", "different"), ("files", [])):
            altered = copy.deepcopy(self.manifest)
            altered["configuration"][key] = value
            with self.subTest(key=key), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(parity.scientific_manifest(self.manifest),
                                     parity.scientific_manifest(altered))

    def test_engine_input_settings_environment_and_warning_changes_fail(self):
        mutations = []
        for key, value in (("engineVersion", "different-engine"),
                           ("inputData", {"file": "fixture.csv", "sha256": "c" * 64}),
                           ("executionEnvironment", {"fingerprint": "different-environment"}),
                           ("warnings", [])):
            altered = copy.deepcopy(self.manifest)
            altered[key] = value
            mutations.append(altered)
        altered = copy.deepcopy(self.manifest)
        altered["configuration"]["Repetitions"] += 1
        mutations.append(altered)
        for altered in mutations:
            with self.subTest(altered=altered), self.assertRaises(VALIDATION_ERRORS):
                parity.compare_value(parity.scientific_manifest(self.manifest),
                                     parity.scientific_manifest(altered))


class ReadTableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "table.csv"
        self.expected = [
            {"Name": "location", "Count": 9007199254740993, "Estimate": 2.5,
             "Converged": False, "Low": None, "Status": "diagnostic",
             "Curve": [0.1, 0.2], "Details": {"reason": "fixture"}},
            {"Name": 'scale, "quoted"', "Count": 4, "Estimate": 0.5,
             "Converged": True, "Low": 0.25, "Status": "available",
             "Curve": [], "Details": {}},
        ]
        self.fields = ["Name", "Count", "Estimate", "Converged", "Low", "Status"]
        self.cells = [
            ["location", "9007199254740993", "2.5", "False", "", "diagnostic"],
            ['scale, "quoted"', "4", "0.5", "True", "0.25", "available"],
        ]

    def write_table(self, fields=None, cells=None):
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(self.fields if fields is None else fields)
            writer.writerows(self.cells if cells is None else cells)

    def assert_bad_table(self, *, fields=None, cells=None):
        self.write_table(fields, cells)
        with self.assertRaises(VALIDATION_ERRORS):
            parity.read_table(self.path, self.expected)

    def test_round_trip_all_scalar_properties_and_expected_types(self):
        self.write_table()
        fields, rows = parity.read_table(self.path, self.expected)
        expected = [{key: row[key] for key in self.fields} for row in self.expected]
        self.assertEqual(fields, self.fields)
        self.assertEqual(rows, expected)
        self.assertIs(type(rows[0]["Count"]), int)
        self.assertIs(type(rows[0]["Estimate"]), float)
        self.assertIs(rows[0]["Converged"], False)
        self.assertIsNone(rows[0]["Low"])
        self.assertIs(type(rows[1]["Low"]), float)

    def test_float_rounding_within_tolerance_is_allowed(self):
        cells = copy.deepcopy(self.cells)
        cells[0][2] = "2.50000000001"
        self.write_table(cells=cells)
        _, rows = parity.read_table(self.path, self.expected)
        self.assertEqual(rows[0]["Estimate"], 2.50000000001)

    def test_numeric_string_identity_is_preserved(self):
        self.write_table(fields=["Entity"], cells=[["0007"]])
        self.assertEqual(parity.read_table(self.path, [{"Entity": "0007"}]),
                         (["Entity"], [{"Entity": "0007"}]))

    def test_spreadsheet_formula_protection_preserves_string_identity(self):
        for identity in ("=formula", "+positive", "-negative", "@name", "\ttab", "\rreturn"):
            self.write_table(fields=["Entity"], cells=[["'" + identity]])
            with self.subTest(identity=identity):
                self.assertEqual(parity.read_table(self.path, [{"Entity": identity}]),
                                 (["Entity"], [{"Entity": identity}]))

    def test_csv_scientific_scalar_disagreement_fails(self):
        for column, value in ((0, "changed-name"), (1, "9007199254740993" + "0"),
                              (2, "2.6"), (3, "True"), (4, "0"), (5, "completed")):
            cells = copy.deepcopy(self.cells)
            cells[0][column] = value
            with self.subTest(column=column):
                self.assert_bad_table(cells=cells)

    def test_one_unit_large_count_mutation_fails_without_float_rounding(self):
        cells = copy.deepcopy(self.cells)
        cells[0][1] = "9007199254740992"
        self.assert_bad_table(cells=cells)

    def test_integer_cells_require_integer_spelling(self):
        for bad in ("4.0", "4e0", "4.1", "true", ""):
            cells = copy.deepcopy(self.cells)
            cells[1][1] = bad
            with self.subTest(cell=bad):
                self.assert_bad_table(cells=cells)

    def test_nonfinite_and_overflow_float_cells_fail(self):
        for bad in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999", ""):
            cells = copy.deepcopy(self.cells)
            cells[0][2] = bad
            with self.subTest(cell=bad):
                self.assert_bad_table(cells=cells)

    def test_nonblank_null_cells_fail(self):
        for bad in ("null", "NaN", "None", "0", " "):
            cells = copy.deepcopy(self.cells)
            cells[0][4] = bad
            with self.subTest(cell=bad):
                self.assert_bad_table(cells=cells)

    def test_invalid_boolean_cells_fail(self):
        for bad in ("0", "1", "yes", ""):
            cells = copy.deepcopy(self.cells)
            cells[0][3] = bad
            with self.subTest(cell=bad):
                self.assert_bad_table(cells=cells)

    def test_missing_extra_duplicate_and_reordered_headers_fail(self):
        self.assert_bad_table(fields=self.fields[:-1], cells=[row[:-1] for row in self.cells])
        self.assert_bad_table(fields=self.fields + ["Unexpected"], cells=[row + [""] for row in self.cells])
        self.assert_bad_table(fields=self.fields + ["Name"], cells=[row + [row[0]] for row in self.cells])
        self.assert_bad_table(fields=list(reversed(self.fields)),
                              cells=[list(reversed(row)) for row in self.cells])

    def test_missing_extra_and_reordered_rows_fail(self):
        for cells in (self.cells[:1], self.cells + [self.cells[0]], list(reversed(self.cells))):
            with self.subTest(cells=cells):
                self.assert_bad_table(cells=cells)

    def test_ragged_rows_are_not_silently_truncated_or_filled(self):
        for first in (self.cells[0][:-1], self.cells[0] + ["unexpected"]):
            with self.subTest(first=first):
                self.assert_bad_table(cells=[first, self.cells[1]])

    def test_header_only_empty_array_requires_the_declared_columns(self):
        self.write_table(cells=[])
        self.assertEqual(parity.read_table(self.path, [], expected_columns=self.fields),
                         (self.fields, []))
        for fields in (self.fields[:-1], list(reversed(self.fields)), self.fields + ["Name"]):
            self.write_table(fields=fields, cells=[])
            with self.subTest(fields=fields), self.assertRaises(VALIDATION_ERRORS):
                parity.read_table(self.path, [], expected_columns=self.fields)

    def test_header_only_does_not_hide_missing_expected_rows(self):
        self.assert_bad_table(cells=[])

    def test_empty_expected_array_does_not_allow_unexpected_data(self):
        self.write_table()
        with self.assertRaises(VALIDATION_ERRORS):
            parity.read_table(self.path, [], expected_columns=self.fields)


class ProcessTreeSampleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.proc_root = Path(temporary.name)
        for pid, parent, name, rss in ((100, 1, "python-wrapper", 120),
                                       (101, 100, "native-cli", 230),
                                       (102, 101, "native-helper", 340),
                                       (200, 1, "unrelated", 9000)):
            directory = self.proc_root / str(pid)
            directory.mkdir()
            (directory / "status").write_text(
                f"Name:\t{name}\nPid:\t{pid}\nPPid:\t{parent}\nVmRSS:\t{rss} kB\n",
                encoding="utf-8",
            )
        self.affinities = {100: {7, 3}, 101: {3, 7}, 102: {7}, 200: {99}}
        self.affinity_calls = []

    def affinity(self, pid):
        self.affinity_calls.append(pid)
        return self.affinities[pid]

    def test_ppid_statuses_capture_native_descendants_without_task_children_files(self):
        self.assertEqual(list(self.proc_root.rglob("children")), [])
        self.assertEqual(list(self.proc_root.rglob("task")), [])
        sample = parity.process_tree_sample(100, proc_root=self.proc_root, affinity=self.affinity)
        by_pid = {item["pid"]: item for item in sample}
        self.assertEqual(set(by_pid), {100, 101, 102})
        self.assertEqual(len(sample), 3)
        self.assertEqual(sum(item["rssKiB"] for item in sample), 690)
        self.assertEqual(by_pid[100], {"pid": 100, "rssKiB": 120,
                                      "affinity": [3, 7], "name": "python-wrapper"})
        self.assertEqual(by_pid[101], {"pid": 101, "rssKiB": 230,
                                      "affinity": [3, 7], "name": "native-cli"})
        self.assertEqual(by_pid[102], {"pid": 102, "rssKiB": 340,
                                      "affinity": [7], "name": "native-helper"})
        self.assertCountEqual(self.affinity_calls, [100, 101, 102])

    def test_process_exiting_during_affinity_read_preserves_other_descendants(self):
        def exited_affinity(pid):
            self.affinity_calls.append(pid)
            if pid == 101:
                raise ProcessLookupError("fixture process exited after status snapshot")
            return self.affinities[pid]

        sample = parity.process_tree_sample(100, proc_root=self.proc_root, affinity=exited_affinity)
        self.assertEqual({item["pid"] for item in sample}, {100, 102})
        self.assertEqual(sum(item["rssKiB"] for item in sample), 460)
        self.assertCountEqual(self.affinity_calls, [100, 101, 102])

    def test_process_disappearing_before_status_read_is_tolerated(self):
        (self.proc_root / "300").mkdir()
        (self.proc_root / "self").mkdir()
        sample = parity.process_tree_sample(100, proc_root=self.proc_root, affinity=self.affinity)
        self.assertEqual({item["pid"] for item in sample}, {100, 101, 102})
        self.assertEqual(sum(item["rssKiB"] for item in sample), 690)


class FileIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "report.json"
        self.data = b'{"estimate":1.25,"status":"available"}\n'
        self.path.write_bytes(self.data)
        self.size = len(self.data)
        self.sha256 = hashlib.sha256(self.data).hexdigest()

    def test_original_size_and_checksum_pass(self):
        parity.verify_file(self.path, self.size, self.sha256)

    def test_same_length_content_corruption_fails_checksum(self):
        self.path.write_bytes(self.data.replace(b"1.25", b"1.26"))
        self.assertEqual(self.path.stat().st_size, self.size)
        with self.assertRaises(VALIDATION_ERRORS):
            parity.verify_file(self.path, self.size, self.sha256)

    def test_recorded_size_corruption_fails_even_when_hash_matches(self):
        with self.assertRaises(VALIDATION_ERRORS):
            parity.verify_file(self.path, self.size + 1, self.sha256)

    def test_recorded_checksum_corruption_fails_even_when_size_matches(self):
        with self.assertRaises(VALIDATION_ERRORS):
            parity.verify_file(self.path, self.size, "0" * 64)

    def test_truncated_file_fails(self):
        self.path.write_bytes(self.data[:-1])
        with self.assertRaises(VALIDATION_ERRORS):
            parity.verify_file(self.path, self.size, self.sha256)

    def test_ignoring_operational_manifest_differences_does_not_skip_integrity(self):
        left = {"created": "first", "runId": "first", "kind": "fixture",
                "files": [{"FileName": self.path.name, "SizeBytes": self.size, "sha256": self.sha256}]}
        right = copy.deepcopy(left)
        right.update(created="second", runId="second")
        right["files"][0]["sha256"] = "0" * 64
        parity.compare_value(parity.scientific_manifest(left), parity.scientific_manifest(right))
        first = left["files"][0]
        parity.verify_file(self.path, first["SizeBytes"], first["sha256"])
        changed = right["files"][0]
        with self.assertRaises(VALIDATION_ERRORS):
            parity.verify_file(self.path, changed["SizeBytes"], changed["sha256"])


if __name__ == "__main__":
    unittest.main()
