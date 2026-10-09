"""Start a real Uvicorn process, verify HTTP responses, and stop that process."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parents[1]
log_directory = project_root / "work" / "logs"
log_directory.mkdir(parents=True, exist_ok=True)

with socket.socket() as reserved_socket:
    reserved_socket.bind(("127.0.0.1", 0))
    port = reserved_socket.getsockname()[1]

server_environment = {**os.environ, "ENVIRONMENT": "test", "LOG_LEVEL": "INFO"}
with (log_directory / "smoke-server.log").open("w", encoding="utf-8") as server_log:
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=project_root / "backend",
        env=server_environment,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=1
        ) as client:
            deadline = time.monotonic() + 20
            while True:
                if server.poll() is not None:
                    raise RuntimeError(
                        "Server exited before health check; see work/logs/smoke-server.log"
                    )
                try:
                    health = client.get("/health")
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Live HTTP check timed out") from None
                    time.sleep(0.2)

            health.raise_for_status()
            expected = {"status": "ok", "service": "reliability-agent-backend"}
            if health.json() != expected:
                raise RuntimeError("Unexpected health response")
            schema = client.get("/openapi.json")
            schema.raise_for_status()
            if "/health" not in schema.json()["paths"]:
                raise RuntimeError("Health is missing from OpenAPI")
            docs = client.get("/docs")
            docs.raise_for_status()
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "health_status": health.status_code,
                        "body": health.json(),
                        "docs_status": docs.status_code,
                    }
                )
            )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
