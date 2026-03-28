from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .guardrails import _first_str, _parse_timestamp, _seconds_since
from .models import GuardrailState, SupervisorComponentState, SupervisorState


def build_supervisor_state(
    *,
    policy_payload: dict[str, Any],
    supervisor_payload: dict[str, Any],
    guardrail_state: GuardrailState | None,
) -> SupervisorState | None:
    policy = policy_payload.get("supervisor", {})
    if not policy and not supervisor_payload:
        return None

    observed_at_raw = _first_str(
        supervisor_payload.get("observedAt"),
        supervisor_payload.get("observed_at"),
        policy_payload.get("updatedAt"),
        policy_payload.get("updated_at"),
    )
    observed_at = _parse_timestamp(observed_at_raw)

    worker_stall_seconds = int(policy.get("workerStallSeconds", 900))
    scheduler_stall_seconds = int(policy.get("schedulerStallSeconds", 900))
    restart_cooldown_seconds = int(policy.get("restartCooldownSeconds", 900))
    max_restarts_per_window = int(policy.get("maxRestartsPerWindow", 2))
    restart_window_seconds = int(policy.get("restartWindowSeconds", 3600))
    restart_command_template = str(policy.get("restartCommand", "catfish-supervisor restart --component {component}"))

    components = _build_components(
        supervisor_payload=supervisor_payload,
        observed_at=observed_at,
        worker_stall_seconds=worker_stall_seconds,
        scheduler_stall_seconds=scheduler_stall_seconds,
    )
    unhealthy_components = [component for component in components if component.status in {"stalled", "unhealthy", "failed"}]

    attempts = _restart_attempts(supervisor_payload)
    recent_attempts = [
        attempt
        for attempt in attempts
        if _attempt_is_recent(
            attempt=attempt,
            observed_at=observed_at,
            restart_window_seconds=restart_window_seconds,
        )
    ]
    recent_restart_count = len(recent_attempts)
    last_attempt_at_raw = _latest_attempt_timestamp(attempts)
    last_attempt_at = _parse_timestamp(last_attempt_at_raw)
    cooldown_until = ""
    cooldown_until_dt: datetime | None = None
    if last_attempt_at is not None:
        cooldown_until_dt = last_attempt_at + timedelta(seconds=restart_cooldown_seconds)
        cooldown_until = cooldown_until_dt.isoformat().replace("+00:00", "Z")
    in_cooldown = bool(observed_at is not None and cooldown_until_dt is not None and observed_at < cooldown_until_dt)
    restart_budget_exhausted = recent_restart_count >= max_restarts_per_window

    guardrail_blockers = []
    if guardrail_state is not None:
        guardrail_blockers = [check.policy_id for check in guardrail_state.checks if check.blocking]

    restart_requested = bool(supervisor_payload.get("restartRequested", False))
    restart_required = restart_requested or bool(unhealthy_components)
    primary_component = unhealthy_components[0].component_id if unhealthy_components else "catfish-runtime"
    restart_command = restart_command_template.format(component=primary_component)

    if restart_required and (in_cooldown or restart_budget_exhausted):
        restart_intent = "restart-blocked"
        restart_allowed = False
    elif restart_required:
        restart_intent = "restart-required"
        restart_allowed = True
    else:
        restart_intent = "none"
        restart_allowed = False

    if restart_budget_exhausted:
        restart_reason = "Restart budget exhausted; refusing another respawn in the current window."
    elif in_cooldown:
        restart_reason = "Restart cooldown still active; refusing to respawn early."
    elif unhealthy_components:
        restart_reason = (
            "Components are unhealthy or stalled: "
            + ", ".join(component.component_id for component in unhealthy_components)
        )
    elif restart_requested:
        restart_reason = "Supervisor requested a controlled restart."
    else:
        restart_reason = "Supervisor is healthy."

    if restart_intent == "restart-blocked":
        overall_status = "restart-blocked"
    elif restart_required:
        overall_status = "restart-required"
    elif guardrail_state is not None and guardrail_state.overall_status == "blocked":
        overall_status = "guardrail-blocked"
    elif components:
        overall_status = "healthy"
    else:
        overall_status = "unknown"

    return SupervisorState(
        observed_at=observed_at_raw,
        overall_status=overall_status,
        restart_intent=restart_intent,
        restart_allowed=restart_allowed,
        restart_reason=restart_reason,
        restart_command=restart_command if restart_required else "",
        cooldown_until=cooldown_until,
        max_restarts_per_window=max_restarts_per_window,
        restart_window_seconds=restart_window_seconds,
        recent_restart_count=recent_restart_count,
        components=tuple(components),
        metadata={
            "guardrail_blockers": guardrail_blockers,
            "restart_budget_exhausted": restart_budget_exhausted,
            "restart_requested": restart_requested,
        },
    )


