"""Opt-in live API check. Sends one static prompt; does not print provider text."""

import asyncio
import json

from pydantic import ValidationError

from app.agent.client import NebiusClient, NebiusError
from app.config import Settings
from app.logging import configure_logging


async def run_smoke(settings: Settings) -> int:
    try:
        configure_logging(settings.log_level)
        async with NebiusClient(settings) as client:
            await client.verify_model_available()
            result = await client.complete(
                "Reply with one short greeting. This is a connectivity test."
            )
        print(json.dumps({"result": "PASS", "model": result.model, "reply_received": True}))
        return 0
    except NebiusError as error:
        print(json.dumps({"result": "NOT_VERIFIED", "reason": error.code}))
        return 1


def main() -> int:
    try:
        settings = Settings()
    except ValidationError:
        print(json.dumps({"result": "NOT_VERIFIED", "reason": "invalid_configuration"}))
        return 1
    # Fail before event-loop creation: even asyncio needs loopback access on Windows.
    if settings.nebius_api_key is None:
        print(json.dumps({"result": "NOT_VERIFIED", "reason": "missing_api_key"}))
        return 1
    return asyncio.run(run_smoke(settings))


if __name__ == "__main__":
    raise SystemExit(main())
