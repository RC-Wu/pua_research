from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _str_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(item) for item in value)


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


@dataclass(frozen=True)
class ProjectState:
    project_id: str
    label: str
    status: str
    active_branch: str
    owner: str = ""
    active_agents: int = 0
    pending_reviews: int = 0
    current_stage: str = ""
    frontier_width: int = 0
    last_event_at: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(
            project_id=str(data["project_id"]),
            label=str(data.get("label", data["project_id"])),
            status=str(data.get("status", "unknown")),
            active_branch=str(data.get("active_branch", "")),
            owner=str(data.get("owner", "")),
            active_agents=_int(data.get("active_agents")),
            pending_reviews=_int(data.get("pending_reviews")),
            current_stage=str(data.get("current_stage", "")),
            frontier_width=_int(data.get("frontier_width")),
            last_event_at=str(data.get("last_event_at", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentNode:
    agent_id: str
    label: str
    role: str
    status: str
    project_id: str
    provider_profile: str
    task_kind: str
    branch: str = ""
    parent_id: str = ""
    machine_id: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentNode":
        return cls(
            agent_id=str(data["agent_id"]),
            label=str(data.get("label", data["agent_id"])),
            role=str(data.get("role", "worker")),
            status=str(data.get("status", "unknown")),
            project_id=str(data.get("project_id", "")),
            provider_profile=str(data.get("provider_profile", "")),
            task_kind=str(data.get("task_kind", "builder")),
            branch=str(data.get("branch", "")),
            parent_id=str(data.get("parent_id", "")),
            machine_id=str(data.get("machine_id", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderState:
    profile_id: str
    label: str
    machine_ids: tuple[str, ...]
    available: bool
    verified: bool
    remaining_credit: float
    reserve_floor: float
    routing_weight: float = 1.0
    active_launches: int = 0
    verified_models: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)
    route_tiers: dict[str, Any] = field(default_factory=dict)
    selected: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderState":
        return cls(
            profile_id=str(data["profile_id"]),
            label=str(data.get("label", data["profile_id"])),
            machine_ids=_str_list(data.get("machine_ids")),
            available=bool(data.get("available", True)),
            verified=bool(data.get("verified", True)),
            remaining_credit=_float(data.get("remaining_credit")),
            reserve_floor=_float(data.get("reserve_floor")),
            routing_weight=_float(data.get("routing_weight"), default=1.0),
            active_launches=_int(data.get("active_launches")),
            verified_models=_str_list(data.get("verified_models")),
            issues=_str_list(data.get("issues")),
            route_tiers=dict(data.get("route_tiers", {})),
            selected=bool(data.get("selected", False)),
        )

    @property
    def health_summary(self) -> str:
        if not self.available:
            return "offline"
        if not self.verified:
            return "unverified"
        return "healthy"

    @property
    def quota_summary(self) -> str:
        delta = self.remaining_credit - self.reserve_floor
        if delta <= 0:
            return f"below reserve by {abs(delta):.2f}"
        return f"{delta:.2f} above reserve"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["machine_ids"] = list(self.machine_ids)
        payload["verified_models"] = list(self.verified_models)
        payload["issues"] = list(self.issues)
        return payload


@dataclass(frozen=True)
class BranchScore:
    branch: str
    project_id: str
    score: float
    wins: int
    losses: int
    state: str
    head_commit: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BranchScore":
        return cls(
            branch=str(data["branch"]),
            project_id=str(data.get("project_id", "")),
            score=_float(data.get("score")),
            wins=_int(data.get("wins")),
            losses=_int(data.get("losses")),
            state=str(data.get("state", "unknown")),
            head_commit=str(data.get("head_commit", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ControlEvent:
    event_id: str
    timestamp: str
    level: str
    kind: str
    message: str
    project_id: str = ""
    agent_id: str = ""
    branch: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlEvent":
        return cls(
            event_id=str(data["event_id"]),
            timestamp=str(data.get("timestamp", "")),
            level=str(data.get("level", "info")),
            kind=str(data.get("kind", "event")),
            message=str(data.get("message", "")),
            project_id=str(data.get("project_id", "")),
            agent_id=str(data.get("agent_id", "")),
            branch=str(data.get("branch", "")),
            payload=dict(data.get("payload", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StageCompetition:
    competition_id: str
    project_id: str
    stage_id: str
    stage_label: str
    status: str
    parent_id: str
    parent_label: str
    advancement_mode: str
    candidate_count: int
    run_count: int = 0
    scored_run_count: int = 0
    pending_runs: int = 0
    winner_run_id: str = ""
    winner_label: str = ""
    leading_score: float = 0.0
    score_spread: float = 0.0
    providers: tuple[str, ...] = field(default_factory=tuple)
    models: tuple[str, ...] = field(default_factory=tuple)
    agent_groups: tuple[str, ...] = field(default_factory=tuple)
    unique_stacks: int = 0
    dominant_stack_share: float = 0.0
    last_activity_at: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageCompetition":
        return cls(
            competition_id=str(data["competition_id"]),
            project_id=str(data.get("project_id", "")),
            stage_id=str(data.get("stage_id", "")),
            stage_label=str(data.get("stage_label", data.get("stage_id", ""))),
            status=str(data.get("status", "unknown")),
            parent_id=str(data.get("parent_id", "")),
            parent_label=str(data.get("parent_label", "")),
            advancement_mode=str(data.get("advancement_mode", "winner-take-all")),
            candidate_count=_int(data.get("candidate_count")),
            run_count=_int(data.get("run_count")),
            scored_run_count=_int(data.get("scored_run_count")),
            pending_runs=_int(data.get("pending_runs")),
            winner_run_id=str(data.get("winner_run_id", "")),
            winner_label=str(data.get("winner_label", "")),
            leading_score=_float(data.get("leading_score")),
            score_spread=_float(data.get("score_spread")),
            providers=_str_list(data.get("providers")),
            models=_str_list(data.get("models")),
            agent_groups=_str_list(data.get("agent_groups")),
            unique_stacks=_int(data.get("unique_stacks")),
            dominant_stack_share=_float(data.get("dominant_stack_share")),
            last_activity_at=str(data.get("last_activity_at", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["providers"] = list(self.providers)
        payload["models"] = list(self.models)
        payload["agent_groups"] = list(self.agent_groups)
        return payload


@dataclass(frozen=True)
class ReviewTask:
    review_id: str
    project_id: str
    stage_id: str
    target_kind: str
    target_id: str
    status: str
    requested_by: str = ""
    created_at: str = ""
    priority: str = "medium"
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewTask":
        return cls(
            review_id=str(data["review_id"]),
            project_id=str(data.get("project_id", "")),
            stage_id=str(data.get("stage_id", "")),
            target_kind=str(data.get("target_kind", "competition")),
            target_id=str(data.get("target_id", "")),
            status=str(data.get("status", "pending")),
            requested_by=str(data.get("requested_by", "")),
            created_at=str(data.get("created_at", "")),
            priority=str(data.get("priority", "medium")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LaunchRecord:
    launch_id: str
    project_id: str
    stage_id: str
    node_id: str
    node_label: str
    branch: str
    status: str
    provider: str
    model: str
    launched_at: str
    source: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LaunchRecord":
        return cls(
            launch_id=str(data["launch_id"]),
            project_id=str(data.get("project_id", "")),
            stage_id=str(data.get("stage_id", "")),
            node_id=str(data.get("node_id", "")),
            node_label=str(data.get("node_label", "")),
            branch=str(data.get("branch", "")),
            status=str(data.get("status", "unknown")),
            provider=str(data.get("provider", "")),
            model=str(data.get("model", "")),
            launched_at=str(data.get("launched_at", "")),
            source=str(data.get("source", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilitySummaryState:
    source_kind: str
    subject_id: str
    subject_label: str
    capability: str
    project_id: str = ""
    sample_count: int = 0
    average_score: float = 0.0
    last_score: float = 0.0
    confidence: float = 0.0
    updated_at: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapabilitySummaryState":
        return cls(
            source_kind=str(data["source_kind"]),
            subject_id=str(data.get("subject_id", "")),
            subject_label=str(data.get("subject_label", "")),
            capability=str(data.get("capability", "")),
            project_id=str(data.get("project_id", "")),
            sample_count=_int(data.get("sample_count")),
            average_score=_float(data.get("average_score")),
            last_score=_float(data.get("last_score")),
            confidence=_float(data.get("confidence")),
            updated_at=str(data.get("updated_at", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiversityMetric:
    metric_id: str
    project_id: str
    stage_id: str
    label: str
    candidate_count: int
    unique_providers: int
    unique_models: int
    unique_agent_groups: int
    unique_stacks: int
    dominant_stack_share: float
    wildcard_count: int = 0
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiversityMetric":
        return cls(
            metric_id=str(data["metric_id"]),
            project_id=str(data.get("project_id", "")),
            stage_id=str(data.get("stage_id", "")),
            label=str(data.get("label", "")),
            candidate_count=_int(data.get("candidate_count")),
            unique_providers=_int(data.get("unique_providers")),
            unique_models=_int(data.get("unique_models")),
            unique_agent_groups=_int(data.get("unique_agent_groups")),
            unique_stacks=_int(data.get("unique_stacks")),
            dominant_stack_share=_float(data.get("dominant_stack_share")),
            wildcard_count=_int(data.get("wildcard_count")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ControlSnapshot:
    generated_at: str
    projects: tuple[ProjectState, ...]
    agents: tuple[AgentNode, ...]
    providers: tuple[ProviderState, ...]
    branches: tuple[BranchScore, ...]
    events: tuple[ControlEvent, ...]
    stage_competitions: tuple[StageCompetition, ...] = field(default_factory=tuple)
    pending_reviews: tuple[ReviewTask, ...] = field(default_factory=tuple)
    launches: tuple[LaunchRecord, ...] = field(default_factory=tuple)
    capability_summaries: tuple[CapabilitySummaryState, ...] = field(default_factory=tuple)
    diversity_metrics: tuple[DiversityMetric, ...] = field(default_factory=tuple)
    route_preview: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlSnapshot":
        return cls(
            generated_at=str(data.get("generated_at", "")),
            projects=tuple(ProjectState.from_dict(item) for item in data.get("projects", [])),
            agents=tuple(AgentNode.from_dict(item) for item in data.get("agents", [])),
            providers=tuple(ProviderState.from_dict(item) for item in data.get("providers", [])),
            branches=tuple(BranchScore.from_dict(item) for item in data.get("branches", [])),
            events=tuple(ControlEvent.from_dict(item) for item in data.get("events", [])),
            stage_competitions=tuple(
                StageCompetition.from_dict(item) for item in data.get("stage_competitions", [])
            ),
            pending_reviews=tuple(ReviewTask.from_dict(item) for item in data.get("pending_reviews", [])),
            launches=tuple(LaunchRecord.from_dict(item) for item in data.get("launches", [])),
            capability_summaries=tuple(
                CapabilitySummaryState.from_dict(item) for item in data.get("capability_summaries", [])
            ),
            diversity_metrics=tuple(DiversityMetric.from_dict(item) for item in data.get("diversity_metrics", [])),
            route_preview=dict(data["route_preview"]) if data.get("route_preview") else None,
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "projects": [item.to_dict() for item in self.projects],
            "agents": [item.to_dict() for item in self.agents],
            "providers": [item.to_dict() for item in self.providers],
            "branches": [item.to_dict() for item in self.branches],
            "events": [item.to_dict() for item in self.events],
            "stage_competitions": [item.to_dict() for item in self.stage_competitions],
            "pending_reviews": [item.to_dict() for item in self.pending_reviews],
            "launches": [item.to_dict() for item in self.launches],
            "capability_summaries": [item.to_dict() for item in self.capability_summaries],
            "diversity_metrics": [item.to_dict() for item in self.diversity_metrics],
            "route_preview": self.route_preview,
            "metadata": self.metadata,
        }
