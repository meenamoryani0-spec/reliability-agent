"""Read the exact accepted retry; fixtures never establish a real customer outcome."""

import httpx
from pydantic import SecretStr

from app.db.models import now
from app.tools.n8n import N8nClient, N8nService
from app.tools.n8n_fixtures import FIXTURE_BASE, FIXTURE_KEY, execution_record


async def read_execution(config, action):
    if config.n8n_recovery_mode == "fixture":

        async def resolver(_host, _timeout):
            return ["93.184.216.34"]

        def handler(request):
            if request.method != "GET" or request.url.path != "/api/v1/executions/2001":
                return httpx.Response(404)
            record = execution_record("2001", failed=False)
            record.update(
                mode="retry",
                retryOf="1001",
                startedAt=action["dispatch_started_at"].isoformat(),
                stoppedAt=now().isoformat(),
            )
            return httpx.Response(200, json=record)

        client = N8nClient(
            FIXTURE_BASE,
            SecretStr(FIXTURE_KEY),
            resolver=resolver,
            transport_factory=lambda: httpx.MockTransport(handler),
        )
    else:
        client = N8nClient(
            config.n8n_base_url,
            config.n8n_api_key,
            timeout=config.n8n_timeout_seconds,
            nameservers=config.n8n_dns_nameservers,
        )
    return await N8nService(config.n8n_recovery_mode, client).read(
        "execution", execution_id=action["new_execution_id"]
    )
