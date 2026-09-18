#!/usr/bin/env python3
"""Verify the paper benchmark artifact before it is used in a manuscript."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

EXPECTED = {
    "protocolVersion": "MVS-BENCH-1.2.0",
    "protocolHash": "b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268",
    "profile": "full",
    "seed": 20260904,
    "appVersion": "1.4.0",
    "engineVersion": "1.6.0",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit("paper benchmark verification failed: " + message)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifests = list(root.rglob("benchmark_manifest.json"))
    if len(manifests) != 1:
        fail(f"expected exactly one benchmark_manifest.json, found {len(manifests)}")
    manifest_path = manifests[0]
    folder = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("kind") != "mvs-benchmark":
        fail("manifest kind is not mvs-benchmark")
    for key, value in EXPECTED.items():
        if manifest.get(key) != value:
            fail(f"{key} is {manifest.get(key)!r}, expected {value!r}")
    if manifest.get("protocolUnchanged") is not True:
        fail("frozen protocol hash is not marked unchanged")
    if manifest.get("overall") not in {"go", "conditional", "no-go"}:
        fail(f"unexpected scientific verdict {manifest.get('overall')!r}")

    sums_path = folder / "SHA256SUMS.txt"
    if not sums_path.is_file():
        fail("SHA256SUMS.txt is missing")
    checked = set()
    for raw in sums_path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        try:
            digest, name = raw.split(maxsplit=1)
        except ValueError:
            fail("malformed SHA256SUMS.txt line")
        name = name.lstrip(" *")
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file():
            fail(f"checksum target is missing or unsafe: {name}")
        if sha256(target) != digest.lower():
            fail(f"checksum mismatch: {name}")
        checked.add(name.replace("\\", "/"))

    for name in manifest.get("files", []):
        if name not in checked:
            fail(f"manifest file is not covered by checksums: {name}")

    resume = folder / "backup_resume.json"
    if resume.is_file():
        provenance = json.loads(resume.read_text(encoding="utf-8-sig"))
        environments = provenance.get("environments", [])
        if len(set(environments)) > 1:
            fail("benchmark resumed across different arithmetic environments")

    print("paper benchmark artifact verified")
    print(f"  result:   {manifest['overall']}")
    print(f"  protocol: {manifest['protocolVersion']} / {manifest['protocolHash'][:16]}...")
    print(f"  app:      {manifest['appVersion']}  engine: {manifest['engineVersion']}")
    print(f"  profile:  {manifest['profile']}  seed: {manifest['seed']}")
    print(f"  folder:   {folder}")


if __name__ == "__main__":
    main()
