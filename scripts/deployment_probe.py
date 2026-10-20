"""Public liveness/readiness probes only; no credentials or application writes."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROBES = (
    ("backend", "https://reliability-agent-josr.onrender.com/ready", "ready"),
    ("frontend", "https://reliability-agent.vercel.app/api/health", "ok"),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def probe(url, expected_status):
    try:
        request = Request(url, headers={"User-Agent": "Reliability-Agent-Deployment-Probe/1"})
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                return {"passed": False, "reason": "unexpected_http_status"}
            if response.headers.get_content_type() != "application/json":
                return {"passed": False, "reason": "unexpected_content_type"}
            raw = response.read(2049)
            if len(raw) > 2048:
                return {"passed": False, "reason": "response_too_large"}
        body = json.loads(raw)
        passed = isinstance(body, dict) and body.get("status") == expected_status
        return {"passed": passed, "reason": "expected_status" if passed else "not_ready"}
    except HTTPError as error:
        return {"passed": False, "reason": "http_error", "http_status": error.code}
    except (URLError, TimeoutError, OSError):
        return {"passed": False, "reason": "request_failed"}
    except (ValueError, UnicodeError):
        return {"passed": False, "reason": "invalid_json"}


def check_deployment(*, read=probe, pause=time.sleep):
    results = {}
    for name, url, expected in PROBES:
        # A sleeping backend can return Render's HTML loading screen. Bound all
        # retries and retain failure rather than interpreting that screen as ready.
        attempts = 3 if name == "backend" else 1
        for attempt in range(attempts):
            result = dict(read(url, expected))
            result["attempts"] = attempt + 1
            if result["passed"] or result.get("http_status") in {401, 403}:
                break
            if attempt + 1 < attempts:
                pause(10)
        results[name] = result
    return {
        "result": "PASS" if all(item["passed"] for item in results.values()) else "NOT_READY",
        "checks": results,
        "coverage": "frontend_liveness_and_backend_storage_readiness",
        "business_outcome_verified": False,
    }


if __name__ == "__main__":
    result = check_deployment()
    print(json.dumps(result))
    raise SystemExit(0 if result["result"] == "PASS" else 1)
