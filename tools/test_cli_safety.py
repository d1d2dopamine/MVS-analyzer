#!/usr/bin/env python3
"""Synthetic, real-CLI input preservation and machine-error regressions.

Run with --cli /path/to/mvs --artifacts /path/to/evidence. Each invocation creates
a new retained child directory; existing evidence is never replaced. This is an
I/O safety smoke suite, not a scientific/numerical benchmark. Calibration uses
48 rows, eight independent subjects and 100 repetitions. Scientific rejection
probes carry a deliberately invalid late numeric option: if preflight regresses,
that fuse prevents variance/bootstrap/model computation, and the test fails on
the wrong error. No fake executable or copied numerical baseline is used.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
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
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "mvs-cli-result/v1"
FUSE = "preflight-must-reject-before-computation"
OUTPUTS = {
    "calibrate": ("calibration.csv", "calibration_tracks.csv",
                  "calibration_recommendations.csv", "calibration_state.json"),
    "variance": ("variance_report.json", "variance_components.csv",
                 "variance_tests.csv", "run_manifest.json"),
    "melsm": ("melsm_report.json", "melsm_parameters.csv",
              "melsm_random_effects.csv", "run_manifest.json"),
    "estimation": ("estimation_report.json", "estimation_performance.csv",
                   "estimation_draws.csv", "run_manifest.json"),
}


def strict_json(text: str):
    def constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=constant, object_pairs_hook=pairs)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_csv() -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["entity", "group", "value", "sequence", "unit"])
    for group_index, group in enumerate(("A", "B")):
        for entity in range(4):
            for sequence in range(1, 7):
                writer.writerow([f"{group}{entity}", group,
                                 f"{10 + entity + group_index * 3 + sequence * .1:.1f}",
                                 sequence, "synthetic-unit"])
    return stream.getvalue().encode("utf-8")


def snapshot(root: Path) -> dict:
    """Compare actual bytes and link text, without following directory links."""
    result = {}

    def visit(path: Path):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            result[relative] = ("symlink", os.readlink(path))
            if path.is_file():
                result[relative + " [referent bytes]"] = ("file", path.read_bytes())
        elif stat.S_ISDIR(mode):
            result[relative] = ("directory",)
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(mode):
            result[relative] = ("file", path.read_bytes())
        else:
            result[relative] = ("special", stat.S_IFMT(mode))

    visit(root)
    return result


def inventory(value: dict) -> dict:
    return {name: [entry[0], sha(entry[1]), len(entry[1])]
            if entry[0] == "file" else list(entry) for name, entry in value.items()}


def link(source: Path, target: Path, *, directory: bool = False, hard: bool = False):
    try:
        if hard:
            os.link(source, target)
        else:
            target.symlink_to(source, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        raise unittest.SkipTest(f"{'Hardlinks' if hard else 'Symlinks'} unavailable: {error}")


class Harness:
    def __init__(self, cli: Path, artifacts: Path, timeout: float):
        artifacts.mkdir(parents=True, exist_ok=True)
        self.run = Path(tempfile.mkdtemp(prefix="cli-safety-", dir=artifacts)).resolve()
        self.cli = cli
        self.timeout = timeout
        self.records = []
        self.checks = 0
        self.calls = 0
        self.python_calls = 0
        self.state = None
        self.baseline = None
        self.data = synthetic_csv()
        self.valid = self.run / "synthetic.csv"
        self.valid.write_bytes(self.data)
        (self.run / "cases").mkdir()
        (self.run / "captures").mkdir()
        self.env = dict(os.environ, XDG_DATA_HOME=str(self.run / "runtime" / "data"),
                        XDG_CONFIG_HOME=str(self.run / "runtime" / "config"),
                        MVS_DISABLE_BACKUPS="1", MVS_BACKUP_DIR=str(self.run / "runtime" / "backups"),
                        PYTHONDONTWRITEBYTECODE="1")

    def check(self, condition, message):
        self.checks += 1
        if not condition:
            raise AssertionError(message)

    def case(self, name):
        path = self.run / "cases" / name
        path.mkdir()
        (path / "unrelated.bin").write_bytes(b"unrelated synthetic bytes\x00\xff\n")
        return path

    def invoke(self, name, arguments, *, machine=True, expected=1, error_type=None):
        self.calls += 1
        args = [str(value) for value in arguments]
        record = {"name": name, "args": args}
        self.records.append(record)
        started = time.monotonic()
        try:
            process = subprocess.run([str(self.cli), *args], cwd=self.run, env=self.env,
                                     capture_output=True, text=True, encoding="utf-8",
                                     timeout=self.timeout, check=False)
            record.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
        except subprocess.TimeoutExpired as error:
            record.update(timeout=True, stdout=str(error.stdout), stderr=str(error.stderr))
            raise AssertionError(f"{name}: CLI exceeded {self.timeout}s; possible preflight regression") from error
        finally:
            record["seconds"] = round(time.monotonic() - started, 4)
            self.capture(record)
        self.check(process.returncode == expected,
                   f"{name}: expected exit {expected}, got {process.returncode}; stderr={process.stderr!r}")
        self.check("Unhandled exception" not in process.stderr, f"{name}: unhandled exception")
        if not machine:
            return process
        payload = strict_json(process.stdout)
        record["payload"] = payload
        self.capture(record)
        self.check(isinstance(payload, dict), f"{name}: stdout must be exactly one JSON object")
        self.check(payload.get("schemaVersion") == SCHEMA, f"{name}: wrong machine schema")
        self.check(payload.get("exitCode") == expected, f"{name}: JSON/process exit disagreement")
        self.check(payload.get("status") == {0: "completed", 1: "error", 2: "diagnostic"}[expected],
                   f"{name}: wrong status")
        command = args[0].lower() if args and not args[0].startswith("-") else ""
        self.check(payload.get("command") == command, f"{name}: wrong command identity")
        if expected == 1:
            error = payload.get("error")
            self.check(isinstance(error, dict) and bool(error.get("message")), f"{name}: missing structured error")
            if error_type:
                self.check(error.get("type") == error_type,
                           f"{name}: expected {error_type}, got {error!r}")
            self.check(payload.get("outputDirectory") is None and payload.get("artifacts") == [],
                       f"{name}: preflight error claimed generated artifacts")
        return payload

    def capture(self, record):
        (self.run / "captures" / (record["name"] + ".json")).write_text(
            json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def arguments(self, command, source, output, *, overwrite=False, extra=()):
        args = [command, "--out", output, "--json", "--quiet"]
        if source is not None:
            args += ["--in", source]
        if command == "calibrate":
            args += ["--repetitions", "100", "--seed", "71"]
        else:
            # Parsed after output preflight. Never launch the costly workflows.
            fuse_option = {"variance": "--bootstrap", "melsm": "--max-iterations",
                           "estimation": "--repetitions"}[command]
            args += [fuse_option + "=" + FUSE]
        if overwrite:
            args.append("--overwrite")
        return [*args, *extra]

    def rejected_unchanged(self, name, root, arguments):
        before = snapshot(root)
        try:
            payload = self.invoke(name, arguments, error_type="InvalidDataException")
            self.check(FUSE not in payload["error"]["message"], f"{name}: late option evaluated before preflight")
        finally:
            after = snapshot(root)
            (self.run / "captures" / (name + "-preservation.json")).write_text(
                json.dumps({"before": inventory(before), "after": inventory(after)}, indent=2) + "\n",
                encoding="utf-8")
            self.check(before == after, f"{name}: files, directories, links, or exact input bytes changed")
            self.check(self.valid.read_bytes() == self.data, f"{name}: shared source bytes changed")

    def require_state(self):
        if self.state is None:
            raise unittest.SkipTest("Valid calibration setup failed; cannot fabricate a compatible job/state")
        return self.state

    def job(self, dataset="synthetic.csv"):
        state = self.require_state()
        keys = ("DatasetHash", "Repetitions", "Seed", "Effect", "Scenario", "OutlierRate",
                "MissingRate", "Alpha", "EquivalenceMargin", "SplitCalibration", "AppVersion",
                "EngineVersion", "FormulaVersion", "FormulaHash", "CreatedUtc", "Processing", "SchemaVersion")
        job = {key: state[key] for key in keys}
        job["Processing"] = dict(job["Processing"])
        job.update({key: state["Processing"][key] for key in ("MinValue", "MaxValue", "MinMeasurements")})
        job.update(Dataset=dataset, Kind="calibrate", Project="Synthetic CLI regression",
                   Description="Disposable fixture only", InterfaceMode="simple", Language="en")
        return job

    @contextlib.contextmanager
    def python_environment(self):
        old_env, old_cwd = dict(os.environ), Path.cwd()
        try:
            os.environ.update(self.env)
            os.chdir(self.run)
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def profile():
    return {"Id": "synthetic-cli-safety", "Name": "Synthetic", "Plugin": "synthetic",
            "Delimiter": ",", "DecimalComma": False, "Columns": {}}


def check_state(h, name, output, seed, jobfile=None):
    state = strict_json((output / "calibration_state.json").read_text(encoding="utf-8"))
    h.check(state["DatasetHash"].lower() == sha(h.data), f"{name}: state lost source byte identity")
    h.check(state["Seed"] == seed and state["Repetitions"] == 100, f"{name}: state settings mismatch")
    before = snapshot(output)
    args = ["state-check", "--json", "--in", h.valid, "--calibration", output]
    if jobfile is not None:
        args += ["--job", jobfile]
    h.invoke(name + "-state-check", args, expected=0)
    h.check(snapshot(output) == before, f"{name}: read-only state-check changed files")
    return state


def successful_calibration(h):
    name = "valid-calibration"
    root = h.case(name)
    output = root / "output"
    output.mkdir()
    sentinel = output / "unrelated.txt"
    sentinel.write_bytes(b"Preserve unrelated output-folder content.\n")
    payload = h.invoke(name, h.arguments("calibrate", h.valid, output), expected=0)
    for filename in OUTPUTS["calibrate"]:
        h.check((output / filename).is_file(), f"{name}: missing {filename}")
    h.check(sentinel.read_bytes() == b"Preserve unrelated output-folder content.\n", f"{name}: unrelated file changed")
    h.check(h.valid.read_bytes() == h.data, f"{name}: source changed")
    h.check(Path(payload["outputDirectory"]).resolve() == output.resolve(), f"{name}: incorrect output path")
    artifacts = {Path(item["path"]).name: item for item in payload["artifacts"]}
    for filename in OUTPUTS["calibrate"]:
        content = (output / filename).read_bytes()
        h.check(filename in artifacts, f"{name}: missing artifact metadata for {filename}")
        h.check(artifacts[filename]["sha256"].lower() == sha(content), f"{name}: wrong artifact hash for {filename}")
        h.check(artifacts[filename]["sizeBytes"] == len(content), f"{name}: wrong artifact size for {filename}")
    h.state = check_state(h, name, output, 71)
    h.baseline = output


def successful_overwrite(h):
    h.require_state()
    name = "valid-overwrite"
    root = h.case(name)
    output = root / "output"
    shutil.copytree(h.baseline, output)
    old_state = (output / "calibration_state.json").read_bytes()
    args = h.arguments("calibrate", h.valid, output, overwrite=True)
    args[args.index("--seed") + 1] = "72"
    h.invoke(name, args, expected=0)
    check_state(h, name, output, 72)
    h.check((output / "calibration_state.json").read_bytes() != old_state, "Overwrite did not replace the old state")
    h.check((output / "unrelated.txt").read_bytes() == (h.baseline / "unrelated.txt").read_bytes(), "Overwrite changed unrelated file")
    h.check(h.valid.read_bytes() == h.data, "Overwrite changed source bytes")


def input_collision(h, command, filename, overwrite, relative=False, padded=False):
    name = f"{command}-input-{filename}-overwrite-{overwrite}" + ("-relative" if relative else "")
    name += "-padded" if padded else ""
    root = h.case(name)
    output = root / "output"
    output.mkdir()
    source = output / filename
    source.write_bytes(h.data)
    argument = source
    if relative:
        (output / "nested").mkdir()
        argument = output.relative_to(h.run) / "nested" / ".." / filename
    if padded:
        argument = "  " + str(argument) + "  "
    h.rejected_unchanged(name, root, h.arguments(command, argument, output, overwrite=overwrite))


def existing_calibration_target(h, filename):
    name = "existing-" + filename
    root = h.case(name)
    output = root / "output"
    output.mkdir()
    (output / filename).write_bytes(b"Existing synthetic file must survive without overwrite.\n")
    h.rejected_unchanged(name, root, h.arguments("calibrate", h.valid, output))


def obstructed_target(h, command, filename, overwrite):
    name = f"{command}-directory-{filename}-overwrite-{overwrite}"
    root = h.case(name)
    output = root / "output"
    if overwrite and command == "calibrate":
        h.require_state()
        shutil.copytree(h.baseline, output)
        # Only replace disposable copies, never the native baseline or source.
        (output / filename).unlink()
    else:
        output.mkdir()
        if overwrite:
            for target in OUTPUTS[command]:
                if target != filename:
                    (output / target).write_bytes(("old synthetic artifact: " + target).encode())
    (output / filename).mkdir()
    (output / filename / "keep.txt").write_bytes(b"Nested obstruction bytes\n")
    source = None if command == "estimation" else h.valid
    h.rejected_unchanged(name, root, h.arguments(command, source, output, overwrite=overwrite))


def job_collision(h, filename, overwrite):
    name = f"job-{filename}-overwrite-{overwrite}"
    root = h.case(name)
    (root / "synthetic.csv").write_bytes(h.data)
    jobfile = root / filename
    write_json(jobfile, h.job())
    args = h.arguments("calibrate", None, root, overwrite=overwrite, extra=["--job", jobfile])
    h.rejected_unchanged(name, root, args)


def job_directory(h, *, sidecar=False, collision=False):
    name = "job-directory" + ("-sidecar" if sidecar else "") + ("-alias-collision" if collision else "-success")
    root = h.case(name)
    jobdir = root / "job"
    jobdir.mkdir()
    output = root / "output"
    (jobdir / "synthetic.csv").write_bytes(h.data)
    job = h.job()
    if sidecar:
        text = json.dumps(profile(), indent=2)
        job["Processing"].update(ImportProfile=profile()["Id"], ImportProfileHash=sha(text.encode()))
        if collision:
            output.mkdir()
            target = output / "calibration_recommendations.csv"
            target.write_text(text, encoding="utf-8")
            link(target, jobdir / "import_profile.json")
        else:
            (jobdir / "import_profile.json").write_text(text, encoding="utf-8")
    if collision and not sidecar:
        output.mkdir()
        target = output / "calibration_tracks.csv"
        write_json(target, job)
        link(target, jobdir / "job.json")
    else:
        write_json(jobdir / "job.json", job)
    args = h.arguments("calibrate", None, output, overwrite=collision, extra=["--job", jobdir])
    if collision:
        h.rejected_unchanged(name, root, args)
    else:
        before = snapshot(jobdir)
        h.invoke(name, args, expected=0)
        h.check(snapshot(jobdir) == before, f"{name}: job input bytes changed")
        check_state(h, name, output, 71, jobfile=jobdir / "job.json")


def profile_collision(h, command, filename, overwrite):
    name = f"{command}-profile-{filename}-overwrite-{overwrite}"
    root = h.case(name)
    output = root / "output"
    output.mkdir()
    source = output / filename
    write_json(source, profile())
    h.rejected_unchanged(name, root, h.arguments(command, h.valid, output, overwrite=overwrite,
                                               extra=["--import-profile", source]))


def alias_collision(h, kind, overwrite):
    name = f"alias-{kind}-overwrite-{overwrite}"
    root = h.case(name)
    output = root / "output"
    output.mkdir()
    source = output / "calibration.csv"
    source.write_bytes(h.data)
    argument = source
    if kind == "output-parent":
        alias = root / "parent-link"
        link(output, alias, directory=True)
        output = alias
    elif kind == "input-parent":
        alias = root / "parent-link"
        link(output, alias, directory=True)
        argument = alias / "calibration.csv"
    elif kind == "input-leaf":
        argument = root / "source-link.csv"
        link(source, argument)
    elif kind in ("output-leaf", "dangling-output-leaf"):
        source.rename(root / "source.csv")
        argument = root / "source.csv"
        target = argument if kind == "output-leaf" else root / "absent.csv"
        link(target, source)
    h.rejected_unchanged(name, root, h.arguments("calibrate", argument, output, overwrite=overwrite))


def safe_distinct_entry(h, hard):
    name = "distinct-hardlink-overwrite" if hard else "distinct-equal-copy-overwrite"
    root = h.case(name)
    source = root / "source.csv"
    source.write_bytes(h.data)
    output = root / "output"
    output.mkdir()
    target = output / "calibration.csv"
    if hard:
        link(source, target, hard=True)
    else:
        target.write_bytes(h.data)
    h.invoke(name, h.arguments("calibrate", source, output, overwrite=True), expected=0)
    h.check(source.read_bytes() == h.data, f"{name}: atomic replacement damaged outside input")
    h.check(target.read_bytes() != h.data, f"{name}: target was not replaced")
    check_state(h, name, output, 71)


def nested_link_collision(h):
    name = "nested-raw-link-dotdot-collision"
    root = h.case(name)
    (root / "actual" / "child").mkdir(parents=True)
    output = root / "actual" / "out"
    output.mkdir()
    (output / "calibration.csv").write_bytes(h.data)
    (root / "out").mkdir()
    (root / "out" / "calibration.csv").write_bytes(h.data + b"\n")
    link(root / "actual" / "child", root / "jump", directory=True)
    source = root / "source.csv"
    link(Path("jump/../out/calibration.csv"), source)
    h.check(source.read_bytes() == h.data, "Nested link fixture does not reach the intended input")
    h.rejected_unchanged(name, root, h.arguments("calibrate", source, output, overwrite=True))


def analyze_help_value(h, project):
    h.require_state()
    name = "analyze-project-" + ("h" if project == "-h" else "h-equals-banana")
    root = h.case(name)
    before = snapshot(h.baseline)
    payload = h.invoke(name, ["analyze", "--in", h.valid, "--calibration", h.baseline,
                              "--out", root / "output", "--project", project, "--json", "--quiet"], expected=0)
    output = Path(payload["outputDirectory"])
    h.check((output / "results.csv").is_file() and (output / "results.json").is_file(),
            f"{name}: analysis did not actually produce scientific results")
    manifest = strict_json((output / "run_manifest.json").read_text(encoding="utf-8"))
    h.check(manifest["inputData"]["sha256"].lower() == sha(h.data), f"{name}: manifest input identity changed")
    h.check(manifest["project"]["name"] == project, f"{name}: project value was not preserved")
    h.check(snapshot(h.baseline) == before and h.valid.read_bytes() == h.data,
            f"{name}: analysis changed input calibration/data")


def global_error(h, name, args, machine=True):
    root = h.case(name)
    before = snapshot(root)
    result = h.invoke(name, args, machine=machine, error_type="ArgumentException")
    if not machine:
        h.check(result.stdout == "" and bool(result.stderr.strip()), f"{name}: expected human stderr-only error")
    h.check(snapshot(root) == before, f"{name}: global error wrote output")


def calibration_global_error(h):
    name = "calibrate-global-bad-quiet"
    root = h.case(name)
    args = h.arguments("calibrate", h.valid, root / "output")
    args[args.index("--quiet")] = "--quiet=banana"
    before = snapshot(root)
    h.invoke(name, args, error_type="ArgumentException")
    h.check(snapshot(root) == before, "Malformed global flag created calibration output")


def human_version(h):
    process = h.invoke("json-false-version", ["version", "--json=false"], machine=False, expected=0)
    h.check(bool(process.stdout.strip()) and not process.stdout.lstrip().startswith("{"),
            "--json=false no longer produces human version output")


def python_error(h, kind):
    name = "python-" + kind
    root = h.case(name)
    output = root / "output"
    options = {"repetitions": 100, "seed": 71}
    source = h.valid
    if kind == "input-collision":
        output.mkdir()
        source = output / "calibration.csv"
        source.write_bytes(h.data)
        options["overwrite"] = True
    elif kind == "global-bad-quiet":
        options["quiet=banana"] = True
    else:
        options["json=banana"] = True
    before = snapshot(root)
    sys.path.insert(0, str(ROOT / "python" / "src"))
    try:
        import mvs
    finally:
        sys.path.pop(0)
    with h.python_environment():
        engine = mvs.Engine(h.cli)  # Real version handshake, no mocked subprocess.
        h.python_calls += 1
        try:
            h.python_calls += 1
            engine.calibrate(source, output=output, **options)
        except mvs.InputError as error:
            record = {"name": name, "exception": type(error).__name__, "message": str(error)}
            h.records.append(record)
            h.capture(record)
            h.check(bool(str(error)), f"{name}: InputError lost its message")
        else:
            raise AssertionError(f"{name}: actual Python API did not raise mvs.InputError")
        finally:
            h.check(snapshot(root) == before, f"{name}: Python call changed input/output bytes")
            h.check(h.valid.read_bytes() == h.data, f"{name}: Python call changed shared source")


def suite(h):
    tests = unittest.TestSuite()

    def add(name, function, *args, **kwargs):
        def execute_case():
            function(h, *args, **kwargs)

        execute_case.__name__ = function.__name__
        tests.addTest(unittest.FunctionTestCase(execute_case, description=name))

    add("Separate input calibration, native state-check and artifact hashes", successful_calibration)
    add("Explicit legitimate overwrite and preserved unrelated file", successful_overwrite)
    for command in ("calibrate", "variance", "melsm"):
        for filename in OUTPUTS[command]:
            for overwrite in (False, True):
                add(f"{command}: preserve input {filename}, overwrite={overwrite}", input_collision,
                    command, filename, overwrite)
    add("Relative normalized input collision", input_collision, "calibrate", "calibration.csv", True, relative=True)
    for command in ("variance", "melsm"):
        add(f"{command}: preserve whitespace-trimmed --in collision", input_collision,
            command, OUTPUTS[command][0], True, padded=True)
    for filename in OUTPUTS["calibrate"]:
        add(f"Block standalone existing {filename} without overwrite", existing_calibration_target, filename)
        for overwrite in (False, True):
            add(f"Protect declared job {filename}, overwrite={overwrite}", job_collision, filename, overwrite)
    for command, filenames in OUTPUTS.items():
        for filename in filenames:
            for overwrite in (False, True):
                add(f"{command}: directory at {filename}, overwrite={overwrite}", obstructed_target,
                    command, filename, overwrite)
    for sidecar in (False, True):
        for collision in (False, True):
            add(f"Job directory resolution, sidecar={sidecar}, collision={collision}", job_directory,
                sidecar=sidecar, collision=collision)
    for command in ("variance", "melsm"):
        for filename in OUTPUTS[command]:
            for overwrite in (False, True):
                add(f"{command}: preserve import profile {filename}, overwrite={overwrite}", profile_collision,
                    command, filename, overwrite)
    for kind in ("output-parent", "input-parent", "input-leaf", "output-leaf", "dangling-output-leaf"):
        for overwrite in (False, True):
            add(f"Preserve {kind} alias, overwrite={overwrite}", alias_collision, kind, overwrite)
    for hard in (False, True):
        add(f"Permit safe distinct {'hardlink' if hard else 'equal-content copy'} replacement", safe_distinct_entry, hard)
    add("Resolve nested raw symlink parent traversal before collision check", nested_link_collision)
    for project in ("-h", "-h=banana"):
        add(f"Real analysis accepts project value {project!r}", analyze_help_value, project)
    malformed = [
        ("bad-json", ["version", "--json=banana"]),
        ("empty-json", ["version", "--json="]),
        ("bad-json-before-false", ["version", "--json=banana", "--json=false"]),
        ("bad-json-after-false", ["version", "--json=false", "--json=banana"]),
        ("bad-json-after-true", ["version", "--json", "--json=banana"]),
        ("bad-quiet-json-after-false", ["version", "--json=false", "--quiet=banana", "--json"]),
    ]
    for flag in ("--quiet", "--help", "-h", "--version"):
        tag = flag.lstrip("-")
        malformed += [(f"bad-{tag}-before-json", ["version", flag + "=banana", "--json"]),
                      (f"bad-{tag}-after-json", ["version", "--json", flag + "=banana"]),
                      (f"bad-{tag}-duplicate", ["version", "--json", flag, flag + "=banana"])]
    for name, arguments in malformed:
        add(f"Structured global error: {name}", global_error, name, arguments)
    for flag in ("--quiet", "--help", "-h", "--version"):
        name = "false-json-bad-" + flag.lstrip("-")
        add(f"Human error when only JSON false: {flag}", global_error, name,
            ["version", "--json=false", flag + "=banana"], machine=False)
    add("Human version retains JSON false semantics", human_version)
    add("Calibration global parser rejects before output creation", calibration_global_error)
    for kind in ("input-collision", "global-bad-quiet", "global-bad-json"):
        add(f"Actual Python InputError: {kind}", python_error, kind)
    return tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, type=Path, help="Actual compiled mvs executable, not a DLL")
    parser.add_argument("--artifacts", required=True, type=Path, help="Parent for unique retained synthetic evidence")
    parser.add_argument("--timeout", type=float, default=90, help="Per-CLI-call timeout in seconds (default: 90)")
    args = parser.parse_args()
    cli = args.cli.expanduser().resolve()
    if not cli.is_file() or not os.access(cli, os.X_OK):
        parser.error(f"CLI is not an executable file: {cli}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    # An old crashing CLI must not leave a core dump in the source checkout.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, OSError, ValueError):
        pass
    h = Harness(cli, args.artifacts.expanduser().resolve(), args.timeout)
    print(f"Synthetic CLI safety evidence: {h.run}", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite(h))
    summary = {
        "syntheticOnly": True, "cli": str(cli), "cliSha256": sha(cli.read_bytes()),
        # Framework-dependent apphosts do not themselves contain the tested C#.
        # Self-contained single-file publishes may have no adjacent assemblies.
        "managedAssemblies": [{"path": str(path), "sha256": sha(path.read_bytes()),
                               "sizeBytes": path.stat().st_size}
                              for path in (cli.parent / "mvs.dll", cli.parent / "MvsAnalyzer.Core.dll")
                              if path.is_file()],
        "sourceRoot": str(ROOT), "fixture": {"rows": 48, "subjects": 8, "repetitions": 100,
                                             "sha256": sha(h.data)},
        "testsRun": result.testsRun, "checks": h.checks, "cliInvocations": h.calls,
        "pythonCliInvocations": h.python_calls, "passed": result.wasSuccessful(),
        "failures": [{"test": str(test), "detail": detail} for test, detail in result.failures],
        "errors": [{"test": str(test), "detail": detail} for test, detail in result.errors],
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
        "limits": ["I/O and error-contract smoke checks, not scientific validation",
                   "Variance, estimation and MELSM probes stop before computation via preflight or a late invalid option",
                   "Preflight is not transactional or race-proof; no FIFO/device or adversarial filesystem tests"],
    }
    write_json(h.run / "summary.json", summary)
    print(f"{result.testsRun} cases; {h.checks} assertions; {h.calls} direct CLI calls; "
          f"{h.python_calls} actual Python CLI calls; {len(result.skipped)} skips. Evidence: {h.run}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
