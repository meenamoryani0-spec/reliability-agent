from fastapi import APIRouter, HTTPException, Request, Response

from app.api.history import capture_history
from app.tools.models import CheckResult, CheckType

router = APIRouter(tags=["website checks"])


@router.get("/services/websites")
async def list_websites(request: Request) -> list[dict[str, str]]:
    return [
        {"id": target.id, "url": target.url}
        for target in request.app.state.website_targets.values()
    ]


@router.post("/checks/websites/{target_id}", response_model=CheckResult)
async def check_website(
    target_id: str, request: Request, response: Response, kind: CheckType = CheckType.HTTP
) -> CheckResult:
    target = request.app.state.website_targets.get(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Website target is not configured")
    checker = request.app.state.website_checker
    if kind == CheckType.DNS:
        result = await checker.check_dns(target)
    elif kind == CheckType.SSL:
        result = await checker.check_ssl(target)
    else:
        result = await checker.check_http(target)
    return await capture_history(request, response, result, target.url)
