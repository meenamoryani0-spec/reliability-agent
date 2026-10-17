from fastapi import APIRouter, Request

from app.security import require_authenticated

router = APIRouter(tags=["model tool catalog"])


@router.get("/tools")
async def describe_tools(request: Request):
    require_authenticated(request)
    return request.app.state.tool_registry.describe()
