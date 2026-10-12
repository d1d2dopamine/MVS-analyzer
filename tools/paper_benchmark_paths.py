#!/usr/bin/env python3
"""Read-only path/configuration checks for the bounded paper chunk runner."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import verify_paper_benchmark as verifier


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plain(value):
    require(not any(ord(c) < 32 or ord(c) == 127 for c in str(value)),
            f"control characters are not allowed in paths: {str(value)!r}")


def canonical(value):
    plain(value)
    require(bool(value), "an output path must not be empty")
    path = Path(value).absolute()
    # Inspect the original components before resolve() collapses any '..'.
    for part in reversed((path, *path.parents)):
        require(not part.is_symlink(), f"symlink path is not allowed: {part}")
    return path.resolve()


def positive(value, label):
    require(re.fullmatch(r"[1-9][0-9]{0,9}", value) is not None
            and int(value) <= 2147483647,
            f"{label} must be a positive decimal integer at most 2147483647")


def scan(root):
    """Reject ambiguous names and links before discovering or copying evidence."""
    files = []
    def fail(error):
        raise error
    for parent, directories, names in os.walk(root, followlinks=False, onerror=fail):
        for name in sorted(directories + names):
            path = Path(parent) / name
            plain(path)
            require(not path.is_symlink(), f"symlink in evidence directory: {path}")
            require(path.is_dir() or path.is_file(), f"non-regular evidence entry: {path}")
            if path.is_file():
                files.append(path)
    return files


def result_folder(root, files):
    manifests = [p for p in files if p.name == "benchmark_manifest.json"]
    require(len(manifests) <= 1,
            f"expected at most one benchmark_manifest.json under {root}, found {len(manifests)}")
    if manifests:
        folder, _ = verifier.validate(root)
        return str(folder)
    return ""


def preflight(args):
    for value, label in ((args.chunk, "chunk"), (args.threads, "MVS_BENCH_THREADS"),
                         (args.seconds, "MVS_BENCH_CHUNK_SECONDS")):
        positive(value, label)
    require(args.profile == "full", "historical paper benchmark requires MVS_BENCH_PROFILE=full")
    require(args.seed == "20260904", "historical paper benchmark requires MVS_BENCH_SEED=20260904")
    state, work = canonical(args.state), canonical(args.work)
    incoming = canonical(args.incoming) if args.incoming else None
    paths = {"state": state, "work": work}
    if incoming is not None:
        require(incoming.is_dir(), f"incoming directory does not exist: {incoming}")
        paths["incoming"] = incoming
    for name, path in paths.items():
        for other, target in paths.items():
            if name < other:
                require(not (path.is_relative_to(target) or target.is_relative_to(path)),
                        f"{name} and {other} must be disjoint (including ancestors): {path}, {target}")
    for name, path in (("state", state), ("work", work)):
        for protected in (Path.cwd().resolve(), Path(__file__).resolve().parents[1]):
            require(not protected.is_relative_to(path),
                    f"unsafe {name} destination is the working/source directory or an ancestor: {path}")
        require(not path.exists() or path.is_dir(), f"{name} destination is not a directory: {path}")
        require(not path.exists() or not any(path.iterdir()),
                f"{name} destination is nonempty; keep it and choose a new directory: {path}")
    result, archive = "", ""
    if incoming is not None:
        files = scan(incoming)
        result = result_folder(incoming, files)
        archives = [p for p in files if p.name == "MVS_Backups.zip"]
        require(len(archives) <= 1, f"multiple MVS_Backups.zip archives under {incoming}; choose one input state")
        archive = str(archives[0]) if archives else ""
        require(bool(result or archive), "incoming contains neither a verified result nor MVS_Backups.zip; refusing to restart")
        for suffix in ("txt", "log"):
            require(not (incoming / f"chunk-{args.chunk}.{suffix}").exists(),
                    f"incoming already contains chunk-{args.chunk}.{suffix}; choose the next chunk number")
    # Paths cannot contain line breaks, and the shell never evaluates these values.
    print("\n".join((str(incoming) if incoming else "", str(state), str(work), result, archive)))


def provenance(args):
    require(re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", args.commit) is not None,
            "cannot determine a full Git commit identity; use a verified source checkout")
    if not args.incoming:
        return
    for path in sorted(Path(args.incoming).glob("chunk-*.txt")):
        require(re.fullmatch(r"chunk-[1-9][0-9]*\.txt", path.name) is not None,
                f"malformed chunk provenance filename: {path.name}")
        fields = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            require(bool(separator) and key not in fields, f"malformed/duplicate provenance field: {path}")
            fields[key] = value
        require(fields.get("commit") == args.commit,
                f"incoming provenance commit mismatch or missing commit in {path}; current commit is {args.commit}")
        for key, expected in (("profile", "full"), ("seed", "20260904")):
            require(key not in fields or fields[key] == expected, f"incoming provenance {key} mismatch: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    before = commands.add_parser("preflight")
    for name in ("chunk", "incoming", "state", "work", "profile", "seed", "threads", "seconds"):
        before.add_argument("--" + name, required=True)
    prior = commands.add_parser("provenance")
    prior.add_argument("--incoming", required=True)
    prior.add_argument("--commit", required=True)
    result = commands.add_parser("result")
    result.add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            preflight(args)
        elif args.command == "provenance":
            provenance(args)
        else:
            root = canonical(str(args.root))
            require(root.is_dir(), f"result directory does not exist: {root}")
            print(result_folder(root, scan(root)))
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, verifier.csv.Error,
            RecursionError, OverflowError) as error:
        print(f"paper chunk safety check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
