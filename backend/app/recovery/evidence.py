"""A receipt or top-level success alone never verifies the configured workflow path."""

from datetime import timedelta

from app.recovery.contracts import Decision

MAX_OBSERVATION_AGE = 120
MAX_COMPLETION_AGE = 300
CLOCK_SKEW = timedelta(seconds=5)


def evaluate(action, original, execution, policy, observed_at, at):
    def inconclusive(reason):
        return Decision(result="INCONCLUSIVE", reason=reason)

    if (
        execution.id != action["new_execution_id"]
        or execution.workflow_id != action["workflow_id"]
        or execution.execution_mode != "retry"
        or execution.retry_of != action["execution_id"]
    ):
        return inconclusive("identity_mismatch")
    if (
        observed_at.tzinfo is None
        or not at - timedelta(seconds=MAX_OBSERVATION_AGE) <= observed_at <= at + CLOCK_SKEW
    ):
        return inconclusive("observation_stale")
    if execution.execution_state in {"error", "crashed", "canceled"}:
        return Decision(result="NOT_RECOVERED", reason="execution_failed")
    if execution.execution_state != "success":
        return inconclusive("execution_not_finished")
    if execution.data_availability != "present":
        return inconclusive("missing_execution_data")
    start, stop = execution.started_at, execution.stopped_at
    if (
        start is None
        or stop is None
        or start.tzinfo is None
        or stop.tzinfo is None
        or start < action["dispatch_started_at"] - CLOCK_SKEW
        or stop < start
        or stop > observed_at + CLOCK_SKEW
    ):
        return inconclusive("invalid_timestamps")
    if stop < observed_at - timedelta(seconds=MAX_COMPLETION_AGE):
        return inconclusive("completion_stale")
    failures = {item.node_id for item in original.failures}
    if (
        not failures
        or None in failures
        or not failures <= set(policy.required_node_ids)
        or policy.completion_node_id in failures
    ):
        return inconclusive("original_failure_not_covered")
    nodes = {item.node_id: item for item in execution.observed_nodes if item.node_id is not None}
    if len(nodes) != len([item for item in execution.observed_nodes if item.node_id is not None]):
        return inconclusive("missing_required_nodes")
    if not set(policy.required_node_ids) <= set(nodes):
        return inconclusive("missing_required_nodes")
    if execution.failures or any(
        nodes[identifier].attempts < 1
        or nodes[identifier].failed_attempts != 0
        or nodes[identifier].successful_attempts != nodes[identifier].attempts
        for identifier in policy.required_node_ids
    ):
        return inconclusive("node_not_successful")
    if execution.last_node_ref != nodes[policy.completion_node_id].node_ref:
        return inconclusive("completion_node_not_observed")
    return Decision(result="VERIFIED", reason="required_path_succeeded")
