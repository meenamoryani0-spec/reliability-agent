import asyncio
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.client import NebiusClient, NebiusError
from app.agent.fixtures import DEMO_QUESTION, FIXTURE_KEY
from app.agent.orchestrator import InvestigationService
from app.config import PROJECT_ROOT, Settings
from app.db.database import create_storage_engine
from app.db.migrate import upgrade
from app.main import create_app

MODEL = "nvidia/Nemotron-3_5-Lightning"
KEY = "test-model-secret"


def config(**options):
    return Settings(
        _env_file=None,
        environment="test",
        investigation_mode="fixture",
        n8n_mode="fixture",
        infrastructure_mode="fixture",
        **options,
    )


def tool_turn(*calls):
    return {
        "id": "test-turn",
        "model": MODEL,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": identifier,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                        for identifier, name, arguments in calls
                    ],
                },
            }
        ],
    }


def final_turn(**options):
    draft = {
        "hypothesis": "authentication_rejection",
        "evidence_ids": ["e1"],
        "next_steps": ["inspect_authentication_configuration", "verify_business_flow"],
        **options,
    }
    return {
        "id": "final",
        "model": MODEL,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(draft)},
            }
        ],
    }


def scripted_client(turns, requests=None):
    sequence = iter(turns)
    records = requests if requests is not None else []

    def factory():
        def handler(request):
            records.append(request)
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"id": MODEL}]})
            value = next(sequence)
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)

        return NebiusClient(config(nebius_api_key=KEY), transport=httpx.MockTransport(handler))

    return factory


def run_turns(turns, **options):
    records = []
    app = create_app(config(), agent_client_factory=scripted_client(turns, records), **options)

    async def run():
        try:
            return await app.state.investigator.investigate(DEMO_QUESTION)
        finally:
            await app.state.investigator.close()
            await app.state.tool_registry.close()
            await app.state.history.close()

    return asyncio.run(run()), records


def test_fixture_runs_real_request_tool_result_loop_and_keeps_provenance():
    with TestClient(create_app(config())) as client:
        description = client.get("/agent").json()
        assert description["mode"] == "fixture"
        assert description["live_connectivity_verified"] is False
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["status"] == "COMPLETED" and report["assessment"] == "observed_failure"
        assert report["hypothesis"] == "authentication_rejection"
        assert report["inference_source"] == "scripted_fixture"
        assert report["evidence_provenance"] == "synthetic_only"
        assert report["model_requests"] == 3 and report["tool_calls"] == 4
        assert report["cited_evidence_ids"] == ["e2"]
        assert [item["id"] for item in report["evidence"]] == ["e1", "e2", "e3", "e4"]
        assert (
            report["evidence"][1]["result"]["data"]["evidence"]["failures"][0]["http_status"] == 401
        )
        assert all(
            report[field] is False
            for field in (
                "root_cause_verified",
                "business_outcome_verified",
                "incident_created",
                "remediation_executed",
            )
        )
        assert "expired" not in report["summary"]
        assert FIXTURE_KEY not in json.dumps(report)
        assert "SYNTHETIC_PRIVATE_DATA" not in json.dumps(report)


def test_wire_protocol_passes_schemas_and_actual_evidence_with_matching_call_ids():
    report, requests = run_turns(
        [
            tool_turn(("call_a", "get_n8n_execution", '{"execution_id":"1001"}')),
            final_turn(),
        ]
    )
    assert report.status == "COMPLETED"
    assert len(requests) == 3  # one catalog GET plus two chat POSTs
    payload = json.loads(requests[2].content)
    assert payload["store"] is False and payload["stream"] is False
    assert payload["tool_choice"] == "auto" and payload["max_tokens"] == 2048
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == DEMO_QUESTION
    assert payload["messages"][-2]["tool_calls"][0]["id"] == "call_a"
    assert payload["messages"][-1]["tool_call_id"] == "call_a"
    evidence = json.loads(payload["messages"][-1]["content"])
    assert evidence["id"] == "e1" and evidence["result"]["data"]["status"] == "UNHEALTHY"
    assert all(
        tool["function"]["parameters"]["additionalProperties"] is False for tool in payload["tools"]
    )
    assert "check_website_http" not in {tool["function"]["name"] for tool in payload["tools"]}
    assert KEY not in requests[2].content.decode()


