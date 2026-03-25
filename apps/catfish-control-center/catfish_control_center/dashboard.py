from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, TypeVar

from .models import (
    AgentNode,
    BranchScore,
    CapabilitySummaryState,
    ControlEvent,
    ControlSnapshot,
    DiversityMetric,
    LaunchRecord,
    ReviewTask,
    StageCompetition,
)


def _section(title: str, lines: list[str]) -> str:
    body = lines or ["- no data"]
    return "\n".join([title, *body])


def render_multi_project_overview(snapshot: ControlSnapshot) -> list[str]:
    lines: list[str] = []
    for project in sorted(snapshot.projects, key=lambda item: item.project_id):
        lines.append(
            "- "
            f"{project.label} [{project.status}] "
            f"stage={project.current_stage or 'n/a'} "
            f"branch={project.active_branch or 'n/a'} "
            f"frontier={project.frontier_width} "
            f"agents={project.active_agents} "
            f"pending_reviews={project.pending_reviews} "
            f"owner={project.owner or 'unassigned'} "
            f"last_event={project.last_event_at or 'n/a'}"
        )
        if project.summary:
            lines.append(f"  summary: {project.summary}")
    return lines


def render_agent_graph(snapshot: ControlSnapshot) -> list[str]:
    agents_by_parent: dict[str, list[AgentNode]] = defaultdict(list)
    roots: list[AgentNode] = []
    for agent in sorted(snapshot.agents, key=lambda item: (item.project_id, item.parent_id, item.agent_id)):
        if agent.parent_id:
            agents_by_parent[agent.parent_id].append(agent)
        else:
            roots.append(agent)

    lines: list[str] = []

    def walk(node: AgentNode, depth: int) -> None:
        indent = "  " * depth
        lines.append(
            f"{indent}- {node.label} [{node.role}/{node.status}] "
            f"project={node.project_id or 'n/a'} "
            f"branch={node.branch or 'n/a'} "
            f"provider={node.provider_profile or 'n/a'} "
            f"task={node.task_kind}"
        )
        if node.summary:
            lines.append(f"{indent}  summary: {node.summary}")
        for child in sorted(agents_by_parent.get(node.agent_id, []), key=lambda item: item.agent_id):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)

    return lines


def render_provider_health(snapshot: ControlSnapshot) -> list[str]:
    lines: list[str] = []
    for provider in sorted(snapshot.providers, key=lambda item: item.profile_id):
        selected = " SELECTED" if provider.selected else ""
        tiers = ",".join(sorted(provider.route_tiers)) or "n/a"
        issues = ", ".join(provider.issues) if provider.issues else "none"
        machines = ",".join(provider.machine_ids) or "n/a"
        verified_models = ",".join(provider.verified_models) or "n/a"
        lines.append(
            "- "
            f"{provider.label} ({provider.profile_id}){selected} "
            f"machines={machines} "
            f"health={provider.health_summary} "
            f"quota={provider.remaining_credit:.2f} ({provider.quota_summary}) "
            f"weight={provider.routing_weight:.2f} "
            f"active_launches={provider.active_launches} "
            f"verified_models={verified_models} "
            f"tiers={tiers} "
            f"issues={issues}"
        )
    return lines


def render_branch_scoreboards(snapshot: ControlSnapshot) -> list[str]:
    grouped: dict[str, list[BranchScore]] = defaultdict(list)
    for branch in snapshot.branches:
        grouped[branch.project_id or "unassigned"].append(branch)

    lines: list[str] = []
    for project_id in sorted(grouped):
        lines.append(f"- project={project_id}")
        for branch in sorted(grouped[project_id], key=lambda item: (-item.score, item.branch)):
            lines.append(
                "  "
                f"* {branch.branch} score={branch.score:.2f} "
                f"record={branch.wins}-{branch.losses} "
                f"state={branch.state} "
                f"head={branch.head_commit or 'n/a'}"
            )
            if branch.summary:
                lines.append(f"    summary: {branch.summary}")
    return lines


def render_stage_competitions(snapshot: ControlSnapshot) -> list[str]:
    lines: list[str] = []
    grouped: dict[tuple[str, str], list[StageCompetition]] = defaultdict(list)
    for competition in snapshot.stage_competitions:
        grouped[(competition.project_id, competition.stage_id)].append(competition)

    for project_id, stage_id in sorted(grouped):
        lines.append(f"- project={project_id} stage={stage_id}")
        for competition in sorted(grouped[(project_id, stage_id)], key=lambda item: item.competition_id):
            providers = ",".join(competition.providers) or "n/a"
            models = ",".join(competition.models) or "n/a"
            groups = ",".join(competition.agent_groups) or "n/a"
            lines.append(
                "  "
                f"* {competition.competition_id} [{competition.status}] "
                f"parent={competition.parent_label or competition.parent_id or 'n/a'} "
                f"mode={competition.advancement_mode} "
                f"candidates={competition.candidate_count} "
                f"runs={competition.run_count} "
                f"scored={competition.scored_run_count} "
                f"pending={competition.pending_runs} "
                f"winner={competition.winner_label or 'n/a'} "
                f"lead={competition.leading_score:.2f} "
                f"spread={competition.score_spread:.2f} "
                f"unique_stacks={competition.unique_stacks} "
                f"dominant_stack_share={competition.dominant_stack_share:.2f}"
            )
            lines.append(f"    stacks: providers={providers} models={models} agent_groups={groups}")
            if competition.summary:
                lines.append(f"    summary: {competition.summary}")
    return lines


