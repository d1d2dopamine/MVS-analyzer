#!/usr/bin/env python3
"""Verify a Round 37 ZIP overlay, then recoverably retire old plugin entries.

Dry-run is the default. --apply only renames verified Round 36 originals into a
unique .mvs-layout-backup directory; the installed plugins are never modified.
The manifest is a shipped integrity record, not an authenticity/signature check.
Run with the application and other writers stopped. A partial failure preserves
all originals in their current locations and records recovery instructions; no
automatic rollback, replacement, or deletion is performed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
import uuid
from typing import Any


ROOT = Path(__file__).absolute().parent.parent
MANIFEST_PATH = "packaging/root-layout-migration-v1.json"
BACKUP_DIRECTORY = ".mvs-layout-backup"
SCHEMA = "mvs-root-layout-migration/v1"
ALLOWED_MOVES = {
    "plugin-example-source": ("plugins/sources/plugin-example-source", "directory"),
    "plugin-lab-pack-source": ("plugins/sources/plugin-lab-pack-source", "directory"),
    "plugin-report-pack-source": ("plugins/sources/plugin-report-pack-source", "directory"),
    "plugin-stress-pack-source": ("plugins/sources/plugin-stress-pack-source", "directory"),
    "MVS_Report_Pack_v1.0.0.mvsplugin": (
        "plugins/packages/MVS_Report_Pack_v1.0.0.mvsplugin", "file"),
    "example-visualization.mvsplugin": (
        "plugins/packages/example-visualization.mvsplugin", "file"),
}
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
_RESERVED.update(f"{prefix}{number}" for prefix in ("COM", "LPT")
                 for number in "123456789¹²³")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class MigrationError(ValueError):
    """A verification failed before any old entry was moved."""


class PartialMigrationError(MigrationError):
    """Some entries may have moved; the backup and journal must be retained."""

    def __init__(self, message: str, backup: Path, locations: list[dict[str, str]]):
        super().__init__(message)
        self.backup = backup
        self.locations = locations


@dataclass(frozen=True)
class Move:
    old_path: str
    new_path: str
    kind: str
    source_files: dict[str, str]
    destination_files: dict[str, str]


@dataclass(frozen=True)
class Plan:
    root: Path
    manifest_path: Path
    manifest_hash: str
    moves: tuple[Move, ...]
    present: tuple[str, ...]


def _canonical(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _relative_path(value: Any, *, dot: bool = False) -> str:
    if dot and value == ".":
        return value
    if not isinstance(value, str) or not value or "\\" in value:
        raise MigrationError(f"Unsafe relative path: {value!r}")
    parts = value.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part[-1:] in (".", " ")
                or any(ord(char) < 32 or ord(char) == 127 for char in part)
                or any(char in '<>:"|?*' for char in part)
                or part.split(".")[0].upper() in _RESERVED
                or unicodedata.normalize("NFC", part) != part):
            raise MigrationError(f"Unsafe relative path: {value!r}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _directories(files: dict[str, str]) -> set[str]:
    result = set()
    for name in files:
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            result.add(str(parent))
            parent = parent.parent
    return result


def _file_map(value: Any, kind: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise MigrationError("Each file inventory must be a nonempty object.")
    keys: set[str] = set()
    for name, digest in value.items():
        _relative_path(name, dot=kind == "file")
        canonical = _canonical(name)
        if canonical in keys:
            raise MigrationError(f"Duplicate canonical file path: {name!r}")
        keys.add(canonical)
        if not isinstance(digest, str) or _HASH.fullmatch(digest) is None:
            raise MigrationError(f"Invalid SHA-256 for {name!r}")
    if kind == "file" and set(value) != {"."}:
        raise MigrationError("A file entry must contain exactly the '.' hash.")
    if kind == "directory":
        all_names: dict[str, str] = {}
        for name in sorted(set(value) | _directories(value)):
            canonical = _canonical(name)
            if canonical in all_names and all_names[canonical] != name:
                raise MigrationError(f"Duplicate canonical path: {name!r}")
            all_names[canonical] = name
        if set(value) & _directories(value):
            raise MigrationError("A manifest path cannot be both file and directory.")
        for directory in _directories(value):
            if _canonical(directory) in keys:
                raise MigrationError("Canonical file/directory path collision.")
    return dict(value)


def _parse_manifest(data: bytes) -> tuple[Move, ...]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MigrationError(f"Malformed migration manifest: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "stage", "sourceStage", "moves"}:
        raise MigrationError("Unexpected migration manifest fields.")
    if (value["schema"] != SCHEMA or type(value["stage"]) is not int
            or value["stage"] != 37 or type(value["sourceStage"]) is not int
            or value["sourceStage"] != 36):
        raise MigrationError("Expected the Round 36 to Round 37 v1 migration manifest.")
    if not isinstance(value["moves"], list) or len(value["moves"]) != len(ALLOWED_MOVES):
        raise MigrationError("Manifest must specify all six approved plugin moves.")
    found: dict[str, Move] = {}
    seen: set[str] = set()
    for item in value["moves"]:
        if not isinstance(item, dict) or set(item) != {
                "oldPath", "newPath", "kind", "sourceFiles", "destinationFiles"}:
            raise MigrationError("Unexpected move fields in manifest.")
        old = _relative_path(item["oldPath"])
        new = _relative_path(item["newPath"])
        for path in (old, new):
            canonical = _canonical(path)
            if canonical in seen:
                raise MigrationError(f"Duplicate canonical move path: {path!r}")
            seen.add(canonical)
        if old not in ALLOWED_MOVES or (new, item["kind"]) != ALLOWED_MOVES[old]:
            raise MigrationError(f"Move is outside the fixed migration allowlist: {old!r}")
        source = _file_map(item["sourceFiles"], item["kind"])
        destination = _file_map(item["destinationFiles"], item["kind"])
        if set(source) != set(destination):
            raise MigrationError("Relocation must preserve the file path inventory.")
        found[old] = Move(old, new, item["kind"], source, destination)
    if set(found) != set(ALLOWED_MOVES):
        raise MigrationError("Manifest does not contain each approved move exactly once.")
    return tuple(found[name] for name in ALLOWED_MOVES)


def _safe_stat(path: Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        raise MigrationError(f"Symlink or reparse point is not allowed: {path}")
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise MigrationError(f"Special filesystem entry is not allowed: {path}")
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise MigrationError(f"Hard-linked file is not allowed: {path}")
    return info


def _root_path(value: str | Path) -> Path:
    supplied = Path(value)
    if ".." in supplied.parts:
        raise MigrationError("The root path must not contain '..' components.")
    root = Path(os.path.abspath(supplied))
    for part in list(reversed(root.parents)) + [root]:
        if not stat.S_ISDIR(_safe_stat(part).st_mode):
            raise MigrationError(f"Root or parent is not a directory: {part}")
    return root


def _check_components(root: Path, relative: str, *, missing: bool = False) -> bool:
    """Check lexical descendants without following links, including their parents."""
    _relative_path(relative)
    current = root
    parts = relative.split("/")
    for index, part in enumerate(parts):
        parent_info = _safe_stat(current)
        if not stat.S_ISDIR(parent_info.st_mode):
            raise MigrationError(f"Parent is not a directory: {current}")
        aliases = [entry.name for entry in current.iterdir()
                   if _canonical(entry.name) == _canonical(part)]
        if aliases and aliases != [part]:
            raise MigrationError(f"Noncanonical or duplicate path at {current / part}: {aliases}")
        current = current / part
        try:
            info = _safe_stat(current)
        except FileNotFoundError:
            if missing and index == len(parts) - 1:
                return False
            raise MigrationError(f"Required path is missing: {current}") from None
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise MigrationError(f"Parent is not a directory: {current}")
    return True


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_file(path: Path, *, maximum: int | None = None) -> bytes:
    before = _safe_stat(path)
    if not stat.S_ISREG(before.st_mode):
        raise MigrationError(f"Expected a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if _identity(before) != _identity(opened):
            raise MigrationError(f"File changed while opening: {path}")
        if maximum is not None and opened.st_size > maximum:
            raise MigrationError(f"Manifest exceeds size limit: {path}")
        data = handle.read() if maximum is None else handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
    if (maximum is not None and len(data) > maximum
            or _identity(before) != _identity(after)
            or _identity(before) != _identity(_safe_stat(path))):
        raise MigrationError(f"File changed during verification: {path}")
    return data


def _file_hash(path: Path) -> str:
    # Plugin payloads are small; the same stable-file reader also validates manifests.
    return hashlib.sha256(_read_file(path)).hexdigest()


def _inventory(path: Path, kind: str) -> tuple[dict[str, str], set[str]]:
    info = _safe_stat(path)
    if kind == "file":
        if not stat.S_ISREG(info.st_mode):
            raise MigrationError(f"Expected file: {path}")
        return {".": _file_hash(path)}, set()
    if not stat.S_ISDIR(info.st_mode):
        raise MigrationError(f"Expected directory: {path}")
    files: dict[str, str] = {}
    directories: set[str] = set()
    canonical: set[str] = set()

    def visit(folder: Path) -> None:
        before = _safe_stat(folder)
        if not stat.S_ISDIR(before.st_mode):
            raise MigrationError(f"Expected directory: {folder}")
        for child in sorted(folder.iterdir(), key=lambda item: item.name):
            relative = child.relative_to(path).as_posix()
            _relative_path(relative)
            key = _canonical(relative)
            if key in canonical:
                raise MigrationError(f"Duplicate canonical filesystem path: {child}")
            canonical.add(key)
            entry = _safe_stat(child)
            if stat.S_ISDIR(entry.st_mode):
                directories.add(relative)
                visit(child)
            else:
                files[relative] = _file_hash(child)
        if _identity(before) != _identity(_safe_stat(folder)):
            raise MigrationError(f"Directory changed during verification: {folder}")

    visit(path)
    return files, directories


def _verify_entry(root: Path, relative: str, kind: str, expected: dict[str, str]) -> None:
    _check_components(root, relative)
    actual, directories = _inventory(root / relative, kind)
    expected_directories = _directories(expected) if kind == "directory" else set()
    if set(actual) != set(expected) or directories != expected_directories:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        missing_dirs = sorted(expected_directories - directories)
        extra_dirs = sorted(directories - expected_directories)
        raise MigrationError(f"Inventory mismatch at {relative}: missing files={missing}; "
                             f"extra files={extra}; missing directories={missing_dirs}; "
                             f"extra directories={extra_dirs}")
    changed = [name for name in sorted(expected) if actual[name] != expected[name]]
    if changed:
        raise MigrationError(f"SHA-256 mismatch at {relative}: {changed}")


def prepare(root: str | Path = ROOT, manifest: str | Path | None = None) -> Plan:
    """Perform the complete, read-only preflight. Never create a backup here."""
    try:
        root = _root_path(root)
        manifest_path = Path(manifest) if manifest is not None else Path(MANIFEST_PATH)
        if ".." in manifest_path.parts:
            raise MigrationError("Manifest path must not contain '..' components.")
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
        try:
            relative = manifest_path.relative_to(root).as_posix()
        except ValueError:
            raise MigrationError("Manifest must be inside the selected root.") from None
        _check_components(root, relative)
        data = _read_file(manifest_path, maximum=2 * 1024 * 1024)
        moves = _parse_manifest(data)
        present = []
        # New payloads must all match, even if no old entries remain at the root.
        for move in moves:
            _verify_entry(root, move.new_path, move.kind, move.destination_files)
        for move in moves:
            if _check_components(root, move.old_path, missing=True):
                _verify_entry(root, move.old_path, move.kind, move.source_files)
                present.append(move.old_path)
        if _check_components(root, BACKUP_DIRECTORY, missing=True):
            if not stat.S_ISDIR(_safe_stat(root / BACKUP_DIRECTORY).st_mode):
                raise MigrationError("Backup location must be a real directory.")
        return Plan(root, manifest_path, hashlib.sha256(data).hexdigest(), moves, tuple(present))
    except OSError as exc:
        raise MigrationError(f"Cannot safely inspect the migration tree: {exc}") from exc


def _append_event(handle: Any, event: dict[str, Any]) -> None:
    handle.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), **event},
                            ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _location_report(plan: Plan, backup: Path) -> list[dict[str, str]]:
    result = []
    for move in plan.moves:
        if move.old_path not in plan.present:
            continue
        original = plan.root / move.old_path
        retained = backup / move.old_path
        # lexists reports broken links too; recovery must never overwrite any entry.
        original_exists = os.path.lexists(original)
        retained_exists = os.path.lexists(retained)
        result.append({"entry": move.old_path,
                       "rootPath": str(original), "backupPath": str(retained),
                       "rootExists": str(original_exists).lower(),
                       "backupExists": str(retained_exists).lower()})
    return result


def execute(plan: Plan, *, apply: bool = False) -> dict[str, Any]:
    """Apply a freshly reverified plan, retaining moved originals on any failure."""
    if not apply:
        return {"status": "dry-run" if plan.present else "already-clean",
                "entries": list(plan.present), "backup": None}
    checked = prepare(plan.root, plan.manifest_path)
    if checked != plan:
        raise MigrationError("Migration plan changed since preflight; no entries were moved.")
    if not plan.present:
        return {"status": "already-clean", "entries": [], "backup": None}
    base = plan.root / BACKUP_DIRECTORY
    backup: Path | None = None
    journal = None
    try:
        # No directory is created until both complete preflights have passed.
        _root_path(plan.root)
        if not _check_components(plan.root, BACKUP_DIRECTORY, missing=True):
            base.mkdir(mode=0o700)
        _check_components(plan.root, BACKUP_DIRECTORY)
        if not stat.S_ISDIR(_safe_stat(base).st_mode):
            raise MigrationError("Backup location must be a real directory.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = base / f"{stamp}-{uuid.uuid4().hex}"
        backup.mkdir(mode=0o700)
        _check_components(plan.root, backup.relative_to(plan.root).as_posix())
        journal_path = backup / "journal.jsonl"
        fd = os.open(journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        journal = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
        _append_event(journal, {"event": "prepared", "schema": "mvs-root-layout-journal/v1",
                               "root": str(plan.root), "backup": str(backup),
                               "manifestSha256": plan.manifest_hash,
                               "moves": [{"oldPath": move.old_path, "newPath": move.new_path,
                                          "backupPath": str(backup / move.old_path),
                                          "sourceFiles": move.source_files}
                                         for move in plan.moves if move.old_path in plan.present]})
        for move in plan.moves:
            if move.old_path not in plan.present:
                continue
            _root_path(plan.root)
            _check_components(plan.root, backup.relative_to(plan.root).as_posix())
            _verify_entry(plan.root, move.new_path, move.kind, move.destination_files)
            _verify_entry(plan.root, move.old_path, move.kind, move.source_files)
            target = backup / move.old_path
            if os.path.lexists(target):
                raise MigrationError(f"Backup destination already exists; refusing replacement: {target}")
            _append_event(journal, {"event": "move-intent", "oldPath": move.old_path,
                                   "backupPath": str(target)})
            os.rename(plan.root / move.old_path, target)
            _append_event(journal, {"event": "moved", "oldPath": move.old_path,
                                   "backupPath": str(target)})
        _append_event(journal, {"event": "complete", "entries": list(plan.present)})
        return {"status": "applied", "entries": list(plan.present), "backup": str(backup)}
    except (OSError, MigrationError) as exc:
        if backup is None:
            raise MigrationError(f"Cannot create a safe recovery backup; no entries moved: {exc}") from exc
        locations = _location_report(plan, backup)
        journal_error = None
        if journal is not None:
            try:
                _append_event(journal, {"event": "stopped", "reason": str(exc), "locations": locations})
            except OSError as failure:
                journal_error = str(failure)
        detail = (f"Migration stopped: {exc}\nKeep the recovery directory: {backup}\n"
                  "No rollback or deletion was attempted. Installed plugin targets were not changed.\n"
                  "Recovery: inspect the journal and the locations below. To undo, manually move each "
                  "retained original back only when its root path is absent. Never overwrite an entry. "
                  "Alternatively, rerun this command after fixing the problem to retire remaining "
                  "verified originals into a new backup.")
        if journal_error:
            detail += f"\nJournal update also failed: {journal_error}; inspect both paths for every entry."
        raise PartialMigrationError(detail, backup, locations) from exc
    finally:
        if journal is not None:
            journal.close()


def migrate(root: str | Path = ROOT, *, manifest: str | Path | None = None,
            apply: bool = False) -> dict[str, Any]:
    return execute(prepare(root, manifest), apply=apply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: script's repository)")
    parser.add_argument("--manifest", type=Path, help=f"manifest within root (default: {MANIFEST_PATH})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="move verified originals into a unique recovery backup")
    mode.add_argument("--dry-run", action="store_true", help="verify and show the plan without writing (default)")
    args = parser.parse_args(argv)
    try:
        result = migrate(args.root, manifest=args.manifest, apply=args.apply)
    except PartialMigrationError as exc:
        print(str(exc), file=sys.stderr)
        for item in exc.locations:
            print(f"  {item['entry']}: root exists={item['rootExists']} at {item['rootPath']}; "
                  f"backup exists={item['backupExists']} at {item['backupPath']}", file=sys.stderr)
        return 3
    except MigrationError as exc:
        print(f"REFUSED: {exc}\nPreflight failed; no old entries were moved.", file=sys.stderr)
        return 2
    if result["status"] == "already-clean":
        print("Already clean: all six installed plugin targets verified; no old root entries remain. No changes.")
    elif result["status"] == "dry-run":
        print("DRY RUN: all installed plugin targets and present old entries verified. No changes.")
        for name in result["entries"]:
            print(f"  Would move {name} -> {BACKUP_DIRECTORY}/<unique>/{name}")
        print("Rerun with --apply to move these originals into a recovery backup.")
    else:
        print(f"Moved {len(result['entries'])} verified old entries. Recovery backup: {result['backup']}")
        print("Installed plugin targets were not changed. Keep the backup and its journal for recovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
