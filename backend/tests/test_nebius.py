import asyncio
import json

import httpx
import pytest

from app.agent.client import MAX_RESPONSE_BYTES, NebiusClient, NebiusError
from app.agent.smoke import main as smoke_main
from app.config import Settings

MODEL = "nvidia/Nemotron-3_5-Lightning"
TEST_KEY = "unit-test-key"


def settings(**overrides):
    return Settings(_env_file=None, nebius_api_key=TEST_KEY, **overrides)


def response_data():
    return {
        "id": "test-completion",
        "model": MODEL,
        "choices": [
            {"message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
        ],
    }


def complete_with_response(response):
    async def scenario():
        async with NebiusClient(
            settings(), transport=httpx.MockTransport(lambda _: response)
        ) as client:
            return await client.complete("Test prompt")

    return asyncio.run(scenario())


def test_model_check_and_completion_use_documented_contract():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
        assert request.url.host == "api.tokenfactory.nebius.com"
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        assert request.method == "POST"
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload == {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Test prompt"}],
            "max_tokens": 2048,
            "stream": False,
            "store": False,
        }
        assert TEST_KEY not in request.content.decode()
        return httpx.Response(200, json=response_data())

    async def scenario():
        async with NebiusClient(settings(), transport=httpx.MockTransport(handler)) as client:
            await client.verify_model_available()
            completion = await client.complete("Test prompt")
            assert completion.choices[0].message.content == "Hello"

    asyncio.run(scenario())
    assert len(requests) == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "invalid_request"),
        (401, "authentication_failed"),
        (403, "access_denied"),
        (404, "model_or_endpoint_unavailable"),
        (422, "invalid_request"),
        (429, "rate_limited"),
        (500, "provider_error"),
        (503, "provider_error"),
        (302, "unexpected_status"),
        (204, "unexpected_status"),
    ],
)
def test_provider_errors_are_sanitized_and_never_retried(status, code, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text=f"Untrusted provider data {TEST_KEY}",
            headers={"Location": "https://untrusted.example/collect"},
        )

    async def scenario():
        async with NebiusClient(settings(), transport=httpx.MockTransport(handler)) as client:
            await client.complete("Test prompt")

    with pytest.raises(NebiusError) as error:
        asyncio.run(scenario())
    assert error.value.code == code
    assert TEST_KEY not in str(error.value)
    assert TEST_KEY not in caplog.text
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"data": []}, []])
def test_malformed_completion_response(payload):
    with pytest.raises(NebiusError, match="invalid_response"):
        complete_with_response(httpx.Response(200, json=payload))


def test_non_json_response():
    with pytest.raises(NebiusError, match="invalid_response"):
        complete_with_response(httpx.Response(200, text="not-json"))


@pytest.mark.parametrize(
    ("finish_reason", "code"),
    [
        ("length", "truncated_response"),
        ("tool_calls", "incomplete_response"),
        ("content_filter", "incomplete_response"),
    ],
)
def test_incomplete_output_is_not_success(finish_reason, code):
    payload = response_data()
    payload["choices"][0]["finish_reason"] = finish_reason
    with pytest.raises(NebiusError, match=code):
        complete_with_response(httpx.Response(200, json=payload))


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_output_is_not_success(content):
    payload = response_data()
    payload["choices"][0]["message"]["content"] = content
    with pytest.raises(NebiusError, match="empty_response"):
        complete_with_response(httpx.Response(200, json=payload))


def test_wrong_model_is_not_success():
    payload = response_data()
    payload["model"] = "different-provider/model"
    with pytest.raises(NebiusError, match="unexpected_model"):
        complete_with_response(httpx.Response(200, json=payload))


def test_response_size_is_bounded():
    with pytest.raises(NebiusError, match="response_too_large"):
        complete_with_response(httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)))


@pytest.mark.parametrize(
    ("exception_type", "code"),
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "transport_error")],
)
def test_transport_failures_hide_original_exception(exception_type, code):
    def handler(request):
        raise exception_type(f"Sensitive data {TEST_KEY}", request=request)

    async def scenario():
        async with NebiusClient(settings(), transport=httpx.MockTransport(handler)) as client:
            await client.complete("Test prompt")

    with pytest.raises(NebiusError) as error:
        asyncio.run(scenario())
    assert error.value.code == code
    assert TEST_KEY not in str(error.value)
    assert error.value.__suppress_context__


def test_total_deadline_applies_even_if_transport_does_not_timeout():
    async def handler(request):
        await asyncio.sleep(2)
        return httpx.Response(200, json=response_data())

    async def scenario():
        async with NebiusClient(
            settings(nebius_timeout_seconds=1), transport=httpx.MockTransport(handler)
        ) as client:
            await client.complete("Test prompt")

    with pytest.raises(NebiusError, match="timeout"):
        asyncio.run(scenario())


@pytest.mark.parametrize("prompt", ["", " ", "x" * 8001])
def test_invalid_prompt_makes_no_request(prompt):
    def handler(request):
        pytest.fail("An invalid prompt must not make a network request")

    async def scenario():
        async with NebiusClient(settings(), transport=httpx.MockTransport(handler)) as client:
            await client.complete(prompt)

    with pytest.raises(NebiusError, match="invalid_prompt"):
        asyncio.run(scenario())


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"data": []}, "model_unavailable"),
        ({"data": [{"id": 7}]}, "invalid_response"),
        ({}, "invalid_response"),
    ],
)
def test_model_availability_is_checked(payload, code):
    async def scenario():
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        async with NebiusClient(settings(), transport=transport) as client:
            await client.verify_model_available()

    with pytest.raises(NebiusError, match=code):
        asyncio.run(scenario())


def test_missing_key_is_configuration_error(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(NebiusError, match="missing_api_key"):
        NebiusClient(Settings(_env_file=None))


def test_smoke_fails_before_event_loop_when_key_is_missing(monkeypatch, capsys):
    from app.agent import smoke

    monkeypatch.setattr(smoke, "Settings", lambda: Settings(_env_file=None, nebius_api_key=None))

    def unexpected_run(*args):
        pytest.fail("Missing credentials must not create an event loop or attempt a request")

    monkeypatch.setattr(smoke.asyncio, "run", unexpected_run)
    assert smoke_main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "result": "NOT_VERIFIED",
        "reason": "missing_api_key",
    }
