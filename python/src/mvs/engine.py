from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, TypeVar

from .models import (
    AnalysisResult,
    Artifact,
    BaseResult,
    BenchmarkResult,
    Calibration,
    Diagnostic,
    EstimationResult,
    MelsmResult,
    VarianceResult,
)

SCHEMA = "mvs-cli-result/v1"
SUPPORTED_CLI_PROTOCOL = ("mvs-cli", 1)
T = TypeVar("T", bound=BaseResult)


class MvsError(RuntimeError):
    """Base error raised by the Python interface."""


class EngineNotFoundError(MvsError):
    pass


class EngineCompatibilityError(MvsError):
    pass


class InputError(MvsError):
    pass


class EngineError(MvsError):
    pass


class ScientificDiagnostic(MvsError):
    def __init__(self, message: str, result: BaseResult):
        super().__init__(message)
        self.result = result


def _default_output(command: str) -> Path:
    root = Path.cwd() / "mvs-output"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{command}-{uuid.uuid4().hex[:8]}"


def _option_name(name: str) -> str:
    return "--" + name.replace("_", "-")


def _append_options(args: list[str], options: Mapping[str, Any]) -> None:
    for key, value in options.items():
        if value is None or value is False:
            continue
        name = _option_name(key)
        if value is True:
            args.append(name)
        elif isinstance(value, (list, tuple)):
            for item in value:
                args.extend([name, str(item)])
        else:
            args.extend([name, str(value)])


