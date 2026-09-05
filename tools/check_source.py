#!/usr/bin/env python3
"""Static contracts only. Does not compile C#, run the application or certify science."""
import ast
import collections
import hashlib
import json
import pathlib
import re
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def specification(path, name):
    text = (ROOT / path).read_text(encoding="utf-8-sig")
    match = re.search(r"public const string " + re.escape(name) + r"\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*(?:\+\s*)?)+);", text)
    assert match, f"Missing specification in {path}"
    return "".join(json.loads(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', match.group(1)))


def main():
    for path in list(ROOT.rglob("*.csproj")) + list(ROOT.rglob("*.props")) + [ROOT / "app.manifest", ROOT / "MvsAnalyzer.slnx"]:
        tree = ET.parse(path)
        for node in tree.iter("Compile"):
            include = node.attrib.get("Include", "")
            if not include or "*" in include:
                continue
            include = include.replace("$(MSBuildThisFileDirectory)", str(ROOT) + "/").replace("\\", "/")
            target = pathlib.Path(include)
            if not target.is_absolute():
                target = path.parent / target
            assert target.is_file(), f"Missing compile source: {target}"
    for path in ROOT.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    notebooks = list((ROOT / "notebooks").glob("*.ipynb"))
    assert len(notebooks) == 2
    for path in notebooks:
        book = json.loads(path.read_text())
        assert book["nbformat"] == 4 and len(book["cells"]) == 3
        for i, cell in enumerate(book["cells"]):
            assert cell["cell_type"] == "code" and not cell.get("outputs"), f"Invalid or stale notebook cell: {path}:{i}"
            ast.parse("".join(cell["source"]), filename=f"{path}:{i}")
    for path in notebooks:
        assert (ROOT / "notebooks/mvs_colab.py").read_text().replace("from __future__ import annotations\n", "") in "".join(json.loads(path.read_text())["cells"][0]["source"]), "Notebook helper is stale"
    from build_colab_payload import verify_payload
    verify_payload()
    hashes = json.loads((ROOT / "validation/method-hashes.json").read_text())
    actual_formula = digest(specification("Infrastructure/OutputExporter.cs", "FormulaSpecification").encode())
    actual_protocol = digest(specification("Benchmark/BenchmarkProtocol.cs", "Specification").encode())
    assert actual_formula == hashes["formulaSha256"]
    assert actual_protocol == hashes["benchmarkSha256"]
    assert actual_protocol in (ROOT / "Benchmark/BenchmarkProtocol.cs").read_text()
    for path in [ROOT / "MvsAnalyzer.Tests/Program.cs", ROOT / "MvsAnalyzer.Core.Tests/Program.cs"]:
        assert actual_formula in path.read_text(), f"Test hash pin missing: {path}"
    protected = json.loads((ROOT / "validation/protected-assets.json").read_text())
    for name, expected in protected["sha256"].items():
        assert digest((ROOT / name).read_bytes()) == expected, f"Protected image/plugin changed: {name}"
    actual_images = re.findall(r"<img\b[^>]*>", (ROOT / "README.md").read_text(), flags=re.S)
    assert not (collections.Counter(protected["readmeImageTags"]) - collections.Counter(actual_images)), "Original README badges/images changed"
    assert digest((ROOT / "examples/demo_three_groups.csv").read_bytes()) == "290a96afd11b7d041790ca48e03ed547be25bff5646cc935199e25b093c42af5"
    for name in ["MvsAnalyzer.csproj", "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj"]:
        assert ET.parse(ROOT / name).findtext(".//Version") == "1.4.0"
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        assert "PLACEHOLDER" not in path.read_text(), f"Unfinished workflow: {path}"
    assert (ROOT / "MvsAnalyzer.Cli/ScientificCommands.cs").is_file()
    assert (ROOT / "Assets/colab-cli-source.zip").is_file()
    assert not list(ROOT.glob("*.cs")), "Loose root C# sources returned"
    for path in list((ROOT / "Desktop").glob("*.cs")) + [ROOT / "README.md"]:
        assert "\ufffd" not in path.read_text(), f"Damaged display text: {path}"
    assert "MVS_Analyzer_v1.4.0_win-x64.zip" in (ROOT / "RELEASE_NOTES_v1.4.0.md").read_text()
    print(f"Static contracts passed: XML/source paths, Python AST, {len(notebooks)} notebooks, method hashes, {len(protected['sha256'])} protected assets, original badges and demo")
    print("This is not a C# compile, runtime test, Windows render or independent statistical validation.")


if __name__ == "__main__":
    main()
