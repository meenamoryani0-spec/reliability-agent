"""One browser worker at a time with a deadline and process-tree cleanup."""

import asyncio
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from pydantic import ValidationError

from app.tools.browser_models import FLOW_IDS, BrowserEvidence, BrowserFlowResult, FlowId
from app.tools.models import CheckStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER_TIMEOUT_SECONDS = 30


def failed_result(flow_id: FlowId, reason: str) -> BrowserFlowResult:
    return BrowserFlowResult(
        component=flow_id,
        status=CheckStatus.CHECK_FAILED,
        severity="error",
        summary="Synthetic browser check could not complete",
        evidence=BrowserEvidence(reason=reason),
    )


def stop_worker(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        # PID comes directly from our own Popen; no user-controlled shell command.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


class BrowserChecker:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    async def check(self, flow_id: FlowId) -> BrowserFlowResult:
        if flow_id not in FLOW_IDS:
            raise ValueError("Browser flow is not configured")
        return await asyncio.to_thread(self._check_sync, flow_id)

    def _check_sync(self, flow_id: FlowId) -> BrowserFlowResult:
        if not self._lock.acquire(blocking=False):
            return failed_result(flow_id, "browser_busy")
        process = None
        try:
            # Provider secrets and proxy settings are not inherited by the browser worker.
            worker_env = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}
            }
            temporary = PROJECT_ROOT / "work" / "tmp"
            temporary.mkdir(parents=True, exist_ok=True)
            worker_env.update(
                TEMP=str(temporary),
                TMP=str(temporary),
                PLAYWRIGHT_BROWSERS_PATH=str(PROJECT_ROOT / "work" / "browsers"),
                PYTHONPYCACHEPREFIX=str(PROJECT_ROOT / "work" / "cache" / "pycache"),
                PYTHONUTF8="1",
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "app.tools.browser_worker", flow_id],
                cwd=PROJECT_ROOT / "backend",
                env=worker_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                start_new_session=sys.platform != "win32",
            )
            output, _ = process.communicate(timeout=WORKER_TIMEOUT_SECONDS)
            if process.returncode != 0:
                return failed_result(flow_id, "browser_worker_failed")
            if len(output) > 16384:
                return failed_result(flow_id, "browser_worker_invalid_output")
            try:
                result = BrowserFlowResult.model_validate_json(output)
            except ValidationError:
                return failed_result(flow_id, "browser_worker_invalid_output")
            if result.component != flow_id:
                return failed_result(flow_id, "browser_worker_invalid_output")
            return result
        except subprocess.TimeoutExpired:
            return failed_result(flow_id, "browser_timeout")
        except (OSError, UnicodeError):
            return failed_result(flow_id, "browser_worker_failed")
        finally:
            try:
                if process is not None and process.poll() is None:
                    stop_worker(process)
            finally:
                if process is not None and process.stdout is not None:
                    process.stdout.close()
                self._lock.release()
