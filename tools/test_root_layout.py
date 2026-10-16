#!/usr/bin/env python3
"""Round 37 root-layout and recoverable overlay-migration contracts.

Only synthetic temporary trees are mutated. Repository checks are read-only;
no native compilation, numerical computation, network, or Git mutation is used.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import migrate_root_layout as migration


ROOT = Path(__file__).absolute().parent.parent
EXPECTED_ROOT_FILES = {
    ".editorconfig", ".gitattributes", ".gitignore", ".markdownlint-cli2.jsonc",
    "CHANGELOG.md", "CITATION.cff", "CODE_OF_CONDUCT.md", "LICENSE",
    "MvsAnalyzer.csproj", "MvsAnalyzer.slnx", "README.md", "SECURITY.md",
    "SharedSources.props", "app.ico", "app.manifest",
}
EXPECTED_ROOT_DIRECTORIES = {
    ".codex", ".github", "Assets", "Benchmark", "Core", "Desktop", "Infrastructure",
    "MvsAnalyzer.Cli", "MvsAnalyzer.Core", "MvsAnalyzer.Core.Tests", "MvsAnalyzer.Tests",
    "MvsAnalyzer.Ui.Tests", "Properties", "benchmark_data", "benchmark_history", "docs",
    "examples", "notebooks", "packaging", "plugins", "python", "tools", "validation",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Capture all regular test content, including unexpected empty directories."""
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = os.readlink(path).encode()
        elif path.is_dir():
            result[name] = None
        else:
            result[name] = path.read_bytes()
    return result


class SyntheticMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Some platforms use a symlink for /tmp; synthetic roots must use its real path.
        self.root = Path(self.temp.name).resolve() / "repository"
        self.root.mkdir()
        self.baseline: dict[str, dict[str, bytes]] = {}
        self.final: dict[str, dict[str, bytes]] = {}
        self.manifest = {"schema": migration.SCHEMA, "stage": 37,
                         "sourceStage": 36, "moves": []}
        for old, (new, kind) in migration.ALLOWED_MOVES.items():
            if kind == "file":
                source = {".": ("package:" + old).encode()}
            else:
                source = {"plugin.json": ("plugin:" + old).encode(),
                          "templates/example.txt": b"template body\n",
                          "README.md": b"[Root](../README.md)\n"}
            destination = dict(source)
            if kind == "directory":
                destination["README.md"] = b"[Root](../../../README.md)\n"
            self.baseline[old] = source
            self.final[old] = destination
            self.write_entry(old, kind, source)
            self.write_entry(new, kind, destination)
            self.manifest["moves"].append({
                "oldPath": old, "newPath": new, "kind": kind,
                "sourceFiles": {name: digest(data) for name, data in source.items()},
                "destinationFiles": {name: digest(data) for name, data in destination.items()},
            })
        self.save_manifest()

    def write_entry(self, relative: str, kind: str, files: dict[str, bytes]):
        entry = self.root / relative
        if kind == "directory":
            entry.mkdir(parents=True)
        for name, data in files.items():
            target = entry if name == "." else entry / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def save_manifest(self):
        path = self.root / migration.MANIFEST_PATH
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")

    def remove_old(self, names=None):
        for name in names if names is not None else migration.ALLOWED_MOVES:
            path = self.root / name
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def assert_refused_unchanged(self, *, message=None, root=None, manifest=None):
        before = snapshot(self.root)
        with self.assertRaises(migration.MigrationError) as raised:
            migration.migrate(root or self.root, manifest=manifest, apply=True)
        self.assertNotIsInstance(raised.exception, migration.PartialMigrationError)
        if message:
            self.assertIn(message, str(raised.exception))
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse((self.root / migration.BACKUP_DIRECTORY).exists())

    def link(self, target: Path, link: Path, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Creating test symlinks is unsupported: {exc}")

    def test_default_dry_run_verifies_without_writes(self):
        before = snapshot(self.root)
        result = migration.migrate(self.root)
        self.assertEqual("dry-run", result["status"])
        self.assertEqual(list(migration.ALLOWED_MOVES), result["entries"])
        self.assertIsNone(result["backup"])
        self.assertEqual(before, snapshot(self.root))

    def test_apply_moves_all_originals_with_intact_destination_and_journal(self):
        targets_before = snapshot(self.root / "plugins")
        result = migration.migrate(self.root, apply=True)
        self.assertEqual("applied", result["status"])
        backup = Path(result["backup"])
        self.assertEqual(self.root / migration.BACKUP_DIRECTORY, backup.parent)
        self.assertEqual(targets_before, snapshot(self.root / "plugins"))
        for old, (_, kind) in migration.ALLOWED_MOVES.items():
            self.assertFalse((self.root / old).exists())
            actual, _ = migration._inventory(backup / old, kind)
            self.assertEqual({name: digest(data) for name, data in self.baseline[old].items()}, actual)
        events = [json.loads(line) for line in (backup / "journal.jsonl").read_text().splitlines()]
        self.assertEqual("prepared", events[0]["event"])
        self.assertEqual("complete", events[-1]["event"])
        self.assertEqual(6, len([event for event in events if event["event"] == "moved"]))
        self.assertEqual(digest((self.root / migration.MANIFEST_PATH).read_bytes()),
                         events[0]["manifestSha256"])

    def test_apply_is_idempotent_and_keeps_first_backup(self):
        migration.migrate(self.root, apply=True)
        before = snapshot(self.root)
        result = migration.migrate(self.root, apply=True)
        self.assertEqual("already-clean", result["status"])
        self.assertEqual(before, snapshot(self.root))

    def test_already_clean_does_not_create_backup(self):
        self.remove_old()
        before = snapshot(self.root)
        for apply in (False, True):
            result = migration.migrate(self.root, apply=apply)
            self.assertEqual("already-clean", result["status"])
            self.assertEqual([], result["entries"])
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse((self.root / migration.BACKUP_DIRECTORY).exists())

    def test_partial_overlay_moves_only_present_old_entries(self):
        self.remove_old(list(migration.ALLOWED_MOVES)[1:])
        result = migration.migrate(self.root, apply=True)
        self.assertEqual([next(iter(migration.ALLOWED_MOVES))], result["entries"])

    def test_unrelated_root_files_and_directories_are_preserved(self):
        (self.root / "owner-notes.txt").write_bytes(b"local notes")
        (self.root / "owner-empty-directory").mkdir()
        migration.migrate(self.root, apply=True)
        self.assertEqual(b"local notes", (self.root / "owner-notes.txt").read_bytes())
        self.assertTrue((self.root / "owner-empty-directory").is_dir())

    def test_modified_old_file_is_refused_before_first_rename(self):
        # A conflict in the LAST move must prevent the earlier five from moving.
        (self.root / "example-visualization.mvsplugin").write_bytes(b"owner-modified")
        self.assert_refused_unchanged(message="SHA-256 mismatch")

    def test_modified_old_directory_file_is_refused(self):
        (self.root / "plugin-stress-pack-source/plugin.json").write_bytes(b"edited")
        self.assert_refused_unchanged(message="SHA-256 mismatch")

    def test_readme_uses_distinct_source_and_destination_hashes(self):
        old = "plugin-report-pack-source"
        new, _ = migration.ALLOWED_MOVES[old]
        self.assertNotEqual((self.root / old / "README.md").read_bytes(),
                            (self.root / new / "README.md").read_bytes())
        self.assertEqual("applied", migration.migrate(self.root, apply=True)["status"])

    def test_extra_old_file_is_refused(self):
        (self.root / "plugin-stress-pack-source/owner-data.txt").write_text("keep")
        self.assert_refused_unchanged(message="extra files")

    def test_extra_empty_old_directory_is_refused(self):
        (self.root / "plugin-stress-pack-source/empty-owner-data").mkdir()
        self.assert_refused_unchanged(message="extra directories")

    def test_missing_old_file_is_refused(self):
        (self.root / "plugin-example-source/plugin.json").unlink()
        self.assert_refused_unchanged(message="missing files")

    def test_missing_destination_is_refused_before_any_moves(self):
        (self.root / "plugins/packages/example-visualization.mvsplugin").unlink()
        self.assert_refused_unchanged(message="Required path is missing")

    def test_wrong_destination_hash_is_refused(self):
        (self.root / "plugins/packages/example-visualization.mvsplugin").write_bytes(b"wrong")
        self.assert_refused_unchanged(message="SHA-256 mismatch")

    def test_clean_tree_still_requires_all_destination_hashes(self):
        self.remove_old()
        (self.root / "plugins/packages/example-visualization.mvsplugin").write_bytes(b"wrong")
        self.assert_refused_unchanged(message="SHA-256 mismatch")

    def test_extra_destination_file_is_refused(self):
        (self.root / "plugins/sources/plugin-example-source/extra.txt").write_text("extra")
        self.assert_refused_unchanged(message="extra files")

    def test_extra_empty_destination_directory_is_refused(self):
        (self.root / "plugins/sources/plugin-example-source/empty").mkdir()
        self.assert_refused_unchanged(message="extra directories")

    def test_wrong_kind_is_refused(self):
        path = self.root / "example-visualization.mvsplugin"
        path.unlink()
        path.mkdir()
        self.assert_refused_unchanged(message="Expected file")

    def test_invalid_hash_in_manifest_is_refused(self):
        self.manifest["moves"][0]["sourceFiles"]["plugin.json"] = "not-a-hash"
        self.save_manifest()
        self.assert_refused_unchanged(message="Invalid SHA-256")

    def test_well_formed_wrong_hash_is_refused(self):
        self.manifest["moves"][0]["destinationFiles"]["plugin.json"] = "0" * 64
        self.save_manifest()
        self.assert_refused_unchanged(message="SHA-256 mismatch")

    def test_duplicate_canonical_manifest_file_paths_are_refused(self):
        self.manifest["moves"][0]["sourceFiles"]["PLUGIN.JSON"] = digest(b"anything")
        self.save_manifest()
        self.assert_refused_unchanged(message="Duplicate canonical")

    def test_duplicate_canonical_manifest_directories_are_refused(self):
        files = self.manifest["moves"][0]["sourceFiles"]
        files["Templates/another.txt"] = digest(b"anything")
        self.save_manifest()
        self.assert_refused_unchanged(message="Duplicate canonical")

    def test_duplicate_move_is_refused(self):
        self.manifest["moves"][-1] = copy.deepcopy(self.manifest["moves"][0])
        self.save_manifest()
        self.assert_refused_unchanged(message="Duplicate canonical move")

    def test_duplicate_json_key_is_refused(self):
        path = self.root / migration.MANIFEST_PATH
        path.write_text(path.read_text().replace('"stage": 37,', '"stage": 37, "stage": 37,'))
        self.assert_refused_unchanged(message="Duplicate JSON key")

    def test_invalid_manifest_shape_is_refused(self):
        original = copy.deepcopy(self.manifest)
        cases = [None, [], {}, {**original, "schema": "wrong"},
                 {**original, "stage": True}, {**original, "sourceStage": 35},
                 {**original, "unexpected": "field"}, {**original, "moves": []}]
        for value in cases:
            with self.subTest(value=value):
                self.manifest = value
                self.save_manifest()
                self.assert_refused_unchanged()

    def test_truncated_and_non_utf8_manifest_are_refused(self):
        path = self.root / migration.MANIFEST_PATH
        for data in (b'{"schema":', b"\xff\xfe", b"NaN"):
            with self.subTest(data=data):
                path.write_bytes(data)
                self.assert_refused_unchanged(message="manifest")

    def test_unsafe_manifest_relative_names_are_refused(self):
        original = copy.deepcopy(self.manifest)
        for name in ("../outside", "/absolute", "a/../outside", "a//b", "a/./b", "a/",
                     "a\\b", "C:/escape", "a:stream", "NUL.txt", "a. ", "a.",
                     "CON", "COM1", "a\x00b", "a\nb", "a?b", "a*b", ".", ""):
            with self.subTest(name=name):
                self.manifest = copy.deepcopy(original)
                self.manifest["moves"][0]["sourceFiles"][name] = digest(b"anything")
                self.save_manifest()
                self.assert_refused_unchanged(message="Unsafe relative path")

    def test_move_outside_fixed_allowlist_is_refused(self):
        for field, value in (("oldPath", "owner-notes"), ("newPath", "plugins/other"),
                             ("oldPath", "../outside"), ("newPath", "/outside")):
            original = copy.deepcopy(self.manifest)
            with self.subTest(field=field, value=value):
                self.manifest["moves"][0][field] = value
                self.save_manifest()
                self.assert_refused_unchanged()
            self.manifest = original

    def test_file_entry_requires_dot_key(self):
        self.manifest["moves"][-1]["sourceFiles"] = {"nested": digest(b"anything")}
        self.save_manifest()
        self.assert_refused_unchanged(message="exactly the '.'")

    def test_empty_file_inventory_is_refused(self):
        self.manifest["moves"][0]["sourceFiles"] = {}
        self.save_manifest()
        self.assert_refused_unchanged(message="nonempty")

    def test_manifest_file_directory_collision_is_refused(self):
        self.manifest["moves"][0]["sourceFiles"]["templates"] = digest(b"anything")
        self.save_manifest()
        self.assert_refused_unchanged(message="both file and directory")

    def test_source_and_destination_inventories_must_agree(self):
        del self.manifest["moves"][0]["sourceFiles"]["README.md"]
        self.save_manifest()
        self.assert_refused_unchanged(message="preserve the file path inventory")

    def test_external_manifest_and_root_traversal_are_refused(self):
        outside = self.root.parent / "outside.json"
        outside.write_text(json.dumps(self.manifest))
        self.assert_refused_unchanged(manifest=outside, message="inside the selected root")
        self.assert_refused_unchanged(manifest="../outside.json", message="'..'")
        self.assert_refused_unchanged(root=self.root / ".." / "repository", message="'..'")

    def test_old_symlink_is_refused_even_when_content_matches(self):
        path = self.root / "example-visualization.mvsplugin"
        path.unlink()
        self.link(self.root / "plugins/packages/example-visualization.mvsplugin", path)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_dangling_old_symlink_is_not_treated_as_absent(self):
        path = self.root / "example-visualization.mvsplugin"
        path.unlink()
        self.link(self.root / "missing", path)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_nested_old_symlink_is_refused(self):
        path = self.root / "plugin-example-source/templates/example.txt"
        path.unlink()
        self.link(self.root / "plugins/sources/plugin-example-source/templates/example.txt", path)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_destination_parent_symlink_is_refused(self):
        original = self.root / "plugins"
        relocated = self.root.parent / "external-plugins"
        original.rename(relocated)
        self.link(relocated, original, directory=True)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_root_symlink_is_refused(self):
        alias = self.root.parent / "alias"
        self.link(self.root, alias, directory=True)
        self.assert_refused_unchanged(root=alias, message="Symlink or reparse")

    def test_root_parent_symlink_is_refused(self):
        alias = self.root.parent / "parent-alias"
        self.link(self.root.parent, alias, directory=True)
        self.assert_refused_unchanged(root=alias / self.root.name, message="Symlink or reparse")

    def test_manifest_parent_symlink_is_refused(self):
        path = self.root / "packaging"
        relocated = self.root.parent / "external-packaging"
        path.rename(relocated)
        self.link(relocated, path, directory=True)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_manifest_file_symlink_is_refused(self):
        path = self.root / migration.MANIFEST_PATH
        relocated = self.root.parent / "outside.json"
        path.rename(relocated)
        self.link(relocated, path)
        self.assert_refused_unchanged(message="Symlink or reparse")

    def test_backup_symlink_is_refused_before_any_moves(self):
        outside = self.root.parent / "external-backup"
        outside.mkdir()
        self.link(outside, self.root / migration.BACKUP_DIRECTORY, directory=True)
        before = snapshot(self.root)
        with self.assertRaisesRegex(migration.MigrationError, "Symlink or reparse"):
            migration.migrate(self.root, apply=True)
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual([], list(outside.iterdir()))

    def test_regular_file_at_backup_location_is_refused(self):
        (self.root / migration.BACKUP_DIRECTORY).write_bytes(b"owner-data")
        before = snapshot(self.root)
        with self.assertRaisesRegex(migration.MigrationError, "Backup location"):
            migration.migrate(self.root, apply=True)
        self.assertEqual(before, snapshot(self.root))

    def test_existing_backups_are_preserved_and_new_run_is_unique(self):
        existing = self.root / migration.BACKUP_DIRECTORY / "previous"
        existing.mkdir(parents=True)
        (existing / "keep.txt").write_bytes(b"keep")
        result = migration.migrate(self.root, apply=True)
        self.assertNotEqual(existing, Path(result["backup"]))
        self.assertEqual(b"keep", (existing / "keep.txt").read_bytes())

    def test_reparse_point_attribute_is_refused_portably(self):
        original_lstat = Path.lstat
        unsafe = self.root / "example-visualization.mvsplugin"

        def fake_lstat(path):
            info = original_lstat(path)
            if path == unsafe:
                return SimpleNamespace(st_mode=info.st_mode,
                                       st_file_attributes=migration._REPARSE_POINT)
            return info

        before = snapshot(self.root)
        with patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(migration.MigrationError, "reparse"):
                migration.migrate(self.root, apply=True)
        self.assertEqual(before, snapshot(self.root))

    def test_hardlinked_old_file_is_refused(self):
        if not hasattr(os, "link"):
            self.skipTest("Hard links are unavailable")
        path = self.root / "example-visualization.mvsplugin"
        try:
            os.link(path, self.root.parent / "outside-hardlink")
        except OSError as exc:
            self.skipTest(f"Creating test hardlinks is unsupported: {exc}")
        self.assert_refused_unchanged(message="Hard-linked")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO test requires POSIX")
    def test_special_file_is_refused_without_reading_it(self):
        os.mkfifo(self.root / "plugin-example-source/fifo")
        with self.assertRaisesRegex(migration.MigrationError, "Special filesystem"):
            migration.migrate(self.root, apply=True)
        self.assertFalse((self.root / migration.BACKUP_DIRECTORY).exists())

    def test_duplicate_canonical_actual_file_is_refused(self):
        original = self.root / "plugin-example-source/plugin.json"
        alias = original.with_name("PLUGIN.JSON")
        if alias.exists():
            self.skipTest("Case-insensitive filesystem")
        alias.write_bytes(original.read_bytes())
        self.assert_refused_unchanged(message="Duplicate canonical filesystem")

    def test_noncanonical_root_alias_is_refused(self):
        original = self.root / "plugin-example-source"
        alias = self.root / "PLUGIN-EXAMPLE-SOURCE"
        if alias.exists():
            self.skipTest("Case-insensitive filesystem")
        original.rename(alias)
        self.assert_refused_unchanged(message="Noncanonical or duplicate")

    def test_plan_reverified_before_any_write(self):
        plan = migration.prepare(self.root)
        path = self.root / "example-visualization.mvsplugin"
        path.write_bytes(b"changed after dry-run")
        before = snapshot(self.root)
        with self.assertRaisesRegex(migration.MigrationError, "SHA-256 mismatch"):
            migration.execute(plan, apply=True)
        self.assertEqual(before, snapshot(self.root))

    def test_manifest_change_after_plan_is_refused(self):
        plan = migration.prepare(self.root)
        path = self.root / migration.MANIFEST_PATH
        path.write_bytes(path.read_bytes() + b"\n")
        before = snapshot(self.root)
        with self.assertRaisesRegex(migration.MigrationError, "plan changed"):
            migration.execute(plan, apply=True)
        self.assertEqual(before, snapshot(self.root))

    def test_partial_failure_retains_originals_without_destructive_rollback(self):
        rename = os.rename
        count = 0
        installed = snapshot(self.root / "plugins")

        def fail_second(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("injected second rename failure")
            return rename(source, destination)

        with patch.object(migration.os, "rename", side_effect=fail_second):
            with self.assertRaises(migration.PartialMigrationError) as caught:
                migration.migrate(self.root, apply=True)
        error = caught.exception
        self.assertEqual(2, count, "There must be no automatic rollback renames")
        self.assertIn("No rollback or deletion", str(error))
        self.assertIn("Never overwrite", str(error))
        self.assertEqual(installed, snapshot(self.root / "plugins"))
        for index, (old, (_, kind)) in enumerate(migration.ALLOWED_MOVES.items()):
            retained = error.backup / old if index == 0 else self.root / old
            self.assertFalse((self.root / old if index == 0 else error.backup / old).exists())
            actual, _ = migration._inventory(retained, kind)
            self.assertEqual({name: digest(data) for name, data in self.baseline[old].items()}, actual)
        events = [json.loads(line) for line in (error.backup / "journal.jsonl").read_text().splitlines()]
        self.assertEqual("stopped", events[-1]["event"])
        self.assertEqual("true", error.locations[0]["backupExists"])
        self.assertEqual("false", error.locations[0]["rootExists"])
        retained_before = snapshot(error.backup)
        result = migration.migrate(self.root, apply=True)
        self.assertEqual(5, len(result["entries"]))
        self.assertNotEqual(str(error.backup), result["backup"])
        self.assertEqual(retained_before, snapshot(error.backup))
        self.assertEqual("already-clean", migration.migrate(self.root, apply=True)["status"])

    def test_journal_failure_after_rename_reports_actual_locations(self):
        append = migration._append_event

        def fail_moved(handle, event):
            if event["event"] == "moved":
                raise OSError("injected journal failure after move")
            return append(handle, event)

        with patch.object(migration, "_append_event", side_effect=fail_moved):
            with self.assertRaises(migration.PartialMigrationError) as caught:
                migration.migrate(self.root, apply=True)
        self.assertEqual("true", caught.exception.locations[0]["backupExists"])
        self.assertEqual("false", caught.exception.locations[0]["rootExists"])
        self.assertEqual(5, sum((self.root / name).exists() for name in migration.ALLOWED_MOVES))

    def test_journal_failure_before_first_rename_moves_nothing(self):
        with patch.object(migration, "_append_event", side_effect=OSError("journal unwritable")):
            with self.assertRaises(migration.PartialMigrationError) as caught:
                migration.migrate(self.root, apply=True)
        self.assertIn("Journal update also failed", str(caught.exception))
        self.assertTrue(all((self.root / name).exists() for name in migration.ALLOWED_MOVES))

    def test_cli_default_and_apply_and_exit_codes(self):
        command = [sys.executable, str(ROOT / "tools/migrate_root_layout.py"), "--root", str(self.root)]
        before = snapshot(self.root)
        dry_run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        self.assertIn("DRY RUN", dry_run.stdout)
        self.assertEqual(before, snapshot(self.root))
        applied = subprocess.run(command + ["--apply"], capture_output=True, text=True)
        self.assertEqual(0, applied.returncode, applied.stderr)
        self.assertIn("Moved 6", applied.stdout)
        clean = subprocess.run(command + ["--apply"], capture_output=True, text=True)
        self.assertEqual(0, clean.returncode, clean.stderr)
        self.assertIn("Already clean", clean.stdout)
        (self.root / "plugins/packages/example-visualization.mvsplugin").write_bytes(b"bad")
        refused = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(2, refused.returncode)
        self.assertIn("REFUSED", refused.stderr)

    def test_cli_partial_failure_has_distinct_exit_code_and_recovery_paths(self):
        stderr = io.StringIO()
        with patch.object(migration.os, "rename", side_effect=OSError("injected rename failure")):
            with contextlib.redirect_stderr(stderr):
                code = migration.main(["--root", str(self.root), "--apply"])
        self.assertEqual(3, code)
        self.assertIn("Recovery:", stderr.getvalue())
        self.assertIn("root exists=true", stderr.getvalue())
        self.assertIn("backup exists=false", stderr.getvalue())


class RepositoryLayoutTests(unittest.TestCase):
    def test_exact_root_inventory_preserves_conventions(self):
        entries = [path for path in ROOT.iterdir()
                   if path.name not in {".git", migration.BACKUP_DIRECTORY}]
        files = {path.name for path in entries if path.is_file()}
        directories = {path.name for path in entries if path.is_dir()}
        self.assertEqual(EXPECTED_ROOT_FILES, files)
        self.assertEqual(EXPECTED_ROOT_DIRECTORIES, directories)
        self.assertEqual(15, len(files))
        self.assertEqual(23, len(directories))
        self.assertEqual(len(entries), len(files) + len(directories))
        self.assertFalse(any(path.is_symlink() for path in entries))
        self.assertNotIn("bin", directories)
        self.assertNotIn("obj", directories)
        for required in ("README.md", "LICENSE", "CITATION.cff", "SECURITY.md",
                         "CODE_OF_CONDUCT.md", "MvsAnalyzer.csproj", "MvsAnalyzer.slnx",
                         "SharedSources.props", "app.ico", "app.manifest", ".codex", ".github"):
            self.assertTrue((ROOT / required).exists(), required)

    def test_no_old_six_entries_and_all_new_targets_match_real_manifest(self):
        for old, (new, _) in migration.ALLOWED_MOVES.items():
            self.assertFalse(os.path.lexists(ROOT / old), old)
            self.assertTrue((ROOT / new).exists(), new)
        plan = migration.prepare(ROOT)
        self.assertEqual((), plan.present)
        self.assertEqual(6, len(plan.moves))
        self.assertEqual("already-clean", migration.execute(plan)["status"])

    def test_shipped_manifest_has_only_intended_readme_content_change(self):
        manifest = json.loads((ROOT / migration.MANIFEST_PATH).read_text(encoding="utf-8"))
        self.assertEqual("mvs-root-layout-migration/v1", manifest["schema"])
        self.assertEqual(37, manifest["stage"])
        self.assertEqual(36, manifest["sourceStage"])
        differences = []
        for item in manifest["moves"]:
            self.assertEqual(set(item["sourceFiles"]), set(item["destinationFiles"]))
            for name, checksum in item["sourceFiles"].items():
                if checksum != item["destinationFiles"][name]:
                    differences.append((item["oldPath"], name))
        self.assertEqual([("plugin-report-pack-source", "README.md")], differences)


if __name__ == "__main__":
    unittest.main(verbosity=2)
