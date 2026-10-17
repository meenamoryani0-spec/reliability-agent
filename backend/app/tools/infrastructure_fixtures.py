"""Explicit local provider/driver fixtures; no external requests or database."""

import httpx
from pydantic import SecretStr

from app.tools.infrastructure_http import InfrastructureHttp
from app.tools.postgres import PostgresChecker

DEPLOYMENT_ID = "dpl_fixtureBooking"
PROJECT_REF = "abcdefghijklmnopqrst"
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_DATA_DO_NOT_RETURN"


async def fixture_resolver(_host, _timeout):
    return ["93.184.216.34"]


def provider_response(request):
    path = request.url.path
    if path == "/v13/deployments/" + DEPLOYMENT_ID:
        return httpx.Response(
            200,
            json={
                "id": DEPLOYMENT_ID,
                "readyState": "ERROR",
                "errorMessage": PRIVATE_MARKER,
                "env": {"PRIVATE": PRIVATE_MARKER},
            },
        )
    if path == "/v3/deployments/" + DEPLOYMENT_ID + "/events":
        return httpx.Response(
            200,
            json=[
                {
                    "type": "stderr",
                    "created": 1791720000000,
                    "payload": {"deploymentId": DEPLOYMENT_ID, "text": PRIVATE_MARKER},
                }
            ],
        )
    if path == "/v1/projects/" + PROJECT_REF:
        return httpx.Response(
            200,
            json={
                "id": PROJECT_REF,
                "ref": PROJECT_REF,
                "status": "ACTIVE_HEALTHY",
                "name": PRIVATE_MARKER,
                "database": {"host": PRIVATE_MARKER},
            },
        )
    if path == "/v1/projects/" + PROJECT_REF + "/health":
        return httpx.Response(
            200,
            json=[
                {"name": name, "status": "ACTIVE_HEALTHY", "healthy": True, "info": PRIVATE_MARKER}
                for name in ("db", "auth", "rest")
            ],
        )
    raise AssertionError("Unexpected fixture request")


class FixtureConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, *, prepare):
        from app.tools.postgres import PROBE_SQL

        if query != PROBE_SQL or prepare is not False:
            raise AssertionError("Unexpected fixture SQL")
        return self

    def fetchone(self):
        return (1, "on")


def fixture_clients(timeout=10):
    clients = [
        InfrastructureHttp(
            name,
            SecretStr("fixture-key"),
            timeout=timeout,
            resolver=fixture_resolver,
            transport_factory=lambda: httpx.MockTransport(provider_response),
        )
        for name in ("vercel", "supabase")
    ]
    postgres = PostgresChecker(
        "postgres-fixture.test",
        5432,
        "fixture",
        "fixture",
        SecretStr("fixture-password"),
        timeout=timeout,
        resolver=fixture_resolver,
        connect=lambda **_: FixtureConnection(),
    )
    return (*clients, postgres)