class Engine:
    def __init__(self, executable: str | os.PathLike[str] | None = None):
        explicit = str(executable) if executable is not None else os.environ.get("MVS_CLI")
        if explicit:
            resolved = shutil.which(explicit) if not Path(explicit).exists() else str(Path(explicit).expanduser().resolve())
        else:
            resolved = shutil.which("mvs")
        if not resolved:
            raise EngineNotFoundError("Cannot find the MVS CLI. Install `mvs` or set MVS_CLI=/path/to/mvs.")
        self.executable = resolved
        self.identity = self._invoke(["version"], allow_diagnostic=False, result_type=BaseResult)
        if self.identity.raw.get("schemaVersion") != SCHEMA:
            raise EngineCompatibilityError(
                f"Unsupported MVS CLI machine schema: {self.identity.raw.get('schemaVersion')!r}; expected {SCHEMA!r}."
            )
        protocol = self.identity.raw.get("cliProtocol")
        if not isinstance(protocol, dict) or (protocol.get("name"), protocol.get("major")) != SUPPORTED_CLI_PROTOCOL:
            raise EngineCompatibilityError(f"Unsupported MVS CLI command protocol: {protocol!r}.")
        if not self.identity.engine_version:
            raise EngineCompatibilityError("The MVS CLI did not publish an engine version.")

    def _invoke(self, args: Sequence[str], *, allow_diagnostic: bool, result_type: type[T]) -> T:
        command = args[0] if args else ""
        process = subprocess.run(
            [self.executable, *args, "--json", "--quiet"],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            detail = process.stderr.strip() or process.stdout.strip() or "no output"
            raise EngineError(f"MVS CLI did not return valid machine JSON for {command!r}: {detail}") from exc
        if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA:
            raise EngineCompatibilityError(f"Unsupported or missing MVS CLI machine schema in {command!r} response.")
        result = _result_from_payload(payload, result_type)
        if result.command != command:
            raise EngineCompatibilityError(f"MVS response command {result.command!r} does not match request {command!r}.")
        expected_status = {0: "completed", 1: "error", 2: "diagnostic"}.get(result.exit_code)
        if expected_status is None or result.status != expected_status:
            raise EngineCompatibilityError(f"Invalid status/exitCode pair from MVS: {result.status!r}/{result.exit_code!r}.")
        if process.returncode != result.exit_code:
            raise EngineError(
                f"MVS process exit code {process.returncode} disagrees with JSON exitCode {result.exit_code} for {command!r}."
            )
        if result.exit_code == 0:
            return result
        if result.exit_code == 2:
            if allow_diagnostic:
                return result
            raise ScientificDiagnostic(_diagnostic_message(result), result)
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        message = message or process.stderr.strip() or f"MVS command {command!r} failed."
        error_type = error.get("type", "") if isinstance(error, dict) else ""
        if error_type in {"ArgumentException", "InvalidDataException", "FileNotFoundException", "FormatException"}:
            raise InputError(message)
        raise EngineError(message)

    def calibrate(self, data: str | os.PathLike[str], *, output: str | os.PathLike[str] | None = None,
                  allow_diagnostic: bool = False, **options: Any) -> Calibration:
        out = Path(output) if output is not None else _default_output("calibration")
        args = ["calibrate", "--in", str(Path(data)), "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=Calibration)

    def analyze(self, data: str | os.PathLike[str], *, calibration: Calibration | str | os.PathLike[str],
                output: str | os.PathLike[str] | None = None, allow_diagnostic: bool = False,
                **options: Any) -> AnalysisResult:
        out = Path(output) if output is not None else _default_output("analysis")
        calibration_path = calibration.output_directory if isinstance(calibration, Calibration) else Path(calibration)
        if calibration_path is None:
            raise InputError("Calibration result does not have an output directory.")
        args = ["analyze", "--in", str(Path(data)), "--calibration", str(calibration_path), "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=AnalysisResult)

    def variance(self, data: str | os.PathLike[str], *, output: str | os.PathLike[str] | None = None,
                 allow_diagnostic: bool = True, **options: Any) -> VarianceResult:
        out = Path(output) if output is not None else _default_output("variance")
        args = ["variance", "--in", str(Path(data)), "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=VarianceResult)

    def estimation(self, *, output: str | os.PathLike[str] | None = None,
                   allow_diagnostic: bool = True, **options: Any) -> EstimationResult:
        out = Path(output) if output is not None else _default_output("estimation")
        args = ["estimation", "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=EstimationResult)

    def melsm(self, data: str | os.PathLike[str], *, output: str | os.PathLike[str] | None = None,
              allow_diagnostic: bool = True, **options: Any) -> MelsmResult:
        out = Path(output) if output is not None else _default_output("melsm")
        args = ["melsm", "--in", str(Path(data)), "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=MelsmResult)

    def benchmark(self, *, output: str | os.PathLike[str] | None = None,
                  allow_diagnostic: bool = True, **options: Any) -> BenchmarkResult:
        out = Path(output) if output is not None else _default_output("benchmark")
        args = ["benchmark", "--out", str(out)]
        _append_options(args, options)
        return self._invoke(args, allow_diagnostic=allow_diagnostic, result_type=BenchmarkResult)


def _diagnostic_message(result: BaseResult) -> str:
    if result.diagnostics:
        return "; ".join(item.message for item in result.diagnostics)
    return f"MVS command {result.command!r} completed with a scientific/numerical diagnostic."


def _result_from_payload(payload: Mapping[str, Any], result_type: type[T]) -> T:
    artifacts = tuple(
        Artifact(
            name=str(item.get("name", "")),
            path=Path(item["path"]),
            size_bytes=item.get("sizeBytes"),
            sha256=item.get("sha256"),
        )
        for item in payload.get("artifacts", [])
        if isinstance(item, dict) and item.get("path")
    )
    diagnostics = tuple(
        Diagnostic(str(item.get("level", "warning")), str(item.get("code", "diagnostic")), str(item.get("message", "")))
        for item in payload.get("diagnostics", [])
        if isinstance(item, dict)
    )
    output = payload.get("outputDirectory")
    manifest = payload.get("manifestPath")
    return result_type(
        command=str(payload.get("command", "")),
        status=str(payload.get("status", "")),
        exit_code=int(payload.get("exitCode", -1)),
        output_directory=Path(output) if output else None,
        run_id=payload.get("runId"),
        engine_version=str(payload.get("engineVersion", "")),
        application_version=str(payload.get("applicationVersion") or payload.get("appVersion") or ""),
        manifest_path=Path(manifest) if manifest else None,
        artifacts=artifacts,
        diagnostics=diagnostics,
        raw=dict(payload),
    )
