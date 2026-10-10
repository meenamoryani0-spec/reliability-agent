from fastapi import APIRouter, HTTPException, Request

from app.tools.browser_models import FLOW_IDS, BrowserFlowResult

router = APIRouter(tags=["synthetic browser checks"])


def require_development(request: Request) -> None:
    if request.app.state.settings.environment == "production":
        raise HTTPException(status_code=404, detail="Synthetic browser checks are disabled")


@router.get("/services/browser-flows")
async def list_browser_flows(request: Request) -> list[dict]:
    require_development(request)
    return [{"id": flow_id, "synthetic": True} for flow_id in FLOW_IDS]


@router.post("/checks/browser-flows/{flow_id}", response_model=BrowserFlowResult)
async def check_browser_flow(flow_id: str, request: Request) -> BrowserFlowResult:
    require_development(request)
    if flow_id not in FLOW_IDS:
        raise HTTPException(status_code=404, detail="Browser flow is not configured")
    return await request.app.state.browser_checker.check(flow_id)