@pytest.mark.parametrize("path,method", [("/agent", "get"), ("/investigations", "post")])
def test_production_routes_and_internal_calls_are_disabled(path, method):
    app = create_app(Settings(_env_file=None, environment="production", investigation_mode="live"))
    with TestClient(app) as client:
        assert getattr(client, method)(path).status_code == 404
        result = client.portal.call(app.state.investigator.investigate, "Question")
        assert result.reason == "access_disabled" and result.model_requests == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": " "},
        {"question": 7},
        {"question": "x" * 2001},
        {"question": "valid", "mode": "live"},
        [],
        None,
    ],
)
def test_invalid_http_input_is_sanitized(body):
    with TestClient(create_app(config())) as client:
        response = client.post(
            "/investigations",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid investigation request"}


@pytest.mark.parametrize(
    "body",
    [
        b'{"question":"one","question":"two"}',
        b'{"question":NaN}',
        b'{"question":',
        b"[" * 1500 + b"]" * 1500,
        b'{"question":"\\ud800"}',
    ],
)
def test_malformed_json_is_rejected(body):
    with TestClient(create_app(config())) as client:
        assert (
            client.post(
                "/investigations", content=body, headers={"Content-Type": "application/json"}
            ).status_code
            == 422
        )


def test_http_byte_limit_and_content_type():
    with TestClient(create_app(config())) as client:
        assert (
            client.post(
                "/investigations", content=b"x" * 4097, headers={"Content-Type": "application/json"}
            ).status_code
            == 413
        )
        assert client.post("/investigations", content="text").status_code == 415
        assert (
            client.post("/investigations", json={"question": "Different demo question"}).json()[
                "reason"
            ]
            == "fixture_question_unsupported"
        )
        schema = client.get("/openapi.json").json()
        assert (
            schema["paths"]["/investigations"]["post"]["requestBody"]["content"][
                "application/json"
            ]["schema"]["additionalProperties"]
            is False
        )


@pytest.mark.parametrize("mode,reason", [("disabled", "disabled"), ("live", "missing_api_key")])
def test_missing_configuration_never_makes_a_provider_request(mode, reason):
    factory = Mock()
    app = create_app(
        Settings(_env_file=None, environment="test", investigation_mode=mode, nebius_api_key=None),
        agent_client_factory=factory,
    )
    report = asyncio.run(app.state.investigator.investigate("Question"))
    assert report.reason == reason and report.model_requests == 0
    factory.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"environment": "production", "n8n_mode": "fixture", "infrastructure_mode": "fixture"},
        {"n8n_mode": "live", "infrastructure_mode": "fixture"},
        {"n8n_mode": "fixture", "infrastructure_mode": "disabled"},
    ],
)
def test_fixture_mode_cannot_drive_live_adapters(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, investigation_mode="fixture", **changes)


def test_known_secret_in_question_stops_before_model_and_is_not_echoed(caplog):
    factory = Mock()
    app = create_app(config(nebius_api_key=KEY), agent_client_factory=factory)
    result = asyncio.run(app.state.investigator.investigate(KEY))
    assert result.reason == "sensitive_input"
    assert KEY not in result.model_dump_json() and KEY not in caplog.text
    factory.assert_not_called()


@pytest.mark.parametrize(
    "name", ["retry_n8n_execution", "shell", "create_incident", "check_website_http"]
)
def test_disallowed_call_in_batch_prevents_every_dispatch(name):
    service = Mock(read=AsyncMock())
    report, requests = run_turns(
        [tool_turn(("valid", "list_n8n_workflows", "{}"), ("bad", name, "{}"))], n8n_service=service
    )
    assert report.reason == "tool_not_allowed" and report.tool_calls == 0
    assert service.read.await_count == 0 and len(requests) == 2


@pytest.mark.parametrize(
    "arguments",
    [
        '{"execution_id":1001}',
        '{"execution_id":"1001","url":"https://evil.example"}',
        '{"execution_id":"1001","execution_id":"1002"}',
    ],
)
def test_invalid_tool_arguments_stop_without_provider_io(arguments):
    service = Mock(read=AsyncMock())
    report, _ = run_turns(
        [tool_turn(("call", "get_n8n_execution", arguments))], n8n_service=service
    )
    assert report.reason == "tool_failed"
    assert report.evidence[0].result.reason == "invalid_arguments"
    service.read.assert_not_awaited()


