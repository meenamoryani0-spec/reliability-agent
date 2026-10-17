from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["model tool catalog"])


@router.get("/tools")
async def describe_tools(request: Request):
    if request.app.state.settings.environment == "production":
        raise HTTPException(
            status_code=404, detail="Tool catalog requires deployment access controls"
        )
    return request.app.state.tool_registry.describe()
