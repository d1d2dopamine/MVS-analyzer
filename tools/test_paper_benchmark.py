#!/usr/bin/env python3
"""Offline artifact/preflight regressions; never reruns or rewrites a benchmark."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import verify_paper_benchmark as verifier

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "benchmark_history/1.4.0-engine-1.6.0-MVS-BENCH-1.2.0"
CURRENT = ROOT / "benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0"


class PaperBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mvs-paper-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "artifact"
        shutil.copytree(ARCHIVE, self.folder)
        self.manifest = json.loads((self.folder / "benchmark_manifest.json").read_text())

    def refresh(self):
        names = sorted(p.name for p in self.folder.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
        (self.folder / "SHA256SUMS.txt").write_text("".join(
            verifier.sha256(self.folder / name) + "  " + name + "\n" for name in names))

    def save(self):
        (self.folder / "benchmark_manifest.json").write_text(json.dumps(self.manifest))
        self.refresh()

    def bad(self, pattern=None):
        with self.assertRaisesRegex(ValueError, pattern or ".+"):
            verifier.validate(self.folder)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools/verify_paper_benchmark.py"),
                               *map(str, args)], capture_output=True, text=True)

    def rows(self, name):
        with (self.folder / name).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            return reader.fieldnames, list(reader)

    def write_rows(self, name, fields, rows):
        with (self.folder / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_actual_historical_no_go_passes_without_mutation(self):
        before = {p.name: verifier.sha256(p) for p in ARCHIVE.iterdir() if p.is_file()}
        folder, result = verifier.validate(ARCHIVE)
        self.assertEqual(folder, ARCHIVE)
        self.assertEqual(result["overall"], "no-go")
        self.assertEqual(before, {p.name: verifier.sha256(p) for p in ARCHIVE.iterdir() if p.is_file()})
        result = self.cli(ARCHIVE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no-go", result.stdout)

    def test_current_development_archive_is_not_historical_paper(self):
        with self.assertRaisesRegex(ValueError, "engineVersion"):
            verifier.validate(CURRENT)

    def test_empty_fake_go_is_rejected(self):
        shutil.rmtree(self.folder)
        self.folder.mkdir()
        self.manifest = dict(verifier.EXPECTED, kind="mvs-benchmark", protocolUnchanged=True,
                             protocolHashFrozen=verifier.EXPECTED["protocolHash"], overall="go")
        (self.folder / "benchmark_manifest.json").write_text(json.dumps(self.manifest))
        (self.folder / "SHA256SUMS.txt").write_text("")
        self.bad("manifest.files")

    def test_empty_checksums_are_rejected(self):
        (self.folder / "SHA256SUMS.txt").write_text("")
        self.bad("not covered")

    def test_missing_manifest_checksum_is_rejected(self):
        path = self.folder / "SHA256SUMS.txt"
        path.write_text("".join(x for x in path.read_text().splitlines(keepends=True)
                                if "benchmark_manifest.json" not in x))
        self.bad("not covered")

    def test_missing_required_file_is_rejected(self):
        (self.folder / "benchmark_summary.csv").unlink()
        self.bad("missing")

    def test_empty_required_file_is_rejected(self):
        (self.folder / "benchmark_report.md").write_text("")
        self.refresh()
        self.bad("empty artifact")

    def test_required_manifest_files_cannot_be_omitted(self):
        self.manifest["files"] = []
        self.save()
        self.bad("required manifest")

    def test_duplicate_manifest_files_are_rejected(self):
        self.manifest["files"].append(self.manifest["files"][0])
        self.save()
        self.bad("duplicate")

    def test_missing_checksums_are_rejected(self):
        (self.folder / "SHA256SUMS.txt").unlink()
        self.bad("missing")

    def test_no_manifest_and_multiple_manifests_are_rejected(self):
        (self.folder / "benchmark_manifest.json").unlink()
        self.bad("found 0")
        (self.folder / "a").mkdir()
        (self.folder / "b").mkdir()
        for name in ("a", "b"):
            (self.folder / name / "benchmark_manifest.json").write_text("{}")
        self.bad("found 2")

    def test_duplicate_checksum_is_rejected(self):
        path = self.folder / "SHA256SUMS.txt"
        path.write_text(path.read_text() + path.read_text().splitlines()[0] + "\n")
        self.bad("duplicate checksum")

    def test_unsafe_checksum_paths_are_rejected(self):
        for name in ("../outside", "/absolute", "a/../b", "./benchmark_manifest.json", "a//b", "C:/absolute", "a\\b", "bad\tname"):
            with self.subTest(name=name):
                (self.folder / "SHA256SUMS.txt").write_text("0" * 64 + "  " + name + "\n")
                self.bad("unsafe artifact")

    def test_malformed_checksum_syntax_is_rejected(self):
        for line in ("garbage", "0" * 63 + "  benchmark_manifest.json", "g" * 64 + "  benchmark_manifest.json",
                     "0" * 64 + " benchmark_manifest.json", "0" * 64 + "  "):
            with self.subTest(line=line):
                (self.folder / "SHA256SUMS.txt").write_text(line + "\n")
                self.bad("malformed")

    def test_tampered_file_fails_checksum(self):
        with (self.folder / "benchmark_metrics.csv").open("a") as stream:
            stream.write("tampered\n")
        self.bad("checksum mismatch")

    def test_symlink_file_and_directory_are_rejected(self):
        target = self.root / "outside"
        target.write_text("external")
        path = self.folder / "benchmark_report.md"
        path.unlink()
        path.symlink_to(target)
        self.bad("symlink")
        path.unlink()
        (self.folder / "linked").symlink_to(self.root, target_is_directory=True)
        (self.folder / "SHA256SUMS.txt").write_text("0" * 64 + "  linked/outside\n")
        self.bad("symlink")

    def test_symlink_root_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "real directory"):
            verifier.validate(alias)

    def test_strict_json_rejects_malformed_duplicate_nonfinite_and_wrong_shape(self):
        for text in ('{', '[]', '{"kind":"x","kind":"y"}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.subTest(text=text):
                (self.folder / "benchmark_manifest.json").write_text(text)
                self.bad()
                result = self.cli(self.folder)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_frozen_identity_fields_are_checked(self):
        for field in verifier.EXPECTED:
            with self.subTest(field=field):
                original = self.manifest[field]
                self.manifest[field] = "wrong"
                self.save()
                self.bad("manifest." + field)
                self.manifest[field] = original

    def test_real_protocol_bytes_must_match_not_just_label(self):
        (self.folder / "benchmark_protocol.txt").write_text("wrong")
        self.refresh()
        self.bad("protocol text hash")

    def test_all_frozen_budgets_are_checked(self):
        for key in verifier.BUDGETS:
            with self.subTest(key=key):
                self.manifest["replications"][key] -= 1
                self.save()
                self.bad("replications." + key)
                self.manifest["replications"][key] += 1

    def test_boolean_budget_and_count_are_not_numbers(self):
        self.manifest["replications"]["primary"] = True
        self.save()
        self.bad("replications.primary")
        self.manifest["replications"]["primary"] = 1000
        self.manifest["conditions"][0]["failed"] = False
        self.save()
        self.bad("integer")

    def test_threshold_changes_are_rejected(self):
        self.manifest["thresholds"]["powerLossFail"] = .9
        self.save()
        self.bad("thresholds.powerLossFail")

    def test_truncated_or_duplicate_conditions_are_rejected(self):
        saved = self.manifest["conditions"].pop()
        self.save()
        self.bad("19 frozen")
        self.manifest["conditions"].append(self.manifest["conditions"][0])
        self.save()
        self.bad("duplicate condition")
        self.manifest["conditions"][-1] = saved

    def test_condition_design_and_completion_accounting_are_checked(self):
        row = self.manifest["conditions"][0]
        row["shape"] = "normal"
        self.save()
        self.bad("primary_null.shape")
        row["shape"] = "heavy_tail"
        row["completed"] -= 1
        self.save()
        self.bad("incomplete replication")

    def test_summary_rows_counts_and_rates_are_checked(self):
        name = "benchmark_summary.csv"
        fields, rows = self.rows(name)
        for key, value in (("planned", "999"), ("completed", "999"), ("failed", "1"),
                           ("rate", ".999"), ("rejections", "1001"), ("source", "real")):
            with self.subTest(key=key):
                old = rows[0][key]
                rows[0][key] = value
                self.write_rows(name, fields, rows)
                self.refresh()
                self.bad()
                rows[0][key] = old
        self.write_rows(name, fields, rows[:-1])
        self.refresh()
        self.bad("incomplete")

    def test_metric_and_choice_counts_are_checked(self):
        fields, rows = self.rows("benchmark_metrics.csv")
        rows[0]["completed"] = "999"
        self.write_rows("benchmark_metrics.csv", fields, rows)
        self.refresh()
        self.bad("metric completed")
        shutil.copyfile(ARCHIVE / "benchmark_metrics.csv", self.folder / "benchmark_metrics.csv")
        fields, rows = self.rows("benchmark_choices.csv")
        rows.pop()
        self.write_rows("benchmark_choices.csv", fields, rows)
        self.refresh()
        self.bad("choice totals")

    def test_csv_duplicate_and_malformed_rows_are_rejected(self):
        fields, rows = self.rows("benchmark_summary.csv")
        self.write_rows("benchmark_summary.csv", fields, rows + [rows[0]])
        self.refresh()
        self.bad("duplicate summary")
        (self.folder / "benchmark_summary.csv").write_text("condition,condition\na,b\n")
        self.refresh()
        self.bad("CSV columns")

    def test_stability_count_and_summary_are_checked(self):
        self.manifest["stability"]["failed"] = 1
        self.save()
        self.bad("stability accounting")
        self.manifest["stability"]["failed"] = 0
        self.manifest["stability"]["medianTau"] = 0
        self.save()
        self.bad("medianTau")

    def test_verdict_and_overall_disagreement_are_rejected(self):
        self.manifest["overall"] = "go"
        self.save()
        self.bad("overall")
        self.manifest["overall"] = "no-go"
        self.manifest["verdicts"][0]["result"] = "fail"
        self.save()
        self.bad("verdict CSV mismatch")

    def test_replay_inconsistency_is_rejected(self):
        self.manifest["determinism"]["identical"] = False
        self.save()
        self.bad("replay identity")

    def test_failed_stability_is_retained_not_a_new_success_gate(self):
        self.manifest["stability"] = dict(splits=0, failed=120, medianTau=None,
                                          lowerQuartileTau=None, topOneAgreement=None)
        fields, _ = self.rows("benchmark_stability.csv")
        self.write_rows("benchmark_stability.csv", fields, [])
        self.save()
        _, manifest = verifier.validate(self.folder)
        self.assertEqual(manifest["stability"]["failed"], 120)
        self.assertEqual(manifest["overall"], "no-go")

    def test_failed_replication_is_retained_with_successful_denominators(self):
        # Synthetic accounting fixture, not replacement scientific evidence.
        self.manifest["conditions"][0].update(completed=999, failed=1)
        for name in ("benchmark_summary.csv", "benchmark_metrics.csv"):
            fields, rows = self.rows(name)
            for row in rows:
                if row["condition"] == "primary_null":
                    row["completed"] = "999"
                    if "failed" in row:
                        row["failed"] = "1"
                    row["rate"] = f'{int(row["rejections"]) / 999:.6f}'
            self.write_rows(name, fields, rows)
        fields, rows = self.rows("benchmark_choices.csv")
        changed = set()
        retained = []
        for row in rows:
            if row["condition"] == "primary_null":
                if row["procedure"] not in changed:
                    row["count"] = str(int(row["count"]) - 1)
                    changed.add(row["procedure"])
                row["share"] = f'{int(row["count"]) / 999:.6f}'
                if row["count"] == "0":
                    continue
            retained.append(row)
        self.write_rows("benchmark_choices.csv", fields, retained)
        self.save()
        _, manifest = verifier.validate(self.folder)
        self.assertEqual(manifest["conditions"][0]["failed"], 1)

    def test_resume_environment_must_be_valid_and_match(self):
        path = self.folder / "backup_resume.json"
        self.manifest["files"].append("backup_resume.json")
        for value in ({}, {"environments": []}, {"environments": ["a", "b"]}, {"environments": ["wrong"]}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                self.save()
                self.bad("environment")
        path.write_text(json.dumps({"environments": [self.manifest["environmentHash"]]}))
        self.save()
        verifier.validate(self.folder)

    def test_resume_provenance_must_be_declared_and_checksummed(self):
        (self.folder / "backup_resume.json").write_text(json.dumps({
            "environments": [self.manifest["environmentHash"]]}))
        self.bad("provenance")

    def test_zero_successes_preserve_blank_rates_and_all_failures(self):
        self.manifest["conditions"][0].update(completed=0, failed=1000)
        for name in ("benchmark_summary.csv", "benchmark_metrics.csv"):
            fields, rows = self.rows(name)
            for row in rows:
                if row["condition"] == "primary_null":
                    row["completed"] = row["rejections"] = "0"
                    row["rate"] = ""
                    if "failed" in row:
                        row["failed"] = "1000"
                        for key in ("standard_error", "wilson_low", "wilson_high", "claim_rate"):
                            row[key] = ""
            self.write_rows(name, fields, rows)
        fields, rows = self.rows("benchmark_choices.csv")
        self.write_rows("benchmark_choices.csv", fields,
                        [row for row in rows if row["condition"] != "primary_null"])
        self.save()
        _, manifest = verifier.validate(self.folder)
        self.assertEqual(manifest["conditions"][0]["failed"], 1000)
        fields, rows = self.rows("benchmark_summary.csv")
        rows[0]["rate"] = "0"
        self.write_rows("benchmark_summary.csv", fields, rows)
        self.refresh()
        self.bad("unavailable rate")

    def test_failed_replay_is_evidence_not_a_success_gate(self):
        self.manifest["determinism"].update(second="0" * 64, identical=False)
        fields, rows = self.rows("benchmark_verdicts.csv")
        for row in rows + self.manifest["verdicts"]:
            if row["id"] == "E":
                row["result"] = "fail"
        self.write_rows("benchmark_verdicts.csv", fields, rows)
        self.save()
        _, manifest = verifier.validate(self.folder)
        self.assertFalse(manifest["determinism"]["identical"])

    def test_source_preflight_rejects_current_without_traceback(self):
        result = self.cli("--check-source", ROOT)
        self.assertEqual(result.returncode, 1)
        self.assertIn("engine 1.6.2", result.stderr)
        self.assertIn("separately verified historical source", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_source_preflight_reads_exact_formula_protocol_and_engine(self):
        source = self.root / "synthetic-source-fixture"
        for name in ("Core/ScientificInfrastructure.cs", "Infrastructure/OutputExporter.cs", "Benchmark/BenchmarkProtocol.cs"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        release = source / "Core/ScientificInfrastructure.cs"
        release.write_text(release.read_text().replace('EngineVersion = "1.6.2"', 'EngineVersion = "1.6.0"'))
        verifier.check_source(source)  # Identity parser positive fixture; not an authenticated old revision.
        formula = source / "Infrastructure/OutputExporter.cs"
        formula.write_text(formula.read_text().replace('score=100*sqrt', 'score=101*sqrt'))
        with self.assertRaisesRegex(ValueError, "source identity"):
            verifier.check_source(source)

    def test_bad_cli_inputs_have_clear_nonzero_status(self):
        for args in ((self.root / "missing",), ("--check-source", self.root / "missing"),
                     (self.folder, "--check-source", ROOT)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
