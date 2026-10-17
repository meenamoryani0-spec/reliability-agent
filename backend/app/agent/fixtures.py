"""Scripted model protocol fixture; it does not simulate verified AI reasoning."""

import json

import httpx
from pydantic import SecretStr

from app.agent.client import NebiusClient

DEMO_QUESTION = "Why are booking confirmations missing?"
FIXTURE_KEY = "synthetic-model-key-not-a-credential"


def fixture_model(config):
    step = 0

    def handler(request):
        nonlocal step
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": config.nebius_model}]})
        if request.method != "POST" or request.url.path != "/v1/chat/completions":
            return httpx.Response(404)
        payload = json.loads(request.content)
        messages = payload["messages"]
        tool_messages = [message for message in messages if message["role"] == "tool"]
        if step == 0 and not tool_messages:
            calls = [("list_failed_n8n_executions", {})]
        elif step == 1 and len(tool_messages) == 1:
            calls = [
                ("get_n8n_execution", {"execution_id": "1001"}),
                ("check_supabase_health", {}),
                ("check_postgres", {}),
            ]
        elif step == 2 and len(tool_messages) == 4:
            detail = json.loads(tool_messages[1]["content"])
            supported = detail["result"]["data"]["evidence"].get("failures", [])
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "hypothesis": "authentication_rejection" if supported else "unknown",
                        "evidence_ids": [detail["id"]],
                        "next_steps": [
                            "inspect_authentication_configuration",
                            "verify_business_flow",
                        ],
                    }
                ),
            }
            return httpx.Response(
                200,
                json={
                    "id": "fixture-final",
                    "model": config.nebius_model,
                    "choices": [{"message": message, "finish_reason": "stop"}],
                },
            )
        else:
            return httpx.Response(400)
        step += 1
        return httpx.Response(
            200,
            json={
                "id": "fixture-turn",
                "model": config.nebius_model,
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"fixture_{step}_{index}",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                                for index, (name, arguments) in enumerate(calls)
                            ],
                        },
                    }
                ],
            },
        )

    return NebiusClient(
        config.model_copy(update={"nebius_api_key": SecretStr(FIXTURE_KEY)}),
        transport=httpx.MockTransport(handler),
    )
