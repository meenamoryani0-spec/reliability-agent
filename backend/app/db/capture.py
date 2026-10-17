"""Typed persistence outcomes, separate from monitored-system health."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecordId = Annotated[str, Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]


class CaptureSchema(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class IncidentCapture(CaptureSchema):
    status: Literal["disabled", "not_applicable", "created", "existing", "unavailable"] = (
        "not_applicable"
    )
    incident_id: RecordId | None = None

    @model_validator(mode="after")
    def confirmed_identifier(self):
        if (self.status in {"created", "existing"}) != (self.incident_id is not None):
            raise ValueError("Confirmed incident requires an identifier")
        return self


class HistoryCapture(CaptureSchema):
    status: Literal["not_applicable", "saved", "disabled", "unavailable"] = "not_applicable"
    check_id: RecordId | None = None
    incident: IncidentCapture = Field(default_factory=IncidentCapture)

    @model_validator(mode="after")
    def saved_identifier(self):
        if (self.status == "saved") != (self.check_id is not None):
            raise ValueError("Saved history requires a check identifier")
        if self.status != "saved" and self.incident.status in {"created", "existing"}:
            raise ValueError("Incident creation requires persisted evidence")
        return self
