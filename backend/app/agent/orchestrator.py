"""Bounded sequential model/tool loop; conclusions require actual evidence."""

import asyncio
import json
import threading
from dataclasses import dataclass, field

from app.agent.client import NebiusClient, NebiusError
from app.agent.conclusions import (
    SUMMARIES,
    ConclusionError,
    assessment,
    provenance,
    supports,
    validate_conclusion,
)
from app.agent.fixtures import DEMO_QUESTION, fixture_model
from app.agent.investigation_models import EvidenceRecord, InvestigationReport, InvestigationRequest
from app.agent.prompts import system_prompt
from app.agent.safety import configured_secrets, contains_secret, load_object
from app.agent.tool_registry import MAX_RESULT_BYTES
from app.db.assessment import AssessmentCapture, AssessmentDraft

MAX_MODEL_REQUESTS = 6
MAX_TOOL_CALLS = 8
MAX_EVIDENCE_BYTES = 131072
MAX_CONTEXT_BYTES = 196608
INVESTIGATION_TIMEOUT_SECONDS = 120
FIXTURE_TOOLS = frozenset(
    {
        "list_n8n_workflows",
        "list_failed_n8n_executions",
        "get_n8n_execution",
        "test_website_flow",
        "check_vercel_deployment",
        "get_vercel_deployment_events",
        "check_supabase_project",
        "check_supabase_health",
        "check_postgres",
    }
)


@dataclass
class RunState:
    evidence: list[EvidenceRecord] = field(default_factory=list)
    model_requests: int = 0
    tool_calls: int = 0
    evidence_bytes: int = 0
    operation: asyncio.Task | None = None
    report: InvestigationReport | None = None
    stop_reason: str | None = None
    incident_assessment: AssessmentCapture = field(default_factory=AssessmentCapture)


