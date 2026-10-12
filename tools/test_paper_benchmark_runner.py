#!/usr/bin/env python3
"""Offline runner safety tests: shadow Git/CLI, synthetic source identity fixtures.

No Git repositories are modified and no scientific computation or real resume
is run. The preserved historical archive exercises the real artifact verifier.
"""
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

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "benchmark_history/1.4.0-engine-1.6.0-MVS-BENCH-1.2.0"
COMMIT = "a" * 40
INCOMING_BYTES = b"synthetic incoming checkpoint: not a scientific backup\x00\xff"
NEW_BYTES = b"synthetic newly saved checkpoint: not a scientific backup"


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink() else
            ("file", hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file() else
            ("directory", "") for p in root.rglob("*")}


class PaperBenchmarkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mvs-paper-runner-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "synthetic-source"
        self.source.mkdir()
        # This is an identity-only test fixture, never a historical engine build.
        for name in ("tools/run_paper_benchmark_chunk.sh", "tools/paper_benchmark_paths.py",
                     "tools/verify_paper_benchmark.py", "Core/ScientificInfrastructure.cs",
                     "Infrastructure/OutputExporter.cs", "Benchmark/BenchmarkProtocol.cs"):
            target = self.source / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        release = self.source / "Core/ScientificInfrastructure.cs"
        release.write_text(release.read_text().replace('EngineVersion = "1.6.2"', 'EngineVersion = "1.6.0"'))
        self.bin = self.base / "fake-bin"
        self.bin.mkdir()
        self.executable("git", '''import os, sys
if os.environ.get("MVS_TEST_GIT_FAIL"):
    sys.exit(1)
print("a" * 40 if "rev-parse" in sys.argv else "synthetic-test-fixture")
''')
        self.executable("dotnet", '''import json, os, pathlib, shutil, signal, sys, time
args = sys.argv[1:]
pathlib.Path(os.environ["MVS_TEST_CALLS"]).write_text(json.dumps(args))
output = pathlib.Path(args[args.index("--out") + 1])
backup = pathlib.Path(os.environ["MVS_BACKUP_DIR"]) / "MVS_Backups.zip"
if os.environ.get("MVS_TEST_CHECKPOINT", "1") == "1":
    backup.write_bytes(b"synthetic newly saved checkpoint: not a scientific backup")
mode = os.environ.get("MVS_TEST_MODE", "none")
if mode in ("valid", "multiple", "incomplete"):
    shutil.copytree(os.environ["MVS_TEST_ARTIFACT"], output / "result")
    if mode == "multiple":
        shutil.copytree(os.environ["MVS_TEST_ARTIFACT"], output / "extra")
    if mode == "incomplete":
        (output / "result/benchmark_summary.csv").unlink()
elif mode == "malformed":
    (output / "benchmark_manifest.json").write_text("{")
elif mode == "symlink":
    (output / "linked").symlink_to(os.environ["MVS_TEST_ARTIFACT"], target_is_directory=True)
elif mode == "interrupt":
    signal.signal(signal.SIGINT, lambda *args: sys.exit(130))
    time.sleep(10)
print("Synthetic CLI only; no scientific computation")
sys.exit(int(os.environ.get("MVS_TEST_EXIT", "124")))
''')
        self.incoming = self.base / "incoming"
        self.state = self.base / "state"
        self.work = self.base / "work"
        self.calls = self.base / "cli-called.json"
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith("MVS_BENCH_") or key.startswith("MVS_TEST_"):
                del self.env[key]
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env.get("PATH", ""),
                        PYTHONDONTWRITEBYTECODE="1", MVS_BENCH_THREADS="2",
                        MVS_BENCH_CHUNK_SECONDS="3", MVS_TEST_CALLS=str(self.calls),
                        MVS_TEST_ARTIFACT=str(ARCHIVE))

    def executable(self, name, script):
        target = self.bin / name
        target.write_text("#!" + sys.executable + "\n" + script)
        target.chmod(0o755)

    def checkpoint(self, provenance=True):
        self.incoming.mkdir()
        (self.incoming / "MVS_Backups.zip").write_bytes(INCOMING_BYTES)
        (self.incoming / "keep.bin").write_bytes(b"original bytes\x00\xff")
        if provenance:
            (self.incoming / "chunk-1.txt").write_text("chunk=1\ncommit=" + COMMIT + "\nprofile=full\nseed=20260904\n")
            (self.incoming / "chunk-1.log").write_text("prior log\n")

    def artifact(self):
        self.incoming.mkdir()
        shutil.copytree(ARCHIVE, self.incoming / "result")

    def run_chunk(self, chunk="2", incoming=None, state=None, work=None, env=None):
        updates = {} if env is None else env
        return subprocess.run(["bash", str(self.source / "tools/run_paper_benchmark_chunk.sh"),
                               chunk, str(self.incoming if incoming is None else incoming),
                               str(self.state if state is None else state),
                               str(self.work if work is None else work)],
                              cwd=self.source, env=self.env | updates, capture_output=True,
                              text=True, timeout=15)

    def denied(self, result, contains):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(contains, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.calls.exists(), "preflight must not launch even the fake CLI")

    def no_outputs(self):
        self.assertFalse(self.state.exists())
        self.assertFalse(self.work.exists())

    def not_complete(self):
        self.assertFalse((self.state / "status.txt").exists())
        provenance = self.state / "chunk-2.txt"
        if provenance.exists():
            self.assertNotIn("status=complete", provenance.read_text())

    def test_equal_incoming_state_retains_every_byte(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        self.denied(self.run_chunk(state=self.incoming), "disjoint")
        self.assertEqual(snapshot(self.incoming), before)
        self.assertFalse(self.work.exists())

    def test_all_pairwise_ancestor_overlaps_are_refused(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        cases = [dict(state=self.incoming / "nested"), dict(state=self.base),
                 dict(work=self.incoming), dict(work=self.incoming / "nested"),
                 dict(work=self.base), dict(work=self.state),
                 dict(work=self.state / "nested"), dict(state=self.work / "nested")]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.denied(self.run_chunk(**overrides), "disjoint")
                self.assertEqual(snapshot(self.incoming), before)
                self.no_outputs()

    def test_canonical_dotdot_overlap_is_refused(self):
        self.checkpoint()
        self.denied(self.run_chunk(state=self.incoming / ".." / "incoming"), "disjoint")
        self.assertEqual((self.incoming / "MVS_Backups.zip").read_bytes(), INCOMING_BYTES)

    def test_root_cwd_and_ancestors_are_refused(self):
        for destination in ("/", str(self.source), str(self.source.parent), ".", ".."):
            with self.subTest(destination=destination):
                message = "disjoint" if destination in ("/", str(self.source.parent), "..") else "unsafe"
                self.denied(self.run_chunk(incoming="", state=destination), message)
                self.assertFalse(self.work.exists())

    def test_nonempty_destinations_are_never_reset(self):
        self.checkpoint()
        for destination in (self.state, self.work):
            with self.subTest(destination=destination):
                destination.mkdir()
                (destination / ".marker").write_bytes(INCOMING_BYTES)
                before = snapshot(self.base)
                self.denied(self.run_chunk(), "nonempty")
                self.assertEqual(snapshot(self.base), before)
                # Fixture cleanup only, after asserting the runner preserved it.
                shutil.rmtree(destination)

    def test_file_destination_is_refused(self):
        self.state.write_bytes(INCOMING_BYTES)
        self.denied(self.run_chunk(incoming=""), "not a directory")
        self.assertEqual(self.state.read_bytes(), INCOMING_BYTES)
        self.assertFalse(self.work.exists())

    def test_symlink_destination_and_parent_are_refused(self):
        external = self.base / "external"
        external.mkdir()
        (external / "marker").write_bytes(INCOMING_BYTES)
        self.state.symlink_to(external, target_is_directory=True)
        for destination in (self.state, self.state / "child", self.state / ".." / "other"):
            with self.subTest(destination=destination):
                self.denied(self.run_chunk(incoming="", state=destination), "symlink")
                self.assertEqual((external / "marker").read_bytes(), INCOMING_BYTES)
                self.assertFalse(self.work.exists())

    def test_missing_and_file_incoming_are_refused(self):
        self.denied(self.run_chunk(), "incoming directory does not exist")
        self.no_outputs()
        self.incoming.write_bytes(INCOMING_BYTES)
        self.denied(self.run_chunk(), "incoming directory does not exist")
        self.no_outputs()

    def test_empty_incoming_cannot_silently_restart(self):
        self.incoming.mkdir()
        self.denied(self.run_chunk(), "refusing to restart")
        self.no_outputs()

    def test_symlink_incoming_or_evidence_is_refused(self):
        self.checkpoint()
        link = self.base / "incoming-alias"
        link.symlink_to(self.incoming, target_is_directory=True)
        self.denied(self.run_chunk(incoming=link), "symlink")
        (self.incoming / "linked").symlink_to(ARCHIVE, target_is_directory=True)
        self.denied(self.run_chunk(), "symlink")
        self.no_outputs()

    def test_control_characters_in_paths_and_evidence_are_refused(self):
        for value in ("bad\npath", "bad\rpath", "bad\tpath"):
            with self.subTest(value=value):
                self.denied(self.run_chunk(incoming="", state=self.base / value), "control characters")
                self.no_outputs()
        self.checkpoint()
        (self.incoming / "bad\nname").write_text("untouched")
        before = snapshot(self.incoming)
        self.denied(self.run_chunk(), "control characters")
        self.assertEqual(snapshot(self.incoming), before)
        self.no_outputs()

    def test_invalid_chunks_are_refused_before_any_write(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        for value in ("", "0", "-1", "1.2", "01", "2147483648", "a/b", "2\n3", "$(touch PWNED)"):
            with self.subTest(value=value):
                self.denied(self.run_chunk(chunk=value), "chunk must be")
                self.assertEqual(snapshot(self.incoming), before)
                self.no_outputs()
        self.assertFalse((self.source / "PWNED").exists())

    def test_invalid_numeric_configuration_is_refused(self):
        for name in ("MVS_BENCH_THREADS", "MVS_BENCH_CHUNK_SECONDS"):
            for value in ("", "0", "-1", "1.2", "2s", "2147483648", "$(touch PWNED)"):
                with self.subTest(name=name, value=value):
                    self.denied(self.run_chunk(incoming="", env={name: value}), name + " must be")
                    self.no_outputs()

    def test_profile_and_seed_are_frozen(self):
        for name, value in (("MVS_BENCH_PROFILE", "quick"), ("MVS_BENCH_PROFILE", ""),
                            ("MVS_BENCH_SEED", "1"), ("MVS_BENCH_SEED", "020260904"),
                            ("MVS_BENCH_SEED", "")):
            with self.subTest(name=name, value=value):
                self.denied(self.run_chunk(incoming="", env={name: value}), "requires " + name)
                self.no_outputs()

    def test_empty_output_path_is_not_replaced_by_default(self):
        self.denied(self.run_chunk(incoming="", state=""), "path must not be empty")
        self.no_outputs()

    def test_provenance_mismatch_and_malformed_commit_are_refused(self):
        self.checkpoint()
        path = self.incoming / "chunk-1.txt"
        for contents in ("commit=" + "b" * 40 + "\n", "chunk=1\n", "commit=\n",
                         "commit=" + COMMIT + "\ncommit=" + COMMIT + "\n",
                         "commit=" + COMMIT + "\nprofile=quick\n",
                         "commit=" + COMMIT + "\nseed=1\n"):
            with self.subTest(contents=contents):
                path.write_text(contents)
                before = snapshot(self.incoming)
                self.denied(self.run_chunk(), "provenance")
                self.assertEqual(snapshot(self.incoming), before)
                self.no_outputs()

    def test_existing_chunk_number_cannot_replace_provenance(self):
        self.checkpoint()
        self.denied(self.run_chunk(chunk="1"), "choose the next chunk number")
        self.no_outputs()

    def test_git_failure_preserves_input_and_destinations(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        self.denied(self.run_chunk(env={"MVS_TEST_GIT_FAIL": "1"}), "Cannot read source Git identity")
        self.assertEqual(snapshot(self.incoming), before)
        self.no_outputs()

    def test_current_source_cannot_start_or_resume_historical_work(self):
        shutil.copyfile(ROOT / "Core/ScientificInfrastructure.cs", self.source / "Core/ScientificInfrastructure.cs")
        self.denied(self.run_chunk(incoming=""), "source identity does not match")
        self.no_outputs()
        self.checkpoint()
        before = snapshot(self.incoming)
        self.denied(self.run_chunk(), "source identity does not match")
        self.assertEqual(snapshot(self.incoming), before)
        self.no_outputs()

    def test_historical_no_go_passes_through_current_source_without_compute(self):
        shutil.copyfile(ROOT / "Core/ScientificInfrastructure.cs", self.source / "Core/ScientificInfrastructure.cs")
        self.artifact()
        (self.incoming / "MVS_Backups.zip").write_bytes(INCOMING_BYTES)
        before = snapshot(self.incoming)
        result = self.run_chunk()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual((self.state / "status.txt").read_text(), "complete\n")
        self.assertIn("action=pass-through", (self.state / "chunk-2.txt").read_text())
        self.assertEqual(snapshot(self.state / "result"), snapshot(ARCHIVE))
        self.assertEqual(snapshot(self.incoming), before)
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), INCOMING_BYTES)

    def test_malformed_and_incomplete_incoming_results_fail_before_write(self):
        self.artifact()
        manifest = self.incoming / "result/benchmark_manifest.json"
        original = manifest.read_bytes()
        for bad in (b"{", b"{}", b"[]"):
            with self.subTest(bad=bad):
                manifest.write_bytes(bad)
                before = snapshot(self.incoming)
                self.denied(self.run_chunk(), "safety check failed")
                self.assertEqual(snapshot(self.incoming), before)
                self.no_outputs()
        manifest.write_bytes(original)
        (self.incoming / "result/benchmark_summary.csv").unlink()
        self.denied(self.run_chunk(), "missing")
        self.no_outputs()

    def test_multiple_incoming_manifests_are_refused(self):
        self.artifact()
        shutil.copytree(ARCHIVE, self.incoming / "extra")
        self.denied(self.run_chunk(), "found 2")
        self.no_outputs()

    def test_multiple_incoming_checkpoint_archives_are_refused(self):
        self.checkpoint()
        (self.incoming / "nested").mkdir()
        (self.incoming / "nested/MVS_Backups.zip").write_bytes(INCOMING_BYTES)
        self.denied(self.run_chunk(), "multiple MVS_Backups.zip")
        self.no_outputs()

    def test_empty_destinations_and_literal_shell_characters_are_supported(self):
        self.checkpoint()
        state = self.base / "state with spaces;$(touch PWNED)"
        work = self.base / "-work 'quoted'"
        state.mkdir()
        work.mkdir()
        result = self.run_chunk(state=state, work=work)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((state / "status.txt").read_text(), "incomplete\n")
        self.assertFalse((self.source / "PWNED").exists())
        arguments = json.loads(self.calls.read_text())
        self.assertEqual(arguments[arguments.index("--out") + 1], str(work / "results"))

    def test_fake_fresh_start_uses_frozen_arguments(self):
        result = self.run_chunk(incoming="")
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = json.loads(self.calls.read_text())
        self.assertEqual(arguments[1:], ["benchmark", "--profile", "full", "--seed", "20260904",
                                         "--threads", "2", "--out", str(self.work / "results")])
        self.assertEqual((self.state / "status.txt").read_text(), "incomplete\n")
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)

    def test_fake_resume_copies_input_and_preserves_prior_checkpoint(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        result = self.run_chunk()
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = json.loads(self.calls.read_text())
        self.assertEqual(arguments[1:], ["resume", "--in", str(self.work / "incoming-backups.zip"),
                                         "--out", str(self.work / "results")])
        self.assertEqual(snapshot(self.incoming), before)
        self.assertEqual((self.work / "incoming-backups.zip").read_bytes(), INCOMING_BYTES)
        self.assertEqual((self.state / "incoming-backups.zip").read_bytes(), INCOMING_BYTES)
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)
        self.assertEqual((self.state / "chunk-1.log").read_bytes(), (self.incoming / "chunk-1.log").read_bytes())

    def test_real_timeout_of_fake_cli_saves_incomplete_checkpoint(self):
        result = self.run_chunk(incoming="", env={"MVS_TEST_MODE": "interrupt", "MVS_BENCH_CHUNK_SECONDS": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "status.txt").read_text(), "incomplete\n")
        self.assertIn("command_exit_code=124", (self.state / "chunk-2.txt").read_text())

    def test_valid_fake_cli_completion_accepts_no_go_exit_two(self):
        for code in ("0", "2"):
            with self.subTest(code=code):
                result = self.run_chunk(incoming="", env={"MVS_TEST_MODE": "valid", "MVS_TEST_EXIT": code})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.state / "status.txt").read_text(), "complete\n")
                self.assertEqual(snapshot(self.state / "result"), snapshot(ARCHIVE))
                shutil.rmtree(self.state)
                shutil.rmtree(self.work)

    def test_unexpected_exit_with_valid_manifest_never_marks_complete(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        result = self.run_chunk(env={"MVS_TEST_MODE": "valid", "MVS_TEST_EXIT": "7"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected exit code 7", result.stderr)
        self.not_complete()
        self.assertEqual(snapshot(self.incoming), before)
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)
        self.assertEqual((self.state / "incoming-backups.zip").read_bytes(), INCOMING_BYTES)
        self.assertTrue((self.work / "results/result/benchmark_manifest.json").exists())

    def test_timeout_with_valid_manifest_does_not_mark_complete(self):
        result = self.run_chunk(incoming="", env={"MVS_TEST_MODE": "valid"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command timed out", result.stderr)
        self.not_complete()
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)

    def test_malformed_multiple_incomplete_and_symlink_cli_output_fail(self):
        for mode in ("malformed", "multiple", "incomplete", "symlink"):
            with self.subTest(mode=mode):
                result = self.run_chunk(incoming="", env={"MVS_TEST_MODE": mode, "MVS_TEST_EXIT": "0"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("safety check failed", result.stderr)
                self.not_complete()
                self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)
                shutil.rmtree(self.state)
                shutil.rmtree(self.work)

    def test_early_failure_keeps_original_checkpoint_in_upload_state(self):
        self.checkpoint()
        before = snapshot(self.incoming)
        result = self.run_chunk(env={"MVS_TEST_EXIT": "7", "MVS_TEST_CHECKPOINT": "0"})
        self.assertNotEqual(result.returncode, 0)
        self.not_complete()
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), INCOMING_BYTES)
        self.assertEqual(snapshot(self.incoming), before)
        self.assertEqual((self.work / "incoming-backups.zip").read_bytes(), INCOMING_BYTES)

    def test_no_manifest_or_no_new_timeout_checkpoint_fails(self):
        for code in ("0", "2", "124"):
            with self.subTest(code=code):
                result = self.run_chunk(incoming="", env={"MVS_TEST_EXIT": code, "MVS_TEST_CHECKPOINT": "0"})
                self.assertNotEqual(result.returncode, 0)
                self.not_complete()
                self.assertIn("verified result" if code != "124" else "no portable checkpoint", result.stderr)
                shutil.rmtree(self.state)
                shutil.rmtree(self.work)

    def test_log_failure_cannot_certify_a_valid_result(self):
        self.executable("tee", "import sys\nsys.stdin.read()\nsys.exit(9)\n")
        result = self.run_chunk(incoming="", env={"MVS_TEST_MODE": "valid", "MVS_TEST_EXIT": "2"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("log could not be saved", result.stderr)
        self.not_complete()
        self.assertEqual((self.state / "MVS_Backups.zip").read_bytes(), NEW_BYTES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
