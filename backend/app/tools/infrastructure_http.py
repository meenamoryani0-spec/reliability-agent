"""Fixed-host GET-only clients for documented infrastructure API operations."""

import asyncio
import json
import re
from functools import partial

import httpx
from pydantic import SecretStr

from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.infrastructure_models import InfrastructureError
from app.tools.targets import PinnedTransport, TargetError, validate_addresses

MAX_RESPONSE_BYTES = 1_048_576
PATHS = {
    "vercel": re.compile(
        r"/v13/deployments/dpl_[A-Za-z0-9]{1,100}"
        r"|/v3/deployments/dpl_[A-Za-z0-9]{1,100}/events"
    ),
    "supabase": re.compile(r"/v1/projects/[a-z]{20}(?:/health)?"),
}
HOSTS = {"vercel": "api.vercel.com", "supabase": "api.supabase.com"}


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InfrastructureError("invalid_response")
        result[key] = value
    return result


def reject_json_constant(_value):
    raise ValueError("Non-finite JSON number")


class InfrastructureHttp:
    def __init__(
        self,
        provider: str,
        token: SecretStr,
        *,
        timeout=10,
        nameservers=(),
        resolver=None,
        transport_factory=None,
    ):
        if provider not in HOSTS:
            raise ValueError("Unsupported infrastructure provider")
        self.provider = provider
        self._token = token
        self._timeout = timeout
        self._resolver = resolver or partial(resolve_addresses, nameservers=nameservers)
        self._transport_factory = transport_factory or (
            lambda: httpx.AsyncHTTPTransport(trust_env=False, retries=0)
        )

    async def get(self, path: str, params: dict[str, str] | None = None):
        if not PATHS[self.provider].fullmatch(path):
            raise InfrastructureError("invalid_request")
        host = HOSTS[self.provider]
        try:
            async with asyncio.timeout(self._timeout):
                addresses = validate_addresses(await self._resolver(host, self._timeout))
                async with httpx.AsyncClient(
                    transport=PinnedTransport(addresses[0], self._transport_factory()),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self._timeout,
                    headers={
                        "Authorization": "Bearer " + self._token.get_secret_value(),
                        "Accept": "application/json",
                    },
                ) as client:
                    async with client.stream(
                        "GET",
                        "https://" + host + path,
                        params=params or {},
                    ) as response:
                        if response.status_code != 200:
                            code = {
                                401: "authentication_failed",
                                403: "access_denied",
                                404: "not_found",
                                429: "rate_limited",
                            }.get(
                                response.status_code,
                                "redirect_rejected"
                                if 300 <= response.status_code < 400
                                else "provider_error",
                            )
                            raise InfrastructureError(code)
                        if (
                            response.headers.get("content-type", "").split(";")[0].lower()
                            != "application/json"
                        ):
                            raise InfrastructureError("invalid_response")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise InfrastructureError("response_too_large")
                            body.extend(chunk)
                try:
                    return json.loads(
                        body,
                        object_pairs_hook=json_object,
                        parse_constant=reject_json_constant,
                    )
                except (ValueError, RecursionError):
                    raise InfrastructureError("invalid_response") from None
        except (TimeoutError, httpx.TimeoutException):
            raise InfrastructureError("timeout") from None
        except httpx.RequestError:
            raise InfrastructureError("transport_error") from None
        except (TargetError, ResolutionError) as error:
            raise InfrastructureError(error.code) from None
