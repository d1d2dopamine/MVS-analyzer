#!/usr/bin/env python3
"""Validate artifacts after the CLI has run. This script does not run or compile C#."""
import hashlib
import json
import pathlib
import sys


def strict_json(path):
    def invalid(value):
        raise ValueError(f"Nonstandard JSON literal in {path}: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    documents = list(root.rglob("*.json"))
    assert documents, "No JSON artifacts were produced"
    states = 0
    manifests = 0
    for path in documents:
        document = strict_json(path)
        if path.name == "calibration_state.json":
            states += 1
            assert document["SchemaVersion"] == 2
            assert document["AppVersion"] == "1.4.0" and document["EngineVersion"] == "1.6.0"
            assert len(document["PayloadHash"]) == 64 and len(document["SettingsHash"]) == 64
            assert len(document["Rows"]) == 12
            assert "heterogeneity" in document["Tracks"]
            assert document["Processing"]["MinMeasurements"] >= 2
            if document["Repetitions"] < 500:
                assert all(row["Mde"] is None for row in document["Rows"]), "Small budget invented an MDE"
        if path.name == "run_manifest.json":
            manifests += 1
            names = []
            for record in document.get("files", []):
                name = record["FileName"]
                assert pathlib.PurePath(name).name == name and "\\" not in name
                file = path.parent / name
                assert file.is_file(), file
                assert hashlib.sha256(file.read_bytes()).hexdigest() == record["sha256"], file
                names.append(name)
            if document.get("decision"):
                assert "calibration_state.json" in names, "Calibration state was omitted from the manifest"
                assert document["decision"]["familySize"] == 12
    assert states and manifests, "The calibrate/analyze pipeline is incomplete"
    print(f"Validated {len(documents)} JSON documents, {states} states and {manifests} manifests")


if __name__ == "__main__":
    main()
