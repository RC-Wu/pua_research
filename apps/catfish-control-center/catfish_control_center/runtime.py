from __future__ import annotations

import importlib.util
import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import (
    AgentNode,
    BranchScore,
    CapabilitySummaryState,
    ControlEvent,
    ControlSnapshot,
    DiversityMetric,
    LaunchRecord,
    ProjectState,
    ProviderState,
    ReviewTask,
    StageCompetition,
)
from .storage import JsonSnapshotStore


REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTE_PREVIEW_PATH = REPO_ROOT / "tools" / "codex_route_preview.py"
DEFAULT_PROVIDER_REGISTRY_PATH = REPO_ROOT / "assets" / "router" / "catfish_provider_registry.json"
DEFAULT_PROVIDER_HEALTH_PATH = REPO_ROOT / "assets" / "router" / "catfish_provider_health_20260325.json"
DEFAULT_CAPABILITY_LEDGER_PATH = REPO_ROOT / "assets" / "router" / "catfish_capability_ledger.json"


def load_snapshot(snapshot_path: Path) -> ControlSnapshot:
    return JsonSnapshotStore(snapshot_path).load()


def load_live_state(state_root: Path) -> ControlSnapshot:
    system_root = state_root / "system"
    projects_root = state_root / "projects"

    scheduler_state = _load_optional_json(system_root / "scheduler_state.json", default={})
    dispatch_state = _load_optional_json(system_root / "dispatch_queue.json", default={})
    review_state = _load_optional_json(system_root / "review_queue.json", default={})
    provider_registry = _load_optional_json(
        system_root / "provider_registry.json",
        default=_load_optional_json(DEFAULT_PROVIDER_REGISTRY_PATH, default={}),
    )
    provider_health = _load_optional_json(
        system_root / "provider_health.json",
        default=_load_optional_json(DEFAULT_PROVIDER_HEALTH_PATH, default={}),
    )
    capability_ledger = _load_optional_json(
        system_root / "capability_ledger.json",
        default=_load_optional_json(DEFAULT_CAPABILITY_LEDGER_PATH, default={}),
    )

    project_dirs = sorted(
        [path for path in projects_root.iterdir() if path.is_dir()],
        key=lambda item: item.name,
    ) if projects_root.exists() else []

    projects: list[ProjectState] = []
    agents: list[AgentNode] = []
    branches: list[BranchScore] = []
    events: list[ControlEvent] = []
    stage_competitions: list[StageCompetition] = []
    pending_reviews: list[ReviewTask] = _load_review_tasks(review_state)
    launches: dict[str, LaunchRecord] = {
        launch.launch_id: launch for launch in _load_dispatch_launches(dispatch_state)
    }
    capability_summaries: list[CapabilitySummaryState] = _load_provider_capability_summaries(capability_ledger)
    diversity_metrics: list[DiversityMetric] = []

    pending_reviews_by_project: dict[str, int] = defaultdict(int)
    for review in pending_reviews:
        if review.status not in {"completed", "resolved", "archived"}:
            pending_reviews_by_project[review.project_id] += 1

    scheduler_projects = {
        str(item.get("projectId", item.get("project_id", ""))): item
        for item in scheduler_state.get("projects", [])
        if item.get("projectId") or item.get("project_id")
    }

    for project_dir in project_dirs:
        manifest = _load_optional_json(project_dir / "manifest.json", default={})
        project_id = str(manifest.get("projectId") or manifest.get("project_id") or project_dir.name)
        project_snapshot = _load_project_snapshot(project_dir / "runtime_snapshot.json", project_id=project_id)
        scheduler_project = scheduler_projects.get(project_id, {})

        project_agents, node_lookup = _build_project_agents(project_id, manifest, project_snapshot)
        project_competitions = _build_stage_competitions(project_id, manifest, project_snapshot, node_lookup)
        project_capabilities = _build_agent_capability_summaries(project_id, node_lookup)
        project_events = _load_project_events(project_dir, project_id=project_id)
        project_launches = _build_runtime_launches(project_id, manifest, project_snapshot, node_lookup)
        project_reviews = _build_runtime_review_tasks(project_id, project_competitions)
        project_branches = _build_branch_scores(project_id, manifest, project_snapshot)

        agents.extend(project_agents)
        stage_competitions.extend(project_competitions)
        capability_summaries.extend(project_capabilities)
        events.extend(project_events)
        branches.extend(project_branches)
        diversity_metrics.extend(_build_diversity_metrics(project_competitions))

        for launch in project_launches:
            launches.setdefault(launch.launch_id, launch)

        for review in project_reviews:
            pending_reviews.append(review)
            if review.status not in {"completed", "resolved", "archived"}:
                pending_reviews_by_project[review.project_id] += 1

        active_agents = sum(1 for agent in project_agents if agent.status not in {"completed", "terminated", "archived"})
        current_stage = str(
            manifest.get("currentStage")
            or manifest.get("current_stage")
            or scheduler_project.get("activeStage")
            or scheduler_project.get("active_stage")
            or _project_stage_from_competitions(project_competitions)
        )
        frontier_width = _intish(
            manifest.get("frontierWidth")
            or manifest.get("frontier_width")
            or scheduler_project.get("frontierWidth")
            or scheduler_project.get("frontier_width")
            or max((competition.candidate_count for competition in project_competitions), default=0)
        )
        last_event_at = _max_timestamp(
            [event.timestamp for event in project_events]
            + [launch.launched_at for launch in project_launches]
            + [review.created_at for review in project_reviews]
            + [competition.last_activity_at for competition in project_competitions]
        )
        active_branch = _first_str(
            manifest.get("activeBranch"),
            manifest.get("active_branch"),
            scheduler_project.get("activeBranch"),
            scheduler_project.get("active_branch"),
            next((branch.branch for branch in project_branches), ""),
        )
        label = _first_str(
            manifest.get("label"),
            manifest.get("title"),
            project_snapshot.get("project", {}).get("title", ""),
            project_id,
        )
        summary = _first_str(
            manifest.get("summary"),
            manifest.get("objective"),
            project_snapshot.get("project", {}).get("objective", ""),
        )

        projects.append(
            ProjectState(
                project_id=project_id,
                label=label,
                status=_first_str(
                    manifest.get("status"),
                    project_snapshot.get("project", {}).get("status", ""),
                    "unknown",
                ),
                active_branch=active_branch,
                owner=_first_str(manifest.get("owner"), manifest.get("operator")),
                active_agents=active_agents,
                pending_reviews=pending_reviews_by_project.get(project_id, 0),
                current_stage=current_stage,
                frontier_width=frontier_width,
                last_event_at=last_event_at,
                summary=summary,
            )
        )

    providers = _build_provider_states(
        provider_registry=provider_registry,
        provider_health=provider_health,
        scheduler_state=scheduler_state,
        launches=list(launches.values()),
    )
    generated_at = _first_str(
        scheduler_state.get("generatedAt"),
        scheduler_state.get("generated_at"),
        dispatch_state.get("generatedAt"),
        dispatch_state.get("generated_at"),
        review_state.get("generatedAt"),
        review_state.get("generated_at"),
        provider_registry.get("updatedAt"),
        provider_health.get("observedAt"),
        capability_ledger.get("updatedAt"),
    )
    metadata = {
        "source": "state-root",
        "state_root": str(state_root),
        "system_files": {
            "scheduler_state": str(system_root / "scheduler_state.json"),
            "dispatch_queue": str(system_root / "dispatch_queue.json"),
            "review_queue": str(system_root / "review_queue.json"),
        },
    }
    if not generated_at:
        generated_at = _max_timestamp([project.last_event_at for project in projects] + [launch.launched_at for launch in launches.values()])

    return ControlSnapshot(
        generated_at=generated_at,
        projects=tuple(sorted(projects, key=lambda item: item.project_id)),
        agents=tuple(sorted(agents, key=lambda item: (item.project_id, item.parent_id, item.agent_id))),
        providers=tuple(sorted(providers, key=lambda item: item.profile_id)),
        branches=tuple(sorted(branches, key=lambda item: (item.project_id, -item.score, item.branch))),
        events=tuple(sorted(events, key=lambda item: item.timestamp)),
        stage_competitions=tuple(sorted(stage_competitions, key=lambda item: (item.project_id, item.stage_id, item.competition_id))),
        pending_reviews=tuple(sorted(pending_reviews, key=lambda item: (item.status, item.created_at, item.review_id))),
        launches=tuple(sorted(launches.values(), key=lambda item: item.launched_at)),
        capability_summaries=tuple(
            sorted(
                capability_summaries,
                key=lambda item: (item.source_kind, item.project_id, -item.average_score, item.subject_id, item.capability),
            )
        ),
        diversity_metrics=tuple(sorted(diversity_metrics, key=lambda item: (item.project_id, item.stage_id, item.metric_id))),
        metadata=metadata,
    )