def _build_components(
    *,
    supervisor_payload: dict[str, Any],
    observed_at: datetime | None,
    worker_stall_seconds: int,
    scheduler_stall_seconds: int,
) -> list[SupervisorComponentState]:
    payload = supervisor_payload.get("components", {})
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = []
        for key, value in payload.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("componentId", key)
                items.append(item)
    else:
        items = []

    built: list[SupervisorComponentState] = []
    for item in items:
        component_id = str(item.get("componentId", item.get("component_id", "unknown-component")))
        role = str(item.get("role", component_id))
        configured_status = str(item.get("status", "unknown")).lower()
        healthy = bool(item.get("healthy", configured_status in {"running", "active", "ready"}))
        last_heartbeat_at = _first_str(item.get("lastHeartbeatAt"), item.get("last_heartbeat_at"))
        last_progress_at = _first_str(item.get("lastProgressAt"), item.get("last_progress_at"))
        threshold = int(
            item.get(
                "stallAfterSeconds",
                item.get(
                    "stall_after_seconds",
                    worker_stall_seconds if "worker" in role or "worker" in component_id else scheduler_stall_seconds,
                ),
            )
        )
        stall_seconds = max(
            _seconds_since(observed_at, _parse_timestamp(last_progress_at)),
            _seconds_since(observed_at, _parse_timestamp(last_heartbeat_at)),
        )
        if not healthy or configured_status in {"failed", "crashed"}:
            status = "failed"
        elif stall_seconds > threshold:
            status = "stalled"
        elif configured_status in {"running", "active", "ready"}:
            status = "healthy"
        else:
            status = "unhealthy"

        summary = str(item.get("summary", ""))
        if not summary:
            if status == "stalled":
                summary = f"No heartbeat or progress inside {threshold}s."
            elif status == "failed":
                summary = "Component reported an unhealthy runtime state."
            elif status == "healthy":
                summary = "Component is within heartbeat and progress thresholds."
            else:
                summary = "Component requires operator attention."

        built.append(
            SupervisorComponentState(
                component_id=component_id,
                role=role,
                status=status,
                healthy=(status == "healthy"),
                last_heartbeat_at=last_heartbeat_at,
                last_progress_at=last_progress_at,
                stall_seconds=stall_seconds if stall_seconds < 10**9 else 0,
                stall_threshold_seconds=threshold,
                summary=summary,
                metadata={key: value for key, value in item.items() if key not in {"componentId", "component_id"}},
            )
        )
    return built


def _restart_attempts(supervisor_payload: dict[str, Any]) -> list[dict[str, Any]]:
    payload = supervisor_payload.get("restartHistory", supervisor_payload.get("restarts", []))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _attempt_is_recent(
    *,
    attempt: dict[str, Any],
    observed_at: datetime | None,
    restart_window_seconds: int,
) -> bool:
    if observed_at is None:
        return False
    started_at = _parse_timestamp(_first_str(attempt.get("startedAt"), attempt.get("started_at")))
    if started_at is None:
        return False
    return (observed_at - started_at) <= timedelta(seconds=restart_window_seconds)


def _latest_attempt_timestamp(attempts: list[dict[str, Any]]) -> str:
    timestamps = [
        _first_str(item.get("startedAt"), item.get("started_at"))
        for item in attempts
        if _first_str(item.get("startedAt"), item.get("started_at"))
    ]
    if not timestamps:
        return ""
    latest = max(_parse_timestamp(timestamp) for timestamp in timestamps)
    if latest is None:
        return ""
    return latest.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
