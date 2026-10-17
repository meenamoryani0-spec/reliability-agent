"""Read-only public n8n adapter with pinned public destinations and explicit modes."""

import asyncio
import json
import re
from collections.abc import Callable
from functools import partial

import httpx
from pydantic import SecretStr, TypeAdapter

from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.n8n_models import Cursor, ExecutionId, N8nReadResult, ResourceId, validate_n8n_url
from app.tools.n8n_normalize import (
    N8nError,
    ProviderPage,
    execution_evidence,
    execution_summary,
    normalize_errors,
    workflow_summary,
)
from app.tools.targets import PinnedTransport, TargetError, validate_addresses

MAX_RESPONSE_BYTES = 1_048_576


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise N8nError("invalid_response")
        result[key] = value
    return result


class N8nClient:
    def __init__(
        self,
        base_url: str,
        api_key: SecretStr,
        *,
        timeout: float = 10,
        nameservers: tuple[str, ...] = (),
        resolver=None,
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
    ):
        self._base = httpx.URL(validate_n8n_url(base_url))
        self._key = api_key
        self._timeout = timeout
        self._resolver = resolver or partial(resolve_addresses, nameservers=nameservers)
        self._transport_factory = transport_factory or (
            lambda: httpx.AsyncHTTPTransport(trust_env=False, retries=0)
        )

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        return await self._request("GET", path, params)

    async def _request(self, method: str, path: str, params: dict[str, str]) -> dict:
        read = method == "GET" and re.fullmatch(r"workflows|executions(?:/[1-9][0-9]{0,18})?", path)
        retry = (
            method == "POST"
            and re.fullmatch(r"executions/[1-9][0-9]{0,18}/retry", path)
            and not params
        )
        if not (read or retry):
            raise N8nError("invalid_request")
        try:
            async with asyncio.timeout(self._timeout):
                addresses = validate_addresses(await self._resolver(self._base.host, self._timeout))
                transport = PinnedTransport(addresses[0], self._transport_factory())
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self._timeout,
                    headers={
                        "X-N8N-API-KEY": self._key.get_secret_value(),
                        "Accept": "application/json",
                    },
                ) as client:
                    async with client.stream(
                        method,
                        self._base.join(path),
                        params=params,
                        **({"json": {"loadWorkflow": False}} if retry else {}),
                    ) as response:
                        if response.status_code != 200:
                            code = {
                                401: "authentication_failed",
                                403: "access_denied",
                                404: "not_found",
                                429: "rate_limited",
                            }.get(response.status_code)
                            if code is None:
                                code = (
                                    "redirect_rejected"
                                    if 300 <= response.status_code < 400
                                    else "provider_error"
                                )
                            raise N8nError(code)
                        if (
                            response.headers.get("content-type", "").split(";")[0].lower()
                            != "application/json"
                        ):
                            raise N8nError("invalid_response")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise N8nError("response_too_large")
                            body.extend(chunk)
                try:
                    raw = json.loads(body, object_pairs_hook=unique_json_object)
                except (ValueError, RecursionError):
                    raise N8nError("invalid_response") from None
                if not isinstance(raw, dict):
                    raise N8nError("invalid_response")
                return raw
        except (httpx.TimeoutException, TimeoutError):
            raise N8nError("timeout") from None
        except httpx.RequestError:
            raise N8nError("transport_error") from None
        except (TargetError, ResolutionError) as error:
            raise N8nError(error.code) from None

    @staticmethod
    def _page_params(limit: int, cursor: str | None) -> dict[str, str]:
        if type(limit) is not int or not 1 <= limit <= 50:
            raise N8nError("invalid_request")
        params = {"limit": str(limit)}
        if cursor is not None:
            params["cursor"] = normalize_errors(lambda: TypeAdapter(Cursor).validate_python(cursor))
        return params

    async def workflows(self, *, limit=25, cursor=None) -> dict:
        params = self._page_params(limit, cursor)
        params["excludePinnedData"] = "true"
        return await self._get("workflows", params)

    async def failed_executions(self, *, limit=25, cursor=None, workflow_id=None) -> dict:
        params = {**self._page_params(limit, cursor), "status": "error", "includeData": "false"}
        if workflow_id is not None:
            params["workflowId"] = normalize_errors(
                lambda: TypeAdapter(ResourceId).validate_python(workflow_id)
            )
        return await self._get("executions", params)

    async def execution(self, execution_id: str) -> dict:
        value = normalize_errors(lambda: TypeAdapter(ExecutionId).validate_python(execution_id))
        return await self._get(f"executions/{value}", {"includeData": "true"})


class N8nService:
    def __init__(self, mode: str, client: N8nClient | None = None):
        self.mode = mode
        self._client = client

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "configured": self._client is not None,
            "synthetic": self.mode == "fixture",
        }

    async def read(self, operation: str, **options) -> N8nReadResult:
        synthetic = self.mode == "fixture"
        if operation not in {"workflows", "failed_executions", "execution"}:
            raise ValueError("Unsupported n8n read operation")
        try:
            if self.mode == "disabled":
                raise N8nError("integration_disabled")
            if self._client is None:
                raise N8nError("missing_configuration")
            raw = await getattr(self._client, operation)(**options)
            result = N8nReadResult(operation=operation, status="OK", synthetic=synthetic)
            if operation == "execution":
                result.execution = normalize_errors(lambda: execution_evidence(raw))
                if result.execution.id != options["execution_id"]:
                    raise N8nError("execution_identity_mismatch")
            else:
                page = normalize_errors(lambda: ProviderPage.model_validate(raw))
                if len(page.data) > options.get("limit", 25):
                    raise N8nError("invalid_response")
                result.next_cursor = page.nextCursor
                if operation == "workflows":
                    result.workflows = normalize_errors(
                        lambda: [workflow_summary(x) for x in page.data]
                    )
                else:
                    result.executions = normalize_errors(
                        lambda: [execution_summary(x) for x in page.data]
                    )
                    if any(x.execution_state != "error" for x in result.executions):
                        raise N8nError("unexpected_execution_state")
                    if options.get("workflow_id") is not None and any(
                        x.workflow_id != options["workflow_id"] for x in result.executions
                    ):
                        raise N8nError("workflow_identity_mismatch")
            # Fail closed if a malicious provider echoes the configured key in retained metadata.
            if self._client._key.get_secret_value() in result.model_dump_json():
                raise N8nError("invalid_response")
            return result
        except N8nError as error:
            return N8nReadResult(
                operation=operation, status="CHECK_FAILED", synthetic=synthetic, reason=error.code
            )