def merge_recent_events(snapshot: ControlSnapshot, events: list[ControlEvent]) -> ControlSnapshot:
    merged = tuple(sorted((*snapshot.events, *events), key=lambda event: event.timestamp))
    return replace(snapshot, events=merged)


def _load_route_preview_module() -> Any:
    spec = importlib.util.spec_from_file_location("codex_route_preview", ROUTE_PREVIEW_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load route preview module from {ROUTE_PREVIEW_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_route_preview(
    snapshot: ControlSnapshot,
    *,
    config_path: Path,
    machine_id: str,
    task_kind: str,
    difficulty: str,
    requested_profile: str | None = None,
    locked_profile: str | None = None,
) -> ControlSnapshot:
    route_module = _load_route_preview_module()
    config = route_module.load_json(config_path)
    route_preview = route_module.select_route(
        config,
        machine_id=machine_id,
        task_kind=task_kind,
        difficulty=difficulty,
        requested_profile=requested_profile,
        locked_profile=locked_profile,
    )

    providers: tuple[ProviderState, ...] = tuple(
        replace(provider, selected=(provider.profile_id == route_preview["profileId"]))
        for provider in snapshot.providers
    )
    metadata = dict(snapshot.metadata)
    metadata["route_preview_source"] = str(config_path)
    return replace(snapshot, providers=providers, route_preview=route_preview, metadata=metadata)


def _load_optional_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_project_snapshot(path: Path, *, project_id: str) -> dict[str, Any]:
    payload = _load_optional_json(path, default={})
    if not payload:
        return {}
    if "projects" in payload and isinstance(payload["projects"], dict):
        project_payload = payload["projects"].get(project_id)
        if project_payload is not None:
            return dict(project_payload)
        if len(payload["projects"]) == 1:
            return dict(next(iter(payload["projects"].values())))
        return {}
    return dict(payload)


def _build_project_agents(
    project_id: str,
    manifest: dict[str, Any],
    project_snapshot: dict[str, Any],
) -> tuple[list[AgentNode], dict[str, dict[str, Any]]]:
    nodes = project_snapshot.get("nodes", {})
    agents: list[AgentNode] = []
    node_lookup: dict[str, dict[str, Any]] = {}
    default_branch = _first_str(manifest.get("activeBranch"), manifest.get("active_branch"))

    for node_id, node in sorted(nodes.items()):
        provider_assignment = node.get("provider_assignment") or {}
        metadata = node.get("metadata") or {}
        task_kind = _first_str(
            metadata.get("taskKind"),
            metadata.get("task_kind"),
            metadata.get("stageId"),
            metadata.get("stage_id"),
            manifest.get("currentStage"),
            manifest.get("current_stage"),
            node.get("role"),
            "builder",
        )
        summary = _first_str(
            metadata.get("summary"),
            metadata.get("objective"),
            metadata.get("notes"),
        )
        agent = AgentNode(
            agent_id=node_id,
            label=str(node.get("label", node_id)),
            role=str(node.get("role", "worker")),
            status=str(node.get("status", "unknown")),
            project_id=project_id,
            provider_profile=str(provider_assignment.get("provider", "")),
            task_kind=task_kind,
            branch=_first_str(metadata.get("branch"), default_branch),
            parent_id=str(node.get("parent_node_id") or ""),
            machine_id=_first_str(metadata.get("machineId"), metadata.get("machine_id")),
            summary=summary,
        )
        agents.append(agent)
        node_lookup[node_id] = node
    return agents, node_lookup


def _build_stage_competitions(
    project_id: str,
    manifest: dict[str, Any],
    project_snapshot: dict[str, Any],
    node_lookup: dict[str, dict[str, Any]],
) -> list[StageCompetition]:
    competitions = project_snapshot.get("competitions", {})
    runs = project_snapshot.get("runs", {})
    verdicts = project_snapshot.get("verdicts", {})
    built: list[StageCompetition] = []

    runs_by_competition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs.values():
        runs_by_competition[str(run.get("competition_id", ""))].append(run)

    verdicts_by_id = {str(verdict.get("verdict_id")): verdict for verdict in verdicts.values()}

    for competition_id, competition in sorted(competitions.items()):
        metadata = competition.get("metadata") or {}
        stage_id = _first_str(
            metadata.get("stageId"),
            metadata.get("stage_id"),
            manifest.get("currentStage"),
            manifest.get("current_stage"),
            "unknown-stage",
        )
        stage_label = _first_str(metadata.get("stageLabel"), metadata.get("stage_label"), stage_id)
        parent_id = str(competition.get("parent_node_id", ""))
        parent_label = str(node_lookup.get(parent_id, {}).get("label", parent_id or "unknown-parent"))
        competition_runs = sorted(runs_by_competition.get(competition_id, []), key=lambda item: item.get("submitted_at", ""))
        verdict = verdicts_by_id.get(str(competition.get("last_verdict_id") or ""))
        scores = [
            float(run["parent_score"])
            for run in competition_runs
            if run.get("parent_score") not in (None, "")
        ]
        winner_run_id = _first_str(
            competition.get("winner_run_id"),
            verdict.get("winner_run_id") if verdict else "",
        )
        winner_run = next((run for run in competition_runs if str(run.get("run_id")) == winner_run_id), None)
        winner_label = ""
        if winner_run is not None:
            winner_node = node_lookup.get(str(winner_run.get("node_id")), {})
            winner_label = str(winner_node.get("label", winner_run.get("node_id", "")))

        stacks = _competition_stacks(competition, competition_runs, node_lookup)
        providers = tuple(sorted({provider for provider, _, _ in stacks if provider}))
        models = tuple(sorted({model for _, model, _ in stacks if model}))
        agent_groups = tuple(sorted({group for _, _, group in stacks if group}))
        stack_counter = Counter(stacks)
        dominant_stack_share = 0.0
        if stack_counter:
            dominant_stack_share = max(stack_counter.values()) / max(sum(stack_counter.values()), 1)
        pending_runs = 0
        if competition_runs:
            pending_runs = max(len(competition_runs) - len(scores), 0)
        elif competition.get("status") != "scored":
            pending_runs = len(competition.get("candidate_node_ids", []))

        last_activity_at = _max_timestamp(
            [run.get("submitted_at", "") for run in competition_runs]
            + ([verdict.get("submitted_at", "")] if verdict else [])
        )
        summary = _first_str(
            metadata.get("summary"),
            verdict.get("rationale") if verdict else "",
            f"{stage_label} competition under {parent_label}",
        )

        built.append(
            StageCompetition(
                competition_id=competition_id,
                project_id=project_id,
                stage_id=stage_id,
                stage_label=stage_label,
                status=str(competition.get("status", "unknown")),
                parent_id=parent_id,
                parent_label=parent_label,
                advancement_mode=_first_str(
                    metadata.get("advancementMode"),
                    metadata.get("advancement_mode"),
                    "winner-take-all",
                ),
                candidate_count=len(competition.get("candidate_node_ids", [])),
                run_count=len(competition_runs),
                scored_run_count=len(scores),
                pending_runs=pending_runs,
                winner_run_id=winner_run_id,
                winner_label=winner_label,
                leading_score=max(scores) if scores else 0.0,
                score_spread=(max(scores) - min(scores)) if len(scores) > 1 else 0.0,
                providers=providers,
                models=models,
                agent_groups=agent_groups,
                unique_stacks=len(stack_counter),
                dominant_stack_share=dominant_stack_share,
                last_activity_at=last_activity_at,
                summary=summary,
            )
        )
    return built


def _competition_stacks(
    competition: dict[str, Any],
    runs: list[dict[str, Any]],
    node_lookup: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str]]:
    stacks: list[tuple[str, str, str]] = []
    if runs:
        for run in runs:
            node = node_lookup.get(str(run.get("node_id")), {})
            provider_assignment = run.get("provider_assignment") or node.get("provider_assignment") or {}
            metadata = run.get("metadata") or node.get("metadata") or {}
            stacks.append(
                (
                    str(provider_assignment.get("provider", "")),
                    str(provider_assignment.get("model", "")),
                    _first_str(metadata.get("agentGroup"), metadata.get("agent_group"), node.get("role", "")),
                )
            )
        return stacks

    for node_id in competition.get("candidate_node_ids", []):
        node = node_lookup.get(str(node_id), {})
        provider_assignment = node.get("provider_assignment") or {}
        metadata = node.get("metadata") or {}
        stacks.append(
            (
                str(provider_assignment.get("provider", "")),
                str(provider_assignment.get("model", "")),
                _first_str(metadata.get("agentGroup"), metadata.get("agent_group"), node.get("role", "")),
            )
        )
    return stacks


def _build_agent_capability_summaries(
    project_id: str,
    node_lookup: dict[str, dict[str, Any]],
) -> list[CapabilitySummaryState]:
    built: list[CapabilitySummaryState] = []
    for node_id, node in sorted(node_lookup.items()):
        summaries = node.get("capability_summaries") or {}
        for capability, payload in sorted(summaries.items()):
            built.append(
                CapabilitySummaryState(
                    source_kind="agent",
                    subject_id=node_id,
                    subject_label=str(node.get("label", node_id)),
                    project_id=project_id,
                    capability=capability,
                    sample_count=_intish(payload.get("sample_count")),
                    average_score=float(payload.get("average_score", 0.0)),
                    last_score=float(payload.get("last_score") or 0.0),
                    confidence=float(payload.get("confidence") or 0.0),
                    updated_at=str(payload.get("updated_at", "")),
                    summary=_first_str(payload.get("last_summary"), payload.get("summary")),
                )
            )
    return built


def _load_provider_capability_summaries(capability_ledger: dict[str, Any]) -> list[CapabilitySummaryState]:
    built: list[CapabilitySummaryState] = []
    for entry in capability_ledger.get("entries", []):
        provider_id = str(entry.get("providerId", ""))
        task_category = str(entry.get("taskCategory", "unknown"))
        difficulty = str(entry.get("difficulty", "unknown"))
        reasoning_tier = str(entry.get("reasoningTier", "unknown"))
        built.append(
            CapabilitySummaryState(
                source_kind="provider",
                subject_id=provider_id,
                subject_label=provider_id,
                capability=f"{task_category}/{difficulty}/{reasoning_tier}",
                sample_count=1,
                average_score=float(entry.get("parentScore", 0.0)),
                last_score=float(entry.get("parentScore", 0.0)),
                confidence=float(entry.get("confidence", 0.0)),
                updated_at=str(entry.get("recency", "")),
                summary=str(entry.get("notes", "")),
            )
        )
    return built


def _load_project_events(project_dir: Path, *, project_id: str) -> list[ControlEvent]:
    events_dir = project_dir / "events"
    if not events_dir.exists():
        return []

    built: list[ControlEvent] = []
    for path in sorted(events_dir.iterdir()):
        if path.suffix == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                payload.setdefault("event_id", f"{path.stem}:{line_number}")
                payload.setdefault("project_id", project_id)
                built.append(ControlEvent.from_dict(payload))
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                for index, item in enumerate(payload, start=1):
                    item.setdefault("event_id", f"{path.stem}:{index}")
                    item.setdefault("project_id", project_id)
                    built.append(ControlEvent.from_dict(item))
            elif isinstance(payload, dict):
                records = payload.get("events")
                if isinstance(records, list):
                    for index, item in enumerate(records, start=1):
                        item.setdefault("event_id", f"{path.stem}:{index}")
                        item.setdefault("project_id", project_id)
                        built.append(ControlEvent.from_dict(item))
    return built


def _load_review_tasks(review_state: dict[str, Any]) -> list[ReviewTask]:
    tasks: list[ReviewTask] = []
    for item in review_state.get("reviews", []):
        tasks.append(
            ReviewTask(
                review_id=str(item.get("reviewId", item.get("review_id", ""))),
                project_id=str(item.get("projectId", item.get("project_id", ""))),
                stage_id=str(item.get("stageId", item.get("stage_id", ""))),
                target_kind=str(item.get("targetKind", item.get("target_kind", "competition"))),
                target_id=str(item.get("targetId", item.get("target_id", ""))),
                status=str(item.get("status", "pending")),
                requested_by=str(item.get("requestedBy", item.get("requested_by", ""))),
                created_at=str(item.get("createdAt", item.get("created_at", ""))),
                priority=str(item.get("priority", "medium")),
                summary=str(item.get("summary", item.get("reason", ""))),
            )
        )
    return tasks


def _build_runtime_review_tasks(
    project_id: str,
    competitions: list[StageCompetition],
) -> list[ReviewTask]:
    tasks: list[ReviewTask] = []
    for competition in competitions:
        if competition.pending_runs <= 0:
            continue
        tasks.append(
            ReviewTask(
                review_id=f"runtime-review:{competition.project_id}:{competition.competition_id}",
                project_id=project_id,
                stage_id=competition.stage_id,
                target_kind="competition",
                target_id=competition.competition_id,
                status="pending-parent-verdict",
                requested_by=competition.parent_label,
                created_at=competition.last_activity_at,
                priority="high" if competition.pending_runs > 1 else "medium",
                summary=(
                    f"{competition.pending_runs} candidate runs still need parent scoring in "
                    f"{competition.stage_label}"
                ),
            )
        )
    return tasks


def _load_dispatch_launches(dispatch_state: dict[str, Any]) -> list[LaunchRecord]:
    launches: list[LaunchRecord] = []
    for item in dispatch_state.get("launches", []):
        launches.append(
            LaunchRecord(
                launch_id=str(item.get("launchId", item.get("launch_id", ""))),
                project_id=str(item.get("projectId", item.get("project_id", ""))),
                stage_id=str(item.get("stageId", item.get("stage_id", ""))),
                node_id=str(item.get("nodeId", item.get("node_id", ""))),
                node_label=str(item.get("nodeLabel", item.get("node_label", item.get("nodeId", item.get("node_id", ""))))),
                branch=str(item.get("branch", "")),
                status=str(item.get("status", "unknown")),
                provider=str(item.get("provider", "")),
                model=str(item.get("model", "")),
                launched_at=str(item.get("launchedAt", item.get("launched_at", ""))),
                source="dispatch",
                summary=str(item.get("summary", item.get("reason", ""))),
            )
        )
    return launches


def _build_runtime_launches(
    project_id: str,
    manifest: dict[str, Any],
    project_snapshot: dict[str, Any],
    node_lookup: dict[str, dict[str, Any]],
) -> list[LaunchRecord]:
    launches: list[LaunchRecord] = []
    runs = project_snapshot.get("runs", {})
    competitions = project_snapshot.get("competitions", {})
    default_branch = _first_str(manifest.get("activeBranch"), manifest.get("active_branch"))

    for run_id, run in sorted(runs.items(), key=lambda item: item[1].get("submitted_at", "")):
        node_id = str(run.get("node_id", ""))
        node = node_lookup.get(node_id, {})
        competition = competitions.get(str(run.get("competition_id", "")), {})
        competition_meta = competition.get("metadata") or {}
        run_meta = run.get("metadata") or {}
        provider_assignment = run.get("provider_assignment") or node.get("provider_assignment") or {}
        launches.append(
            LaunchRecord(
                launch_id=str(run.get("run_id", run_id)),
                project_id=project_id,
                stage_id=_first_str(
                    run_meta.get("stageId"),
                    run_meta.get("stage_id"),
                    competition_meta.get("stageId"),
                    competition_meta.get("stage_id"),
                    manifest.get("currentStage"),
                    manifest.get("current_stage"),
                ),
                node_id=node_id,
                node_label=str(node.get("label", node_id)),
                branch=_first_str(run_meta.get("branch"), (node.get("metadata") or {}).get("branch"), default_branch),
                status=str(run.get("status", "unknown")),
                provider=str(provider_assignment.get("provider", "")),
                model=str(provider_assignment.get("model", "")),
                launched_at=str(run.get("submitted_at", "")),
                source="runtime-run",
                summary=str(run.get("notes", "")),
            )
        )
    return launches


def _build_branch_scores(
    project_id: str,
    manifest: dict[str, Any],
    project_snapshot: dict[str, Any],
) -> list[BranchScore]:
    built: list[BranchScore] = []
    manifest_branches = manifest.get("branches") or []
    if manifest_branches:
        for branch in manifest_branches:
            built.append(
                BranchScore(
                    branch=str(branch.get("branch", "")),
                    project_id=project_id,
                    score=float(branch.get("score", 0.0)),
                    wins=_intish(branch.get("wins")),
                    losses=_intish(branch.get("losses")),
                    state=str(branch.get("state", "unknown")),
                    head_commit=str(branch.get("headCommit", branch.get("head_commit", ""))),
                    summary=str(branch.get("summary", "")),
                )
            )
        return built

    runs = project_snapshot.get("runs", {})
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    default_branch = _first_str(manifest.get("activeBranch"), manifest.get("active_branch"), "unassigned")
    for run in runs.values():
        run_meta = run.get("metadata") or {}
        branch = _first_str(run_meta.get("branch"), default_branch)
        grouped[branch].append(run)

    for branch, branch_runs in sorted(grouped.items()):
        scores = [float(run["parent_score"]) for run in branch_runs if run.get("parent_score") not in (None, "")]
        wins = 0
        losses = 0
        for score in scores:
            if score >= 0.7:
                wins += 1
            else:
                losses += 1
        built.append(
            BranchScore(
                branch=branch,
                project_id=project_id,
                score=(sum(scores) / len(scores)) if scores else 0.0,
                wins=wins,
                losses=losses,
                state="leading" if wins and wins >= losses else "contending",
                summary="Derived from live competition verdicts.",
            )
        )
    return built


def _build_provider_states(
    *,
    provider_registry: dict[str, Any],
    provider_health: dict[str, Any],
    scheduler_state: dict[str, Any],
    launches: list[LaunchRecord],
) -> list[ProviderState]:
    health_by_provider = {
        str(item.get("providerId", item.get("provider_id", ""))): item
        for item in provider_health.get("providers", [])
        if item.get("providerId") or item.get("provider_id")
    }
    scheduler_by_provider = {}
    for item in scheduler_state.get("providers", []):
        provider_id = str(item.get("providerId", item.get("provider_id", item.get("id", ""))))
        if provider_id:
            scheduler_by_provider[provider_id] = item

    launch_counts = Counter(launch.provider for launch in launches if launch.provider)
    built: list[ProviderState] = []

    for provider in provider_registry.get("providers", []):
        provider_id = str(provider.get("id", ""))
        health = health_by_provider.get(provider_id, {})
        budget = scheduler_by_provider.get(provider_id, {})
        quota_state = str(health.get("quotaState", health.get("quota_state", "")))
        endpoint_reachable = bool(health.get("endpointReachable", health.get("endpoint_reachable", provider.get("enabled", True))))
        enabled = bool(provider.get("enabled", True))
        available = enabled and endpoint_reachable and quota_state not in {"exhausted", "blocked"}
        verified_models = tuple(str(item) for item in health.get("verifiedModels", []))
        any_verified_tier = any(
            bool(tier.get("verified", False))
            for tier in (provider.get("modelTiers") or {}).values()
            if isinstance(tier, dict)
        )
        issues: list[str] = []
        if quota_state:
            issues.append(f"quota={quota_state}")
        if not endpoint_reachable:
            issues.append("endpoint-unreachable")
        issues.extend(str(item) for item in budget.get("issues", []))

        built.append(
            ProviderState(
                profile_id=provider_id,
                label=str(provider.get("displayName", provider_id)),
                machine_ids=tuple(str(item) for item in provider.get("machineIds", [])),
                available=available,
                verified=bool(verified_models) or any_verified_tier,
                remaining_credit=float(budget.get("remainingCredit", budget.get("remaining_credit", 1.0 if available else 0.0))),
                reserve_floor=float(budget.get("reserveFloor", budget.get("reserve_floor", 0.0))),
                routing_weight=float(budget.get("routingWeight", budget.get("routing_weight", provider.get("routingWeight", 1.0)))),
                active_launches=int(budget.get("activeLaunches", budget.get("active_launches", launch_counts.get(provider_id, 0)))),
                verified_models=verified_models,
                issues=tuple(dict.fromkeys(issues)),
                route_tiers=dict(provider.get("modelTiers", {})),
            )
        )
    return built


def _build_diversity_metrics(competitions: list[StageCompetition]) -> list[DiversityMetric]:
    metrics: list[DiversityMetric] = []
    for competition in competitions:
        metrics.append(
            DiversityMetric(
                metric_id=f"{competition.project_id}:{competition.competition_id}",
                project_id=competition.project_id,
                stage_id=competition.stage_id,
                label=competition.stage_label,
                candidate_count=competition.candidate_count,
                unique_providers=len(competition.providers),
                unique_models=len(competition.models),
                unique_agent_groups=len(competition.agent_groups),
                unique_stacks=competition.unique_stacks,
                dominant_stack_share=competition.dominant_stack_share,
                wildcard_count=1 if competition.advancement_mode == "top-k-survival" and competition.unique_stacks > 1 else 0,
                summary=(
                    f"{competition.stage_label} is using {len(competition.providers)} providers, "
                    f"{len(competition.models)} models, and dominant stack share "
                    f"{competition.dominant_stack_share:.2f}"
                ),
            )
        )
    return metrics


def _project_stage_from_competitions(competitions: list[StageCompetition]) -> str:
    if not competitions:
        return ""
    newest = max(competitions, key=lambda item: item.last_activity_at or "")
    return newest.stage_id


def _first_str(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _intish(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _max_timestamp(values: list[str]) -> str:
    filtered = [value for value in values if value]
    if not filtered:
        return ""
    return max(filtered)
