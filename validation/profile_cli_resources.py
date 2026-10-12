#!/usr/bin/env python3
"""One opt-in, frozen Linux CLI resource/cancellation diagnostic.

This is an operational profile, not statistical validation or a benchmark gate.
No CLI is run on import or by the unit tests. Evidence/output paths must be new.
Only child processes receive affinity; stdout/stderr are ordinary files. wait4
reaps each exact PID once, preserving its own kernel CPU and maximum RSS rather
than the cumulative RUSAGE_CHILDREN high-water mark.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import sys
import time
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "validation" / "cli-resource-profile-v1.json"
SCHEMA = "mvs-cli-result/v1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(text):
    def invalid(value):
        raise ValueError(f"Nonfinite JSON literal: {value}")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=invalid, object_pairs_hook=pairs)


def write_json_new(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")


def generate_dataset(entities, measurements, seed=20261011):
    """Independent deterministic stream per size; bounded strictly positive data."""
    rng = random.Random(seed)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["entity", "group", "value", "sequence", "unit"])
    for group_index, group in enumerate(("A", "B", "C")):
        for entity in range(1, entities + 1):
            intercept = rng.uniform(-10.0, 10.0)
            for sequence in range(1, measurements + 1):
                value = 100.0 + 12.0 * group_index + intercept + .03 * sequence + rng.uniform(-4.0, 4.0)
                writer.writerow([f"{group}{entity:04d}", group, f"{value:.9f}", sequence, "synthetic-unit"])
    return stream.getvalue().encode("utf-8")


def validate_protocol(protocol):
    """Refuse accidental expansion of this one bounded protocol."""
    if protocol.get("protocolId") != "MVS-CLI-RESOURCE-1":
        raise ValueError("Unsupported resource protocol")
    sizes = [(x["entitiesPerGroup"], x["measurementsPerEntity"], x["rows"]) for x in protocol["datasets"]]
    if sizes != [(4, 6, 72), (20, 20, 1200), (100, 50, 15000)]:
        raise ValueError("Dataset sizes differ from frozen protocol")
    if protocol["generator"]["seed"] != 20261011 or protocol["calibration"] != {"repetitions": 100, "seed": 20260719}:
        raise ValueError("Seed/repetition budget differs from frozen protocol")
    expected_limits = {"cpus": 2, "rssLimitMiB": 768, "pollSeconds": .05,
                       "calibrationTimeoutSeconds": 120, "analysisTimeoutSeconds": 30,
                       "cancelAfterSeconds": 1, "cancelGraceSeconds": 10}
    if protocol["limits"] != expected_limits:
        raise ValueError("Resource limits differ from frozen protocol")
    if protocol["cancellation"]["repetitions"] != 100000 or protocol["cancellation"]["dataset"] != "medium":
        raise ValueError("Cancellation case differs from frozen protocol")
    for dataset in protocol["datasets"]:
        data = generate_dataset(dataset["entitiesPerGroup"], dataset["measurementsPerEntity"])
        if hashlib.sha256(data).hexdigest() != dataset["sha256"]:
            raise ValueError(f"Generated input hash differs: {dataset['id']}")


def require_linux():
    if sys.platform != "linux" or not all(hasattr(os, name) for name in ("wait4", "sched_getaffinity", "sched_setaffinity", "killpg")):
        raise RuntimeError("Unsupported platform: Linux with /proc, wait4 and CPU affinity is required")
    if not Path("/proc/self/status").is_file():
        raise RuntimeError("Unsupported environment: readable Linux /proc is required")


def select_affinity(allowed, count=2):
    selected = sorted(allowed)[:count]
    if not selected:
        raise RuntimeError("No allowed CPU found")
    return selected


def child_affinity(cpus):
    os.sched_setaffinity(0, set(cpus))


def clean_environment(inherited, selected):
    env = dict(inherited, **selected)
    removed = sorted(k for k in env if k.startswith(("COMPlus_", "DOTNET_", "MVS_")) and k not in selected)
    for key in removed:
        env.pop(key)
    return env, removed


def sample_process(pid):
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        values = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        rss = int(values.get("VmRSS", "0 kB").split()[0])
        affinity = sorted(os.sched_getaffinity(pid))
        runtime = []
        for line in Path(f"/proc/{pid}/maps").read_text(encoding="utf-8").splitlines():
            if line.endswith("/libcoreclr.so"):
                runtime.append(line.split()[-1])
        return {"rssKiB": rss, "affinity": affinity, "coreclrPaths": sorted(set(runtime))}
    except (FileNotFoundError, ProcessLookupError):
        return None  # Exit may race a sample; wait4 still owns final accounting.


def monitor_process(pid, started, limits, timeout, cpus, *, cancellation=False,
                    wait4=None, sample=None, send_signal=None, now=None, sleep=None):
    """Dependency-injected controls let tests exercise deadlines without any child."""
    wait4 = wait4 or os.wait4
    sample = sample or sample_process
    send_signal = send_signal or os.killpg
    now = now or time.monotonic
    sleep = sleep or time.sleep
    samples, events, violations = [], [], []
    cancel_at = None
    killed = False
    while True:
        waited, status, usage = wait4(pid, os.WNOHANG)
        elapsed = now() - started
        if waited:
            if waited != pid:
                raise RuntimeError("wait4 returned an unexpected PID")
            return {"returncode": os.waitstatus_to_exitcode(status), "wallSeconds": elapsed,
                    "cpuUserSeconds": usage.ru_utime, "cpuSystemSeconds": usage.ru_stime,
                    "cpuTotalSeconds": usage.ru_utime + usage.ru_stime,
                    "peakRssKiB": usage.ru_maxrss, "sampledPeakRssKiB": max([s["rssKiB"] for s in samples] or [0]),
                    "minorPageFaults": usage.ru_minflt, "majorPageFaults": usage.ru_majflt,
                    "voluntaryContextSwitches": usage.ru_nvcsw, "involuntaryContextSwitches": usage.ru_nivcsw,
                    "samples": samples, "events": events, "violations": violations,
                    "cancellationSignalSent": cancel_at is not None,
                    "cancellationLatencySeconds": elapsed - cancel_at if cancel_at is not None else None,
                    "forcedKill": killed}
        sampled = sample(pid)
        reason = None
        if sampled is not None:
            samples.append({"elapsedSeconds": elapsed, **sampled})
            if sampled["rssKiB"] > limits["rssLimitMiB"] * 1024:
                reason = "rss_watchdog"
            if sampled["affinity"] != cpus:
                reason = "affinity_changed"
        if cancellation and cancel_at is not None and elapsed - cancel_at >= limits["cancelGraceSeconds"]:
            reason = reason or "cancellation_grace_expired"
        if elapsed >= timeout:
            reason = reason or "timeout"
        if reason and not killed:
            violations.append(reason)
            try:
                send_signal(pid, signal.SIGKILL)
                events.append({"signal": "SIGKILL", "elapsedSeconds": elapsed, "reason": reason})
            except ProcessLookupError:
                events.append({"signal": "SIGKILL", "elapsedSeconds": elapsed, "reason": reason, "processAlreadyExited": True})
            killed = True
        elif cancellation and not killed and cancel_at is None and elapsed >= limits["cancelAfterSeconds"]:
            try:
                send_signal(pid, signal.SIGINT)
                cancel_at = elapsed
                events.append({"signal": "SIGINT", "elapsedSeconds": elapsed, "reason": "planned_cancellation"})
            except ProcessLookupError:
                violations.append("exited_before_cancellation_signal")
        sleep(limits["pollSeconds"])


def check_payload(payload, record, *, cancellation=False):
    problems = []
    expected = 1 if cancellation else 0
    if not isinstance(payload, dict):
        return ["stdout is not exactly one JSON object"]
    for key, value in (("schemaVersion", SCHEMA), ("exitCode", expected),
                       ("status", "error" if cancellation else "completed"),
                       ("command", record["command"][1]), ("engineVersion", "1.6.2")):
        if payload.get(key) != value:
            problems.append(f"Unexpected {key}: {payload.get(key)!r}")
    if record["returncode"] != expected:
        problems.append(f"Expected process exit {expected}, got {record['returncode']}")
    if cancellation:
        if not record["cancellationSignalSent"]:
            problems.append("Process finished before planned cancellation")
        if not isinstance(payload.get("error"), dict) or payload["error"].get("type") != "OperationCanceledException":
            problems.append("Missing OperationCanceledException")
        if payload.get("outputDirectory") is not None or payload.get("manifestPath") is not None or payload.get("artifacts") != []:
            problems.append("Cancellation claimed completed output/artifacts")
    elif payload.get("error") is not None:
        problems.append("Completed invocation reported an error")
    return problems


def check_output(payload, output, dataset, calibration=None, *, cancellation=False):
    """Verify byte identities/registry count only; not independent numerics."""
    problems = []
    files = list(output.rglob("*")) if output.exists() else []
    if cancellation:
        if any(p.name in {"calibration_state.json", "run_manifest.json"} for p in files):
            problems.append("Cancellation left a completed state or manifest")
        return problems
    reported = payload.get("outputDirectory")
    if not reported:
        return ["Completed invocation omitted outputDirectory"]
    folder = Path(reported).resolve()
    if not folder.is_relative_to(output.resolve()) or not folder.is_dir():
        return ["Reported output is missing or outside the fresh output directory"]
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ["Completed invocation omitted artifacts"]
    for artifact in artifacts:
        path = Path(artifact["path"]).resolve()
        if path.parent != folder or path.name != artifact["name"] or not path.is_file():
            problems.append("Invalid artifact path")
        elif path.stat().st_size != artifact["sizeBytes"] or sha256(path) != artifact["sha256"]:
            problems.append(f"Artifact bytes/hash mismatch: {path.name}")
    state = strict_json((folder / "calibration_state.json").read_text(encoding="utf-8"))
    for key, value in (("DatasetHash", dataset["sha256"]), ("EngineVersion", "1.6.2"),
                       ("Repetitions", 100), ("Seed", 20260719)):
        if state.get(key) != value:
            problems.append(f"Calibration identity mismatch: {key}")
    if len(state.get("Rows", [])) != 12:
        problems.append("Active calibration registry count is not twelve")
    if calibration is not None:
        if sha256(folder / "calibration_state.json") != sha256(calibration / "calibration_state.json"):
            problems.append("Analysis changed the calibration state bytes")
        results = strict_json((folder / "results.json").read_text(encoding="utf-8"))
        manifest = strict_json((folder / "run_manifest.json").read_text(encoding="utf-8"))
        if len(results.get("rows", [])) != 12 or manifest.get("decision", {}).get("familySize") != 12:
            problems.append("Analysis family/registry count is not twelve")
        for row in results.get("rows", []):
            if row.get("PValue") is not None and abs(row["AdjustedP"] - min(1, 12 * row["PValue"])) > 1e-12:
                problems.append("Analysis no longer uses twelve-metric Bonferroni")
    return problems


def invoke(cli, args, case, run, env, cpus, protocol, dataset, *, calibration=None, cancellation=False):
    captures = run / "captures"
    output = run / "outputs" / case
    command = [str(cli), *args, "--out", str(output), "--json", "--quiet"]
    record = {"id": case, "dataset": dataset["id"], "inputSha256": dataset["sha256"],
              "command": command, "cwd": str(run), "startedUtc": utc_now(), "selectedAffinity": cpus}
    stdout = captures / f"{case}.stdout.txt"
    stderr = captures / f"{case}.stderr.txt"
    limits = protocol["limits"]
    timeout = limits["calibrationTimeoutSeconds"] if args[0] == "calibrate" else limits["analysisTimeoutSeconds"]
    record["timeoutSeconds"] = timeout
    started = time.monotonic()
    process = None
    try:
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.Popen(command, cwd=run, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True,
                                       preexec_fn=lambda: child_affinity(cpus))
            record["pid"] = process.pid
            record.update(monitor_process(process.pid, started, limits, timeout, cpus, cancellation=cancellation))
            process.returncode = record["returncode"]  # wait4 already reaped it; never call Popen.poll/wait.
    except BaseException as error:
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
            record.update(returncode=process.returncode, cpuUserSeconds=usage.ru_utime,
                          cpuSystemSeconds=usage.ru_stime, peakRssKiB=usage.ru_maxrss)
        record["harnessError"] = f"{type(error).__name__}: {error}"
    record["finishedUtc"] = utc_now()
    record["captureFiles"] = {"stdout": stdout.relative_to(run).as_posix(), "stderr": stderr.relative_to(run).as_posix()}
    record["captureSha256"] = {"stdout": sha256(stdout), "stderr": sha256(stderr)}
    problems = list(record.get("violations", []))
    if "harnessError" in record:
        problems.append(record["harnessError"])
    if record.get("peakRssKiB", 0) > limits["rssLimitMiB"] * 1024:
        problems.append("Kernel peak RSS exceeded the watchdog threshold (sampling is not a hard memory cap)")
    if not record.get("samples"):
        problems.append("No live process sample was captured; affinity/RSS observation is unverified")
    try:
        payload = strict_json(stdout.read_text(encoding="utf-8"))
        record["payload"] = payload
        problems += check_payload(payload, record, cancellation=cancellation)
        if isinstance(payload, dict):
            problems += check_output(payload, output, dataset, calibration, cancellation=cancellation)
    except (ValueError, OSError, KeyError, TypeError) as error:
        problems.append(f"Output verification failed: {type(error).__name__}: {error}")
    record["problems"] = problems
    record["passed"] = not problems
    write_json_new(captures / f"{case}.record.json", record)
    print(json.dumps({key: record.get(key) for key in ("id", "passed", "returncode", "wallSeconds", "cpuTotalSeconds", "peakRssKiB", "problems")}), flush=True)
    return record


def archive_evidence(run, archive):
    files = []
    for path in sorted(run.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Evidence may not contain symlinks: {path}")
        if path.is_file():
            if path.suffix.lower() in {".dll", ".so", ".exe", ".pdb", ".pyc"}:
                raise ValueError(f"Compiled binary/cache in evidence: {path}")
            files.append(path)
    inventory = [{"path": p.relative_to(run).as_posix(), "sizeBytes": p.stat().st_size, "sha256": sha256(p)} for p in files]
    write_json_new(run / "evidence-files.json", inventory)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
        for path in [*files, run / "evidence-files.json"]:
            target.write(path, arcname="cli-resource-profile-round17/" + path.relative_to(run).as_posix())
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise RuntimeError("Evidence archive failed CRC check")
        for item in inventory:
            data = target.read("cli-resource-profile-round17/" + item["path"])
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise RuntimeError("Evidence archive content/hash mismatch")
    return {"path": str(archive), "sha256": sha256(archive), "sizeBytes": archive.stat().st_size,
            "files": len(files) + 1, "crcVerified": True, "inventoryHashesVerified": True}


def run_profile(cli, run, summary, archive, protocol_path=PROTOCOL):
    require_linux()
    protocol_bytes = protocol_path.read_bytes()
    protocol = strict_json(protocol_bytes.decode("utf-8"))
    validate_protocol(protocol)
    cli = cli.resolve(strict=True)
    run, summary, archive = run.resolve(), summary.resolve(), archive.resolve()
    if run.is_relative_to(ROOT) or summary.is_relative_to(run) or archive.is_relative_to(run):
        raise ValueError("Use a fresh evidence directory outside source, with summary/archive outside evidence")
    if len({run, summary, archive}) != 3 or any(p.exists() for p in (run, summary, archive)):
        raise FileExistsError("Evidence, summary and archive must be distinct new paths; existing evidence is never overwritten")
    binaries = []
    for name, expected in protocol["expectedBinarySha256"].items():
        path = cli.parent / name
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Frozen binary identity mismatch: {name}")
        binaries.append({"name": name, "sha256": actual, "sizeBytes": path.stat().st_size})
    parent_affinity = sorted(os.sched_getaffinity(0))
    cpus = select_affinity(parent_affinity, protocol["limits"]["cpus"])
    run.mkdir(parents=True, exist_ok=False)
    for name in ("inputs", "captures", "outputs", "runtime"):
        (run / name).mkdir()
    (run / "frozen-protocol.json").write_bytes(protocol_bytes)
    (run / "profile_cli_resources.py").write_bytes(Path(__file__).read_bytes())
    runtime = run / "runtime"
    selected_env = {"DOTNET_ROOT": "/tmp/mvs-dotnet", "DOTNET_CLI_HOME": "/tmp/mvs-dotnet-home",
                    "NUGET_PACKAGES": "/tmp/mvs-nuget/packages", "XDG_DATA_HOME": str(runtime / "data"),
                    "XDG_CONFIG_HOME": str(runtime / "config"), "XDG_CACHE_HOME": str(runtime / "cache"),
                    "MVS_BACKUP_DIR": str(runtime / "backups"), "MVS_DISABLE_BACKUPS": "1",
                    "PYTHONDONTWRITEBYTECODE": "1"}
    # Optional host debugging/CPU/backup-job overrides are not part of this run.
    env, removed_env = clean_environment(os.environ, selected_env)
    report = {"schema": "mvs-cli-resource-result/v1", "protocolId": protocol["protocolId"],
              "protocolSha256": hashlib.sha256(protocol_bytes).hexdigest(), "startedUtc": utc_now(),
              "runnerSha256": sha256(Path(__file__)), "runDirectory": str(run), "syntheticOnly": True,
              "scientificValidation": False, "developmentBaselineDecision": "NO-GO retained",
              "platform": platform.platform(), "machine": platform.machine(), "pythonVersion": platform.python_version(),
              "selectedEnvironment": selected_env, "removedRuntimeOverrideNames": removed_env,
              "parentAffinityBefore": parent_affinity, "selectedChildAffinity": cpus, "binaries": binaries,
              "installedSdkDirectories": sorted(p.name for p in Path(selected_env["DOTNET_ROOT"], "sdk").iterdir()),
              "installedRuntimeDirectories": sorted(p.name for p in Path(selected_env["DOTNET_ROOT"], "shared", "Microsoft.NETCore.App").iterdir()),
              "datasets": protocol["datasets"], "records": [], "skipped": [], "limits": protocol["interpretationLimits"]}
    write_json_new(run / "preflight.json", {k: v for k, v in report.items() if k not in {"records", "skipped"}})
    for dataset in protocol["datasets"]:
        (run / "inputs" / f"{dataset['id']}.csv").write_bytes(generate_dataset(dataset["entitiesPerGroup"], dataset["measurementsPerEntity"]))
    halted = False
    for dataset in protocol["datasets"]:
        name = dataset["id"]
        if halted:
            report["skipped"].append({"dataset": name, "reason": "Earlier failure; larger sizes are not attempted"})
            continue
        source = run / "inputs" / f"{name}.csv"
        calibration = run / "outputs" / f"{name}-calibrate"
        args = ["calibrate", "--in", str(source), "--repetitions", "100", "--seed", "20260719"]
        record = invoke(cli, args, f"{name}-calibrate", run, env, cpus, protocol, dataset)
        report["records"].append(record)
        if not record["passed"]:
            halted = True
            report["skipped"].append({"case": f"{name}-analyze", "reason": "Calibration failed"})
            continue
        record = invoke(cli, ["analyze", "--in", str(source), "--calibration", str(calibration)],
                        f"{name}-analyze", run, env, cpus, protocol, dataset, calibration=calibration)
        report["records"].append(record)
        if not record["passed"]:
            halted = True
            continue
        if name == "medium":
            args = ["calibrate", "--in", str(source), "--repetitions", "100000", "--seed", "20260719"]
            record = invoke(cli, args, "medium-cancel", run, env, cpus, protocol, dataset, cancellation=True)
            report["records"].append(record)
            halted = not record["passed"]
    if not any(r["id"] == "medium-cancel" for r in report["records"]):
        report["skipped"].append({"case": "medium-cancel", "reason": "Earlier failure; cancellation prerequisite did not complete"})
    report["parentAffinityAfter"] = sorted(os.sched_getaffinity(0))
    report["inputPreserved"] = all(sha256(run / "inputs" / f"{d['id']}.csv") == d["sha256"] for d in protocol["datasets"])
    report["protocolPreserved"] = sha256(protocol_path) == report["protocolSha256"]
    report["runnerPreserved"] = sha256(Path(__file__)) == report["runnerSha256"]
    report["binaryIdentityPreserved"] = all(sha256(cli.parent / b["name"]) == b["sha256"] for b in binaries)
    report["passed"] = (len(report["records"]) == 7 and all(r["passed"] for r in report["records"])
                        and report["parentAffinityAfter"] == parent_affinity and report["inputPreserved"]
                        and report["protocolPreserved"] and report["runnerPreserved"] and report["binaryIdentityPreserved"])
    report["finishedUtc"] = utc_now()
    write_json_new(run / "results.json", report)
    archive_info = archive_evidence(run, archive)
    # Full per-50ms samples/payloads remain in the nested evidence archive.
    compact = dict(report, evidenceArchive=archive_info,
                   records=[{k: v for k, v in r.items() if k not in {"samples", "payload"}} for r in report["records"]])
    write_json_new(summary, compact)
    print(json.dumps({"passed": report["passed"], "summary": str(summary), "archive": archive_info}), flush=True)
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--execute-frozen-profile", action="store_true", help="Explicit opt-in; invokes the real CLI seven times at most")
    args = parser.parse_args()
    if not args.execute_frozen_profile:
        parser.error("Execution requires --execute-frozen-profile; unit tests never run this profile")
    try:
        return run_profile(args.cli, args.evidence, args.summary, args.archive)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Resource profile failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
