#!/usr/bin/env python3
"""Self-tests for change_guard.py using disposable MVS fixtures only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("change_guard.py")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "MVS"
        fixture = {
            "Core/AnalysisEngine.cs": "class AnalysisEngine {}\n",
            "Core/ScientificInfrastructure.cs": 'const string EngineVersion = "fixture-engine";\n',
            "Infrastructure/OutputExporter.cs": 'const string FormulaVersion = "fixture-formula";\n',
            "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj": "<Project><Version>fixture-app</Version></Project>\n",
            "README.md": "Original documentation\n",
            "docs/VALIDATION.md": "Original limits\n",
            "validation/analyze_results.py": "print('fixture')\n",
            "benchmark_history/run/report.csv": "frozen,evidence\n",
        }
        for name, text in fixture.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.before = self.base / "before.json"

    def call(self, *args, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout if result.stdout else result.stderr)

    def snapshot(self, *extra, out=None):
        return self.call("snapshot", "--root", str(self.root),
                         "--out", str(out or self.before), "--task", "Change README wording",
                         "--allow", "README.md", *extra)

    def verify(self, code=0, baseline=None):
        return self.call("verify", "--root", str(self.root),
                         "--baseline", str(baseline or self.before), code=code)

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def init_git(self):
        if not shutil.which("git"):
            self.skipTest("Git is unavailable")
        self.git("init", "-q")
        self.git("config", "user.name", "Disposable Test")
        self.git("config", "user.email", "test@local.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "Fixture baseline")

    def digest_tree(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob("*") if p.is_file() and not p.is_symlink()}

    def test_inspection_is_read_only_and_reads_live_versions(self):
        before = self.digest_tree()
        result = self.call("inspect", "--root", str(self.root))
        self.assertEqual(result["versions_from_live_source"]["engine"], "fixture-engine")
        self.assertEqual(result["versions_from_live_source"]["formula"], "fixture-formula")
        self.assertEqual(before, self.digest_tree())

    def test_wrong_project_root_is_rejected(self):
        self.call("inspect", "--root", str(self.base), code=2)

    def test_snapshot_must_be_external_and_cannot_overwrite(self):
        self.call("snapshot", "--root", str(self.root), "--out", str(self.root / "before.json"),
                  "--task", "Example", "--allow", "README.md", code=2)
        self.assertFalse((self.root / "before.json").exists())
        self.snapshot()
        original = self.before.read_bytes()
        self.call("snapshot", "--root", str(self.root), "--out", str(self.before),
                  "--task", "Example", "--allow", "README.md", code=2)
        self.assertEqual(self.before.read_bytes(), original)

    def test_unchanged_and_allowed_edits_pass(self):
        self.snapshot()
        self.assertEqual(self.verify()["status"], "PASS")
        (self.root / "README.md").write_text("Requested wording\n")
        report = self.verify()
        self.assertEqual(report["changes"][0]["operation"], "modify")

    def test_unscoped_modified_file_is_blocked(self):
        self.snapshot()
        (self.root / "docs/VALIDATION.md").write_text("Unrequested")
        self.assertEqual(self.verify(1)["changes"][0]["path"], "docs/VALIDATION.md")

    def test_unscoped_new_file_is_blocked(self):
        self.snapshot()
        (self.root / "new.txt").write_text("Unexpected")
        self.assertEqual(self.verify(1)["changes"][0]["operation"], "add")

    def test_authorized_addition_passes(self):
        self.snapshot("--allow", "new.txt")
        (self.root / "new.txt").write_text("Requested")
        self.assertEqual(self.verify()["status"], "PASS")

    def test_deletion_requires_separate_authorization(self):
        self.snapshot()
        (self.root / "README.md").unlink()
        self.verify(1)

    def test_authorized_deletion_passes(self):
        self.snapshot("--allow-delete", "docs/VALIDATION.md")
        (self.root / "docs/VALIDATION.md").unlink()
        self.verify()

    def test_science_scope_requires_sensitive_record(self):
        self.call("snapshot", "--root", str(self.root), "--out", str(self.before),
                  "--task", "Requested scientific change", "--allow", "Core/AnalysisEngine.cs", code=2)

    def test_sensitive_record_requires_reason(self):
        self.call("snapshot", "--root", str(self.root), "--out", str(self.before),
                  "--task", "Requested scientific change", "--allow", "Core/AnalysisEngine.cs",
                  "--allow-sensitive", "Core/AnalysisEngine.cs", code=2)

    def test_explicitly_authorized_science_change_passes(self):
        self.snapshot("--allow", "Core/AnalysisEngine.cs", "--allow-sensitive", "Core/AnalysisEngine.cs",
                      "--sensitive-reason", "Owner requested this Core fix")
        (self.root / "Core/AnalysisEngine.cs").write_text("Requested fixture change")
        result = self.verify()
        self.assertIn("scientific-method", result["changes"][0]["categories"])

    def test_archive_change_outside_scope_is_blocked(self):
        self.snapshot()
        (self.root / "benchmark_history/run/report.csv").write_text("Changed")
        result = self.verify(1)
        self.assertTrue(any("sensitive" in x["reason"] for x in result["violations"]))

    def test_traversal_absolute_globs_and_directory_scope_rejected(self):
        for i, name in enumerate(("../outside", "/absolute", "Core/*", "Core/", "Core/../README.md",
                                  "Core\\AnalysisEngine.cs", ".git/config")):
            self.call("snapshot", "--root", str(self.root), "--out", str(self.base / f"bad{i}.json"),
                      "--task", "Invalid scope", "--allow", name, code=2)

    def test_snapshot_tampering_is_detected(self):
        self.snapshot()
        doc = json.loads(self.before.read_text())
        doc["scope"]["allow"].append("docs/VALIDATION.md")
        self.before.write_text(json.dumps(doc))
        self.verify(2)

    def test_snapshot_root_mismatch_is_rejected(self):
        self.snapshot()
        second = self.base / "another"
        shutil.copytree(self.root, second)
        self.call("verify", "--root", str(second), "--baseline", str(self.before), code=2)

    def test_guard_implementation_change_is_detected(self):
        copied = self.base / "copied_guard.py"
        copied.write_bytes(SCRIPT.read_bytes())
        command = [sys.executable, str(copied), "snapshot", "--root", str(self.root),
                   "--out", str(self.before), "--task", "Example", "--allow", "README.md"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        copied.write_bytes(copied.read_bytes() + b"\n# Implementation changed\n")
        result = subprocess.run([sys.executable, str(copied), "verify", "--root", str(self.root),
                                 "--baseline", str(self.before)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Guard implementation changed", result.stderr)

    def test_generated_cache_excluded_but_reported(self):
        self.snapshot()
        cache = self.root / "__pycache__"
        cache.mkdir()
        (cache / "example.pyc").write_bytes(b"Generated")
        result = self.verify()
        self.assertIn("__pycache__", result["excluded_directories"])

    @unittest.skipIf(os.name == "nt", "Unix mode bits")
    def test_mode_change_is_detected(self):
        self.snapshot()
        path = self.root / "docs/VALIDATION.md"
        path.chmod(path.stat().st_mode ^ 0o100)
        self.verify(1)

    @unittest.skipIf(os.name == "nt", "Symlink privileges vary on Windows")
    def test_symlink_targets_are_not_read_and_changes_are_blocked(self):
        outside = self.base / "outside.txt"
        outside.write_text("External data")
        link = self.root / "link"
        link.symlink_to(outside)
        self.snapshot("--allow", "link")
        outside.write_text("External data changed")
        self.verify()
        link.unlink()
        link.symlink_to(self.base / "different-target")
        result = self.verify(1)
        self.assertTrue(any("symlink" in v["reason"] for v in result["violations"]))

    @unittest.skipIf(os.name == "nt", "FIFO not available")
    def test_special_file_refuses_incomplete_scan(self):
        os.mkfifo(self.root / "special")
        self.call("inspect", "--root", str(self.root), code=2)

    def test_extend_preserves_original_hashes_and_existing_edits(self):
        self.snapshot()
        original = json.loads(self.before.read_text())
        (self.root / "README.md").write_text("Requested first edit")
        extended = self.base / "extended.json"
        self.call("extend", "--root", str(self.root), "--baseline", str(self.before),
                  "--out", str(extended), "--task", "Necessary limits wording", "--allow", "docs/VALIDATION.md")
        doc = json.loads(extended.read_text())
        self.assertEqual(doc["files"], original["files"])
        self.assertEqual(doc["amendments"][0]["previous_snapshot_sha256"], original["snapshot_sha256"])
        (self.root / "docs/VALIDATION.md").write_text("Requested second edit")
        self.verify(baseline=extended)
        self.verify(1)  # Original scope stays intact.

    def test_extend_refuses_retroactive_scope(self):
        self.snapshot()
        (self.root / "docs/VALIDATION.md").write_text("Already unscoped")
        self.call("extend", "--root", str(self.root), "--baseline", str(self.before),
                  "--out", str(self.base / "extended.json"), "--task", "New scope",
                  "--allow", "docs/VALIDATION.md", code=2)

    def test_extend_cannot_overwrite_original(self):
        self.snapshot()
        self.call("extend", "--root", str(self.root), "--baseline", str(self.before),
                  "--out", str(self.before), "--task", "New scope", "--allow", "docs/VALIDATION.md", code=2)

    def test_preexisting_dirty_work_is_preserved(self):
        self.init_git()
        (self.root / "docs/VALIDATION.md").write_text("Owner's unfinished work")
        self.git("add", "docs/VALIDATION.md")
        before = self.git("status", "--porcelain")
        self.snapshot()
        self.verify()
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual((self.root / "docs/VALIDATION.md").read_text(), "Owner's unfinished work")

    def test_staging_changes_blocked_by_default(self):
        self.init_git()
        self.snapshot()
        (self.root / "README.md").write_text("Requested edit")
        self.git("add", "README.md")
        report = self.verify(1)
        self.assertTrue(any("staging" in v["reason"] for v in report["violations"]))

    def test_staging_can_be_explicitly_authorized(self):
        self.init_git()
        self.snapshot("--allow-git-index")
        (self.root / "README.md").write_text("Requested edit")
        self.git("add", "README.md")
        self.verify()

    def test_commit_blocked_by_default(self):
        self.init_git()
        self.snapshot()
        (self.root / "README.md").write_text("Requested edit")
        self.git("add", "README.md")
        self.git("commit", "-qm", "Not authorized by snapshot")
        report = self.verify(1)
        self.assertTrue(any("HEAD" in v["reason"] for v in report["violations"]))

    def test_tracked_generated_looking_file_is_not_excluded(self):
        self.init_git()
        path = self.root / "bin/source.txt"
        path.parent.mkdir()
        path.write_text("Tracked source")
        self.git("add", "-f", "bin/source.txt")
        self.git("commit", "-qm", "Tracked generated-looking source")
        self.snapshot()
        path.write_text("Unscoped source modification")
        self.verify(1)

    def test_invalid_git_metadata_is_not_silently_ignored(self):
        (self.root / ".git").write_text("gitdir: missing\n")
        self.call("inspect", "--root", str(self.root), code=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
