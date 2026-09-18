from __future__ import annotations

from pathlib import Path
from typing import Any

from .engine import (
    Engine,
    EngineCompatibilityError,
    EngineError,
    EngineNotFoundError,
    InputError,
    MvsError,
    ScientificDiagnostic,
)
from .models import (
    AnalysisResult,
    Artifact,
    BaseResult,
    BenchmarkResult,
    Calibration,
    Diagnostic,
    EstimationResult,
    MelsmResult,
    RunManifest,
    VarianceResult,
)

__all__ = [
    "Engine", "Calibration", "AnalysisResult", "VarianceResult", "EstimationResult", "MelsmResult",
    "BenchmarkResult", "RunManifest", "Diagnostic", "Artifact", "MvsError", "EngineNotFoundError",
    "EngineCompatibilityError", "InputError", "EngineError", "ScientificDiagnostic", "configure_engine",
    "calibrate", "analyze", "variance", "estimation", "melsm", "benchmark",
]

_engine: Engine | None = None


def configure_engine(executable: str | Path | None = None) -> Engine:
    global _engine
    _engine = Engine(executable)
    return _engine


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def calibrate(data, **kwargs: Any) -> Calibration:
    return _get_engine().calibrate(data, **kwargs)


def analyze(data, *, calibration, **kwargs: Any) -> AnalysisResult:
    return _get_engine().analyze(data, calibration=calibration, **kwargs)


def variance(data, **kwargs: Any) -> VarianceResult:
    return _get_engine().variance(data, **kwargs)


def estimation(**kwargs: Any) -> EstimationResult:
    return _get_engine().estimation(**kwargs)


def melsm(data, **kwargs: Any) -> MelsmResult:
    return _get_engine().melsm(data, **kwargs)


def benchmark(**kwargs: Any) -> BenchmarkResult:
    return _get_engine().benchmark(**kwargs)
