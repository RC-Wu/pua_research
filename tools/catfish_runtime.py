from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "catfish-runtime/v1"
PARENT_ONLY_SCORING = "parent-only"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _copy_list(values: Sequence[str] | None) -> list[str]:
    return list(values or [])


def _copy_dict(values: dict[str, Any] | None) -> dict[str, Any]:
    return dict(values or {})


@dataclass(slots=True)
class ProviderAssignment:
    provider: str
    model: str
    reasoning_effort: str = "medium"
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ProviderAssignment | None:
        if payload is None:
            return None
        return cls(
            provider=payload["provider"],
            model=payload["model"],
            reasoning_effort=payload.get("reasoning_effort", "medium"),
            capabilities=_copy_list(payload.get("capabilities")),
            metadata=_copy_dict(payload.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ResourceBudget:
    token_budget: int = 0
    usd_budget: float = 0.0
    wall_time_budget_s: float = 0.0
    max_parallel_children: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ResourceBudget:
        payload = payload or {}
        return cls(
            token_budget=int(payload.get("token_budget", 0)),
            usd_budget=float(payload.get("usd_budget", 0.0)),
            wall_time_budget_s=float(payload.get("wall_time_budget_s", 0.0)),
            max_parallel_children=int(payload.get("max_parallel_children", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_budget": self.token_budget,
            "usd_budget": self.usd_budget,
            "wall_time_budget_s": self.wall_time_budget_s,
            "max_parallel_children": self.max_parallel_children,
        }


@dataclass(slots=True)
class ResourceUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    wall_time_s: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ResourceUsage:
        payload = payload or {}
        return cls(
            prompt_tokens=int(payload.get("prompt_tokens", 0)),
            completion_tokens=int(payload.get("completion_tokens", 0)),
            cost_usd=float(payload.get("cost_usd", 0.0)),
            wall_time_s=float(payload.get("wall_time_s", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "wall_time_s": self.wall_time_s,
        }


@dataclass(slots=True)
class CapabilityUpdate:
    node_id: str
    capability: str
    score: float
    summary: str = ""
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CapabilityUpdate:
        return cls(
            node_id=payload["node_id"],
            capability=payload["capability"],
            score=float(payload["score"]),
            summary=payload.get("summary", ""),
            confidence=float(payload.get("confidence", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "capability": self.capability,
            "score": self.score,
            "summary": self.summary,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class CapabilitySummary:
    capability: str
    sample_count: int = 0
    average_score: float = 0.0
    last_score: float | None = None
    last_summary: str = ""
    last_parent_node_id: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CapabilitySummary:
        return cls(
            capability=payload["capability"],
            sample_count=int(payload.get("sample_count", 0)),
            average_score=float(payload.get("average_score", 0.0)),
            last_score=payload.get("last_score"),
            last_summary=payload.get("last_summary", ""),
            last_parent_node_id=payload.get("last_parent_node_id"),
            updated_at=payload.get("updated_at"),
        )

    def apply_update(self, update: CapabilityUpdate, parent_node_id: str, applied_at: str) -> None:
        total = self.average_score * self.sample_count
        self.sample_count += 1
        self.average_score = (total + update.score) / self.sample_count
        self.last_score = update.score
        self.last_summary = update.summary
        self.last_parent_node_id = parent_node_id
        self.updated_at = applied_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "sample_count": self.sample_count,
            "average_score": self.average_score,
            "last_score": self.last_score,
            "last_summary": self.last_summary,
            "last_parent_node_id": self.last_parent_node_id,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class AgentNode:
    node_id: str
    role: str
    label: str
    parent_node_id: str | None = None
    status: str = "active"
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    provider_assignment: ProviderAssignment | None = None
    capability_summaries: dict[str, CapabilitySummary] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentNode:
        capability_summaries = {
            name: CapabilitySummary.from_dict(summary_payload)
            for name, summary_payload in (payload.get("capability_summaries") or {}).items()
        }
        return cls(
            node_id=payload["node_id"],
            role=payload["role"],
            label=payload.get("label", payload["node_id"]),
            parent_node_id=payload.get("parent_node_id"),
            status=payload.get("status", "active"),
            resource_budget=ResourceBudget.from_dict(payload.get("resource_budget")),
            provider_assignment=ProviderAssignment.from_dict(payload.get("provider_assignment")),
            capability_summaries=capability_summaries,
            metadata=_copy_dict(payload.get("metadata")),
        )

    def to_dict(self, *, child_node_ids: Sequence[str] | None = None) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "label": self.label,
            "parent_node_id": self.parent_node_id,
            "child_node_ids": sorted(child_node_ids or []),
            "status": self.status,
            "resource_budget": self.resource_budget.to_dict(),
            "provider_assignment": self.provider_assignment.to_dict() if self.provider_assignment else None,
            "capability_summaries": {
                capability: summary.to_dict()
                for capability, summary in sorted(self.capability_summaries.items())
            },
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Competition:
    competition_id: str
    parent_node_id: str
    candidate_node_ids: list[str]
    scoring_policy: str = PARENT_ONLY_SCORING
    status: str = "open"
    last_verdict_id: str | None = None
    winner_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Competition:
        return cls(
            competition_id=payload["competition_id"],
            parent_node_id=payload["parent_node_id"],
            candidate_node_ids=_copy_list(payload.get("candidate_node_ids")),
            scoring_policy=payload.get("scoring_policy", PARENT_ONLY_SCORING),
            status=payload.get("status", "open"),
            last_verdict_id=payload.get("last_verdict_id"),
            winner_run_id=payload.get("winner_run_id"),
            metadata=_copy_dict(payload.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "competition_id": self.competition_id,
            "parent_node_id": self.parent_node_id,
            "candidate_node_ids": list(self.candidate_node_ids),
            "scoring_policy": self.scoring_policy,
            "status": self.status,
            "last_verdict_id": self.last_verdict_id,
            "winner_run_id": self.winner_run_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CandidateRun:
    run_id: str
    competition_id: str
    node_id: str
    submitted_at: str
    status: str = "completed"
    resource_usage: ResourceUsage = field(default_factory=ResourceUsage)
    provider_assignment: ProviderAssignment | None = None
    parent_score: float | None = None
    verdict_id: str | None = None
    notes: str = ""
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CandidateRun:
        return cls(
            run_id=payload["run_id"],
            competition_id=payload["competition_id"],
            node_id=payload["node_id"],
            submitted_at=payload.get("submitted_at", utc_now()),
            status=payload.get("status", "completed"),
            resource_usage=ResourceUsage.from_dict(payload.get("resource_usage")),
            provider_assignment=ProviderAssignment.from_dict(payload.get("provider_assignment")),
            parent_score=payload.get("parent_score"),
            verdict_id=payload.get("verdict_id"),
            notes=payload.get("notes", ""),
            artifacts=_copy_list(payload.get("artifacts")),
            metadata=_copy_dict(payload.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "competition_id": self.competition_id,
            "node_id": self.node_id,
            "submitted_at": self.submitted_at,
            "status": self.status,
            "resource_usage": self.resource_usage.to_dict(),
            "provider_assignment": self.provider_assignment.to_dict() if self.provider_assignment else None,
            "parent_score": self.parent_score,
            "verdict_id": self.verdict_id,
            "notes": self.notes,
            "artifacts": list(self.artifacts),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ParentVerdict:
    verdict_id: str
    competition_id: str
    parent_node_id: str
    score_by_run_id: dict[str, float]
    capability_updates: list[CapabilityUpdate] = field(default_factory=list)
    winner_run_id: str | None = None
    rationale: str = ""
    submitted_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ParentVerdict:
        return cls(
            verdict_id=payload["verdict_id"],
            competition_id=payload["competition_id"],
            parent_node_id=payload["parent_node_id"],
            score_by_run_id={run_id: float(score) for run_id, score in payload.get("score_by_run_id", {}).items()},
            capability_updates=[
                CapabilityUpdate.from_dict(update_payload)
                for update_payload in payload.get("capability_updates", [])
            ],
            winner_run_id=payload.get("winner_run_id"),
            rationale=payload.get("rationale", ""),
            submitted_at=payload.get("submitted_at", utc_now()),
            metadata=_copy_dict(payload.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "competition_id": self.competition_id,
            "parent_node_id": self.parent_node_id,
            "score_by_run_id": dict(self.score_by_run_id),
            "capability_updates": [update.to_dict() for update in self.capability_updates],
            "winner_run_id": self.winner_run_id,
            "rationale": self.rationale,
            "submitted_at": self.submitted_at,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Project:
    project_id: str
    title: str
    objective: str = ""
    status: str = "active"
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    default_provider_assignment: ProviderAssignment | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Project:
        return cls(
            project_id=payload["project_id"],
            title=payload.get("title", payload["project_id"]),
            objective=payload.get("objective", ""),
            status=payload.get("status", "active"),
            resource_budget=ResourceBudget.from_dict(payload.get("resource_budget")),
            default_provider_assignment=ProviderAssignment.from_dict(payload.get("default_provider_assignment")),
            metadata=_copy_dict(payload.get("metadata")),
            created_at=payload.get("created_at", utc_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "resource_budget": self.resource_budget.to_dict(),
            "default_provider_assignment": (
                self.default_provider_assignment.to_dict() if self.default_provider_assignment else None
            ),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class ProjectState:
    project: Project
    nodes: dict[str, AgentNode] = field(default_factory=dict)
    competitions: dict[str, Competition] = field(default_factory=dict)
    runs: dict[str, CandidateRun] = field(default_factory=dict)
    verdicts: dict[str, ParentVerdict] = field(default_factory=dict)


class CatfishRuntime:
    def __init__(self) -> None:
        self._projects: dict[str, ProjectState] = {}

    def register_project(self, project: Project | dict[str, Any]) -> Project:
        project_obj = project if isinstance(project, Project) else Project.from_dict(project)
        if project_obj.project_id in self._projects:
            raise ValueError(f"Project {project_obj.project_id} is already registered")
        self._projects[project_obj.project_id] = ProjectState(project=project_obj)
        return project_obj

    def upsert_agent_node(self, project_id: str, node: AgentNode | dict[str, Any]) -> AgentNode:
        project_state = self._require_project(project_id)
        node_obj = node if isinstance(node, AgentNode) else AgentNode.from_dict(node)
        if node_obj.parent_node_id and node_obj.parent_node_id not in project_state.nodes:
            raise ValueError(f"Parent node {node_obj.parent_node_id} is not registered in project {project_id}")
        project_state.nodes[node_obj.node_id] = node_obj
        return node_obj

    def define_competition(self, project_id: str, competition: Competition | dict[str, Any]) -> Competition:
        project_state = self._require_project(project_id)
        competition_obj = competition if isinstance(competition, Competition) else Competition.from_dict(competition)
        self._validate_competition(project_state, competition_obj)
        project_state.competitions[competition_obj.competition_id] = competition_obj
        return competition_obj

    def record_candidate_run(self, project_id: str, run: CandidateRun | dict[str, Any]) -> CandidateRun:
        project_state = self._require_project(project_id)
        run_obj = run if isinstance(run, CandidateRun) else CandidateRun.from_dict(run)
        if run_obj.run_id in project_state.runs:
            raise ValueError(f"Run {run_obj.run_id} already exists in project {project_id}")
        competition = self._require_competition(project_state, run_obj.competition_id)
        if run_obj.node_id not in competition.candidate_node_ids:
            raise ValueError(
                f"Run {run_obj.run_id} references node {run_obj.node_id}, "
                f"which is not part of competition {run_obj.competition_id}"
            )
        project_state.runs[run_obj.run_id] = run_obj
        return run_obj

    def apply_parent_verdict(self, project_id: str, verdict: ParentVerdict | dict[str, Any]) -> ParentVerdict:
        project_state = self._require_project(project_id)
        verdict_obj = verdict if isinstance(verdict, ParentVerdict) else ParentVerdict.from_dict(verdict)
        if verdict_obj.verdict_id in project_state.verdicts:
            raise ValueError(f"Verdict {verdict_obj.verdict_id} already exists in project {project_id}")

        competition = self._require_competition(project_state, verdict_obj.competition_id)
        if competition.scoring_policy != PARENT_ONLY_SCORING:
            raise ValueError(
                f"Competition {competition.competition_id} uses unsupported scoring policy {competition.scoring_policy}"
            )
        if verdict_obj.parent_node_id != competition.parent_node_id:
            raise ValueError(
                f"Verdict parent {verdict_obj.parent_node_id} does not match competition parent "
                f"{competition.parent_node_id}"
            )
        if not verdict_obj.score_by_run_id:
            raise ValueError("Parent verdict must contain at least one scored run")

        for run_id in verdict_obj.score_by_run_id:
            run = project_state.runs.get(run_id)
            if run is None:
                raise ValueError(f"Verdict references unknown run {run_id}")
            if run.competition_id != competition.competition_id:
                raise ValueError(f"Run {run_id} does not belong to competition {competition.competition_id}")

        winner_run_id = verdict_obj.winner_run_id
        if winner_run_id is None:
            winner_run_id = max(verdict_obj.score_by_run_id.items(), key=lambda item: item[1])[0]
            verdict_obj.winner_run_id = winner_run_id
        elif winner_run_id not in verdict_obj.score_by_run_id:
            raise ValueError(f"Winner run {winner_run_id} is missing from score_by_run_id")

        for run_id, score in verdict_obj.score_by_run_id.items():
            run = project_state.runs[run_id]
            run.parent_score = score
            run.verdict_id = verdict_obj.verdict_id

        for update in verdict_obj.capability_updates:
            if update.node_id not in competition.candidate_node_ids:
                raise ValueError(
                    f"Capability update for node {update.node_id} is outside competition {competition.competition_id}"
                )
            node = project_state.nodes[update.node_id]
            summary = node.capability_summaries.get(update.capability)
            if summary is None:
                summary = CapabilitySummary(capability=update.capability)
                node.capability_summaries[update.capability] = summary
            summary.apply_update(update, parent_node_id=verdict_obj.parent_node_id, applied_at=verdict_obj.submitted_at)

        competition.last_verdict_id = verdict_obj.verdict_id
        competition.winner_run_id = winner_run_id
        competition.status = "scored"
        project_state.verdicts[verdict_obj.verdict_id] = verdict_obj
        return verdict_obj

    def snapshot(self, *, project_id: str | None = None) -> dict[str, Any]:
        if project_id is not None:
            project_state = self._require_project(project_id)
            projects = {project_id: self._project_snapshot(project_state)}
        else:
            projects = {
                current_project_id: self._project_snapshot(project_state)
                for current_project_id, project_state in sorted(self._projects.items())
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "projects": projects,
        }

    def apply_operations(self, operations: Sequence[dict[str, Any]]) -> dict[str, Any]:
        selected_project_id: str | None = None
        for operation in operations:
            op_name = operation["op"]
            if op_name == "register_project":
                project = self.register_project(operation["project"])
                selected_project_id = project.project_id
            elif op_name == "upsert_agent_node":
                selected_project_id = operation["project_id"]
                self.upsert_agent_node(operation["project_id"], operation["node"])
            elif op_name == "define_competition":
                selected_project_id = operation["project_id"]
                self.define_competition(operation["project_id"], operation["competition"])
            elif op_name == "record_candidate_run":
                selected_project_id = operation["project_id"]
                self.record_candidate_run(operation["project_id"], operation["run"])
            elif op_name == "apply_parent_verdict":
                selected_project_id = operation["project_id"]
                self.apply_parent_verdict(operation["project_id"], operation["verdict"])
            else:
                raise ValueError(f"Unsupported operation {op_name}")
        return self.snapshot(project_id=selected_project_id)

    def _require_project(self, project_id: str) -> ProjectState:
        project_state = self._projects.get(project_id)
        if project_state is None:
            raise ValueError(f"Project {project_id} is not registered")
        return project_state

    def _require_competition(self, project_state: ProjectState, competition_id: str) -> Competition:
        competition = project_state.competitions.get(competition_id)
        if competition is None:
            raise ValueError(f"Competition {competition_id} is not defined")
        return competition

    def _validate_competition(self, project_state: ProjectState, competition: Competition) -> None:
        if competition.parent_node_id not in project_state.nodes:
            raise ValueError(f"Competition parent node {competition.parent_node_id} is not registered")
        if competition.scoring_policy != PARENT_ONLY_SCORING:
            raise ValueError(
                f"Competition {competition.competition_id} must use {PARENT_ONLY_SCORING} scoring"
            )
        if not competition.candidate_node_ids:
            raise ValueError(f"Competition {competition.competition_id} must define candidate nodes")
        for node_id in competition.candidate_node_ids:
            node = project_state.nodes.get(node_id)
            if node is None:
                raise ValueError(f"Competition candidate node {node_id} is not registered")
            if node.parent_node_id != competition.parent_node_id:
                raise ValueError(
                    f"Competition candidate node {node_id} must be a child of {competition.parent_node_id}"
                )

    def _project_snapshot(self, project_state: ProjectState) -> dict[str, Any]:
        child_map: dict[str, list[str]] = {node_id: [] for node_id in project_state.nodes}
        root_node_ids: list[str] = []
        for node in project_state.nodes.values():
            if node.parent_node_id is None:
                root_node_ids.append(node.node_id)
            else:
                child_map.setdefault(node.parent_node_id, []).append(node.node_id)

        return {
            "project": project_state.project.to_dict(),
            "root_node_ids": sorted(root_node_ids),
            "nodes": {
                node_id: project_state.nodes[node_id].to_dict(child_node_ids=child_map.get(node_id, []))
                for node_id in sorted(project_state.nodes)
            },
            "competitions": {
                competition_id: competition.to_dict()
                for competition_id, competition in sorted(project_state.competitions.items())
            },
            "runs": {
                run_id: run.to_dict()
                for run_id, run in sorted(project_state.runs.items())
            },
            "verdicts": {
                verdict_id: verdict.to_dict()
                for verdict_id, verdict in sorted(project_state.verdicts.items())
            },
        }


def load_operations(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("operations"), list):
        return payload["operations"]
    raise ValueError("Operations file must be a list or an object with an operations list")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Minimal Catfish runtime for hierarchical competing agents."
    )
    parser.add_argument(
        "--ops",
        type=Path,
        required=True,
        help="JSON file containing runtime operations",
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="Optional project id override for the emitted snapshot",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    runtime = CatfishRuntime()
    operations = load_operations(args.ops)
    runtime.apply_operations(operations)
    snapshot = runtime.snapshot(project_id=args.project_id or None)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
