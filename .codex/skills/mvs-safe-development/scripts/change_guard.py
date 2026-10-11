#!/usr/bin/env python3
"""Read-only MVS change boundary checks. Only snapshot/extend write external JSON."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

SCHEMA = "mvs-change-guard/v1"
REQUIRED = ("Core/AnalysisEngine.cs", "Infrastructure/OutputExporter.cs",
            "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj")
EXCLUDED_NAMES = {".git", "__pycache__", ".venv", "venv", "node_modules", "bin", "obj"}
EXCLUDED_ROOT_NAMES = {"artifacts", "publish"}


def fail(message):
    raise ValueError(message)


def relpath(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        fail("Scope paths must be exact POSIX repository-relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in (".", "..") for p in value.split("/")):
        fail("Absolute/traversal/noncanonical scope paths are forbidden")
    if any(c in value for c in "*?[]") or path.as_posix() != value or value.endswith("/"):
        fail("Directory-wide scopes, globs and noncanonical paths are forbidden")
    if ".git" in path.parts:
        fail("Git metadata cannot be authorized as a source path")
    return value


def project_root(value):
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir() or any(not (root / p).is_file() for p in REQUIRED):
        fail("Not an MVS source root: required Core/exporter/CLI files are missing")
    for p in REQUIRED:
        if (root / p).is_symlink() or not (root / p).resolve().is_relative_to(root):
            fail("Required MVS identity files must not resolve outside the repository")
    return root


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def seal(document):
    return hash_bytes(json.dumps(document, sort_keys=True, ensure_ascii=True,
                                 separators=(",", ":")).encode())


def git_call(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            check=False, timeout=20)
    if result.returncode:
        fail("Git metadata is present but a read-only Git probe failed: " + args[0])
    return result.stdout


def git_info(root):
    if not os.path.lexists(root / ".git"):
        return {"present": False}, []
    top = Path(os.fsdecode(git_call(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != root:
        fail("Git top-level does not match the selected MVS root")
    # An unborn branch is valid and has no HEAD commit yet.
    head_probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                                capture_output=True, check=False, timeout=20)
    head = head_probe.stdout.decode().strip() if head_probe.returncode == 0 else None
    # Use semantic index entries, not its volatile stat-cache bytes.
    entries = git_call(root, "ls-files", "--stage", "-z")
    paths = [os.fsdecode(p) for p in git_call(root, "ls-files", "-z").split(b"\0") if p]
    return {"present": True, "head": head, "index_entries_sha256": hash_bytes(entries)}, paths


def entry(root, name):
    name = relpath(name)
    path = root / name
    if not path.parent.resolve().is_relative_to(root):
        fail("Cannot inspect a path through a parent symlink outside the repository: " + name)
    details = path.lstat()
    mode = stat.S_IMODE(details.st_mode)
    if stat.S_ISLNK(details.st_mode):
        return {"kind": "symlink", "sha256": hash_bytes(os.fsencode(os.readlink(path))),
                "mode": mode}
    if not stat.S_ISREG(details.st_mode):
        fail("Unsupported special file or submodule directory: " + name)
    # Do not follow a leaf symlink. Detect ordinary modifications while hashing.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (details.st_dev, details.st_ino):
            fail("File changed while opening it: " + name)
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            fail("File changed while hashing it: " + name)
    finally:
        os.close(fd)
    return {"kind": "file", "sha256": digest.hexdigest(), "mode": mode}


def scan(root):
    git, tracked = git_info(root)
    names, excluded = set(), []
    def walk_error(error):
        raise error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        current = Path(current)
        for name in list(dirs):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                names.add(relative)
                dirs.remove(name)
            elif name in EXCLUDED_NAMES or (current == root and name in EXCLUDED_ROOT_NAMES):
                excluded.append(relative)
                dirs.remove(name)
        for name in files:
            path = current / name
            if name == ".git":
                continue
            names.add(path.relative_to(root).as_posix())
    # Git-tracked files remain covered even if they look like build outputs.
    for name in tracked:
        name = relpath(name)
        if os.path.lexists(root / name):
            names.add(name)
    records = {name: entry(root, name) for name in sorted(names)}
    return records, git, sorted(excluded)


def sensitive(path):
    name = path.casefold()
    parts = PurePosixPath(name).parts
    categories = []
    if parts[0] == "core" or name in ("infrastructure/outputexporter.cs",
                                      "benchmark/benchmarkprotocol.cs"):
        categories.append("scientific-method")
    if parts[0] in ("benchmark_history", "benchmark_data", "examples", "assets") or name.startswith("validation/datasets/"):
        categories.append("source-evidence-or-assets")
    if parts[0] in ("desktop", "mvsanalyzer.ui.tests"):
        categories.append("archived-desktop")
    if name.startswith("mvsanalyzer.cli/") or name.startswith("python/src/") or name.startswith("docs/cli"):
        categories.append("interface-contract")
    if (name.startswith("validation/") and any(token in parts[-1] for token in
            ("baseline", "contract", "method-hashes", "protected-assets"))):
        categories.append("test-or-identity-contract")
    if parts[0] in ("mvsanalyzer.core.tests", "mvsanalyzer.tests"):
        categories.append("native-regression-contract")
    if (name.startswith(".github/") or name.startswith("tools/build_")
            or name.startswith("tools/check_") or name.startswith("notebooks/")):
        categories.append("automation-or-generated-payload")
    if (name.endswith((".csproj", ".props", ".slnx")) or parts[0] == "properties"
            or name.endswith("releaseinfo.cs") or parts[-1] in ("global.json", "pyproject.toml", "app.manifest")):
        categories.append("build-or-release-metadata")
    return categories


def excluded_scope(path):
    parts = PurePosixPath(path).parts
    return bool(set(parts) & EXCLUDED_NAMES) or parts[0] in EXCLUDED_ROOT_NAMES


def scope(args, records):
    allowed = sorted({relpath(p) for p in args.allow})
    deletions = sorted({relpath(p) for p in args.allow_delete})
    approvals = sorted({relpath(p) for p in args.allow_sensitive})
    all_allowed = set(allowed) | set(deletions)
    if not all_allowed:
        fail("An edit snapshot requires at least one exact allowed path")
    if not set(approvals).issubset(all_allowed):
        fail("Sensitive approvals must refer to an allowed path")
    if approvals and not args.sensitive_reason.strip():
        fail("Sensitive approvals require --sensitive-reason with the existing authorization")
    for path in all_allowed:
        if excluded_scope(path) and path not in records:
            fail("Cannot scope an excluded generated path without a captured tracked source file: " + path)
        if sensitive(path) and path not in approvals:
            fail("Sensitive path requires a recorded --allow-sensitive approval: " + path)
    for path in deletions:
        if path not in records:
            fail("An authorized deletion must name an existing baseline file: " + path)
    return {"allow": allowed, "allow_delete": deletions,
            "allow_sensitive": approvals, "sensitive_reason": args.sensitive_reason,
            "allow_git_index": args.allow_git_index, "allow_git_history": args.allow_git_history}


def write_external(root, output, document):
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(root):
        fail("Snapshot must be outside the MVS root")
    if output.exists():
        fail("Refusing to overwrite an existing snapshot")
    output.parent.mkdir(parents=True, exist_ok=True)
    document["snapshot_sha256"] = seal(document)
    with output.open("x", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, ensure_ascii=True)
        fh.write("\n")
    return output


def load_baseline(path, root):
    path = Path(path).expanduser().resolve(strict=True)
    if path.is_relative_to(root):
        fail("Baseline must be outside the MVS root")
    with path.open(encoding="utf-8") as fh:
        document = json.load(fh)
    if not isinstance(document, dict):
        fail("Invalid snapshot document")
    digest = document.get("snapshot_sha256")
    unsigned = {k: v for k, v in document.items() if k != "snapshot_sha256"}
    if digest != seal(unsigned):
        fail("Snapshot digest mismatch; do not edit or regenerate baseline evidence")
    if document.get("schema") != SCHEMA or document.get("root") != str(root):
        fail("Snapshot schema/root mismatch")
    if document.get("guard_sha256") != hash_bytes(Path(__file__).read_bytes()):
        fail("Guard implementation changed after the snapshot; do not bypass verification")
    records, policy = document.get("files"), document.get("scope")
    if not isinstance(records, dict) or not isinstance(policy, dict):
        fail("Incomplete snapshot")
    for name, record in records.items():
        relpath(name)
        if (not isinstance(record, dict) or record.get("kind") not in ("file", "symlink")
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", "")))
                or not isinstance(record.get("mode"), int)):
            fail("Invalid baseline file record")
    for key in ("allow", "allow_delete", "allow_sensitive"):
        if not isinstance(policy.get(key), list):
            fail("Invalid baseline scope")
        for name in policy[key]:
            relpath(name)
    return document


def differences(before, after):
    out = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            operation = "add"
        elif path not in after:
            operation = "delete"
        elif before[path] != after[path]:
            operation = "modify"
        else:
            continue
        out.append({"path": path, "operation": operation,
                    "categories": sensitive(path)})
    return out


def violations(changes, document, files, git):
    policy = document["scope"]
    errors = []
    for change in changes:
        path, operation = change["path"], change["operation"]
        expected = policy["allow_delete"] if operation == "delete" else policy["allow"]
        if path not in expected:
            errors.append({"path": path, "reason": "operation outside recorded scope: " + operation})
        if change["categories"] and path not in policy["allow_sensitive"]:
            errors.append({"path": path, "reason": "sensitive change without recorded approval"})
        previous, current = document["files"].get(path), files.get(path)
        if ((previous and previous["kind"] == "symlink") or
                (current and current["kind"] == "symlink")):
            errors.append({"path": path, "reason": "changed symlink is unsupported; inspect it separately"})
    original_git = document["git"]
    if git.get("present") != original_git.get("present"):
        errors.append({"path": ".git", "reason": "Git metadata presence changed"})
    elif git.get("present"):
        if git.get("head") != original_git.get("head") and not policy["allow_git_history"]:
            errors.append({"path": ".git/HEAD", "reason": "Git HEAD changed without authorization"})
        if git.get("index_entries_sha256") != original_git.get("index_entries_sha256") and not policy["allow_git_index"]:
            errors.append({"path": ".git/index", "reason": "Git staging changed without authorization"})
    return errors


def inspect(root):
    files, git, excluded = scan(root)
    probes = [("engine", "Core/ScientificInfrastructure.cs", r'EngineVersion\s*=\s*"([^"]+)"'),
              ("formula", "Infrastructure/OutputExporter.cs", r'FormulaVersion\s*=\s*"([^"]+)"'),
              ("application", "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj", r'<Version>([^<]+)</Version>')]
    versions = {}
    for label, name, pattern in probes:
        text = (root / name).read_text(encoding="utf-8-sig") if (root / name).is_file() else ""
        match = re.search(pattern, text)
        versions[label] = match.group(1) if match else "not found"
    return {"status": "INSPECTED", "root": str(root), "files": len(files), "git": git,
            "versions_from_live_source": versions, "excluded_directories": excluded,
            "note": "Read-only metadata and boundary report; no build/test/scientific guarantee"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    view = subs.add_parser("inspect")
    view.add_argument("--root", required=True)
    for name in ("snapshot", "extend"):
        p = subs.add_parser(name)
        p.add_argument("--root", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--task", required=True)
        p.add_argument("--allow", action="append", default=[])
        p.add_argument("--allow-delete", action="append", default=[])
        p.add_argument("--allow-sensitive", action="append", default=[])
        p.add_argument("--sensitive-reason", default="")
        p.add_argument("--allow-git-index", action="store_true")
        p.add_argument("--allow-git-history", action="store_true")
        if name == "extend":
            p.add_argument("--baseline", required=True)
    verify = subs.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--baseline", required=True)
    args = parser.parse_args()
    try:
        root = project_root(args.root)
        if args.command in ("snapshot", "extend") and not args.task.strip():
            fail("Task description must not be empty")
        if args.command == "inspect":
            report = inspect(root)
        else:
            files, git, excluded = scan(root)
            if args.command in ("verify", "extend"):
                document = load_baseline(args.baseline, root)
                changes = differences(document["files"], files)
                errors = violations(changes, document, files, git)
                if args.command == "verify":
                    print(json.dumps({"status": "BLOCKED" if errors else "PASS", "changes": changes,
                                      "violations": errors, "excluded_directories": excluded,
                                      "baseline_sha256": document["snapshot_sha256"]}, indent=2))
                    return 1 if errors else 0
                if errors:
                    fail("Cannot extend after an unscoped change; preserve evidence and resolve its ownership")
                additions = scope(args, document["files"])
                original = document["scope"]
                # Newly scoped paths must still be unchanged from the first baseline.
                new_paths = (set(additions["allow"]) | set(additions["allow_delete"])) - (
                    set(original["allow"]) | set(original["allow_delete"]))
                if any(files.get(p) != document["files"].get(p) for p in new_paths):
                    fail("Newly authorized path already changed; cannot authorize retroactively")
                if args.allow_git_index and not original["allow_git_index"]:
                    fail("Git staging authorization must be recorded before the initial snapshot")
                if args.allow_git_history and not original["allow_git_history"]:
                    fail("Git history authorization must be recorded before the initial snapshot")
                updated = dict(document)
                updated.pop("snapshot_sha256")
                updated["scope"] = dict(original)
                for key in ("allow", "allow_delete", "allow_sensitive"):
                    updated["scope"][key] = sorted(set(original[key]) | set(additions[key]))
                updated["scope"]["sensitive_reason"] = original["sensitive_reason"] + (
                    "\n" + additions["sensitive_reason"] if additions["sensitive_reason"] else "")
                updated["amendments"] = document.get("amendments", []) + [{
                    "previous_snapshot_sha256": document["snapshot_sha256"],
                    "task": args.task, "new_paths": sorted(new_paths),
                    "at": datetime.now(timezone.utc).isoformat()}]
                output = write_external(root, args.out, updated)
            else:
                if not args.task.strip():
                    fail("Task description must not be empty")
                policy = scope(args, files)
                document = {"schema": SCHEMA, "root": str(root), "task": args.task,
                            "guard_sha256": hash_bytes(Path(__file__).read_bytes()),
                            "created": datetime.now(timezone.utc).isoformat(),
                            "scope": policy, "files": files, "git": git,
                            "excluded_directories": excluded}
                output = write_external(root, args.out, document)
            report = {"status": "SNAPSHOT_CREATED", "path": str(output),
                      "files": len(files), "note": "No project files were modified"}
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