@pytest.mark.parametrize(
    "draft,reason",
    [
        ({"evidence_ids": ["e8"]}, "invalid_citation"),
        ({"evidence_ids": ["e1", "e1"]}, "invalid_citation"),
        ({"hypothesis": "deployment_failure"}, "unsupported_hypothesis"),
        ({"hypothesis": "credential_expired"}, "invalid_final"),
        ({"root_cause_verified": True}, "invalid_final"),
        ({"summary": "Credential expired; fixed"}, "invalid_final"),
        ({"next_steps": ["retry_n8n_execution"]}, "invalid_final"),
        ({"evidence_ids": []}, "invalid_final"),
    ],
)
def test_unsupported_model_conclusions_are_not_returned_as_facts(draft, reason):
    report, _ = run_turns(
        [tool_turn(("call", "get_n8n_execution", '{"execution_id":"1001"}')), final_turn(**draft)]
    )
    assert report.status == "INCOMPLETE" and report.reason == reason
    assert report.hypothesis is None and len(report.evidence) == 1
    assert report.root_cause_verified is False
    assert "Credential expired" not in report.model_dump_json()


def test_healthy_execution_cannot_support_authentication_failure():
    report, _ = run_turns(
        [tool_turn(("call", "get_n8n_execution", '{"execution_id":"1002"}')), final_turn()]
    )
    assert report.reason == "unsupported_hypothesis"
    assert report.assessment == "no_failure_observed"


def test_failed_inspection_is_insufficient_evidence_not_unhealthy():
    app = create_app(
        Settings(_env_file=None, environment="test", investigation_mode="live", nebius_api_key=KEY),
        agent_client_factory=scripted_client(
            [
                tool_turn(("call", "get_n8n_execution", '{"execution_id":"1001"}')),
                final_turn(hypothesis="unknown"),
            ]
        ),
    )
    result = asyncio.run(app.state.investigator.investigate("Question"))
    assert result.status == "COMPLETED" and result.assessment == "insufficient_evidence"
    assert result.evidence[0].result.data["status"] == "CHECK_FAILED"
    assert result.inference_source == "nebius"  # transport is mocked by this test


def test_no_tools_means_no_validated_evidence():
    report, _ = run_turns([final_turn(hypothesis="unknown")])
    assert report.status == "INCOMPLETE" and report.reason == "no_evidence"


@pytest.mark.parametrize(
    "second_id,second_name,second_arguments,reason",
    [
        ("one", "get_n8n_execution", '{"execution_id":"1002"}', "duplicate_tool_id"),
        ("two", "get_n8n_execution", '{"execution_id": "1001"}', "repeated_tool_call"),
    ],
)
def test_repeated_calls_and_ids_stop_the_loop(second_id, second_name, second_arguments, reason):
    report, records = run_turns(
        [
            tool_turn(("one", "get_n8n_execution", '{"execution_id":"1001"}')),
            tool_turn((second_id, second_name, second_arguments)),
        ]
    )
    assert report.reason == reason and report.tool_calls == 1
    assert len(records) == 3


def test_partial_evidence_survives_provider_failure():
    report, requests = run_turns(
        [
            tool_turn(("call", "get_n8n_execution", '{"execution_id":"1001"}')),
            httpx.Response(401, text=KEY),
        ]
    )
    assert report.status == "CHECK_FAILED" and report.reason == "provider_error"
    assert len(report.evidence) == 1 and report.assessment == "observed_failure"
    assert KEY not in report.model_dump_json() and len(requests) == 3


def test_model_secret_echo_and_raw_prose_are_not_exposed():
    raw = final_turn()
    raw["choices"][0]["message"]["content"] = KEY
    app = create_app(config(nebius_api_key=KEY), agent_client_factory=scripted_client([raw]))
    report = asyncio.run(app.state.investigator.investigate(DEMO_QUESTION))
    assert report.reason == "unsafe_model_output" and KEY not in report.model_dump_json()


