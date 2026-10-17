"""Explicit post-deployment acceptance checks. No provider/monitoring/remediation calls."""

import argparse
import json
import os
from urllib.parse import urlsplit

import httpx


def canonical_origin(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise ValueError("Canonical HTTPS origin required")
    return value.rstrip("/")


def require(condition):
    if not condition:
        raise RuntimeError("Deployment acceptance check failed")


def bounded_get(client, path, headers=None):
    with client.stream("GET", path, headers=headers) as response:
        data = bytearray()
        for part in response.iter_bytes():
            if len(data) + len(part) > 1_048_576:
                raise RuntimeError("Deployment response exceeded acceptance limit")
            data.extend(part)
        return response.status_code, json.loads(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", required=True)
    parser.add_argument("--backend", required=True)
    arguments = parser.parse_args()
    try:
        frontend, backend = map(canonical_origin, (arguments.frontend, arguments.backend))
        operator = os.environ.get("RA_DEPLOYMENT_OPERATOR_KEY", "")
        token = os.environ.get("API_ACCESS_TOKEN", "")
        require(43 <= len(operator) <= 128 and 43 <= len(token) <= 128)
        with httpx.Client(base_url=backend, trust_env=False, timeout=10) as api:
            status, health = bounded_get(api, "/health")
            require(status == 200 and health.get("status") == "ok")
            status, ready = bounded_get(api, "/ready")
            require(status == 200 and ready == {"status": "ready"})
            require(api.get("/history/checks?limit=1").status_code == 401)
            status, checks = bounded_get(
                api, "/history/checks?limit=1", {"Authorization": f"Bearer {token}"}
            )
            require(status == 200 and isinstance(checks, list) and len(checks) <= 1)
        with httpx.Client(base_url=frontend, trust_env=False, timeout=20) as ui:
            require(ui.get("/api/dashboard").status_code == 403)
            signed_in = False
            try:
                response = ui.post(
                    "/api/session", headers={"Origin": frontend}, json={"key": operator}
                )
                require(response.status_code == 200)
                signed_in = True
                cookie = response.headers.get("set-cookie", "")
                require(all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=strict")))
                status, snapshot = bounded_get(ui, "/api/dashboard")
                require(status == 200 and snapshot["storage"]["data"]["state"] == "ready")
                require(snapshot["health"]["data"]["status"] == "ok")
                require(snapshot["checks"]["data"] is not None)
                require(token not in json.dumps(snapshot) and operator not in json.dumps(snapshot))
            finally:
                if signed_in:
                    logout = ui.delete(
                        "/api/session",
                        headers={"Origin": frontend, "Content-Type": "application/json"},
                    )
                    require(logout.status_code == 200)
            require(ui.get("/api/dashboard").status_code == 403)
        print(json.dumps({"result": "PASS", "deployed_auth_tls_storage": True}))
        return 0
    except (ValueError, KeyError, TypeError, RuntimeError, httpx.HTTPError):
        # No response body, URL, question or credential is echoed on failure.
        print(json.dumps({"result": "NOT_VERIFIED", "deployed_auth_tls_storage": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
