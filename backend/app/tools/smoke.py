"""Opt-in live checks of one operator-registered website, without provider credentials."""

import argparse
import asyncio
import json

from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.config import Settings
from app.tools.models import CheckStatus, WebsiteTarget
from app.tools.website import WebsiteChecker


async def run_smoke(target: WebsiteTarget, *, nameservers: tuple[str, ...] = ()) -> int:
    checker = WebsiteChecker(nameservers=nameservers)
    results = [
        await checker.check_dns(target),
        await checker.check_http(target),
        await checker.check_ssl(target),
    ]
    passed = all(result.status == CheckStatus.HEALTHY for result in results)
    print(
        json.dumps(
            {
                "result": "PASS" if passed else "ATTENTION",
                "target_id": target.id,
                "checks": [result.model_dump(mode="json") for result in results],
            }
        )
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target_id", help="ID from WEBSITE_TARGETS; arbitrary URLs are not accepted"
    )
    args = parser.parse_args()
    try:
        settings = Settings()
    except (ValidationError, SettingsError):
        print(json.dumps({"result": "NOT_VERIFIED", "reason": "invalid_configuration"}))
        return 1
    target = next((item for item in settings.website_targets if item.id == args.target_id), None)
    if target is None:
        print(json.dumps({"result": "NOT_VERIFIED", "reason": "website_target_not_configured"}))
        return 1
    return asyncio.run(run_smoke(target, nameservers=settings.website_dns_nameservers))


if __name__ == "__main__":
    raise SystemExit(main())
