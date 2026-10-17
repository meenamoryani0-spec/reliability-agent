"""Local recovery verification; only the exact accepted retry is read."""

import argparse
import asyncio
import json

from app.config import Settings
from app.db.repository import StorageError
from app.recovery.service import RecoveryService


async def run(arguments, config):
    service = RecoveryService(config)
    try:
        return await service.verify(arguments.action_id)
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(
        description="Verify the configured path of an accepted n8n retry"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--action-id", required=True)
    try:
        result = asyncio.run(run(parser.parse_args(), Settings()))
    except StorageError as error:
        print(json.dumps({"status": "INCONCLUSIVE", "reason": error.code}))
        return 1
    except Exception:
        print(json.dumps({"status": "INCONCLUSIVE", "reason": "verification_unavailable"}))
        return 1
    print(json.dumps(result, default=lambda value: value.isoformat()))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
