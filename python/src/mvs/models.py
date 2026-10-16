from __future__ import annotations

import csv
import json
import html
import hashlib
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


CURRENT_INVOCATION_ARTIFACT_SCOPE = "current_invocation_successful_writes"


def _validate_scoped_artifact_metadata(item: "Artifact") -> None:
    name = item.name
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or name.endswith((" ", "."))
            or any(char in '/\\:<>"|?*' or ord(char) < 32 or ord(char) == 127 for char in name)
            or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL",
                                              *(f"COM{i}" for i in range(1, 10)),
                                              *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError(f"Unsafe scoped artifact name: {name!r}")
    if type(item.size_bytes) is not int or item.size_bytes < 0:
        raise ValueError(f"Invalid scoped artifact size: {name}")
    if (not isinstance(item.sha256, str) or len(item.sha256) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in item.sha256)):
        raise ValueError(f"Invalid scoped artifact checksum: {name}")


def _reject_scoped_links(path: Path) -> None:
    # Include ancestors: checking the leaf alone misses a redirected parent.
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Links and reparse points are not supported in scoped paths: {component}")


def _verify_scoped_file(path: Path, item: "Artifact") -> None:
    # Reject existing special paths before opening; this is not a race-proof sandbox.
    _reject_scoped_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Scoped artifact is not a regular file: {path}")
    if info.st_size != item.size_bytes:
        raise ValueError(f"Artifact size mismatch: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest().lower() != item.sha256.lower():
        raise ValueError(f"Artifact checksum mismatch: {path}")


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
        if self._has_scoped_artifacts() and self.manifest_path:
            path = self.artifact(self.manifest_path.name)
            if path != self.manifest_path:
                raise ValueError("Manifest path does not match its scoped artifact.")
            return RunManifest.load(path)
        return RunManifest.load(self.manifest_path) if self.manifest_path else None

    def _has_scoped_artifacts(self) -> bool:
        if "artifactScope" not in self.raw:
            return False
        if self.raw["artifactScope"] != CURRENT_INVOCATION_ARTIFACT_SCOPE:
            raise ValueError(f"Unsupported artifact scope: {self.raw['artifactScope']!r}")
        return True

    def _scoped_artifacts(self) -> tuple[Artifact, ...]:
        output = self.output_directory
        if output is None:
            raise ValueError("Scoped artifacts require an output directory.")
        if not output.is_absolute() or ".." in output.parts:
            raise ValueError("Scoped output directory must be an absolute, non-traversing path.")
        # A link or Windows reparse point must not redirect the declared root.
        _reject_scoped_links(output)
        info = output.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Scoped output is not a regular directory: {output}")
        names = set()
        for item in self.artifacts:
            _validate_scoped_artifact_metadata(item)
            key = item.name.casefold()
            if key in names:
                raise ValueError(f"Duplicate scoped artifact name: {item.name}")
            names.add(key)
            if (not item.path.is_absolute() or ".." in item.path.parts
                    or item.path != output / item.name):
                raise ValueError(f"Scoped artifact path does not match its output name: {item.name}")
            info = item.path.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Scoped artifact is not a regular file: {item.path}")
        return self.artifacts

    def artifact(self, name: str) -> Path:
        if self._has_scoped_artifacts():
            for item in self._scoped_artifacts():
                if item.name == name:
                    _verify_scoped_file(item.path, item)
                    return item.path
            raise FileNotFoundError(f"Artifact not found: {name}")
        for item in self.artifacts:
            if item.name == name:
                return item.path
        if self.output_directory and self.status != "error":
            candidate = self.output_directory / name
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"Artifact not found: {name}")

    def read_json(self, name: str) -> Any:
        return json.loads(self.artifact(name).read_text(encoding="utf-8"))

    def verify_artifacts(self) -> None:
        if self._has_scoped_artifacts():
            for item in self._scoped_artifacts():
                _verify_scoped_file(item.path, item)
            return
        for item in self.artifacts:
            if item.sha256:
                digest = hashlib.sha256(item.path.read_bytes()).hexdigest()
                if digest.lower() != item.sha256.lower():
                    raise ValueError(f"Artifact checksum mismatch: {item.path}")

    def copy_to(self, destination: str | Path) -> Path:
        """Copy output, using only verified declared files for scoped results.

        Scoped metadata and content are checked before creating the destination.
        Copying is not a transaction or a concurrent-writer snapshot: an I/O error
        or a file changed during copying can leave a partial destination behind.
        """
        if self.status == "error":
            raise ValueError("Cannot copy incomplete output from a failed result.")
        if self.output_directory is None:
            raise FileNotFoundError("This result has no output directory to copy.")
        target = Path(destination)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Destination already exists: {target}")
        if self._has_scoped_artifacts():
            artifacts = self._scoped_artifacts()
            _reject_scoped_links(target)
            for item in artifacts:
                _verify_scoped_file(item.path, item)
            target.mkdir(parents=True)
            for item in artifacts:
                _verify_scoped_file(item.path, item)
                copied = target / item.name
                shutil.copy2(item.path, copied, follow_symlinks=False)
                _verify_scoped_file(copied, item)
        else:
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
