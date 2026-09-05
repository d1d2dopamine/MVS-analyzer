#!/usr/bin/env python3
"""Create/check the exact portable CLI source carried by the desktop. Never runs .NET."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Assets/colab-cli-source.zip"


def source_files():
    files = {ROOT / "SharedSources.props", ROOT / "LICENSE", ROOT / "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj"}
    for project in (ROOT / "SharedSources.props", ROOT / "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj"):
        for item in ET.parse(project).iter("Compile"):
            include = item.attrib.get("Include")
            if not include:
                continue
            if "*" in include:
                raise ValueError("The portable source registry must stay explicit")
            include = include.replace("$(MSBuildThisFileDirectory)", str(ROOT) + "/").replace("\\", "/")
            path = Path(include)
            if not path.is_absolute():
                path = project.parent / path
            path = path.resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                raise ValueError("Missing/unsafe source reference: " + str(path))
            files.add(path)
    return {p.relative_to(ROOT.resolve()).as_posix(): p.read_bytes() for p in sorted(files)}


def payload_bytes():
    files = source_files()
    metadata = {"appVersion": "1.4.0", "engineVersion": "1.6.0", "revision": "ui-colab-2", "kind": "portable-cli-source-not-a-binary",
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["SOURCE_PAYLOAD.json"] = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 5, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    return memory.getvalue()


def verify_payload():
    expected = payload_bytes()
    if not TARGET.is_file() or TARGET.read_bytes() != expected:
        raise AssertionError("Embedded Colab source is stale/missing. Run python tools/build_colab_payload.py and commit the updated asset.")
    with zipfile.ZipFile(io.BytesIO(expected)) as archive:
        assert archive.testzip() is None
    return hashlib.sha256(expected).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        TARGET.parent.mkdir(exist_ok=True)
        TARGET.write_bytes(payload_bytes())
    digest = verify_payload()
    print("Colab CLI source payload verified:", digest)


if __name__ == "__main__":
    main()
