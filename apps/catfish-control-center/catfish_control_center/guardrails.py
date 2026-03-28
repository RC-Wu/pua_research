from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import AgentNode, GuardrailCheck, GuardrailPolicy, GuardrailState


TERMINAL_AGENT_STATUSES = {"completed", "terminated", "archived", "failed"}
ACTIVE_ALLOCATION_STATUSES = {"active", "allocated", "granted", "running", "leased"}


def build_guardrail_state(
    *,
    policy_payload: dict[str, Any],
    runtime_metrics: dict[str, Any],
    resource_manager_state: dict[str, Any],
    agentdoc_state: dict[str, Any],
    agents: list[AgentNode],
) -> GuardrailState | None:
    if not policy_payload:
        return None

    manager_id = str(
        policy_payload.get("resourceManager", {}).get(
            "managerId",
            resource_manager_state.get("managerId", resource_manager_state.get("manager_id", "resource-manager")),
        )
    )
    observed_at = _first_str(
        runtime_metrics.get("observedAt"),
        runtime_metrics.get("observed_at"),
        resource_manager_state.get("observedAt"),
        resource_manager_state.get("observed_at"),
        agentdoc_state.get("observedAt"),
        agentdoc_state.get("observed_at"),
        policy_payload.get("updatedAt"),
        policy_payload.get("updated_at"),
    )

    policies = _build_policies(policy_payload=policy_payload, manager_id=manager_id)
    checks = [
        _evaluate_root_dir_budget(policy=_policy_by_category(policies, "root_dir_budget_bytes"), runtime_metrics=runtime_metrics),
        _evaluate_vepfs_budget(policy=_policy_by_category(policies, "vepfs_budget_bytes"), runtime_metrics=runtime_metrics),
        _evaluate_cpu_budget(
            policy=_policy_by_category(policies, "cpu_budget_percent"),
            runtime_metrics=runtime_metrics,
            resource_manager_state=resource_manager_state,
        ),
        _evaluate_manager_ownership(
            policy=_policy_by_category(policies, "manager_only_resource_ownership"),
            resource_manager_state=resource_manager_state,
            manager_id=manager_id,
        ),
        _evaluate_gpu_concurrency(
            policy=_policy_by_category(policies, "max_gpu_simultaneous_owners"),
            resource_manager_state=resource_manager_state,
            manager_id=manager_id,
        ),
        _evaluate_agentdoc_cadence(
            policy=_policy_by_category(policies, "agentdoc_cadence_seconds"),
            agentdoc_state=agentdoc_state,
            agents=agents,
        ),
    ]
    overall_status = _overall_guardrail_status(checks)
    return GuardrailState(
        observed_at=observed_at,
        overall_status=overall_status,
        manager_id=manager_id,
        policies=tuple(policy for policy in policies if policy is not None),
        checks=tuple(check for check in checks if check is not None),
        metadata={
            "schema_version": str(policy_payload.get("schemaVersion", "")),
            "resource_manager_owner": manager_id,
        },
    )


