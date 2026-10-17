"""Production entry point: validate before binding; one worker, no implicit migration."""

import json
import os
import re

import uvicorn

from app.config import Settings


def configure_platform_host():
    """Use Render's trusted service metadata when no exact hosts were supplied."""
    if os.environ.get("API_ALLOWED_HOSTS") or os.environ.get("RENDER") != "true":
        return
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com", hostname):
        raise SystemExit("Render startup requires its exact assigned service hostname")
    os.environ["API_ALLOWED_HOSTS"] = json.dumps([hostname])


def main():
    configure_platform_host()
    config = Settings()
    if config.environment != "production" or not config.deployment_access_configured:
        raise SystemExit("Production startup requires explicit access configuration")
    if config.storage_mode != "postgresql":
        raise SystemExit("Production startup requires PostgreSQL application storage")
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("Invalid port")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        proxy_headers=False,
        access_log=False,
        server_header=False,
        limit_concurrency=64,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=180,
        h11_max_incomplete_event_size=8192,
    )


if __name__ == "__main__":
    main()
