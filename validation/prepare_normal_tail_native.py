#!/usr/bin/env python3
"""Prepare isolated Round32 A/B copies; never execute numerical harness modes.

Offline build is opt-in. The required official nupkg must already be available.
Original production trees and previously generated runs are never overwritten.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

PACKAGE_SHA256 = "44724254ce8ec6ab8917b9f931b7bfa0d6ee7016e481ee942dc6c07333a0995a"
ORIGINAL_RETURN = b"        return Math.Clamp(2 * (1 - NormalCdf(z)), 0, 1);"
CANDIDATE_RETURN = b"        return Math.Clamp(MathNet.Numerics.SpecialFunctions.Erfc(z / Math.Sqrt(2)), 0, 1);"
ANALYSIS = "Core/AnalysisEngine.cs"
CORE_PROJECT = "MvsAnalyzer.Core/MvsAnalyzer.Core.csproj"
BASELINE_PINS = {
    ANALYSIS: "bc4caa7600034781861784cedaf64cc19d22ecc5eb26841ada291c0c6d66bd05",
    "Core/ScientificInfrastructure.cs": "7e2947c272e7f3aaecade2829367cf0cdfd3206c67006f6c163b826da3d60d1a",
    "MvsAnalyzer.Core/AssemblyInfo.cs": "76fd41a5433081215c3e89869931a0b9e098aef1a8abcb005c29824cb360a5fd",
    "validation/rank-test-fixtures-v1.json": "41cdf8528ae2af97da7a25273c5a5bd156270b63734923a40ae774a49053b781",
    "Infrastructure/OutputExporter.cs": "aeb34b25ecfbb0427aeb6adde2e1762920e574f09512821c13380d9fd026f021",
}
IGNORED_DIRECTORIES = {".git", "bin", "obj", "__pycache__", ".venv", "venv", "node_modules"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def source_files(root: Path) -> dict[str, str]:
    result = {}
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in IGNORED_DIRECTORIES)
        for name in directories:
            if (Path(current) / name).is_symlink():
                raise ValueError("Symlink source directories require separate review.")
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Unsupported source entry: {path}")
            result[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return dict(sorted(result.items()))


def candidate_source(original: bytes) -> bytes:
    if original.count(ORIGINAL_RETURN) != 1:
        raise ValueError("Expected exactly one unchanged MannWhitneyP tail expression.")
    before, after = original.split(ORIGINAL_RETURN)
    # Scope proof is stronger than a broad string replacement: exactly one
    # occurrence must lie after MW and before private NormalCdf.
    mw_start = original.find(b"internal static double MannWhitneyP(double[] a, double[] b)")
    cdf_start = original.find(b"private static double NormalCdf(double z)")
    if mw_start < 0 or not mw_start < len(before) < cdf_start:
        raise ValueError("Tail expression is outside the expected MW method boundary.")
    changed = before + CANDIDATE_RETURN + after
    if changed.replace(CANDIDATE_RETURN, ORIGINAL_RETURN) != original:
        raise ValueError("Single-expression substitution proof failed.")
    return changed


def candidate_project(original: bytes) -> bytes:
    if original.count(b"</Project>") != 1 or b"PackageReference" in original:
        raise ValueError("Unexpected existing Core project dependency or closing tag.")
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    addition = newline.join([
        b"  <!-- Isolated Round32 experiment only; never copied to production. -->",
        b"  <ItemGroup>",
        b'    <PackageReference Include="MathNet.Numerics" Version="[5.0.0]" />',
        b"  </ItemGroup>", b"",
    ])
    changed = original.replace(b"</Project>", addition + b"</Project>")
    if changed.replace(addition + b"</Project>", b"</Project>") != original:
        raise ValueError("Temporary package-reference substitution proof failed.")
    return changed


def assert_copy_changes(original: dict[str, str], actual: dict[str, str], allowed: set[str]) -> None:
    if original.keys() != actual.keys():
        raise ValueError("Copy source paths differ from original source paths.")
    differences = {name for name in original if original[name] != actual[name]}
    if differences != allowed:
        raise ValueError(f"Unexpected source differences: {sorted(differences)}; expected {sorted(allowed)}")


def package_info(path: Path) -> dict:
    data = path.read_bytes()
    if digest(data) != PACKAGE_SHA256:
        raise ValueError("Math.NET official package byte hash differs from frozen download.")
    with zipfile.ZipFile(path) as archive:
        nuspec = ET.fromstring(archive.read("MathNet.Numerics.nuspec"))
        ns = {"n": "http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"}
        metadata = nuspec.find("n:metadata", ns)
        if metadata is None or metadata.findtext("n:id", namespaces=ns) != "MathNet.Numerics" or metadata.findtext("n:version", namespaces=ns) != "5.0.0":
            raise ValueError("Unexpected package identity.")
        license_node = metadata.find("n:license", ns)
        if license_node is None or license_node.text != "MIT" or license_node.get("type") != "expression":
            raise ValueError("Unexpected package license metadata.")
        dll = archive.read("lib/net6.0/MathNet.Numerics.dll")
    return {"id": "MathNet.Numerics", "version": "5.0.0", "license": "MIT", "bytes": len(data), "sha256": digest(data), "sha512": hashlib.sha512(data).hexdigest(), "asset": "lib/net6.0/MathNet.Numerics.dll", "assetSha256": digest(dll), "officialUrl": "https://api.nuget.org/v3-flatcontainer/mathnet.numerics/5.0.0/mathnet.numerics.5.0.0.nupkg"}


def inventory(root: Path) -> list[dict]:
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path.read_bytes())} for path in sorted(root.rglob("*")) if path.is_file()]


def run_logged(command: list[str], cwd: Path, destination: Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    destination.write_text("COMMAND " + json.dumps(command) + "\n" + result.stdout + "\nSTDERR\n" + result.stderr + f"\nEXIT {result.returncode}\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Build command failed; retained log: {destination}")


def prepare(source: Path, output: Path, templates: Path, package: Path, build: bool, dotnet: str) -> dict:
    source = source.resolve(strict=True)
    output = output.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("Output must be separate from the immutable production source tree.")
    if output.exists():
        raise FileExistsError("Output already exists; preserve it and choose a new run directory.")
    original_files = source_files(source)
    for name, expected in BASELINE_PINS.items():
        if original_files.get(name) != expected:
            raise ValueError(f"Delivered Round31 critical source pin mismatch: {name}")
    package_record = package_info(package)
    template_files = {name: (templates / name).read_bytes() for name in ("Program.cs", "NormalTailHarness.csproj")}
    tree_hash = digest(canonical(original_files))
    manifest = {
        "schema": "mvs-normal-tail-native-build/v1", "experimental": True,
        "sourceRoot": str(source), "sourceTreeSha256": tree_hash, "sourceFiles": original_files,
        "ignoredGeneratedDirectories": sorted(IGNORED_DIRECTORIES), "criticalSourcePins": BASELINE_PINS,
        "package": package_record, "templateHashes": {name: digest(data) for name, data in template_files.items()},
        "preparationScriptSha256": digest(Path(__file__).read_bytes()),
        "replacement": {"path": ANALYSIS, "before": ORIGINAL_RETURN.decode(), "after": CANDIDATE_RETURN.decode(), "count": 1},
        "publish": {"configuration": "Release", "runtimeIdentifier": "linux-x64", "frameworkDependent": True, "selfContained": False, "singleFile": False, "trimmed": False, "readyToRun": False, "nativeProvider": False},
        "sdkRequired": "8.0.425", "runtimeRequired": "8.0.31", "numericModesExecutedByPreparation": False,
    }
    output.mkdir(parents=True)
    write_json(output / "build-manifest.json", manifest)
    manifest_hash = digest((output / "build-manifest.json").read_bytes())
    (output / "packages").mkdir()
    shutil.copyfile(package, output / "packages" / "mathnet.numerics.5.0.0.nupkg")
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear/><add key="frozen-local" value="packages"/></packageSources></configuration>\n', encoding="utf-8")
    variants = {}
    for variant in ("A", "B"):
        base = output / variant
        copied = base / "source"
        copied.mkdir(parents=True)
        for name in original_files:
            destination = copied / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, destination)
        if variant == "B":
            (copied / ANALYSIS).write_bytes(candidate_source((source / ANALYSIS).read_bytes()))
            (copied / CORE_PROJECT).write_bytes(candidate_project((source / CORE_PROJECT).read_bytes()))
        changes = {ANALYSIS, CORE_PROJECT} if variant == "B" else set()
        copied_hashes = source_files(copied)
        assert_copy_changes(original_files, copied_hashes, changes)
        harness = base / "harness"
        harness.mkdir()
        for name, data in template_files.items():
            (harness / name).write_bytes(data)
        identity = {"Variant": variant, "SourceTreeSha256": tree_hash, "SourceAnalysisSha256": original_files[ANALYSIS], "VariantAnalysisSha256": copied_hashes[ANALYSIS], "ProgramSourceSha256": digest(template_files["Program.cs"]), "BuildManifestSha256": manifest_hash, "MathNetPackageSha256": PACKAGE_SHA256}
        (harness / "BuildIdentity.g.cs").write_text("namespace MvsNormalTailExperiment;\ninternal static class BuildIdentity\n{\n" + "".join(f"    public static readonly string {key} = {json.dumps(value)};\n" for key, value in identity.items()) + "}\n", encoding="utf-8")
        variants[variant] = {"sourceAnalysisSha256": copied_hashes[ANALYSIS], "sourceProjectSha256": copied_hashes[CORE_PROJECT], "changedPaths": sorted(changes), "harnessDirectory": str(harness), "publishDirectory": str(base / "publish")}
    diff = "".join(difflib.unified_diff((source / ANALYSIS).read_text().splitlines(True), (output / "B" / "source" / ANALYSIS).read_text().splitlines(True), fromfile="delivered31/Core/AnalysisEngine.cs", tofile="EXPERIMENTAL-B/Core/AnalysisEngine.cs"))
    (output / "candidate-expression.diff").write_text(diff, encoding="utf-8")
    project_diff = "".join(difflib.unified_diff((source / CORE_PROJECT).read_text().splitlines(True), (output / "B" / "source" / CORE_PROJECT).read_text().splitlines(True), fromfile="delivered31/" + CORE_PROJECT, tofile="EXPERIMENTAL-B/" + CORE_PROJECT))
    (output / "candidate-project.diff").write_text(project_diff, encoding="utf-8")
    write_json(output / "variant-copy-verification.json", {"schema": "mvs-normal-tail-copy-verification/v1", "sourceTreeSha256": tree_hash, "buildManifestSha256": manifest_hash, "variants": variants})
    if build:
        env = dict(os.environ)
        env["NUGET_PACKAGES"] = str(output / "nuget-cache")
        sdk = subprocess.check_output([dotnet, "--version"], env=env, text=True).strip()
        if sdk != "8.0.425":
            raise ValueError(f"Unexpected SDK {sdk}; required 8.0.425.")
        runtimes = subprocess.check_output([dotnet, "--list-runtimes"], env=env, text=True)
        if not any(line.startswith("Microsoft.NETCore.App 8.0.31 ") for line in runtimes.splitlines()):
            raise ValueError("Required .NET runtime 8.0.31 is unavailable.")
        (output / "dotnet-info.txt").write_text(subprocess.check_output([dotnet, "--info"], env=env, text=True), encoding="utf-8")
        for variant in ("A", "B"):
            base = output / variant
            project = base / "harness" / "NormalTailHarness.csproj"
            common = [f"-p:MvsTailVariant={variant}", "-p:NuGetAudit=false", "-p:RestoreIgnoreFailedSources=false"]
            run_logged([dotnet, "restore", str(project), "--configfile", str(output / "NuGet.Config"), *common], output, base / "restore.log", env)
            run_logged([dotnet, "publish", str(project), "--no-restore", "-c", "Release", "-r", "linux-x64", "--self-contained", "false", "-o", str(base / "publish"), *common], output, base / "publish.log", env)
            files = inventory(base / "publish")
            write_json(base / "publish-inventory.json", {"variant": variant, "files": files, "totalBytes": sum(item["bytes"] for item in files)})
            expected = {ANALYSIS, CORE_PROJECT} if variant == "B" else set()
            assert_copy_changes(original_files, source_files(base / "source"), expected)
        if not (output / "B" / "publish" / "MathNet.Numerics.dll").is_file() or (output / "A" / "publish" / "MathNet.Numerics.dll").exists():
            raise ValueError("Unexpected package presence/absence in published variants.")
        if digest((output / "B" / "publish" / "MathNet.Numerics.dll").read_bytes()) != package_record["assetSha256"]:
            raise ValueError("Published candidate uses an unexpected Math.NET asset.")
    if source_files(source) != original_files:
        raise ValueError("Original source tree changed during preparation; do not continue.")
    return {"output": str(output), "buildManifestSha256": manifest_hash, "variants": variants, "built": build, "numericModesExecuted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--templates", type=Path, default=Path(__file__).parent / "normal_tail_harness")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.out, args.templates, args.package, args.build, args.dotnet), indent=2))


if __name__ == "__main__":
    main()