def _build_policies(*, policy_payload: dict[str, Any], manager_id: str) -> list[GuardrailPolicy]:
    budgets = policy_payload.get("budgets", {})
    ownership = policy_payload.get("ownership", {})
    gpu = policy_payload.get("gpu", {})
    agentdoc = policy_payload.get("agentDoc", {})

    root_dir = budgets.get("rootDir", {})
    vepfs = budgets.get("vePfs", budgets.get("vepfs", {}))
    cpu = budgets.get("cpu", {})

    return [
        GuardrailPolicy(
            policy_id=str(root_dir.get("policyId", "root-dir-budget")),
            label=str(root_dir.get("label", "Root Directory Budget")),
            category="root_dir_budget_bytes",
            owner=manager_id,
            scope=str(root_dir.get("path", "/")),
            limit=float(root_dir.get("maxBytes", 20 * 1024 * 1024)),
            warn_at=float(root_dir.get("warnBytes", 15 * 1024 * 1024)),
            unit="bytes",
            action_script=str(root_dir.get("actionScript", "")),
            metadata={"path": str(root_dir.get("path", "/"))},
        ),
        GuardrailPolicy(
            policy_id=str(vepfs.get("policyId", "vepfs-budget")),
            label=str(vepfs.get("label", "vePFS Budget")),
            category="vepfs_budget_bytes",
            owner=manager_id,
            scope=str(vepfs.get("path", "/dev_vepfs")),
            limit=float(vepfs.get("maxBytes", 50 * 1024 * 1024 * 1024)),
            warn_at=float(vepfs.get("warnBytes", 45 * 1024 * 1024 * 1024)),
            unit="bytes",
            action_script=str(vepfs.get("actionScript", "")),
            metadata={"path": str(vepfs.get("path", "/dev_vepfs"))},
        ),
        GuardrailPolicy(
            policy_id=str(cpu.get("policyId", "cpu-budget")),
            label=str(cpu.get("label", "CPU Budget")),
            category="cpu_budget_percent",
            owner=manager_id,
            limit=float(cpu.get("maxPercent", 65.0)),
            warn_at=float(cpu.get("warnPercent", 50.0)),
            unit="percent",
            action_script=str(cpu.get("actionScript", "")),
            metadata={"reserve_percent": float(cpu.get("hostReservePercent", 35.0))},
        ),
        GuardrailPolicy(
            policy_id=str(ownership.get("policyId", "resource-manager-ownership")),
            label=str(ownership.get("label", "Manager-Only Resource Ownership")),
            category="manager_only_resource_ownership",
            owner=manager_id,
            limit=0.0,
            warn_at=0.0,
            unit="count",
            action_script=str(ownership.get("actionScript", "")),
            metadata={
                "resource_kinds": list(ownership.get("resourceKinds", ["gpu", "storage", "cpu"])),
            },
        ),
        GuardrailPolicy(
            policy_id=str(gpu.get("policyId", "gpu-manager-only")),
            label=str(gpu.get("label", "GPU Ownership Cap")),
            category="max_gpu_simultaneous_owners",
            owner=manager_id,
            limit=float(gpu.get("maxSimultaneousOwners", 1)),
            warn_at=float(gpu.get("warnSimultaneousOwners", gpu.get("maxSimultaneousOwners", 1))),
            unit="count",
            action_script=str(gpu.get("actionScript", "")),
        ),
        GuardrailPolicy(
            policy_id=str(agentdoc.get("policyId", "agentdoc-heartbeat")),
            label=str(agentdoc.get("label", "AgentDoc Heartbeat Cadence")),
            category="agentdoc_cadence_seconds",
            owner=manager_id,
            limit=float(agentdoc.get("requiredCadenceSeconds", 900)),
            warn_at=float(agentdoc.get("warnCadenceSeconds", 600)),
            unit="seconds",
            action_script=str(agentdoc.get("actionScript", "")),
        ),
    ]


def _policy_by_category(policies: list[GuardrailPolicy], category: str) -> GuardrailPolicy | None:
    for policy in policies:
        if policy.category == category:
            return policy
    return None


def _evaluate_root_dir_budget(
    *,
    policy: GuardrailPolicy | None,
    runtime_metrics: dict[str, Any],
) -> GuardrailCheck | None:
    if policy is None:
        return None
    observed = float(runtime_metrics.get("rootDirUsageBytes", runtime_metrics.get("root_dir_usage_bytes", 0.0)))
    status, severity, blocking = _threshold_status(observed=observed, limit=policy.limit, warn_at=policy.warn_at)
    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=(
            f"Root dir usage is {_format_value(observed, policy.unit)} against "
            f"{_format_value(policy.limit, policy.unit)}."
        ),
        observed=observed,
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata=policy.metadata,
    )


def _evaluate_vepfs_budget(
    *,
    policy: GuardrailPolicy | None,
    runtime_metrics: dict[str, Any],
) -> GuardrailCheck | None:
    if policy is None:
        return None
    observed = float(runtime_metrics.get("vePfsUsageBytes", runtime_metrics.get("vepfs_usage_bytes", 0.0)))
    status, severity, blocking = _threshold_status(observed=observed, limit=policy.limit, warn_at=policy.warn_at)
    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=(
            f"vePFS usage is {_format_value(observed, policy.unit)} against "
            f"{_format_value(policy.limit, policy.unit)}."
        ),
        observed=observed,
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata=policy.metadata,
    )


