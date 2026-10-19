"""Production service authentication. Browser credentials never reach this API."""

import hashlib
import hmac
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse


def require_authenticated(request):
    from fastapi import HTTPException

    if request.app.state.settings.environment == "production" and not getattr(
        request.state, "authenticated", False
    ):
        raise HTTPException(status_code=404, detail="Access unavailable")


class AccessBoundary:
    """Authenticate before routing/body reads; no forwarding-header trust or CORS.

    One worker is the supported deployment. The bounded token bucket is per process,
    not a distributed quota. Hosting edge limits are still needed for public traffic.
    """

    def __init__(self, app, config):
        self.app, self.config = app, config
        self.tokens, self.updated = 120.0, time.monotonic()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        event_ingest = scope["path"] == "/integrations/n8n/failures"
        if self.config.environment != "production" and not event_ingest:
            await self.app(scope, receive, secure_send)
            return
        headers = Headers(scope=scope)
        public = scope["path"] in {"/health", "/ready"} and scope["method"] in {"GET", "HEAD"}
        if self.config.deployment_access_configured:
            hosts = headers.getlist("host")
            if len(hosts) != 1 or hosts[0].lower() not in self.config.api_allowed_hosts:
                await reject(400, "Invalid host")
                return
        if public:
            await self.app(scope, receive, secure_send)
            return
        if event_ingest:
            if not self.config.n8n_events_enabled or scope["method"] != "POST":
                await reject(404, "Access unavailable")
                return
            token = self.config.n8n_events_token
        elif not self.config.deployment_access_configured:
            await reject(404, "Access unavailable")
            return
        else:
            token = self.config.api_access_token
        # This is a server-to-server API. Browser origins/cookies are never authority.
        authorization = headers.getlist("authorization")
        expected = "Bearer " + token.get_secret_value()
        candidate = authorization[0] if len(authorization) == 1 else ""
        if (
            len(candidate) > 256
            or "origin" in headers
            or not hmac.compare_digest(
                hashlib.sha256(candidate.encode()).digest(),
                hashlib.sha256(expected.encode()).digest(),
            )
        ):
            await reject(401, "Authentication required")
            return
        now = time.monotonic()
        self.tokens = min(120.0, self.tokens + (now - self.updated) * 2)
        self.updated = now
        if self.tokens < 1:
            await reject(429, "Request limit reached")
            return
        self.tokens -= 1
        scope.setdefault("state", {})["authenticated"] = not event_ingest
        scope["state"]["n8n_report_authenticated"] = event_ingest
        await self.app(scope, receive, secure_send)
