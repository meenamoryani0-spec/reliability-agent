"""Fixed read/observation tools. No inference loop or remediation lives here."""

import asyncio
import json
import math
import threading
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from pydantic import ValidationError

from app.agent.tool_models import (
    Arguments,
    ExecutionArguments,
    FailedExecutionsArguments,
    FlowArguments,
    HistoryCapture,
    PageArguments,
    ToolResult,
    WebsiteArguments,
)
from app.db.snapshots import snapshot_for, source_for
from app.tools.n8n_models import N8nReadResult

MAX_ARGUMENT_BYTES = 4096
MAX_RESULT_BYTES = 65536


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: type[Arguments]
    timeout_seconds: float


SPECS = (
    ToolSpec("list_website_targets", "List registered website IDs; no health check.", Arguments, 5),
    ToolSpec(
        "check_website_http", "Check HTTP headers at a registered website.", WebsiteArguments, 12
    ),
    ToolSpec("check_dns", "Check DNS for a registered website.", WebsiteArguments, 12),
    ToolSpec("check_ssl", "Check TLS for a registered website.", WebsiteArguments, 12),
    ToolSpec(
        "test_website_flow",
        "Run a fixed synthetic booking fixture in Chromium. No customer system is contacted.",
        FlowArguments,
        41,
    ),
    ToolSpec("list_n8n_workflows", "Read one page of n8n workflow metadata.", PageArguments, 31),
    ToolSpec(
        "list_failed_n8n_executions",
        "Read one page of recorded error executions, not all failure states.",
        FailedExecutionsArguments,
        31,
    ),
    ToolSpec(
        "get_n8n_execution",
        "Read sanitized execution evidence. HTTP 401 does not establish an expired credential.",
        ExecutionArguments,
        31,
    ),
    ToolSpec(
        "check_vercel_deployment",
        "Inspect the configured deployment only; production alias health is unverified.",
        Arguments,
        41,
    ),
    ToolSpec(
        "get_vercel_deployment_events",
        "Read at most 25 sanitized build events; a sample does not verify runtime health.",
        Arguments,
        41,
    ),
    ToolSpec("check_supabase_project", "Inspect the configured project state.", Arguments, 41),
    ToolSpec("check_supabase_health", "Inspect configured db/auth/rest health.", Arguments, 41),
    ToolSpec(
        "check_postgres",
        "Run the configured database's fixed read-only SELECT probe.",
        Arguments,
        41,
    ),
)


class BoundaryError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


def reject_constant(_):
    raise ValueError()


def contains_secret(value, secrets):
    # Inspect decoded strings: JSON escaping must not conceal a secret echo.
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    if isinstance(value, dict):
        return any(
            contains_secret(key, secrets) or contains_secret(item, secrets)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_secret(item, secrets) for item in value)
    return False


