from fastapi import APIRouter, HTTPException, Request

from app.agent.investigation_models import InvestigationReport, InvestigationRequest
from app.agent.safety import load_object

router = APIRouter(tags=["bounded AI investigation"])


def service(request):
    if request.app.state.settings.environment == "production":
        raise HTTPException(
            status_code=404, detail="Investigation requires deployment access controls"
        )
    return request.app.state.investigator


@router.get("/agent")
async def describe_agent(request: Request):
    return service(request).describe()


@router.post(
    "/investigations",
    response_model=InvestigationReport,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": InvestigationRequest.model_json_schema(),
                }
            },
        },
    },
)
async def investigate(request: Request):
    investigator = service(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON content required")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4096:
            raise HTTPException(status_code=413, detail="Investigation request is too large")
        body.extend(chunk)
    try:
        arguments = InvestigationRequest.model_validate(load_object(bytes(body), 4096))
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(status_code=422, detail="Invalid investigation request") from None
    return await investigator.investigate(arguments.question)
