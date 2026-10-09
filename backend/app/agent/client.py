import asyncio
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings

# Official API reference, verified 2026-10-09. No user-controlled destination.
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
MAX_RESPONSE_BYTES = 1_048_576


class NebiusError(Exception):
    """Safe error category; never carry provider bodies, prompts, or credentials."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Nebius request failed ({code}).")


class ProviderSchema(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)


class ModelEntry(ProviderSchema):
    id: str


class ModelsResponse(ProviderSchema):
    data: list[ModelEntry]


class AssistantMessage(ProviderSchema):
    role: Literal["assistant"]
    content: str | None = None


class CompletionChoice(ProviderSchema):
    message: AssistantMessage
    finish_reason: str


class CompletionResponse(ProviderSchema):
    id: str
    model: str
    choices: list[CompletionChoice] = Field(min_length=1, max_length=1)


class NebiusClient:
    """Bounded text inference over the documented OpenAI-compatible REST API.

    Phase 2 offers only a model catalog check and text completion. There is no
    shell execution, remediation, public inference route, or automatic retry.
    """

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        if settings.nebius_api_key is None:
            raise NebiusError("missing_api_key")
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=NEBIUS_BASE_URL,
            headers={"Authorization": f"Bearer {settings.nebius_api_key.get_secret_value()}"},
            timeout=httpx.Timeout(settings.nebius_timeout_seconds, connect=10),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> "NebiusClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: Literal["GET", "POST"],
        path: Literal["models", "chat/completions"],
        payload: dict | None = None,
    ) -> bytes:
        try:
            async with asyncio.timeout(self._settings.nebius_timeout_seconds):
                async with self._http.stream(method, path, json=payload) as response:
                    if response.status_code != 200:
                        code = {
                            400: "invalid_request",
                            401: "authentication_failed",
                            403: "access_denied",
                            404: "model_or_endpoint_unavailable",
                            422: "invalid_request",
                            429: "rate_limited",
                        }.get(response.status_code)
                        if code is None:
                            code = (
                                "provider_error"
                                if response.status_code >= 500
                                else "unexpected_status"
                            )
                        raise NebiusError(code)
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise NebiusError("response_too_large")
                        body.extend(chunk)
                    return bytes(body)
        except (httpx.TimeoutException, TimeoutError):
            raise NebiusError("timeout") from None
        except httpx.RequestError:
            raise NebiusError("transport_error") from None

    async def verify_model_available(self) -> None:
        raw = await self._request("GET", "models")
        try:
            catalog = ModelsResponse.model_validate_json(raw)
        except ValidationError:
            raise NebiusError("invalid_response") from None
        if self._settings.nebius_model not in {model.id for model in catalog.data}:
            raise NebiusError("model_unavailable")

    async def complete(self, prompt: str) -> CompletionResponse:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
            raise NebiusError("invalid_prompt")
        payload = {
            "model": self._settings.nebius_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self._settings.nebius_max_tokens,
            "stream": False,
            "store": False,
        }
        raw = await self._request("POST", "chat/completions", payload)
        try:
            completion = CompletionResponse.model_validate_json(raw)
        except ValidationError:
            raise NebiusError("invalid_response") from None
        if completion.model != self._settings.nebius_model:
            raise NebiusError("unexpected_model")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise NebiusError("truncated_response")
        if choice.finish_reason != "stop":
            raise NebiusError("incomplete_response")
        if not choice.message.content or not choice.message.content.strip():
            raise NebiusError("empty_response")
        return completion
