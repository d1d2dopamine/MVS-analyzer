#!/usr/bin/env python3
"""Validate artifacts after the CLI has run. This script does not run or compile C#."""
import hashlib
import csv
import json
import pathlib
import sys


def strict_json(path):
    def invalid(value):
        raise ValueError(f"Nonstandard JSON literal in {path}: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def check_availability(document, folder):
    """Cross-check independent-unit accounting and availability in JSON/CSV exports."""
    expected = []
    group_order = None
    metrics = set()
    def text(value):
        return "'" + value if value and value[0] in "=+-@\t\r" else value
    for row in document["rows"]:
        assert row["Metric"] not in metrics, "Duplicate result metric"
        metrics.add(row["Metric"])
        assert type(row["Applicable"]) is bool and type(row["CalibrationApplicable"]) is bool
        groups = row["GroupAvailability"]
        assert isinstance(groups, list) and 2 <= len(groups) <= 10
        names = [g["Group"] for g in groups]
        assert len(set(names)) == len(names), "Duplicate group in metric availability"
        if group_order is None:
            group_order = names
        assert names == group_order, "Metric availability changed group order"
        enough = True
        for group in groups:
            retained, usable, excluded = [group[k] for k in ["RetainedEntities", "UsableEntities", "ExcludedEntities"]]
            assert all(type(n) is int and n >= 0 for n in [retained, usable, excluded])
            assert retained == usable + excluded, "Metric entity accounting does not add up"
            reasons = group["ExclusionReasons"]
            assert isinstance(reasons, dict) and all(isinstance(k, str) and k and type(v) is int and v > 0 for k, v in reasons.items())
            assert sum(reasons.values()) == excluded, "Exclusion reasons do not account for every excluded entity"
            enough = enough and usable >= 4
            expected.append({"metric": text(row["Metric"]), "group": text(group["Group"]),
                "retained_entities": str(retained), "usable_entities": str(usable), "excluded_entities": str(excluded),
                "exclusion_reasons": text("|".join(f"{k}:{v}" for k, v in sorted(reasons.items()))),
                "observed_status": row["ObservedStatus"], "calibration_applicable": str(row["CalibrationApplicable"])})
        status = row["ObservedStatus"]
        assert status in {"available", "insufficient_usable_entities", "rank_test_unavailable"}
        assert (status != "insufficient_usable_entities") == enough, "Observed status contradicts the usable entity counts"
        assert row["Applicable"] == (status == "available")
        if row["Applicable"]:
            assert type(row["PValue"]) in (int, float) and 0 <= row["PValue"] <= 1
            assert abs(row["AdjustedP"] - min(1, 12 * row["PValue"])) <= 1e-12, "Correction family changed"
        else:
            assert row["PValue"] is None and row["AdjustedP"] is None and row["Effect"] is None
            assert row["Verdict"] == "not_applicable" and row["EffectIntervalStatus"] == "unavailable"
        if not row["CalibrationApplicable"]:
            assert not row["Candidate"] and not any(row.get("TrackCandidates") or []), "Unavailable calibration created a candidate"
    path = folder / "metric_availability.csv"
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames == ["metric", "group", "retained_entities", "usable_entities", "excluded_entities", "exclusion_reasons", "observed_status", "calibration_applicable"]
        actual = list(reader)
    assert actual == expected, "Availability CSV and JSON disagree"


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    documents = list(root.rglob("*.json"))
    assert documents, "No JSON artifacts were produced"
    states = 0
    manifests = 0
    for path in documents:
        document = strict_json(path)
        if path.name == "results.json":
            check_availability(document, path.parent)
        if path.name == "calibration_state.json":
            states += 1
            assert document["SchemaVersion"] == 2
            assert document["AppVersion"] == "1.4.0" and document["EngineVersion"] == "1.6.2"
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