class ToolRegistry:
    def __init__(
        self,
        config,
        *,
        website_checker,
        browser_checker,
        n8n_service,
        infrastructure_service,
        history,
    ):
        self._config = config
        self._targets = {target.id: target for target in config.website_targets}
        self._history = history
        self._slot = threading.Lock()
        self._task = None
        self._closed = False
        self._specs = MappingProxyType({spec.name: spec for spec in SPECS})
        self._handlers = MappingProxyType(
            {
                "list_website_targets": self._list_websites,
                "check_website_http": partial(self._website, website_checker.check_http),
                "check_dns": partial(self._website, website_checker.check_dns),
                "check_ssl": partial(self._website, website_checker.check_ssl),
                "test_website_flow": partial(self._browser, browser_checker),
                "list_n8n_workflows": partial(self._n8n, n8n_service, "workflows"),
                "list_failed_n8n_executions": partial(self._n8n, n8n_service, "failed_executions"),
                "get_n8n_execution": partial(self._n8n, n8n_service, "execution"),
                "check_vercel_deployment": partial(
                    self._infrastructure, infrastructure_service, "vercel-deployment"
                ),
                "get_vercel_deployment_events": partial(
                    self._infrastructure, infrastructure_service, "vercel-events"
                ),
                "check_supabase_project": partial(
                    self._infrastructure, infrastructure_service, "supabase-project"
                ),
                "check_supabase_health": partial(
                    self._infrastructure, infrastructure_service, "supabase-health"
                ),
                "check_postgres": partial(self._infrastructure, infrastructure_service, "postgres"),
            }
        )
        self._secrets = tuple(
            value.get_secret_value()
            for value in (
                config.nebius_api_key,
                config.n8n_api_key,
                config.vercel_token,
                config.supabase_access_token,
                config.postgres_password,
                config.storage_database_url,
            )
            if value
        )

    def definitions(self):
        """Fresh JSON schemas in the documented Nebius function descriptor shape.

        Server validation is authoritative; no provider-enforced strict mode is assumed.
        """
        if self._config.environment == "production" or self._closed:
            return []
        definitions = []
        for spec in self._specs.values():
            schema = spec.arguments.model_json_schema()
            if spec.arguments is WebsiteArguments and self._targets:
                schema["properties"]["target_id"]["enum"] = sorted(self._targets)
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": schema,
                    },
                }
            )
        return definitions

    def describe(self):
        return {
            "tools": self.definitions(),
            "policy": {
                "monitored_system_writes": False,
                "automatic_incidents": False,
                "max_argument_bytes": MAX_ARGUMENT_BYTES,
                "max_result_bytes": MAX_RESULT_BYTES,
                "max_in_flight": 1,
                "automatic_retries": 0,
                "deadlines_seconds": {
                    spec.name: spec.timeout_seconds for spec in self._specs.values()
                },
                "evidence_is_untrusted_data": True,
            },
        }

    async def execute(self, name: str, arguments_json: str) -> ToolResult:
        if self._config.environment == "production" or self._closed:
            return ToolResult(name=None, status="REJECTED", reason="access_disabled")
        if not isinstance(name, str) or name not in self._specs:
            return ToolResult(name=None, status="REJECTED", reason="unknown_tool")
        spec = self._specs[name]
        try:
            if not isinstance(arguments_json, str):
                raise ValueError()
            if (
                len(arguments_json) > MAX_ARGUMENT_BYTES
                or len(arguments_json.encode()) > MAX_ARGUMENT_BYTES
            ):
                raise BoundaryError("arguments_too_large")
            raw = json.loads(
                arguments_json, object_pairs_hook=unique_object, parse_constant=reject_constant
            )
            arguments = spec.arguments.model_validate(raw)
            if isinstance(arguments, WebsiteArguments) and arguments.target_id not in self._targets:
                raise BoundaryError("target_not_registered")
        except BoundaryError as error:
            return ToolResult(name=name, status="REJECTED", reason=error.code)
        except (ValueError, TypeError, RecursionError):
            # Never echo Pydantic errors, rejected values, or model arguments.
            return ToolResult(name=name, status="REJECTED", reason="invalid_arguments")
        if not self._slot.acquire(blocking=False):
            return ToolResult(name=name, status="REJECTED", reason="busy")
        completed = {}
        self._task = asyncio.create_task(self._run(spec, arguments, completed))
        try:
            # Shield the bounded adapter/worker. Cancelling to_thread does not stop
            # its process or transaction. Keep the slot until actual work finishes.
            return await asyncio.wait_for(asyncio.shield(self._task), spec.timeout_seconds)
        except TimeoutError:
            if "result" in completed:
                # The observation survived; history is still pending/unknown.
                return completed["result"].model_copy(
                    update={"history": HistoryCapture(status="unavailable")}
                )
            return ToolResult(name=name, status="EXECUTION_FAILED", reason="deadline_exceeded")

    async def _run(self, spec, arguments, completed):
        try:
            observation, source = await self._handlers[spec.name](arguments)
            if source is None:
                data = observation
            elif isinstance(observation, N8nReadResult) and observation.operation != "execution":
                data = observation.model_dump(mode="json")
                source = None  # A list page is not a health observation.
            else:
                snapshot = snapshot_for(observation, source)
                data = {
                    "service": snapshot.category,
                    "component": snapshot.component,
                    "check_type": snapshot.kind,
                    "status": snapshot.status.value,
                    "healthy": True
                    if snapshot.status == "HEALTHY"
                    else False
                    if snapshot.status == "UNHEALTHY"
                    else None,
                    "synthetic": snapshot.synthetic,
                    "checked_at": snapshot.observed_at.isoformat(),
                    **snapshot.payload,
                }
                if isinstance(observation, N8nReadResult):
                    data["inspection"] = observation.status
                elif hasattr(observation, "inspection"):
                    data["inspection"] = observation.inspection
                data["reason"] = getattr(observation, "reason", None)
                severity = getattr(observation, "severity", None)
                if severity not in {None, "none", "low", "medium", "high", "warning", "error"}:
                    raise BoundaryError("invalid_result")
                latency = getattr(observation, "latency_ms", None)
                if latency is not None and (not math.isfinite(latency) or latency < 0):
                    raise BoundaryError("invalid_result")
                data.update(severity=severity, latency_ms=latency)
            result = ToolResult(name=spec.name, status="OK", data=data)
            encoded = result.model_dump_json()
            if len(encoded.encode()) > MAX_RESULT_BYTES:
                raise BoundaryError("result_too_large")
            if any(secret in encoded for secret in self._secrets) or contains_secret(
                data, self._secrets
            ):
                raise BoundaryError("unsafe_result")
            # Reserve envelope space for saved-history metadata.
            if len(encoded.encode()) > MAX_RESULT_BYTES - 256:
                raise BoundaryError("result_too_large")
            completed["result"] = result
            if source is not None:
                try:
                    state, identifier = await self._history.capture(observation, source)
                    history = HistoryCapture(status=state, check_id=identifier)
                except Exception:
                    history = HistoryCapture(status="unavailable")
                result = result.model_copy(update={"history": history})
            return result
        except BoundaryError as error:
            return ToolResult(name=spec.name, status="EXECUTION_FAILED", reason=error.code)
        except (ValueError, TypeError, ValidationError, AttributeError):
            return ToolResult(name=spec.name, status="EXECUTION_FAILED", reason="invalid_result")
        except Exception:
            return ToolResult(name=spec.name, status="EXECUTION_FAILED", reason="execution_failed")
        finally:
            self._slot.release()

    async def close(self):
        self._closed = True
        if self._task is not None:
            await asyncio.shield(self._task)

    async def _list_websites(self, _):
        return {"targets": [{"id": key} for key in sorted(self._targets)]}, None

    async def _website(self, check, arguments):
        target = self._targets[arguments.target_id]
        result = await check(target)
        if result.component != target.id:
            raise BoundaryError("invalid_result")
        return result, target.url

    async def _browser(self, checker, arguments):
        result = await checker.check(arguments.flow_id)
        if result.component != arguments.flow_id:
            raise BoundaryError("invalid_result")
        return result, source_for(result, self._config)

    async def _n8n(self, service, operation, arguments):
        result = await service.read(operation, **arguments.model_dump())
        if result.operation != operation:
            raise BoundaryError("invalid_result")
        return result, source_for(result, self._config)

    async def _infrastructure(self, service, check_id, _):
        result = await service.check(check_id)
        if result.component != check_id:
            raise BoundaryError("invalid_result")
        return result, source_for(result, self._config)