def test_storage_outage_preserves_investigation_evidence(tmp_path):
    path = str((tmp_path / "missing.sqlite3").relative_to(PROJECT_ROOT))
    with TestClient(create_app(config(storage_mode="local", storage_sqlite_file=path))) as client:
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["status"] == "COMPLETED"
        assert all(
            record["result"]["history"]["status"] == "unavailable"
            for record in report["evidence"][1:]
        )


def test_investigation_persists_observations_without_creating_incidents(tmp_path):
    settings = config(
        storage_mode="local",
        storage_sqlite_file=str((tmp_path / "history.sqlite3").relative_to(PROJECT_ROOT)),
    )
    engine = create_storage_engine(settings)
    upgrade(engine)
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["status"] == "COMPLETED"
        assert len(client.get("/history/checks").json()) == 3
        assert len(client.get("/history/services").json()) == 3
        assert client.get("/history/incidents").json() == []
        assert all(
            record["result"]["history"]["status"] == "saved" for record in report["evidence"][1:]
        )


def test_deadline_cancels_future_model_work_and_holds_slot_until_worker_finishes(monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "INVESTIGATION_TIMEOUT_SECONDS", 0.03)

    async def run():
        worker_done = asyncio.Event()
        entered = asyncio.Event()

        async def execute(*_):
            entered.set()
            await asyncio.Event().wait()

        registry = Mock(
            definitions=lambda: [{"type": "function", "function": {"name": "get_n8n_execution"}}],
            execute=execute,
            wait_idle=worker_done.wait,
        )
        requests = []
        service = InvestigationService(
            config(),
            registry,
            client_factory=scripted_client(
                [tool_turn(("one", "get_n8n_execution", '{"execution_id":"1001"}'))], requests
            ),
        )
        report = await service.investigate(DEMO_QUESTION)
        assert entered.is_set() and report.reason == "deadline_exceeded"
        assert (await service.investigate(DEMO_QUESTION)).reason == "busy"
        closing = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not closing.done()
        worker_done.set()
        await closing
        assert len(requests) == 2
        assert (await service.investigate(DEMO_QUESTION)).reason == "access_disabled"

    asyncio.run(run())


def test_caller_cancellation_stops_provider_requests(monkeypatch):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def hanging(_messages, _tools):
            entered.set()
            await release.wait()

        client = Mock(verify_model_available=AsyncMock(), next_turn=hanging)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        registry = Mock(
            definitions=lambda: [{"function": {"name": "get_n8n_execution"}}], wait_idle=AsyncMock()
        )
        service = InvestigationService(config(), registry, client_factory=lambda: client)
        caller = asyncio.create_task(service.investigate(DEMO_QUESTION))
        await entered.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        await service.close()
        client.__aexit__.assert_awaited_once()

    asyncio.run(run())


def test_model_and_tool_budgets_end_without_extra_dispatch(monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "MAX_MODEL_REQUESTS", 1)
    report, requests = run_turns([tool_turn(("one", "list_n8n_workflows", "{}"))])
    assert report.reason == "model_budget_exhausted" and len(requests) == 2
    monkeypatch.setattr(orchestrator, "MAX_MODEL_REQUESTS", 6)
    monkeypatch.setattr(orchestrator, "MAX_TOOL_CALLS", 1)
    report, _ = run_turns(
        [tool_turn(("one", "list_n8n_workflows", "{}"), ("two", "check_postgres", "{}"))]
    )
    assert report.reason == "tool_budget_exhausted" and report.tool_calls == 0


def test_actual_six_turn_and_eight_tool_limits():
    turns = [
        tool_turn((f"call{index}", "list_n8n_workflows", json.dumps({"limit": index})))
        for index in range(1, 7)
    ]
    report, requests = run_turns(turns)
    assert report.reason == "model_budget_exhausted"
    assert report.model_requests == 6 and report.tool_calls == 6 and len(requests) == 7
    turns = [
        tool_turn(
            *[
                (f"c{index}", "list_n8n_workflows", json.dumps({"limit": index}))
                for index in range(1, 5)
            ]
        ),
        tool_turn(
            *[
                (f"c{index}", "list_n8n_workflows", json.dumps({"limit": index}))
                for index in range(5, 9)
            ]
        ),
        tool_turn(("c9", "check_postgres", "{}")),
    ]
    report, _ = run_turns(turns)
    assert report.reason == "tool_budget_exhausted"
    assert report.model_requests == 3 and report.tool_calls == 8 and len(report.evidence) == 8


