from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from catfish_route_core import (  # noqa: E402
    DEFAULT_HEALTH_PATH,
    DEFAULT_LEDGER_PATH,
    DEFAULT_REGISTRY_PATH,
    health_index,
    load_router_inputs,
    provider_blockers,
    select_provider_route,
)
from catfish_runtime import CatfishRuntime, utc_now  # noqa: E402


SCHEMA_VERSION = "catfish.remote-dispatch.v1"
DEFAULT_REMOTE_LAUNCHER_PATH = (
    REPO_ROOT / "skills" / "skills-codex" / "remote-codex-subagents" / "scripts" / "remote_codex_subagents.py"
)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: object) -> str:
    text = str(value).strip().lower()
    chars: list[str] = []
    last_sep = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            last_sep = False
            continue
        if char in {"-", "_", ".", ":", "/"} and not last_sep:
            chars.append("-")
            last_sep = True
    result = "".join(chars).strip("-")
    return result or "item"


def bool_from_any(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Cannot coerce value to bool: {value!r}")


def ensure_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Expected a string or list of strings, got {type(value).__name__}")


def require_nonempty(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    joined = ", ".join(keys)
    raise ValueError(f"Missing required field: {joined}")


def project_id_from_state(state: dict[str, Any]) -> str:
    project = dict(state.get("project") or {})
    runtime = dict(state.get("runtime") or {})
    return require_nonempty(project, "projectId", "project_id") if project else require_nonempty(
        runtime, "projectId", "project_id"
    )


def stage_value(stage: dict[str, Any], *keys: str, default: Any = None) -> Any:
    competition = dict(stage.get("competition") or {})
    dispatch = dict(stage.get("dispatch") or {})
    for source in (stage, competition, dispatch):
        for key in keys:
            if key in source and source.get(key) is not None:
                return source.get(key)
    return default


def read_text_file(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def normalize_agent_groups(stage: dict[str, Any], project: dict[str, Any]) -> list[dict[str, Any]]:
    raw_groups = stage.get("agentGroups")
    if raw_groups is None:
        raw_groups = project.get("agentGroups")
    if raw_groups is None:
        raw_groups = [
            {
                "agentGroupId": "builder",
                "label": "Builder",
                "roles": ["worker"],
                "scoreBias": 0.0,
            }
        ]

    groups: list[dict[str, Any]] = []
    for index, entry in enumerate(raw_groups):
        if isinstance(entry, str):
            entry = {"agentGroupId": entry, "label": entry.replace("-", " ").title(), "roles": ["worker"]}
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid agent group entry at index {index}: {entry!r}")
        agent_group_id = require_nonempty(entry, "agentGroupId", "id", "name")
        groups.append(
            {
                "agentGroupId": agent_group_id,
                "label": str(entry.get("label", agent_group_id)),
                "roles": ensure_string_list(entry.get("roles")) or ["worker"],
                "scoreBias": float(entry.get("scoreBias", 0.0)),
                "promptPrefix": str(entry.get("promptPrefix", "")).strip(),
                "metadata": dict(entry.get("metadata") or {}),
            }
        )
    return groups


def materialize_runtime_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    runtime_payload = dict(state.get("runtime") or {})
    project_id = project_id_from_state(state)
    snapshot = runtime_payload.get("snapshot")
    if isinstance(snapshot, dict):
        if snapshot.get("schema_version") == "catfish-runtime/v1":
            return snapshot
        if "projects" in snapshot:
            return snapshot
    operations = runtime_payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("Dispatch state must provide runtime.snapshot or runtime.operations")
    runtime = CatfishRuntime()
    runtime.apply_operations(operations)
    return runtime.snapshot(project_id=project_id)


def extract_project_snapshot(snapshot: dict[str, Any], project_id: str) -> dict[str, Any]:
    projects = snapshot.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("Runtime snapshot must contain a projects object")
    project_snapshot = projects.get(project_id)
    if not isinstance(project_snapshot, dict):
        raise ValueError(f"Runtime snapshot does not include project {project_id}")
    return project_snapshot


def build_route_spec(route: dict[str, Any], *, route_name: str) -> dict[str, Any]:
    return {
        "route_name": route_name,
        "provider_name": route.get("provider_name") or "",
        "provider_display_name": route.get("provider_display_name") or route.get("provider_name") or "",
        "provider_base_url": route.get("provider_base_url") or "",
        "provider_wire_api": route.get("provider_wire_api") or "responses",
        "provider_env_key": route.get("provider_env_key") or "OPENAI_API_KEY",
        "provider_requires_openai_auth": bool(route.get("provider_requires_openai_auth", False)),
        "model": route.get("model") or "",
    }


def unique_launchable_routes(
    route_payload: dict[str, Any],
    *,
    registry: dict[str, Any],
    health_snapshot: dict[str, Any],
    machine_id: str,
) -> list[dict[str, Any]]:
    health_by_provider = health_index(health_snapshot)
    launchable: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in route_payload.get("alternatives", []):
        provider_id = str(candidate.get("provider_id") or "").strip()
        if not provider_id or provider_id in seen:
            continue
        if candidate.get("blockers"):
            continue
        seen.add(provider_id)
        launchable.append(dict(candidate))

    providers_by_id = {
        str(provider.get("id")): dict(provider)
        for provider in registry.get("providers", [])
        if provider.get("id")
    }
    launchable.sort(
        key=lambda item: (
            -float(item.get("score", 0.0)),
            provider_blockers(
                providers_by_id.get(str(item.get("provider_id")), {}),
                health_by_provider.get(str(item.get("provider_id"))),
                machine_id=machine_id,
                tier_id=str(item.get("tierId") or ""),
                requested_model=str(item.get("model") or "") or None,
            ),
            str(item.get("provider_id") or ""),
        )
    )
    return launchable


def diversity_config(stage: dict[str, Any], project: dict[str, Any]) -> dict[str, float]:
    dispatch = dict(project.get("dispatchDefaults") or {})
    dispatch.update(dict(stage.get("dispatch") or {}))
    return {
        "unused_provider_bonus": float(dispatch.get("unusedProviderBonus", 0.25)),
        "unused_model_bonus": float(dispatch.get("unusedModelBonus", 0.05)),
        "unused_agent_group_bonus": float(dispatch.get("unusedAgentGroupBonus", 0.1)),
        "provider_repeat_penalty": float(dispatch.get("providerRepeatPenalty", 0.2)),
        "model_repeat_penalty": float(dispatch.get("modelRepeatPenalty", 0.05)),
        "agent_group_repeat_penalty": float(dispatch.get("agentGroupRepeatPenalty", 0.12)),
        "bundle_repeat_penalty": float(dispatch.get("bundleRepeatPenalty", 0.3)),
        "route_rank_penalty": float(dispatch.get("routeRankPenalty", 0.02)),
        "agent_group_rank_penalty": float(dispatch.get("agentGroupRankPenalty", 0.01)),
    }


def choose_candidate_bundles(
    *,
    stage: dict[str, Any],
    project: dict[str, Any],
    launchable_routes: list[dict[str, Any]],
    agent_groups: list[dict[str, Any]],
    candidate_count: int,
) -> list[dict[str, Any]]:
    if not launchable_routes:
        raise ValueError(f"Stage {stage.get('stageId', '<unknown>')} has no launchable routes")

    config = diversity_config(stage, project)
    pool: list[dict[str, Any]] = []
    for route_rank, route in enumerate(launchable_routes):
        for group_rank, agent_group in enumerate(agent_groups):
            pool.append(
                {
                    "route": route,
                    "agent_group": agent_group,
                    "baseScore": float(route.get("score", 0.0))
                    + float(agent_group.get("scoreBias", 0.0))
                    - (route_rank * config["route_rank_penalty"])
                    - (group_rank * config["agent_group_rank_penalty"]),
                }
            )

    selected: list[dict[str, Any]] = []
    provider_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    bundle_counts: Counter[str] = Counter()

    for _ in range(candidate_count):
        best_choice: dict[str, Any] | None = None
        best_score: float | None = None
        for option in pool:
            route = option["route"]
            agent_group = option["agent_group"]
            provider_id = str(route.get("provider_id") or "")
            model = str(route.get("model") or "")
            agent_group_id = str(agent_group.get("agentGroupId") or "")
            bundle_key = f"{provider_id}:{model}:{agent_group_id}"
            diversity_score = option["baseScore"]
            diversity_score += config["unused_provider_bonus"] if provider_counts[provider_id] == 0 else -(
                provider_counts[provider_id] * config["provider_repeat_penalty"]
            )
            diversity_score += config["unused_model_bonus"] if model_counts[model] == 0 else -(
                model_counts[model] * config["model_repeat_penalty"]
            )
            diversity_score += config["unused_agent_group_bonus"] if group_counts[agent_group_id] == 0 else -(
                group_counts[agent_group_id] * config["agent_group_repeat_penalty"]
            )
            diversity_score -= bundle_counts[bundle_key] * config["bundle_repeat_penalty"]
            if best_choice is None or diversity_score > float(best_score):
                best_choice = {
                    "route": route,
                    "agent_group": agent_group,
                    "bundle_key": bundle_key,
                    "selectionScore": round(diversity_score, 6),
                    "baseScore": round(float(option["baseScore"]), 6),
                }
                best_score = diversity_score
        assert best_choice is not None
        selected.append(best_choice)
        route = best_choice["route"]
        agent_group = best_choice["agent_group"]
        provider_id = str(route.get("provider_id") or "")
        model = str(route.get("model") or "")
        agent_group_id = str(agent_group.get("agentGroupId") or "")
        provider_counts[provider_id] += 1
        model_counts[model] += 1
        group_counts[agent_group_id] += 1
        bundle_counts[best_choice["bundle_key"]] += 1

    return selected


def resolve_stage_prompt(stage: dict[str, Any], state_dir: Path) -> str:
    parts: list[str] = []
    prompt_file = stage.get("promptFile")
    if prompt_file:
        parts.append(read_text_file((state_dir / str(prompt_file)).resolve()))
    prompt_text = str(stage.get("promptText", "")).strip()
    if prompt_text:
        parts.append(prompt_text)
    prompt = "\n\n".join(part.strip() for part in parts if part.strip()).strip()
    if not prompt:
        raise ValueError(f"Stage {stage.get('stageId', '<unknown>')} must provide promptText or promptFile")
    return prompt


def candidate_identifiers(
    *,
    project_id: str,
    stage: dict[str, Any],
    route: dict[str, Any],
    agent_group: dict[str, Any],
    index: int,
) -> dict[str, str]:
    stage_id = require_nonempty(stage, "stageId", "stage_id")
    cell_prefix = str(stage.get("competitionCellPrefix", f"{stage_id}-cell")).strip()
    provided_cell_ids = ensure_string_list(stage.get("competitionCellIds"))
    if index < len(provided_cell_ids):
        competition_cell_id = provided_cell_ids[index]
    else:
        competition_cell_id = f"{cell_prefix}-{index + 1:02d}"

    branch_prefix = str(stage.get("branchPrefix") or f"{project_id}/{stage_id}").strip().strip("/")
    provided_branch_ids = ensure_string_list(stage.get("branchIds"))
    if index < len(provided_branch_ids):
        branch_id = provided_branch_ids[index]
    else:
        branch_suffix = "-".join(
            [
                slugify(index + 1),
                slugify(route.get("provider_id") or "provider"),
                slugify(route.get("model") or "model"),
                slugify(agent_group.get("agentGroupId") or "group"),
            ]
        )
        branch_id = f"{branch_prefix}/{branch_suffix}"

    wave_run_id = str(stage.get("dispatchRunId") or f"{project_id}-{stage_id}").strip()
    agent_name = slugify(f"{competition_cell_id}-{route.get('provider_id')}-{agent_group.get('agentGroupId')}")
    candidate_run_id = f"{wave_run_id}:{agent_name}"
    node_id = f"{stage_id}:{competition_cell_id}"
    return {
        "competition_cell_id": competition_cell_id,
        "branch_id": branch_id,
        "wave_run_id": wave_run_id,
        "agent_name": agent_name,
        "candidate_run_id": candidate_run_id,
        "node_id": node_id,
    }


def build_candidate_prompt(
    *,
    project: dict[str, Any],
    stage: dict[str, Any],
    route: dict[str, Any],
    agent_group: dict[str, Any],
    identifiers: dict[str, str],
    stage_prompt: str,
) -> str:
    stage_id = require_nonempty(stage, "stageId", "stage_id")
    competition_id = str(stage.get("competitionId") or f"{stage_id}:competition")
    lines = [
        "# Catfish Dispatch Task",
        "",
        f"Project: {require_nonempty(project, 'projectId', 'project_id')}",
        f"Stage: {stage_id}",
        f"Competition ID: {competition_id}",
        f"Competition Cell ID: {identifiers['competition_cell_id']}",
        f"Branch ID: {identifiers['branch_id']}",
        f"Run ID: {identifiers['candidate_run_id']}",
        f"Agent Group: {agent_group['agentGroupId']} ({agent_group['label']})",
        f"Provider Bundle: {route.get('provider_id')} / {route.get('model')} / {agent_group['agentGroupId']}",
        "",
        "Execution constraints:",
        f"- Work only inside {stage.get('cwd') or project.get('workspaceRoot') or ''}",
        "- You are not alone in the codebase. Do not revert work from other branches.",
        "- Adjust to the current integrated Catfish state before changing code.",
        "- Use find/grep/sed fallbacks if rg is unavailable.",
        "- Stop after one pass once the requested deliverable is complete.",
        "",
    ]
    prompt_prefix = str(agent_group.get("promptPrefix", "")).strip()
    if prompt_prefix:
        lines.extend([prompt_prefix, ""])
    lines.extend([stage_prompt.strip(), ""])
    return "\n".join(lines).strip() + "\n"


def launch_defaults(project: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    defaults = dict(project.get("launchDefaults") or {})
    defaults.update(dict(stage.get("launch") or {}))
    return {
        "host": str(defaults.get("host", "local")),
        "remote_home": str(defaults.get("remoteHome", "/dev_vepfs/rc_wu")),
        "remote_binary_store": str(defaults.get("remoteBinaryStore", "/dev_vepfs/rc_wu/bin/codex")),
        "remote_run_root": str(defaults.get("remoteRunRoot", "/dev_vepfs/rc_wu/codex_subagents")),
        "sandbox": str(defaults.get("sandbox", "danger-full-access")),
        "approval": str(defaults.get("approval", "never")),
        "search": bool_from_any(defaults.get("search"), default=False),
        "skip_install": bool_from_any(defaults.get("skipInstall"), default=True),
        "env": ensure_string_list(defaults.get("env")),
        "unset_env": ensure_string_list(defaults.get("unsetEnv")),
        "add_dir": ensure_string_list(defaults.get("addDir")),
        "ensure_dev02_proxy": defaults.get("ensureDev02Proxy"),
        "auto_dev02_sandbox_fix": defaults.get("autoDev02SandboxFix"),
    }


def build_launch_command(launch_spec: dict[str, Any]) -> list[str]:
    command = [
        "python3",
        str(DEFAULT_REMOTE_LAUNCHER_PATH),
        "launch",
        "--host",
        str(launch_spec["host"]),
        "--run-id",
        str(launch_spec["wave_run_id"]),
        "--agent-name",
        str(launch_spec["agent_name"]),
        "--cwd",
        str(launch_spec["cwd"]),
        "--prompt-file",
        str(launch_spec["prompt_file"]),
        "--route-spec-file",
        str(launch_spec["route_specs_file"]),
        "--sandbox",
        str(launch_spec["sandbox"]),
        "--approval",
        str(launch_spec["approval"]),
        "--remote-home",
        str(launch_spec["remote_home"]),
        "--remote-binary-store",
        str(launch_spec["remote_binary_store"]),
        "--remote-run-root",
        str(launch_spec["remote_run_root"]),
    ]
    if bool(launch_spec.get("search")):
        command.append("--search")
    if bool(launch_spec.get("skip_install")):
        command.append("--skip-install")
    if launch_spec.get("ensure_dev02_proxy") is True:
        command.append("--ensure-dev02-proxy")
    elif launch_spec.get("ensure_dev02_proxy") is False:
        command.append("--no-ensure-dev02-proxy")
    if launch_spec.get("auto_dev02_sandbox_fix") is False:
        command.append("--no-auto-dev02-sandbox-fix")
    for item in launch_spec.get("env", []):
        command.extend(["--env", str(item)])
    for item in launch_spec.get("unset_env", []):
        command.extend(["--unset-env", str(item)])
    for item in launch_spec.get("add_dir", []):
        command.extend(["--add-dir", str(item)])
    return command


def control_provider_payloads(
    registry: dict[str, Any],
    health_snapshot: dict[str, Any],
    *,
    selected_provider_ids: set[str],
) -> list[dict[str, Any]]:
    health_by_provider = health_index(health_snapshot)
    providers: list[dict[str, Any]] = []
    for provider in registry.get("providers", []):
        provider = dict(provider)
        provider_id = str(provider.get("id") or "")
        health = dict(health_by_provider.get(provider_id) or {})
        route_tiers = {
            tier_id: {
                "model": tier.get("model"),
                "reasoning_effort": tier.get("reasoningEffort"),
            }
            for tier_id, tier in sorted((provider.get("modelTiers") or {}).items())
        }
        providers.append(
            {
                "profile_id": provider_id,
                "label": provider.get("displayName") or provider.get("providerName") or provider_id,
                "machine_ids": list(provider.get("machineIds") or []),
                "available": bool(health.get("endpointReachable", False)),
                "verified": health.get("quotaState") != "exhausted",
                "remaining_credit": 1.0 if health.get("quotaState") == "healthy" else 0.0,
                "reserve_floor": 0.0,
                "routing_weight": float(provider.get("routingWeight", 1.0)),
                "issues": list(health.get("notes") or []),
                "route_tiers": route_tiers,
                "selected": provider_id in selected_provider_ids,
            }
        )
    return providers


def build_control_snapshot(
    *,
    state: dict[str, Any],
    registry: dict[str, Any],
    health_snapshot: dict[str, Any],
    stage_plans: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    project = dict(state.get("project") or {})
    project_id = require_nonempty(project, "projectId", "project_id")
    active_branches = [
        candidate["branch_id"]
        for stage in stage_plans
        for candidate in stage.get("candidates", [])
    ]
    selected_provider_ids = {
        candidate["selected_route"]["provider_id"]
        for stage in stage_plans
        for candidate in stage.get("candidates", [])
    }

    agents: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for stage in stage_plans:
        for candidate in stage.get("candidates", []):
            agents.append(
                {
                    "agent_id": candidate["candidate_run_id"],
                    "label": candidate["label"],
                    "role": "worker",
                    "status": candidate["status"],
                    "project_id": project_id,
                    "provider_profile": candidate["selected_route"]["provider_id"],
                    "task_kind": stage["task_category"],
                    "branch": candidate["branch_id"],
                    "parent_id": stage["parent_node_id"],
                    "machine_id": stage["machine_id"],
                    "summary": f"Planned {stage['stage_id']} candidate for {candidate['competition_cell_id']}",
                }
            )
            branches.append(
                {
                    "branch": candidate["branch_id"],
                    "project_id": project_id,
                    "score": float(candidate["selection_score"]),
                    "wins": 0,
                    "losses": 0,
                    "state": candidate["status"],
                    "head_commit": "",
                    "summary": candidate["bundle_key"],
                }
            )
            events.append(
                {
                    "event_id": f"dispatch-{slugify(candidate['candidate_run_id'])}",
                    "timestamp": generated_at,
                    "level": "info",
                    "kind": "dispatch-plan",
                    "message": f"Planned {candidate['candidate_run_id']} for {candidate['competition_cell_id']}.",
                    "project_id": project_id,
                    "agent_id": candidate["candidate_run_id"],
                    "branch": candidate["branch_id"],
                    "payload": {
                        "competition_id": stage["competition_id"],
                        "competition_cell_id": candidate["competition_cell_id"],
                        "provider_id": candidate["selected_route"]["provider_id"],
                        "model": candidate["selected_route"]["model"],
                        "agent_group_id": candidate["agent_group"]["agentGroupId"],
                        "agent_root": candidate["agent_root"],
                    },
                }
            )

    return {
        "generated_at": generated_at,
        "projects": [
            {
                "project_id": project_id,
                "label": project.get("title") or project_id,
                "status": str(project.get("status", "dispatch-planned")),
                "active_branch": active_branches[0] if active_branches else "",
                "owner": "catfish-remote-dispatch",
                "active_agents": len(agents),
                "pending_reviews": len(stage_plans),
                "last_event_at": generated_at,
                "summary": f"Prepared {len(agents)} remote Codex launch candidates across {len(stage_plans)} stages.",
            }
        ],
        "agents": agents,
        "providers": control_provider_payloads(
            registry,
            health_snapshot,
            selected_provider_ids=selected_provider_ids,
        ),
        "branches": branches,
        "events": events,
        "metadata": {
            "schemaVersion": SCHEMA_VERSION,
            "source": "catfish_remote_dispatch",
            "workspace": str(project.get("workspaceRoot") or ""),
        },
    }


def build_dispatch_plan(
    state: dict[str, Any],
    *,
    registry: dict[str, Any],
    health_snapshot: dict[str, Any],
    ledger: dict[str, Any],
    state_path: Path,
) -> dict[str, Any]:
    project = dict(state.get("project") or {})
    project_id = require_nonempty(project, "projectId", "project_id")
    base_snapshot = materialize_runtime_snapshot(state)
    project_snapshot = extract_project_snapshot(base_snapshot, project_id)
    nodes = dict(project_snapshot.get("nodes") or {})
    stages = state.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("Dispatch state must define a non-empty stages list")

    generated_at = utc_now()
    launch_defaults_map = dict(project.get("launchDefaults") or {})
    project_machine_id = str(project.get("defaultMachineId") or launch_defaults_map.get("machineId") or "dev-intern-02")
    stage_plans: list[dict[str, Any]] = []
    runtime_operations: list[dict[str, Any]] = []
    state_dir = state_path.resolve().parent

    for stage_index, raw_stage in enumerate(stages):
        if not isinstance(raw_stage, dict):
            raise ValueError(f"Stage at index {stage_index} must be an object")
        stage = dict(raw_stage)
        stage_id = require_nonempty(stage, "stageId", "stage_id")
        parent_node_id = require_nonempty(stage, "parentNodeId", "parent_node_id")
        if parent_node_id not in nodes:
            raise ValueError(f"Stage {stage_id} references unknown parent node {parent_node_id}")

        competition_id = str(stage.get("competitionId") or f"{stage_id}:competition")
        competitive = bool_from_any(stage_value(stage, "competitive", "allowCompetition"), default=True)
        requested_count = int(stage_value(stage, "candidateCount", "frontierWidth", default=1) or 1)
        candidate_count = max(1, requested_count if competitive else 1)
        machine_id = str(stage.get("machineId") or project_machine_id)
        task_category = str(stage.get("taskCategory") or stage.get("task_kind") or "builder")
        difficulty = str(stage.get("difficulty") or "medium")
        parent_score = float(stage.get("parentScore", 0.5))
        requested_tier = str(stage.get("requestedTier") or "").strip() or None
        requested_model = str(stage.get("requestedModel") or "").strip() or None
        route_payload = select_provider_route(
            registry,
            health_snapshot,
            ledger,
            machine_id=machine_id,
            task_category=task_category,
            difficulty=difficulty,
            parent_score=parent_score,
            requested_tier=requested_tier,
            requested_model=requested_model,
        )
        launchable_routes = unique_launchable_routes(
            route_payload,
            registry=registry,
            health_snapshot=health_snapshot,
            machine_id=machine_id,
        )
        agent_groups = normalize_agent_groups(stage, project)
        selected_bundles = choose_candidate_bundles(
            stage=stage,
            project=project,
            launchable_routes=launchable_routes,
            agent_groups=agent_groups,
            candidate_count=candidate_count,
        )
        stage_prompt = resolve_stage_prompt(stage, state_dir)
        launch_defaults_payload = launch_defaults(project, stage)
        cwd = str(stage.get("cwd") or project.get("workspaceRoot") or "").strip()
        if not cwd:
            raise ValueError(f"Stage {stage_id} must define cwd or project.workspaceRoot")

        candidate_node_ids: list[str] = []
        candidates: list[dict[str, Any]] = []
        stage_operations: list[dict[str, Any]] = []
        for candidate_index, bundle in enumerate(selected_bundles):
            route = dict(bundle["route"])
            agent_group = dict(bundle["agent_group"])
            identifiers = candidate_identifiers(
                project_id=project_id,
                stage=stage,
                route=route,
                agent_group=agent_group,
                index=candidate_index,
            )
            route_specs = [
                build_route_spec(route, route_name=f"primary-{candidate_index + 1:02d}")
            ]
            for fallback_index, fallback_route in enumerate(launchable_routes):
                if str(fallback_route.get("provider_id")) == str(route.get("provider_id")):
                    continue
                route_specs.append(build_route_spec(fallback_route, route_name=f"fallback-{fallback_index + 1:02d}"))

            prompt_text = build_candidate_prompt(
                project=project,
                stage=stage,
                route=route,
                agent_group=agent_group,
                identifiers=identifiers,
                stage_prompt=stage_prompt,
            )
            provider_assignment = {
                "provider": str(route.get("provider_id") or ""),
                "model": str(route.get("model") or ""),
                "reasoning_effort": str(route.get("reasoningEffort") or "medium"),
                "capabilities": list(agent_group.get("roles") or []),
                "metadata": {
                    "provider_name": route.get("provider_name"),
                    "provider_display_name": route.get("provider_display_name"),
                    "tier_id": route.get("tierId"),
                    "bundle_key": bundle["bundle_key"],
                },
            }

            agent_root = (
                f"{launch_defaults_payload['remote_run_root']}/{identifiers['wave_run_id']}/{identifiers['agent_name']}"
            )
            metadata = {
                "stage_id": stage_id,
                "task_category": task_category,
                "difficulty": difficulty,
                "branch_id": identifiers["branch_id"],
                "competition_cell_id": identifiers["competition_cell_id"],
                "agent_group_id": agent_group["agentGroupId"],
                "agent_group_label": agent_group["label"],
                "bundle_key": bundle["bundle_key"],
                "dispatch_wave_id": identifiers["wave_run_id"],
                "remote_agent_name": identifiers["agent_name"],
                "agent_root": agent_root,
                "route_specs": route_specs,
                "selected_provider_id": route.get("provider_id"),
                "selected_model": route.get("model"),
                "selection_score": bundle["selectionScore"],
                "base_route_score": route.get("score"),
            }

            stage_operations.append(
                {
                    "op": "upsert_agent_node",
                    "project_id": project_id,
                    "node": {
                        "node_id": identifiers["node_id"],
                        "role": "competitive-leaf",
                        "label": f"{stage_id} / {agent_group['label']} / {route.get('provider_display_name') or route.get('provider_id')}",
                        "parent_node_id": parent_node_id,
                        "status": "planned",
                        "resource_budget": dict(stage.get("resourceBudget") or {}),
                        "provider_assignment": provider_assignment,
                        "metadata": metadata,
                    },
                }
            )
            candidate_node_ids.append(identifiers["node_id"])
            candidates.append(
                {
                    "candidate_run_id": identifiers["candidate_run_id"],
                    "node_id": identifiers["node_id"],
                    "competition_cell_id": identifiers["competition_cell_id"],
                    "branch_id": identifiers["branch_id"],
                    "wave_run_id": identifiers["wave_run_id"],
                    "agent_name": identifiers["agent_name"],
                    "agent_root": agent_root,
                    "label": f"{stage_id} / {agent_group['label']}",
                    "status": "planned",
                    "selected_route": route,
                    "agent_group": agent_group,
                    "bundle_key": bundle["bundle_key"],
                    "selection_score": bundle["selectionScore"],
                    "base_score": bundle["baseScore"],
                    "route_specs": route_specs,
                    "prompt_text": prompt_text,
                    "provider_assignment": provider_assignment,
                    "cwd": cwd,
                    "launch_defaults": launch_defaults_payload,
                }
            )

        stage_operations.append(
            {
                "op": "define_competition",
                "project_id": project_id,
                "competition": {
                    "competition_id": competition_id,
                    "parent_node_id": parent_node_id,
                    "candidate_node_ids": candidate_node_ids,
                    "metadata": {
                        "stage_id": stage_id,
                        "machine_id": machine_id,
                        "task_category": task_category,
                        "difficulty": difficulty,
                        "candidate_count": candidate_count,
                    },
                },
            }
        )
        for candidate in candidates:
            stage_operations.append(
                {
                    "op": "record_candidate_run",
                    "project_id": project_id,
                    "run": {
                        "run_id": candidate["candidate_run_id"],
                        "competition_id": competition_id,
                        "node_id": candidate["node_id"],
                        "submitted_at": generated_at,
                        "status": "planned",
                        "provider_assignment": candidate["provider_assignment"],
                        "notes": f"Dispatch planned for {candidate['competition_cell_id']}",
                        "artifacts": [],
                        "metadata": {
                            "stage_id": stage_id,
                            "task_category": task_category,
                            "difficulty": difficulty,
                            "branch_id": candidate["branch_id"],
                            "competition_cell_id": candidate["competition_cell_id"],
                            "agent_group_id": candidate["agent_group"]["agentGroupId"],
                            "agent_group_label": candidate["agent_group"]["label"],
                            "bundle_key": candidate["bundle_key"],
                            "dispatch_wave_id": candidate["wave_run_id"],
                            "remote_agent_name": candidate["agent_name"],
                            "agent_root": candidate["agent_root"],
                            "route_specs": candidate["route_specs"],
                            "selected_provider_id": candidate["selected_route"]["provider_id"],
                            "selected_model": candidate["selected_route"]["model"],
                            "selection_score": candidate["selection_score"],
                            "base_route_score": candidate["selected_route"]["score"],
                        },
                    },
                }
            )
        runtime_operations.extend(stage_operations)
        stage_plans.append(
            {
                "stage_id": stage_id,
                "competition_id": competition_id,
                "parent_node_id": parent_node_id,
                "machine_id": machine_id,
                "task_category": task_category,
                "difficulty": difficulty,
                "parent_score": parent_score,
                "candidate_count": candidate_count,
                "route_payload": route_payload,
                "launchable_routes": launchable_routes,
                "candidates": candidates,
            }
        )

    control_snapshot = build_control_snapshot(
        state=state,
        registry=registry,
        health_snapshot=health_snapshot,
        stage_plans=stage_plans,
        generated_at=generated_at,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "projectId": project_id,
        "baseRuntimeSnapshot": base_snapshot,
        "stagePlans": stage_plans,
        "runtimeOperations": runtime_operations,
        "controlSnapshot": control_snapshot,
    }


def write_plan_artifacts(plan: dict[str, Any], *, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "dispatch_plan.json"
    runtime_ops_path = output_dir / "runtime_operations.json"
    control_snapshot_path = output_dir / "control_snapshot.json"
    write_json(plan_path, plan)
    write_json(runtime_ops_path, {"operations": plan["runtimeOperations"]})
    write_json(control_snapshot_path, plan["controlSnapshot"])

    launch_specs: list[dict[str, Any]] = []
    for stage in plan.get("stagePlans", []):
        stage_dir = output_dir / slugify(stage["stage_id"])
        for candidate in stage.get("candidates", []):
            candidate_dir = stage_dir / slugify(candidate["competition_cell_id"])
            candidate_dir.mkdir(parents=True, exist_ok=True)
            prompt_file = candidate_dir / "prompt.md"
            route_specs_file = candidate_dir / "route_specs.json"
            prompt_file.write_text(candidate["prompt_text"], encoding="utf-8")
            route_specs_file.write_text(
                json.dumps(candidate["route_specs"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            launch_spec = {
                "schemaVersion": SCHEMA_VERSION,
                "project_id": plan["projectId"],
                "stage_id": stage["stage_id"],
                "competition_id": stage["competition_id"],
                "competition_cell_id": candidate["competition_cell_id"],
                "candidate_run_id": candidate["candidate_run_id"],
                "node_id": candidate["node_id"],
                "branch_id": candidate["branch_id"],
                "host": candidate["launch_defaults"]["host"],
                "cwd": candidate["cwd"],
                "wave_run_id": candidate["wave_run_id"],
                "agent_name": candidate["agent_name"],
                "agent_root": candidate["agent_root"],
                "sandbox": candidate["launch_defaults"]["sandbox"],
                "approval": candidate["launch_defaults"]["approval"],
                "search": candidate["launch_defaults"]["search"],
                "skip_install": candidate["launch_defaults"]["skip_install"],
                "remote_home": candidate["launch_defaults"]["remote_home"],
                "remote_binary_store": candidate["launch_defaults"]["remote_binary_store"],
                "remote_run_root": candidate["launch_defaults"]["remote_run_root"],
                "env": candidate["launch_defaults"]["env"],
                "unset_env": candidate["launch_defaults"]["unset_env"],
                "add_dir": candidate["launch_defaults"]["add_dir"],
                "ensure_dev02_proxy": candidate["launch_defaults"]["ensure_dev02_proxy"],
                "auto_dev02_sandbox_fix": candidate["launch_defaults"]["auto_dev02_sandbox_fix"],
                "selected_route": candidate["selected_route"],
                "route_specs_file": str(route_specs_file),
                "prompt_file": str(prompt_file),
            }
            command = build_launch_command(launch_spec)
            launch_spec["launcher_script"] = str(DEFAULT_REMOTE_LAUNCHER_PATH)
            launch_spec["launch_command"] = command
            launch_spec_path = candidate_dir / "launch_spec.json"
            write_json(launch_spec_path, launch_spec)
            launch_specs.append(
                {
                    "launch_spec_path": str(launch_spec_path),
                    "prompt_file": str(prompt_file),
                    "route_specs_file": str(route_specs_file),
                    "candidate_run_id": candidate["candidate_run_id"],
                    "branch_id": candidate["branch_id"],
                    "competition_cell_id": candidate["competition_cell_id"],
                    "agent_root": candidate["agent_root"],
                    "launch_command": command,
                }
            )

    return {
        "output_dir": str(output_dir),
        "plan_path": str(plan_path),
        "runtime_operations_path": str(runtime_ops_path),
        "control_snapshot_path": str(control_snapshot_path),
        "launch_specs": launch_specs,
    }


def run_launch_specs(generated: dict[str, Any], *, dry_run: bool) -> tuple[int, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    exit_code = 0
    for item in generated.get("launch_specs", []):
        command = list(item["launch_command"])
        if dry_run:
            results.append(
                {
                    "candidate_run_id": item["candidate_run_id"],
                    "dry_run": True,
                    "command": command,
                    "launch_spec_path": item["launch_spec_path"],
                }
            )
            continue
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        result: dict[str, Any] = {
            "candidate_run_id": item["candidate_run_id"],
            "returncode": int(proc.returncode),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "launch_spec_path": item["launch_spec_path"],
        }
        stdout_text = proc.stdout.strip()
        if stdout_text.startswith("{") and stdout_text.endswith("}"):
            try:
                result["payload"] = json.loads(stdout_text)
            except json.JSONDecodeError:
                pass
        if proc.returncode != 0 and exit_code == 0:
            exit_code = proc.returncode
        results.append(result)
    return exit_code, results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge Catfish runtime state into remote Codex subagent launch specs.")
    parser.add_argument("--state", type=Path, required=True, help="Catfish dispatch state JSON file.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--health", type=Path, default=DEFAULT_HEALTH_PATH)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("plan", help="Render a dry-run dispatch plan as JSON.")

    generate = subparsers.add_parser("generate", help="Write launch spec artifacts to disk.")
    generate.add_argument("--output-dir", type=Path, required=True)

    launch = subparsers.add_parser("launch", help="Generate launch specs and optionally invoke the remote launcher.")
    launch.add_argument("--output-dir", type=Path, required=True)
    launch.add_argument("--dry-run", action="store_true", help="Emit commands without invoking the launcher.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state = load_json(args.state)
    registry, health_snapshot, ledger = load_router_inputs(args.registry, args.health, args.ledger)
    plan = build_dispatch_plan(
        state,
        registry=registry,
        health_snapshot=health_snapshot,
        ledger=ledger,
        state_path=args.state,
    )

    if args.command == "plan":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    generated = write_plan_artifacts(plan, output_dir=args.output_dir)
    if args.command == "generate":
        print(json.dumps(generated, ensure_ascii=False, indent=2))
        return 0

    exit_code, results = run_launch_specs(generated, dry_run=bool(args.dry_run))
    payload = dict(generated)
    payload["launch_results"] = results
    payload["dry_run"] = bool(args.dry_run)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
