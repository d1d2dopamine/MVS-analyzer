"""Local workflow CLI. Existing `mvs` remains the native statistical CLI."""
from __future__ import annotations
import argparse
import json
import signal
import sys
import threading
from .workflow import WorkflowError, WorkflowService, envelope, strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded local summary workflow; JSON request on stdin. Linux and experimental Windows local NTFS.")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--read-root", required=True)
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("operation", choices=["register_protocol", "get_protocol", "run_analysis", "get_run", "read_artifact"])
    args = parser.parse_args(argv)
    cancel = threading.Event()
    old = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768: raise WorkflowError("request_too_large", "Request exceeds 32 KiB.")
        request = strict_json(raw)
        service = WorkflowService(args.engine, args.read_root, args.work_root, args.timeout_seconds)
        result = service.dispatch(args.operation, request, cancel)
    except WorkflowError as exc:
        result = envelope(status="error", error={"code": exc.code, "message": str(exc)})
    except (ValueError, TypeError, UnicodeError):
        result = envelope(status="error", error={"code": "invalid_json", "message": "Expected one strict JSON request object."})
    except OSError:
        result = envelope(status="error", error={"code": "storage_error", "message": "Local workflow storage is unavailable."})
    finally:
        signal.signal(signal.SIGINT, old)
    # Machine output is UTF-8 even when Windows pipes inherit a legacy codepage.
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    status = result["execution"]["status"]
    if status == "incomplete": return 3
    if status != "completed": return 1
    return 2 if result["execution"]["nativeExitCode"] == 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