def render_pending_reviews(snapshot: ControlSnapshot) -> list[str]:
    lines: list[str] = []
    for review in sorted(snapshot.pending_reviews, key=lambda item: (item.status, item.created_at, item.review_id)):
        lines.append(
            "- "
            f"{review.review_id} [{review.status}] "
            f"project={review.project_id or 'n/a'} "
            f"stage={review.stage_id or 'n/a'} "
            f"target={review.target_kind}:{review.target_id or 'n/a'} "
            f"priority={review.priority} "
            f"requested_by={review.requested_by or 'n/a'} "
            f"created_at={review.created_at or 'n/a'}"
        )
        if review.summary:
            lines.append(f"  summary: {review.summary}")
    return lines


def render_recent_launches(snapshot: ControlSnapshot, limit: int = 8) -> list[str]:
    lines: list[str] = []
    recent: list[LaunchRecord] = sorted(snapshot.launches, key=lambda item: item.launched_at)[-limit:]
    for launch in recent:
        lines.append(
            "- "
            f"{launch.launched_at} "
            f"{launch.launch_id} [{launch.status}] "
            f"project={launch.project_id or 'n/a'} "
            f"stage={launch.stage_id or 'n/a'} "
            f"node={launch.node_label or launch.node_id or 'n/a'} "
            f"branch={launch.branch or 'n/a'} "
            f"stack={launch.provider or 'n/a'}/{launch.model or 'n/a'} "
            f"source={launch.source or 'n/a'}"
        )
        if launch.summary:
            lines.append(f"  summary: {launch.summary}")
    return lines


def render_capability_summaries(snapshot: ControlSnapshot, limit: int = 12) -> list[str]:
    lines: list[str] = []
    ranked = sorted(
        snapshot.capability_summaries,
        key=lambda item: (-item.average_score, item.source_kind, item.project_id, item.subject_id, item.capability),
    )[:limit]
    for capability in ranked:
        lines.append(
            "- "
            f"{capability.source_kind}:{capability.subject_label or capability.subject_id} "
            f"capability={capability.capability} "
            f"project={capability.project_id or 'system'} "
            f"avg={capability.average_score:.2f} "
            f"last={capability.last_score:.2f} "
            f"samples={capability.sample_count} "
            f"confidence={capability.confidence:.2f} "
            f"updated_at={capability.updated_at or 'n/a'}"
        )
        if capability.summary:
            lines.append(f"  summary: {capability.summary}")
    return lines


def render_diversity_metrics(snapshot: ControlSnapshot) -> list[str]:
    lines: list[str] = []
    for metric in sorted(snapshot.diversity_metrics, key=lambda item: (item.project_id, item.stage_id, item.metric_id)):
        lines.append(
            "- "
            f"{metric.label or metric.metric_id} "
            f"project={metric.project_id or 'n/a'} "
            f"stage={metric.stage_id or 'n/a'} "
            f"candidates={metric.candidate_count} "
            f"providers={metric.unique_providers} "
            f"models={metric.unique_models} "
            f"agent_groups={metric.unique_agent_groups} "
            f"stacks={metric.unique_stacks} "
            f"dominant_stack_share={metric.dominant_stack_share:.2f} "
            f"wildcards={metric.wildcard_count}"
        )
        if metric.summary:
            lines.append(f"  summary: {metric.summary}")
    return lines


def render_recent_events(snapshot: ControlSnapshot, limit: int = 8) -> list[str]:
    lines: list[str] = []
    recent: list[ControlEvent] = sorted(snapshot.events, key=lambda item: item.timestamp)[-limit:]
    for event in recent:
        target = "/".join(part for part in [event.project_id, event.branch, event.agent_id] if part) or "global"
        lines.append(
            "- "
            f"{event.timestamp} [{event.level}/{event.kind}] "
            f"target={target} "
            f"{event.message}"
        )
    return lines


