"""Explicit synthetic preview. Uses a new scratch database and no live provider credentials."""

import argparse
import json
import time

from frontend_support import command, fixture_environment, frontend_server, seed
from smoke_support import ROOT, server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        raise ValueError("Use an unprivileged port")
    environment = fixture_environment()
    command(environment, "app.db.cli", "upgrade")
    logs = ROOT / "work/logs"
    logs.mkdir(parents=True, exist_ok=True)
    with server(environment, logs / "frontend-demo-backend.log") as backend:
        seed(backend, environment)
        with frontend_server(
            backend.base_url, port=arguments.port, name="frontend-demo"
        ) as frontend:
            print(
                json.dumps(
                    {
                        "preview": str(frontend.base_url),
                        "mode": "synthetic_fixture",
                        "live_provider_calls": False,
                        "scratch_database": environment["STORAGE_SQLITE_FILE"],
                    }
                ),
                flush=True,
            )
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
