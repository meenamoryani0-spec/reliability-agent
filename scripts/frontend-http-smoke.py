"""Built frontend HTTP/asset checks, without browser automation or live providers.

This does not establish visual correctness, responsive layout, or UI interaction.
"""

import json
from html.parser import HTMLParser

from frontend_support import fixture_environment, frontend_server
from smoke_support import ROOT, server


class Stylesheets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.paths.add(attributes["href"])


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    environment = {
        **fixture_environment(),
        "STORAGE_MODE": "disabled",
        "INCIDENTS_ENABLED": "false",
        "INVESTIGATION_MODE": "disabled",
        "N8N_RETRY_MODE": "disabled",
        "N8N_RECOVERY_MODE": "disabled",
    }
    logs = ROOT / "work/logs"
    logs.mkdir(parents=True, exist_ok=True)
    with server(environment, logs / "frontend-http-backend.log") as backend:
        with frontend_server(backend.base_url, name="frontend-http") as frontend:
            home = frontend.get("/")
            home.raise_for_status()
            require("Find the failure." in home.text, "New homepage not served")
            require("Illustrative example" in home.text, "Example disclosure missing")
            require('href="/dashboard"' in home.text, "Application entry missing")
            workspace = frontend.get("/dashboard")
            workspace.raise_for_status()
            require("Reliability overview" in workspace.text, "Workspace missing")
            require("Open navigation" in workspace.text, "Phone navigation missing")
            styles = Stylesheets()
            styles.feed(home.text)
            styles.feed(workspace.text)
            require(bool(styles.paths), "No stylesheet links in rendered pages")
            css = []
            for path in styles.paths:
                require(path.startswith("/_next/static/"), "Unexpected external stylesheet")
                response = frontend.get(path)
                response.raise_for_status()
                require("text/css" in response.headers["content-type"], "CSS MIME invalid")
                css.append(response.text)
            combined = "\n".join(css)
            for selector in (".system-map", ".mobile-menu-button", ".landing-hero"):
                require(selector in combined, f"Missing compiled styling: {selector}")
            require("#14171a" in combined.lower(), "Graphite canvas styling missing")
            response = frontend.get("/api/dashboard")
            response.raise_for_status()
            require(response.headers["cache-control"] == "no-store", "History cached")
            data = response.json()
            require(data["health"]["data"]["status"] == "ok", "Backend connection failed")
            require(data["checks"]["data"] is None, "Unavailable history hidden")
            require(data["agent"]["data"]["mode"] == "disabled", "Agent mode misreported")
            for path in ("/api/actions", "/api/recovery", "/api/resolve"):
                require(frontend.post(path).status_code == 404, "Remediation route exposed")
    result = {
        "result": "PASS",
        "built_pages_and_compiled_css_served": True,
        "stylesheet_count": len(styles.paths),
        "backend_connected_and_unavailable_history_explicit": True,
        "no_http_remediation": True,
        "live_provider_calls": False,
        "visual_or_interaction_verification": False,
    }
    evidence = ROOT / "work/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "stitch-frontend-http.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