def _evaluate_cpu_budget(
    *,
    policy: GuardrailPolicy | None,
    runtime_metrics: dict[str, Any],
    resource_manager_state: dict[str, Any],
) -> GuardrailCheck | None:
    if policy is None:
        return None

    observed = runtime_metrics.get("cpuPercent", runtime_metrics.get("cpu_percent"))
    allocated_percent = 0.0
    for allocation in resource_manager_state.get("allocations", []):
        if _resource_kind(allocation) != "cpu":
            continue
        if str(allocation.get("status", "active")) not in ACTIVE_ALLOCATION_STATUSES:
            continue
        allocated_percent += float(allocation.get("percent", allocation.get("cpuPercent", allocation.get("cpu_percent", 0.0))))
    if observed in (None, ""):
        observed = allocated_percent
    observed_value = float(observed or 0.0)
    status, severity, blocking = _threshold_status(
        observed=observed_value,
        limit=policy.limit,
        warn_at=policy.warn_at,
    )
    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=(
            f"CPU usage is {_format_value(observed_value, policy.unit)} with "
            f"{allocated_percent:.1f}% allocated through the manager."
        ),
        observed=observed_value,
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata={"allocated_percent": allocated_percent, **policy.metadata},
    )


def _evaluate_manager_ownership(
    *,
    policy: GuardrailPolicy | None,
    resource_manager_state: dict[str, Any],
    manager_id: str,
) -> GuardrailCheck | None:
    if policy is None:
        return None

    resource_kinds = {str(item) for item in policy.metadata.get("resource_kinds", ["gpu", "storage", "cpu"])}
    invalid_allocations: list[str] = []
    for allocation in resource_manager_state.get("allocations", []):
        if _resource_kind(allocation) not in resource_kinds:
            continue
        owner_id = str(allocation.get("ownerId", allocation.get("owner_id", "")))
        if owner_id != manager_id:
            allocation_id = str(allocation.get("allocationId", allocation.get("allocation_id", "unknown")))
            invalid_allocations.append(f"{allocation_id}:{owner_id or 'unknown'}")

    unmanaged_requests: list[str] = []
    for request in resource_manager_state.get("requests", []):
        if _resource_kind(request) not in resource_kinds:
            continue
        request_status = str(request.get("status", "")).lower()
        if request_status not in {"approved", "active", "granted"}:
            continue
        approved_by = str(request.get("approvedBy", request.get("approved_by", "")))
        if approved_by != manager_id:
            request_id = str(request.get("requestId", request.get("request_id", "unknown")))
            unmanaged_requests.append(f"{request_id}:{approved_by or 'unknown'}")

    violation_count = len(invalid_allocations) + len(unmanaged_requests)
    if violation_count:
        summary = (
            f"Found {violation_count} unmanaged resource grants. "
            f"allocations={','.join(invalid_allocations) or 'none'} "
            f"requests={','.join(unmanaged_requests) or 'none'}."
        )
        status = "breached"
        severity = "critical"
        blocking = True
    else:
        summary = f"All GPU/storage/CPU grants are owned and approved by {manager_id}."
        status = "ok"
        severity = "info"
        blocking = False

    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=summary,
        observed=float(violation_count),
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata={
            "invalid_allocations": invalid_allocations,
            "unmanaged_requests": unmanaged_requests,
        },
    )


def _evaluate_gpu_concurrency(
    *,
    policy: GuardrailPolicy | None,
    resource_manager_state: dict[str, Any],
    manager_id: str,
) -> GuardrailCheck | None:
    if policy is None:
        return None

    holders: set[str] = set()
    for allocation in resource_manager_state.get("allocations", []):
        if _resource_kind(allocation) != "gpu":
            continue
        if str(allocation.get("status", "active")).lower() not in ACTIVE_ALLOCATION_STATUSES:
            continue
        owner_id = str(allocation.get("ownerId", allocation.get("owner_id", "")))
        if owner_id != manager_id:
            continue
        holder = str(
            allocation.get(
                "leaseHolder",
                allocation.get("lease_holder", allocation.get("consumerId", allocation.get("consumer_id", owner_id))),
            )
        )
        if holder:
            holders.add(holder)

    observed = float(len(holders))
    status, severity, blocking = _threshold_status(observed=observed, limit=policy.limit, warn_at=policy.warn_at)
    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=(
            f"Manager-controlled GPU ownership is {int(observed)} holder(s): "
            f"{','.join(sorted(holders)) or 'none'}."
        ),
        observed=observed,
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata={"holders": sorted(holders)},
    )


