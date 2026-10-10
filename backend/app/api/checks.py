from fastapi import APIRouter, HTTPException, Request

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
    target_id: str, request: Request, kind: CheckType = CheckType.HTTP
) -> CheckResult:
    target = request.app.state.website_targets.get(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Website target is not configured")
    checker = request.app.state.website_checker
    if kind == CheckType.DNS:
        return await checker.check_dns(target)
    if kind == CheckType.SSL:
        return await checker.check_ssl(target)
    return await checker.check_http(target)
