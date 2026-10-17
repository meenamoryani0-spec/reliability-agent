"""Real built Next.js/Uvicorn production auth over verified disposable local TLS.

No provider/model calls. No deployed resources. No browser certificate bypass.
Production storage is disabled in this HTTP boundary harness, so readiness MUST
be 503; migrations/storage are tested separately on isolated SQLite/PostgreSQL.
"""

import hashlib
import json
import secrets
import ssl

import httpx
from deployment_support import certificate, free_port, production_backend, tls_frontend_proxy
from frontend_support import fixture_environment, frontend_server
from smoke_support import ROOT


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    directory = ROOT / "work" / "deployment-smoke" / secrets.token_hex(8)
    directory.mkdir(parents=True)
    (ROOT / "work/logs").mkdir(parents=True, exist_ok=True)
    paths = certificate(directory)
    trust = ssl.create_default_context(cafile=str(paths["ca"]))
    operator, backend_key, signing_key = (secrets.token_urlsafe(32) for _ in range(3))
    environment = {
        **fixture_environment(),
        "ENVIRONMENT": "production",
        "STORAGE_MODE": "disabled",
        "API_ACCESS_TOKEN": backend_key,
        "INCIDENTS_ENABLED": "false",
        "INVESTIGATION_MODE": "disabled",
        "N8N_MODE": "disabled",
        "N8N_RETRY_MODE": "disabled",
        "N8N_RECOVERY_MODE": "disabled",
        "INFRASTRUCTURE_MODE": "disabled",
    }
    with production_backend(environment, paths, trust) as backend:
        require(backend.get("/history/checks").status_code == 401, "Backend history is public")
        require(backend.get("/ready").status_code == 503, "Disabled storage must not be ready")
        headers = {"Authorization": f"Bearer {backend_key}"}
        require(backend.get("/agent", headers=headers).status_code == 200, "Service auth failed")
        require(
            backend.get("/agent", headers={**headers, "Origin": "https://evil.example"}).status_code
            == 401,
            "Backend accepted browser-origin credentials",
        )
        require(
            backend.get("/health", headers={"Host": "evil.example"}).status_code == 400,
            "Backend trusted hostile Host",
        )
        frontend_port = free_port()
        with tls_frontend_proxy(frontend_port, paths) as origin:
            overrides = {
                "RELIABILITY_DASHBOARD_MODE": "production",
                "RELIABILITY_PUBLIC_ORIGIN": origin,
                "RELIABILITY_BACKEND_TOKEN": backend_key,
                "RELIABILITY_SESSION_KEY": signing_key,
                "RELIABILITY_OPERATOR_KEY_SHA256": hashlib.sha256(operator.encode()).hexdigest(),
                "NODE_EXTRA_CA_CERTS": str(paths["ca"]),
                "NODE_TLS_REJECT_UNAUTHORIZED": "1",
            }
            with frontend_server(
                backend.base_url,
                port=frontend_port,
                name="phase-14-frontend",
                overrides=overrides,
                standalone=True,
            ):
                with httpx.Client(
                    base_url=origin, verify=trust, trust_env=False, timeout=20
                ) as client:
                    require(client.get("/").status_code == 200, "Product page unavailable")
                    response = client.get("/dashboard")
                    require(response.status_code == 307, "Unauthenticated dashboard rendered")
                    require(response.headers["location"] == "/login", "Wrong sign-in redirect")
                    require(client.get("/login").status_code == 200, "Login page failed")
                    require(client.get("/api/dashboard").status_code == 403, "API is public")
                    require(
                        client.post("/api/session", json={"key": operator}).status_code == 403,
                        "Originless login accepted",
                    )
                    require(
                        client.post(
                            "/api/session",
                            headers={"Origin": "https://evil.example"},
                            json={"key": operator},
                        ).status_code
                        == 403,
                        "Cross-origin login accepted",
                    )
                    origin_headers = {"Origin": origin}
                    require(
                        client.post(
                            "/api/session", headers=origin_headers, json={"key": "wrong"}
                        ).status_code
                        == 401,
                        "Invalid key accepted",
                    )
                    response = client.post(
                        "/api/session", headers=origin_headers, json={"key": operator}
                    )
                    require(response.status_code == 200, "Operator sign-in failed")
                    cookie = response.headers["set-cookie"]
                    for attribute in (
                        "__Host-reliability-session=",
                        "HttpOnly",
                        "Secure",
                        "SameSite=strict",
                        "Path=/",
                        "Max-Age=28800",
                    ):
                        require(attribute in cookie, "Session cookie attribute missing")
                    require("Domain=" not in cookie, "Session cookie set a domain")
                    require(client.get("/dashboard").status_code == 200, "Signed-in page blocked")
                    response = client.get("/api/dashboard")
                    response.raise_for_status()
                    data = response.json()
                    require(data["health"]["data"]["status"] == "ok", "BFF auth/TLS failed")
                    require(data["agent"]["data"]["mode"] == "disabled", "Agent mode changed")
                    require(data["checks"]["data"] is None, "Storage failure was hidden")
                    for secret in (operator, backend_key, signing_key):
                        require(secret not in response.text, "Secret returned in browser data")
                    require(response.headers["cache-control"] == "no-store", "API response cached")
                    require(
                        client.get(
                            "/api/dashboard",
                            headers={"Host": "evil.example", "X-Forwarded-Host": origin},
                        ).status_code
                        == 403,
                        "BFF accepted hostile Host",
                    )
                    for path in ("/api/actions", "/api/recovery", "/api/resolve"):
                        require(client.post(path).status_code == 404, "Browser remediation route")
                    response = client.delete(
                        "/api/session",
                        headers={**origin_headers, "Content-Type": "application/json"},
                    )
                    require(response.status_code == 200, "Sign-out failed")
                    require("Max-Age=0" in response.headers["set-cookie"], "Cookie not expired")
                    require(client.get("/api/dashboard").status_code == 403, "Sign-out ineffective")
    result = {
        "result": "PASS",
        "real_built_nextjs_and_uvicorn": True,
        "production_mode": True,
        "verified_local_tls_both_connections": True,
        "operator_login_secure_cookie_logout": True,
        "unauthenticated_dashboard_blocked": True,
        "backend_service_auth_host_and_origin": True,
        "server_credentials_absent_from_browser_data": True,
        "no_http_remediation": True,
        "storage_disabled_readiness_503": True,
        "cloud_storage_and_container_runtime_verified": False,
        "live_provider_calls": False,
    }
    (ROOT / "work/evidence").mkdir(parents=True, exist_ok=True)
    (ROOT / "work/evidence/phase-14-local-production-smoke.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