def _evaluate_agentdoc_cadence(
    *,
    policy: GuardrailPolicy | None,
    agentdoc_state: dict[str, Any],
    agents: list[AgentNode],
) -> GuardrailCheck | None:
    if policy is None:
        return None

    observed_at = _parse_timestamp(
        _first_str(agentdoc_state.get("observedAt"), agentdoc_state.get("observed_at"))
    )
    entries = {
        str(item.get("agentId", item.get("agent_id", ""))): item
        for item in agentdoc_state.get("agents", [])
        if item.get("agentId") or item.get("agent_id")
    }

    missing: list[str] = []
    stale_checks: list[str] = []
    stale_heartbeats: list[str] = []
    max_staleness_seconds = 0
    cadence_seconds = int(policy.limit)

    for agent in agents:
        if agent.status in TERMINAL_AGENT_STATUSES:
            continue
        entry = entries.get(agent.agent_id)
        if not entry:
            missing.append(agent.agent_id)
            max_staleness_seconds = max(max_staleness_seconds, cadence_seconds + 1)
            continue

        last_check = _parse_timestamp(
            _first_str(
                entry.get("lastAgentDocCheckAt"),
                entry.get("lastCheckAt"),
                entry.get("last_check_at"),
            )
        )
        last_heartbeat = _parse_timestamp(
            _first_str(
                entry.get("lastHeartbeatAt"),
                entry.get("last_heartbeat_at"),
                entry.get("heartbeatAt"),
            )
        )

        check_age = _seconds_since(observed_at, last_check)
        heartbeat_age = _seconds_since(observed_at, last_heartbeat)
        max_staleness_seconds = max(max_staleness_seconds, check_age, heartbeat_age)

        if check_age > cadence_seconds:
            stale_checks.append(agent.agent_id)
        if heartbeat_age > cadence_seconds:
            stale_heartbeats.append(agent.agent_id)

    if missing or stale_checks or stale_heartbeats:
        status = "breached"
        severity = "critical"
        blocking = True
        summary = (
            f"AgentDoc cadence is stale. missing={','.join(missing) or 'none'} "
            f"checks={','.join(stale_checks) or 'none'} "
            f"heartbeats={','.join(stale_heartbeats) or 'none'}."
        )
    elif max_staleness_seconds >= int(policy.warn_at):
        status = "warning"
        severity = "warning"
        blocking = False
        summary = (
            f"AgentDoc cadence is approaching the limit at {max_staleness_seconds}s "
            f"against {cadence_seconds}s."
        )
    else:
        status = "ok"
        severity = "info"
        blocking = False
        summary = "All active agents have recent AgentDoc checks and heartbeats."

    return GuardrailCheck(
        check_id=f"check:{policy.policy_id}",
        policy_id=policy.policy_id,
        status=status,
        severity=severity,
        summary=summary,
        observed=float(max_staleness_seconds),
        limit=policy.limit,
        unit=policy.unit,
        blocking=blocking,
        action_script=policy.action_script,
        metadata={
            "missing_agents": missing,
            "stale_checks": stale_checks,
            "stale_heartbeats": stale_heartbeats,
        },
    )


def _threshold_status(*, observed: float, limit: float, warn_at: float) -> tuple[str, str, bool]:
    if observed > limit:
        return "breached", "critical", True
    if warn_at and observed > warn_at:
        return "warning", "warning", False
    return "ok", "info", False


def _overall_guardrail_status(checks: list[GuardrailCheck | None]) -> str:
    present = [check for check in checks if check is not None]
    if any(check.blocking for check in present):
        return "blocked"
    if any(check.status == "warning" for check in present):
        return "warning"
    if present:
        return "ok"
    return "unknown"


def _resource_kind(payload: dict[str, Any]) -> str:
    return str(payload.get("resourceKind", payload.get("resource_kind", ""))).lower()


def _first_str(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _seconds_since(reference: datetime | None, timestamp: datetime | None) -> int:
    if reference is None or timestamp is None:
        return 10**9
    delta = reference - timestamp
    return max(int(delta.total_seconds()), 0)


def _format_value(value: float, unit: str) -> str:
    if unit == "bytes":
        return _format_bytes(value)
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "seconds":
        return f"{int(value)}s"
    if unit == "count":
        return str(int(value))
    return f"{value:.1f}"


def _format_bytes(value: float) -> str:
    remainder = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(remainder) < 1024.0 or suffix == "TiB":
            return f"{remainder:.1f} {suffix}"
        remainder /= 1024.0
    return f"{remainder:.1f} TiB"