def render_route_preview(snapshot: ControlSnapshot) -> list[str]:
    if not snapshot.route_preview:
        return ["- no live route preview"]
    preview = snapshot.route_preview
    rationale = "; ".join(preview.get("rationale", []))
    return [
        "- "
        f"profile={preview.get('profileId', 'n/a')} "
        f"machine={preview.get('machineId', 'n/a')} "
        f"tier={preview.get('tierId', 'n/a')} "
        f"model={preview.get('model', 'n/a')} "
        f"reasoning={preview.get('reasoningEffort', 'n/a')} "
        f"search={preview.get('search', False)} "
        f"browser={preview.get('browserMode', 'none')}",
        f"  rationale: {rationale}",
    ]


T = TypeVar("T")


def _section_payload(items: tuple[T, ...] | list[T], *, serializer: Callable[[T], dict[str, Any]]) -> list[dict[str, Any]]:
    return [serializer(item) for item in items]


def view_to_dict(snapshot: ControlSnapshot, view: str, event_limit: int = 8) -> dict[str, Any]:
    if view == "dashboard":
        return snapshot.to_dict()
    if view == "projects":
        return {"projects": _section_payload(snapshot.projects, serializer=lambda item: item.to_dict())}
    if view == "stage-competitions":
        return {
            "stage_competitions": _section_payload(
                snapshot.stage_competitions,
                serializer=lambda item: item.to_dict(),
            )
        }
    if view == "pending-reviews":
        return {"pending_reviews": _section_payload(snapshot.pending_reviews, serializer=lambda item: item.to_dict())}
    if view == "provider-status":
        return {"providers": _section_payload(snapshot.providers, serializer=lambda item: item.to_dict())}
    if view == "recent-launches":
        launches = tuple(sorted(snapshot.launches, key=lambda item: item.launched_at)[-event_limit:])
        return {"launches": _section_payload(launches, serializer=lambda item: item.to_dict())}
    if view == "capability-summaries":
        capability_summaries = tuple(
            sorted(snapshot.capability_summaries, key=lambda item: (-item.average_score, item.subject_id))[:event_limit]
        )
        return {
            "capability_summaries": _section_payload(capability_summaries, serializer=lambda item: item.to_dict())
        }
    if view == "diversity-metrics":
        return {"diversity_metrics": _section_payload(snapshot.diversity_metrics, serializer=lambda item: item.to_dict())}
    if view == "recent-events":
        events = tuple(sorted(snapshot.events, key=lambda item: item.timestamp)[-event_limit:])
        return {"events": _section_payload(events, serializer=lambda item: item.to_dict())}
    raise ValueError(f"Unsupported view {view}")


def render_view(snapshot: ControlSnapshot, view: str, event_limit: int = 8) -> str:
    renderers: dict[str, Callable[[ControlSnapshot], list[str]]] = {
        "projects": render_multi_project_overview,
        "stage-competitions": render_stage_competitions,
        "pending-reviews": render_pending_reviews,
        "provider-status": render_provider_health,
        "recent-launches": lambda item: render_recent_launches(item, limit=event_limit),
        "capability-summaries": lambda item: render_capability_summaries(item, limit=max(event_limit, 8)),
        "diversity-metrics": render_diversity_metrics,
        "recent-events": lambda item: render_recent_events(item, limit=event_limit),
    }
    titles = {
        "projects": "Projects",
        "stage-competitions": "Stage Competitions",
        "pending-reviews": "Pending Reviews",
        "provider-status": "Provider Status",
        "recent-launches": "Recent Launches",
        "capability-summaries": "Capability Summaries",
        "diversity-metrics": "Diversity Metrics",
        "recent-events": "Recent Events",
    }
    if view == "dashboard":
        return render_dashboard(snapshot, event_limit=event_limit)
    if view not in renderers:
        raise ValueError(f"Unsupported view {view}")
    return _section(titles[view], renderers[view](snapshot))


def render_dashboard(snapshot: ControlSnapshot, event_limit: int = 8) -> str:
    sections = [
        f"Catfish Control Center Snapshot @ {snapshot.generated_at or 'unknown'}",
        _section("Route Preview", render_route_preview(snapshot)),
        _section("Projects", render_multi_project_overview(snapshot)),
        _section("Agent Graph / Hierarchy", render_agent_graph(snapshot)),
        _section("Provider Status", render_provider_health(snapshot)),
        _section("Branch Scoreboards", render_branch_scoreboards(snapshot)),
        _section("Stage Competitions", render_stage_competitions(snapshot)),
        _section("Pending Reviews", render_pending_reviews(snapshot)),
        _section("Recent Launches", render_recent_launches(snapshot, limit=event_limit)),
        _section("Capability Summaries", render_capability_summaries(snapshot, limit=max(event_limit, 8))),
        _section("Diversity Metrics", render_diversity_metrics(snapshot)),
        _section("Recent Events", render_recent_events(snapshot, limit=event_limit)),
    ]
    return "\n\n".join(sections)