def test_next_turn_request_size_limit_precedes_network_io():
    requests = []

    async def run():
        async with scripted_client([], requests)() as client:
            with pytest.raises(NebiusError, match="request_too_large"):
                await client.next_turn(
                    [
                        {"role": "system", "content": "policy"},
                        {"role": "user", "content": "x" * 262144},
                    ],
                    [{"function": {"name": "check_postgres"}}],
                )

    asyncio.run(run())
    assert requests == []


def test_context_and_evidence_budgets_stop_before_next_io(monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "MAX_CONTEXT_BYTES", 1)
    report, requests = run_turns([])
    assert report.reason == "context_budget_exhausted" and len(requests) == 1
    monkeypatch.setattr(orchestrator, "MAX_CONTEXT_BYTES", 196608)
    monkeypatch.setattr(orchestrator, "MAX_EVIDENCE_BYTES", 1)
    report, _ = run_turns([tool_turn(("one", "check_postgres", "{}"))])
    assert report.reason == "evidence_budget_exhausted" and report.tool_calls == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ({"finish_reason": "length"}, "truncated_response"),
        ({"finish_reason": "stop"}, "incomplete_response"),
        ({"finish_reason": "content_filter"}, "incomplete_response"),
    ],
)
def test_model_protocol_rejects_incomplete_turns(change, code):
    raw = tool_turn(("one", "check_postgres", "{}"))
    raw["choices"][0].update(change)

    async def run():
        async with scripted_client([raw])() as client:
            with pytest.raises(NebiusError, match=code):
                await client.next_turn(
                    [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}],
                    [{"type": "function", "function": {"name": "check_postgres"}}],
                )

    asyncio.run(run())


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_ids",
        "five_calls",
        "invalid_call_id",
        "wrong_model",
        "refusal",
        "duplicate_json_keys",
        "non_json",
    ],
)
def test_invalid_model_payloads_are_sanitized(case):
    raw = tool_turn(("one", "check_postgres", "{}"))
    if case == "duplicate_ids":
        raw = tool_turn(("one", "check_postgres", "{}"), ("one", "check_supabase_health", "{}"))
    elif case == "five_calls":
        raw = tool_turn(*[(f"c{index}", "check_postgres", "{}") for index in range(5)])
    elif case == "invalid_call_id":
        raw["choices"][0]["message"]["tool_calls"][0]["id"] = "../bad"
    elif case == "wrong_model":
        raw["model"] = "other-model"
    elif case == "refusal":
        raw["choices"][0]["message"]["refusal"] = "Private refusal"
    elif case == "duplicate_json_keys":
        raw = httpx.Response(200, content=b'{"model":"one","model":"two"}')
    else:
        raw = httpx.Response(200, content=b"PRIVATE_BODY")
    report, _ = run_turns([raw])
    assert report.reason == "provider_error" and report.evidence == []
    assert "PRIVATE_BODY" not in report.model_dump_json()


def test_null_tool_calls_on_final_response_are_supported():
    raw = final_turn()
    raw["choices"][0]["message"]["tool_calls"] = None
    report, _ = run_turns([tool_turn(("one", "get_n8n_execution", '{"execution_id":"1001"}')), raw])
    assert report.status == "COMPLETED"


def test_tool_protocol_does_not_reduce_legacy_text_response_limit():
    payload = final_turn()
    payload["choices"][0]["message"]["content"] = "x" * 20000

    async def run():
        async with scripted_client([payload])() as client:
            result = await client.complete("Static test prompt")
            assert len(result.choices[0].message.content) == 20000

    asyncio.run(run())


def test_raw_provider_reasoning_is_never_exposed():
    raw = tool_turn(("one", "get_n8n_execution", '{"execution_id":"1001"}'))
    raw["choices"][0]["message"]["reasoning_content"] = "PRIVATE_CHAIN_OF_THOUGHT"
    raw["choices"][0]["message"]["content"] = "Unverified expiry diagnosis"
    report, requests = run_turns([raw, final_turn()])
    assert report.status == "COMPLETED"
    assert "PRIVATE_CHAIN_OF_THOUGHT" not in report.model_dump_json()
    assert "Unverified expiry diagnosis" not in requests[-1].content.decode()
