#!/usr/bin/env python3
"""Build the two shipped Colab notebooks deterministically. Does not execute Colab."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]

def notebook_bytes(mode):
    helper = (ROOT / "notebooks/mvs_colab.py").read_text(encoding="utf-8-sig").replace("from __future__ import annotations\n", "")
    first = '''# @title 1 · Connect and control from MVS · Подключение и управление из MVS
from __future__ import annotations
# Runtime -> Change runtime type -> Python 3 / CPU. No new Drive copy is required.
REPOSITORY_REF = "main" # @param {type:"string"}
MODE = "MODE_DEFAULT" # @param ["standard", "variance", "melsm", "estimation", "benchmark"]
DESKTOP_CONTROL = True # @param {type:"boolean"}
RESET_CONNECTION = False # @param {type:"boolean"}

'''.replace("MODE_DEFAULT", mode) + helper + '''
# A saved calibration is validated and reused. The controller's running cell is not a busy job.
from getpass import getpass
_mvs_previous = globals().get("mvs")
if getattr(_mvs_previous, "controls_ready", False):
    raise RuntimeError("Stop the previous controller cell before reconnecting.")
_mvs_error = getattr(_mvs_previous, "connection_error", None)
_mvs_fresh_code = RESET_CONNECTION or _mvs_previous is None or getattr(_mvs_error, "code", "") in {"connection_revoked", "runtime_conflict", "status_conflict", "stale_status", "wrong_job"}
if _mvs_fresh_code:
    _mvs_code = getpass("MVS connection code / Код подключения (empty = manual upload / пусто = ручная загрузка): ").strip()
else:
    _mvs_code = _mvs_previous.connection
# Runtime code comes only from this approved local job, verified against its manifest.
# Existing ui-colab-3 desktops use the compatible controller embedded in this notebook.
mvs = bootstrap_workspace(connection=_mvs_code, ref=REPOSITORY_REF, mode=MODE,
                          desktop_control=DESKTOP_CONTROL, previous=None if RESET_CONNECTION else _mvs_previous)
RunCancelled = getattr(mvs, "cancel_exception", RunCancelled)
del _mvs_code, _mvs_previous, _mvs_error, _mvs_fresh_code
try:
    mvs.activate()
    if mvs.connection and DESKTOP_CONTROL:
        mvs.serve()  # Intentionally stays running. Use the separate MVS window, not cells 2/3.
    else:
        mvs.calibrate()  # Manual CSV/ZIP workflow remains available.
except (KeyboardInterrupt, RunCancelled):
    mvs.phase = "cancelled"; mvs.controls_ready = False; mvs.send(); raise
except Exception:
    mvs.phase = "failed"; mvs.controls_ready = False; mvs.send(); raise
'''
    second = '''# @title 2 · Manual analysis / additional method · Ручной анализ
# In desktop-control mode, use Analyze in MVS. This cell is the manual fallback.
if "mvs" not in globals() or mvs.dll is None:
    raise RuntimeError("Run the first cell successfully before this cell.")
if mvs.controls_ready:
    raise RuntimeError("Use Analyze in the MVS app, or stop the controller cell to switch to manual mode.")
try:
    mvs.analyze()
except (KeyboardInterrupt, RunCancelled):
    mvs.phase = "cancelled"; mvs.send(); raise
except Exception:
    mvs.phase = "failed"; mvs.send(); raise
'''
    third = '''# @title 3 · Manual results ZIP download · Ручное скачивание результатов
# Output only: no original input file, connection code or source bundle is included.
if "mvs" not in globals() or mvs.folder is None:
    raise RuntimeError("Run the preceding cells first.")
if mvs.controls_ready:
    raise RuntimeError("Use Download results in the MVS app, or stop the controller cell first.")
mvs.download()
'''
    name = "MVS_Colab_Benchmark.ipynb" if mode == "benchmark" else "MVS_Colab.ipynb"
    book = {"cells": [
        {"cell_type": "code", "execution_count": None, "metadata": {"id": id_, "cellView": "form"}, "outputs": [], "source": text.splitlines(True)}
        for id_, text in zip(("mvs-calibrate", "mvs-analyze", "mvs-download"), (first, second, third))],
        "metadata": {"colab": {"name": name, "private_outputs": True},
                     "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"},
                     "mvs": {"appVersion": "1.4.0", "engineVersion": "1.6.0", "revision": "ui-colab-3", "helper": "mvs_colab.py",
                             "note": "Use the matching MVS desktop and notebook controller. Saved calibration is reused only after identity and integrity checks."}},
        "nbformat": 4, "nbformat_minor": 0}
    return (json.dumps(book, ensure_ascii=False, indent=1) + "\n").encode("utf-8")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for mode in ("standard", "benchmark"):
        name = "MVS_Colab_Benchmark.ipynb" if mode == "benchmark" else "MVS_Colab.ipynb"
        path = ROOT / "notebooks" / name
        expected = notebook_bytes(mode)
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                raise SystemExit("Stale notebook: " + name + ". Run python tools/build_notebooks.py")
        else:
            path.write_bytes(expected)
        print("Verified" if args.check else "Built", name)

if __name__ == "__main__":
    main()
