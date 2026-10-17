"""Read-only infrastructure checks with explicit scopes and normalized evidence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.infrastructure_http import InfrastructureHttp
from app.tools.infrastructure_models import (
    CHECK_IDS,
    DeploymentId,
    InfrastructureError,
    InfrastructureResult,
    ProjectRef,
)
from app.tools.models import CheckStatus
from app.tools.postgres import PostgresChecker

TYPES = dict(
    zip(
        CHECK_IDS,
        ("deployment", "events", "project", "service_health", "connectivity"),
        strict=True,
    )
)
DEPLOYMENT_STATES = Literal[
    "BLOCKED", "BUILDING", "CANCELED", "ERROR", "INITIALIZING", "QUEUED", "READY"
]
PROJECT_STATES = Literal[
    "INACTIVE",
    "ACTIVE_HEALTHY",
    "ACTIVE_UNHEALTHY",
    "COMING_UP",
    "UNKNOWN",
    "GOING_DOWN",
    "INIT_FAILED",
    "REMOVED",
    "RESTORING",
    "UPGRADING",
    "PAUSING",
    "RESTORE_FAILED",
    "RESTARTING",
    "PAUSE_FAILED",
    "RESIZING",
]
EVENT_TYPES = Literal[
    "command",
    "delimiter",
    "deployment-state",
    "edge-function-invocation",
    "exit",
    "fatal",
    "metric",
    "middleware",
    "middleware-invocation",
    "report",
    "stderr",
    "stdout",
]


class ProviderModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)


class Deployment(ProviderModel):
    id: DeploymentId
    readyState: DEPLOYMENT_STATES


class Project(ProviderModel):
    ref: ProjectRef
    status: PROJECT_STATES


class ServiceHealth(ProviderModel):
    name: Literal["db", "auth", "rest"]
    status: Literal["COMING_UP", "ACTIVE_HEALTHY", "UNHEALTHY"]
    healthy: bool


class Event(ProviderModel):
    type: EVENT_TYPES
    created: int = Field(ge=0, le=9007199254740991)


class InfrastructureService:
    def __init__(self, config, *, vercel=None, supabase=None, postgres=None):
        self.mode = config.infrastructure_mode
        self._deployment = config.vercel_deployment_id
        self._team = config.vercel_team_id
        self._ref = config.supabase_project_ref
        options = {
            "timeout": config.infrastructure_timeout_seconds,
            "nameservers": config.infrastructure_dns_nameservers,
        }
        if self.mode == "fixture":
            from app.tools.infrastructure_fixtures import (
                DEPLOYMENT_ID,
                PROJECT_REF,
                fixture_clients,
            )

            vercel, supabase, postgres = fixture_clients(config.infrastructure_timeout_seconds)
            self._deployment, self._ref, self._team = DEPLOYMENT_ID, PROJECT_REF, None
        elif self.mode == "live":
            if vercel is None and self._deployment and config.vercel_token:
                vercel = InfrastructureHttp("vercel", config.vercel_token, **options)
            if supabase is None and self._ref and config.supabase_access_token:
                supabase = InfrastructureHttp("supabase", config.supabase_access_token, **options)
            if postgres is None and all(
                (
                    config.postgres_host,
                    config.postgres_dbname,
                    config.postgres_user,
                    config.postgres_password,
                )
            ):
                postgres = PostgresChecker(
                    config.postgres_host,
                    config.postgres_port,
                    config.postgres_dbname,
                    config.postgres_user,
                    config.postgres_password,
                    **options,
                )
        self._vercel, self._supabase, self._postgres = vercel, supabase, postgres
        self._secrets = tuple(
            secret.get_secret_value()
            for secret in (
                config.vercel_token,
                config.supabase_access_token,
                config.postgres_password,
            )
            if secret
        )

    def describe(self):
        return {
            "mode": self.mode,
            "synthetic": self.mode == "fixture",
            "checks": [{"id": check, "configured": self._configured(check)} for check in CHECK_IDS],
        }

    def _configured(self, check):
        if self.mode == "disabled":
            return False
        if check.startswith("vercel"):
            return self._vercel is not None and self._deployment is not None
        if check.startswith("supabase"):
            return self._supabase is not None and self._ref is not None
        return self._postgres is not None

    async def check(self, check_id: str) -> InfrastructureResult:
        if check_id not in CHECK_IDS:
            raise ValueError("Unsupported infrastructure check")
        try:
            if self.mode == "disabled":
                raise InfrastructureError("integration_disabled")
            if not self._configured(check_id):
                raise InfrastructureError("missing_configuration")
            status, summary, evidence = await self._inspect(check_id)
            result = InfrastructureResult(
                component=check_id,
                check_type=TYPES[check_id],
                status=status,
                severity="high"
                if status == CheckStatus.UNHEALTHY
                else "warning"
                if status == CheckStatus.DEGRADED
                else "none",
                summary=summary,
                evidence=evidence,
                synthetic=self.mode == "fixture",
            )
            if any(secret in result.model_dump_json() for secret in self._secrets):
                raise InfrastructureError("invalid_response")
            return result
        except ValidationError:
            return self._failure(check_id, "invalid_response")
        except InfrastructureError as error:
            return self._failure(check_id, error.code)

    def _failure(self, check_id, reason):
        return InfrastructureResult(
            component=check_id,
            check_type=TYPES[check_id],
            status=CheckStatus.CHECK_FAILED,
            inspection="CHECK_FAILED",
            summary="Infrastructure check could not be verified",
            synthetic=self.mode == "fixture",
            reason=reason,
        )

    async def _inspect(self, check_id):
        if check_id == "postgres":
            return (
                CheckStatus.HEALTHY,
                "Database accepted the fixed read-only SELECT probe",
                await self._postgres.check(),
            )
        if check_id.startswith("vercel"):
            params = {"teamId": self._team} if self._team else {}
            if check_id == "vercel-events":
                params.update(
                    {"direction": "backward", "follow": "0", "limit": "25", "builds": "1"}
                )
                raw = await self._vercel.get(f"/v3/deployments/{self._deployment}/events", params)
                return self._events(raw)
            raw = await self._vercel.get(f"/v13/deployments/{self._deployment}", params)
            deployment = Deployment.model_validate(raw)
            if deployment.id != self._deployment:
                raise InfrastructureError("deployment_identity_mismatch")
            state = deployment.readyState
            status = (
                CheckStatus.HEALTHY
                if state == "READY"
                else CheckStatus.UNHEALTHY
                if state in {"ERROR", "BLOCKED"}
                else CheckStatus.UNKNOWN
            )
            return (
                status,
                "Provider-reported state of the configured deployment",
                {
                    "deployment_id": deployment.id,
                    "ready_state": state,
                    "scope": "configured_deployment_only",
                    "production_alias_verified": False,
                },
            )
        if check_id == "supabase-project":
            raw = await self._supabase.get(f"/v1/projects/{self._ref}")
            project = Project.model_validate(raw)
            if project.ref != self._ref:
                raise InfrastructureError("project_identity_mismatch")
            state = project.status
            status = (
                CheckStatus.HEALTHY
                if state == "ACTIVE_HEALTHY"
                else CheckStatus.UNHEALTHY
                if state in {"ACTIVE_UNHEALTHY", "INIT_FAILED", "RESTORE_FAILED", "PAUSE_FAILED"}
                else CheckStatus.UNKNOWN
            )
            return (
                status,
                "Provider-reported project state",
                {"project_ref": project.ref, "state": state},
            )
        raw = await self._supabase.get(
            f"/v1/projects/{self._ref}/health",
            {"services": "db,auth,rest", "timeout_ms": "2000"},
        )
        if not isinstance(raw, list) or len(raw) != 3:
            raise InfrastructureError("incomplete_service_health")
        services = [ServiceHealth.model_validate(row) for row in raw]
        if {row.name for row in services} != {"db", "auth", "rest"}:
            raise InfrastructureError("incomplete_service_health")
        if any(row.healthy != (row.status == "ACTIVE_HEALTHY") for row in services):
            raise InfrastructureError("contradictory_service_health")
        states = {row.status for row in services}
        status = (
            CheckStatus.UNHEALTHY
            if "UNHEALTHY" in states
            else CheckStatus.DEGRADED
            if "COMING_UP" in states
            else CheckStatus.HEALTHY
        )
        return (
            status,
            "Provider-reported health for db, auth and rest only",
            {
                "services": [{"name": row.name, "state": row.status} for row in services],
            },
        )

    def _events(self, raw):
        if raw is None:
            raw = []
        if not isinstance(raw, list) or len(raw) > 25:
            raise InfrastructureError("invalid_response")
        events = []
        for row in raw:
            event = Event.model_validate(row)
            payload = row.get("payload", row)
            if not isinstance(payload, dict):
                raise InfrastructureError("invalid_response")
            if payload.get("deploymentId") != self._deployment:
                raise InfrastructureError("deployment_identity_mismatch")
            # Never retain log text, URLs, environment values, names, or request metadata.
            events.append({"type": event.type, "created_ms": event.created})
        return (
            CheckStatus.UNKNOWN,
            "Build event sample retrieved; runtime health is unverified",
            {
                "events": events,
                "sample_only": True,
                "limit": 25,
                "limit_reached": len(raw) == 25,
            },
        )
