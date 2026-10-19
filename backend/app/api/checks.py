from fastapi import APIRouter, HTTPException, Request, Response

from app.api.history import capture_history
from app.db.repository import StorageError
from app.tools.models import CheckResult, CheckType

router = APIRouter(tags=["website checks"])


@router.get("/services/websites")
async def list_websites(request: Request) -> list[dict[str, str]]:
    try:
        targets = await request.app.state.operator_targets.all()
    except StorageError:
        raise HTTPException(status_code=503, detail="storage_unavailable") from None
    return [{"id": target.id, "url": target.url} for target in targets.values()]


@router.post("/checks/websites/{target_id}", response_model=CheckResult)
async def check_website(
    target_id: str, request: Request, response: Response, kind: CheckType = CheckType.HTTP
) -> CheckResult:
    try:
        target = await request.app.state.operator_targets.get(target_id)
    except StorageError:
        raise HTTPException(status_code=503, detail="storage_unavailable") from None
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
