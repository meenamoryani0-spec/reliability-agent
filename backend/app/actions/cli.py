"""Trusted local operator interface; no HTTP or model approval path."""

import argparse
import asyncio
import json

from app.actions.service import ActionService
from app.config import Settings
from app.db.repository import StorageError


async def run(arguments, config):
    service = ActionService(config)
    try:
        if arguments.command == "plan":
            return await service.plan(arguments.incident_id, arguments.check_id)
        if arguments.command == "execute":
            return await service.execute(
                arguments.action_id, approve_retry_side_effects=arguments.approve_retry_side_effects
            )
        result = await service.inspect(arguments.action_id)
        if result is None:
            raise StorageError("action_not_found")
        return result
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Plan/review a one-shot n8n retry. Retrying may duplicate messages, "
            "payments or other side effects."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--incident-id", required=True)
    plan.add_argument("--check-id", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--action-id", required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--action-id", required=True)
    execute.add_argument(
        "--approve-retry-side-effects",
        action="store_true",
        help="Approve this exact action, acknowledging replay may duplicate external effects.",
    )
    arguments = parser.parse_args()
    try:
        result = asyncio.run(run(arguments, Settings()))
    except StorageError as error:
        print(json.dumps({"status": "REJECTED", "reason": error.code}))
        return 1
    except Exception:
        print(json.dumps({"status": "UNKNOWN", "reason": "action_unavailable"}))
        return 1
    print(json.dumps(result, default=lambda value: value.isoformat()))
    return 0 if result.get("status") not in {"UNKNOWN", "REJECTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
