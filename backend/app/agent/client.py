import asyncio
import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agent.safety import load_object
from app.config import Settings

# Official API reference, verified 2026-10-09. No user-controlled destination.
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 262144


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


class FunctionCall(ProviderSchema):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    arguments: str = Field(max_length=4096)


class ToolCall(ProviderSchema):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    type: Literal["function"]
    function: FunctionCall


class AssistantMessage(ProviderSchema):
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=4)
    refusal: str | None = Field(default=None, max_length=16384)

    @field_validator("tool_calls", mode="before")
    @classmethod
    def absent_calls(cls, value):
        return [] if value is None else value


class CompletionChoice(ProviderSchema):
    message: AssistantMessage
    finish_reason: str


class CompletionResponse(ProviderSchema):
    id: str
    model: str
    choices: list[CompletionChoice] = Field(min_length=1, max_length=1)


class NebiusClient:
    """Bounded text and tool-turn inference; execution belongs to the registry."""

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
        if choice.message.tool_calls or choice.message.refusal:
            raise NebiusError("incomplete_response")
        if not choice.message.content or not choice.message.content.strip():
            raise NebiusError("empty_response")
        return completion

    async def next_turn(self, messages: list[dict], tools: list[dict]) -> CompletionResponse:
        """One documented tool-calling round; no retries or automatic execution."""
        payload = {
            "model": self._settings.nebius_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": self._settings.nebius_max_tokens,
            "stream": False,
            "store": False,
        }
        try:
            if not 2 <= len(messages) <= 24 or not 1 <= len(tools) <= 13:
                raise ValueError()
            if (
                len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())
                > MAX_REQUEST_BYTES
            ):
                raise NebiusError("request_too_large")
        except (ValueError, TypeError, UnicodeError):
            raise NebiusError("invalid_request") from None
        raw = await self._request("POST", "chat/completions", payload)
        try:
            completion = CompletionResponse.model_validate(load_object(raw, MAX_RESPONSE_BYTES))
        except (ValueError, TypeError, RecursionError):
            raise NebiusError("invalid_response") from None
        if completion.model != self._settings.nebius_model:
            raise NebiusError("unexpected_model")
        choice = completion.choices[0]
        if choice.message.refusal:
            raise NebiusError("refused")
        if choice.finish_reason == "length":
            raise NebiusError("truncated_response")
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            if len({call.id for call in choice.message.tool_calls}) != len(
                choice.message.tool_calls
            ):
                raise NebiusError("invalid_response")
        elif choice.finish_reason == "stop" and not choice.message.tool_calls:
            if not choice.message.content or not choice.message.content.strip():
                raise NebiusError("empty_response")
        else:
            raise NebiusError("incomplete_response")
        return completion
