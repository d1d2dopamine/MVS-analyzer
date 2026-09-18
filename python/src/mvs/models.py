from __future__ import annotations

import csv
import json
import html
import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Diagnostic:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class Artifact:
    name: str
    path: Path
    size_bytes: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class RunManifest:
    path: Path
    data: Mapping[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> "RunManifest":
        p = Path(path)
        return cls(p, json.loads(p.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class BaseResult:
    command: str
    status: str
    exit_code: int
    output_directory: Path | None
    run_id: str | None
    engine_version: str
    application_version: str
    manifest_path: Path | None
    artifacts: tuple[Artifact, ...] = field(default_factory=tuple)
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def manifest(self) -> RunManifest | None:
        return RunManifest.load(self.manifest_path) if self.manifest_path else None

    def artifact(self, name: str) -> Path:
        for item in self.artifacts:
            if item.name == name:
                return item.path
        if self.output_directory:
            candidate = self.output_directory / name
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"Artifact not found: {name}")

    def read_json(self, name: str) -> Any:
        return json.loads(self.artifact(name).read_text(encoding="utf-8"))

    def verify_artifacts(self) -> None:
        for item in self.artifacts:
            if item.sha256:
                digest = hashlib.sha256(item.path.read_bytes()).hexdigest()
                if digest.lower() != item.sha256.lower():
                    raise ValueError(f"Artifact checksum mismatch: {item.path}")

    def copy_to(self, destination: str | Path) -> Path:
        if self.output_directory is None:
            raise FileNotFoundError("This result has no output directory to copy.")
        target = Path(destination)
        if target.exists():
            raise FileExistsError(f"Destination already exists: {target}")
        shutil.copytree(self.output_directory, target)
        return target

    def _repr_html_(self) -> str:
        path = html.escape(str(self.output_directory or "—"))
        diagnostics = "" if not self.diagnostics else "<br>" + "<br>".join(
            html.escape(f"{item.level}: {item.message}") for item in self.diagnostics
        )
        return (f"<div><strong>MVS {html.escape(self.command)}</strong> — {html.escape(self.status)}"
                f"<br>engine {html.escape(self.engine_version)}<br><code>{path}</code>{diagnostics}</div>")

    def read_csv(self, name: str, *, dataframe: bool = False):
        path = self.artifact(name)
        if dataframe:
            try:
                import pandas as pd  # type: ignore
            except ImportError as exc:
                raise ImportError("Install pandas to use dataframe=True") from exc
            return pd.read_csv(path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))


@dataclass(frozen=True)
class Calibration(BaseResult):
    @property
    def state_path(self) -> Path:
        return self.artifact("calibration_state.json")


@dataclass(frozen=True)
class AnalysisResult(BaseResult):
    pass


@dataclass(frozen=True)
class VarianceResult(BaseResult):
    pass


@dataclass(frozen=True)
class EstimationResult(BaseResult):
    pass


@dataclass(frozen=True)
class MelsmResult(BaseResult):
    pass


@dataclass(frozen=True)
class BenchmarkResult(BaseResult):
    pass