class InvestigationService:
    def __init__(self, config, registry, *, client_factory=None):
        self._config = config
        self._registry = registry
        self._factory = client_factory or (
            (lambda: fixture_model(config))
            if config.investigation_mode == "fixture"
            else (lambda: NebiusClient(config))
        )
        self._secrets = configured_secrets(config)
        self._slot = threading.Lock()
        self._task = None
        self._active = None
        self._closed = False

    def describe(self):
        return {
            "mode": self._config.investigation_mode,
            "model": self._config.nebius_model,
            "configured": self._config.investigation_mode == "fixture"
            or self._config.nebius_api_key is not None,
            "inference_source": self._source(),
            "live_connectivity_verified": False,
            "max_model_requests": MAX_MODEL_REQUESTS,
            "max_tool_calls": MAX_TOOL_CALLS,
            "max_in_flight": 1,
            "deadline_seconds": INVESTIGATION_TIMEOUT_SECONDS,
            "automatic_incidents": self._config.incidents_enabled,
            "remediation": False,
        }

    def _source(self):
        return {"fixture": "scripted_fixture", "live": "nebius", "disabled": "disabled"}[
            self._config.investigation_mode
        ]

    def _report(self, state, status, reason=None, draft=None):
        return InvestigationReport(
            status=status,
            reason=reason,
            inference_source=self._source(),
            model=self._config.nebius_model
            if self._config.investigation_mode != "disabled"
            else None,
            model_requests=state.model_requests,
            tool_calls=state.tool_calls,
            evidence=list(state.evidence),
            evidence_provenance=provenance(state.evidence),
            assessment=assessment(state.evidence),
            hypothesis=draft.hypothesis if draft else None,
            summary=(
                SUMMARIES[draft.hypothesis]
                + " Its role in the reported problem, underlying cause, "
                "and business outcome remain unverified."
                if draft
                else "Investigation did not reach a validated conclusion. "
                "Collected observations remain available."
            ),
            cited_evidence_ids=draft.evidence_ids if draft else [],
            next_steps=draft.next_steps if draft else [],
            incident_assessment=state.incident_assessment
            if self._config.incidents_enabled
            else AssessmentCapture(status="disabled"),
            incident_created=any(
                record.result.history.incident.status == "created" for record in state.evidence
            ),
            incident_ids=list(
                dict.fromkeys(
                    record.result.history.incident.incident_id
                    for record in state.evidence
                    if record.result.history.incident.incident_id
                )
            ),
        )

    async def investigate(self, question):
        state = RunState()
        if self._closed or self._config.environment == "production":
            return self._report(state, "REJECTED", "access_disabled")
        if self._config.investigation_mode == "disabled":
            return self._report(state, "REJECTED", "disabled")
        try:
            question = InvestigationRequest(question=question).question
        except (ValueError, TypeError):
            return self._report(state, "REJECTED", "invalid_question")
        if contains_secret(question, self._secrets):
            return self._report(state, "REJECTED", "sensitive_input")
        if self._config.investigation_mode == "fixture" and question != DEMO_QUESTION:
            return self._report(state, "REJECTED", "fixture_question_unsupported")
        if self._config.investigation_mode == "live" and self._config.nebius_api_key is None:
            return self._report(state, "CHECK_FAILED", "missing_api_key")
        if not self._slot.acquire(blocking=False):
            return self._report(state, "REJECTED", "busy")
        self._active = state
        self._task = asyncio.create_task(self._work(state, question))
        try:
            return await asyncio.wait_for(asyncio.shield(self._task), INVESTIGATION_TIMEOUT_SECONDS)
        except TimeoutError:
            self._stop(state, "deadline_exceeded")
            return state.report or self._report(state, "INCOMPLETE", "deadline_exceeded")
        except asyncio.CancelledError:
            self._stop(state, "cancelled")
            raise

    @staticmethod
    def _stop(state, reason):
        # Cancel only the model/tool loop. The owner task must finish draining
        # the registry even if a caller disconnects or shutdown follows a timeout.
        if state.stop_reason is None:
            state.stop_reason = reason
            if state.operation is not None and not state.operation.done():
                state.operation.cancel()

    async def _work(self, state, question):
        try:
            if state.stop_reason:
                state.report = self._report(state, "INCOMPLETE", state.stop_reason)
                return state.report
            state.operation = asyncio.create_task(self._loop(state, question))
            try:
                state.report = await state.operation
            except asyncio.CancelledError:
                state.report = self._report(state, "INCOMPLETE", state.stop_reason or "cancelled")
            except NebiusError:
                state.report = self._report(state, "CHECK_FAILED", "provider_error")
            except Exception:
                state.report = self._report(state, "CHECK_FAILED", "execution_failed")
            return state.report
        finally:
            try:
                await self._registry.wait_idle()
            finally:
                self._slot.release()

    async def _loop(self, state, question):
        definitions = self._registry.definitions()
        if self._config.investigation_mode == "fixture":
            definitions = [
                item for item in definitions if item["function"]["name"] in FIXTURE_TOOLS
            ]
        allowed = {item["function"]["name"] for item in definitions}
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": question},
        ]
        seen_ids, seen_calls = set(), set()
        async with self._factory() as client:
            await client.verify_model_available()
            for _ in range(MAX_MODEL_REQUESTS):
                if (
                    len(
                        json.dumps(
                            {"messages": messages, "tools": definitions}, ensure_ascii=False
                        ).encode()
                    )
                    > MAX_CONTEXT_BYTES
                ):
                    return self._report(state, "INCOMPLETE", "context_budget_exhausted")
                state.model_requests += 1
                turn = await client.next_turn(messages, definitions)
                message = turn.choices[0].message
                if contains_secret(message.model_dump(), self._secrets):
                    return self._report(state, "CHECK_FAILED", "unsafe_model_output")
                calls = message.tool_calls
                if not calls:
                    if not state.evidence:
                        return self._report(state, "INCOMPLETE", "no_evidence")
                    try:
                        draft = validate_conclusion(message.content, state.evidence)
                    except ConclusionError as error:
                        return self._report(state, "INCOMPLETE", error.code)
                    if self._config.incidents_enabled:
                        drafts = [
                            AssessmentDraft(
                                check_id=record.result.history.check_id,
                                hypothesis=draft.hypothesis,
                                recommended_steps=draft.next_steps,
                                inference_source=self._source(),
                            )
                            for record in state.evidence
                            if record.id in draft.evidence_ids
                            and record.result.history.incident.incident_id
                            and supports(draft.hypothesis, record.result)
                        ]
                        state.incident_assessment = AssessmentCapture(status="unavailable")
                        state.incident_assessment = await self._registry.save_incident_assessments(
                            drafts
                        )
                    return self._report(state, "COMPLETED", draft=draft)
                if state.tool_calls + len(calls) > MAX_TOOL_CALLS:
                    return self._report(state, "INCOMPLETE", "tool_budget_exhausted")
                # Preflight the whole batch before executing any of it.
                pending_ids, pending_calls = set(), set()
                for call in calls:
                    if call.function.name not in allowed:
                        return self._report(state, "INCOMPLETE", "tool_not_allowed")
                    if call.id in seen_ids or call.id in pending_ids:
                        return self._report(state, "INCOMPLETE", "duplicate_tool_id")
                    try:
                        arguments = load_object(call.function.arguments, 4096)
                        key = (call.function.name, json.dumps(arguments, sort_keys=True))
                    except (ValueError, TypeError, RecursionError):
                        key = (call.function.name, call.function.arguments)
                    if key in seen_calls or key in pending_calls:
                        return self._report(state, "INCOMPLETE", "repeated_tool_call")
                    pending_ids.add(call.id)
                    pending_calls.add(key)
                seen_ids.update(pending_ids)
                seen_calls.update(pending_calls)
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [call.model_dump() for call in calls],
                    }
                )
                for call in calls:
                    # Leave room for the largest allowed result before starting I/O.
                    if state.evidence_bytes > MAX_EVIDENCE_BYTES - MAX_RESULT_BYTES - 256:
                        return self._report(state, "INCOMPLETE", "evidence_budget_exhausted")
                    state.tool_calls += 1
                    result = await self._registry.execute(
                        call.function.name, call.function.arguments
                    )
                    record = EvidenceRecord(id=f"e{state.tool_calls}", result=result)
                    state.evidence.append(record)
                    content = record.model_dump_json()
                    state.evidence_bytes += len(content.encode())
                    if result.status != "OK":
                        return self._report(state, "INCOMPLETE", "tool_failed")
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
            return self._report(state, "INCOMPLETE", "model_budget_exhausted")

    async def close(self):
        self._closed = True
        if self._active is not None:
            self._stop(self._active, "cancelled")
        if self._task is not None:
            await asyncio.shield(self._task)
