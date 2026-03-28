from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from catfish_control_center.cli import main as cli_main
from catfish_control_center.dashboard import render_dashboard, render_view, view_to_dict
from catfish_control_center.models import ControlEvent
from catfish_control_center.runtime import apply_route_preview, load_live_state, load_snapshot
from catfish_control_center.storage import InMemoryEventStore, JsonLinesEventStore, JsonSnapshotStore


class ControlCenterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot_path = APP_ROOT / "examples" / "sample_snapshot.json"
        self.route_config_path = Path(__file__).resolve().parents[3] / "tools" / "examples" / "control_plane.example.json"

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_jsonl(self, path: Path, payloads: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(item, ensure_ascii=False) for item in payloads]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _build_live_state_root(self, root: Path) -> Path:
        state_root = root / "state-root"
        system_root = state_root / "system"
        projects_root = state_root / "projects"

        self._write_json(
            system_root / "scheduler_state.json",
            {
                "generatedAt": "2026-03-25T12:20:00Z",
                "providers": [
                    {
                        "providerId": "ucloud-modelverse",
                        "remainingCredit": 0.92,
                        "reserveFloor": 0.2,
                        "routingWeight": 1.0,
                        "activeLaunches": 2,
                    },
                    {
                        "providerId": "smartaipro",
                        "remainingCredit": 0.0,
                        "reserveFloor": 0.15,
                        "routingWeight": 0.6,
                        "activeLaunches": 1,
                        "issues": ["quota-drained"],
                    },
                ],
                "projects": [
                    {
                        "projectId": "proj-alpha",
                        "activeStage": "implementation",
                        "frontierWidth": 2,
                        "activeBranch": "feature/live-runtime",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "dispatch_queue.json",
            {
                "generatedAt": "2026-03-25T12:19:00Z",
                "launches": [
                    {
                        "launchId": "launch-runtime-a",
                        "projectId": "proj-alpha",
                        "stageId": "implementation",
                        "nodeId": "builder-a",
                        "nodeLabel": "Builder A",
                        "branch": "feature/live-runtime",
                        "status": "running",
                        "provider": "ucloud-modelverse",
                        "model": "gpt-5.4",
                        "launchedAt": "2026-03-25T12:18:00Z",
                        "summary": "Builder A launch from dispatcher.",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "review_queue.json",
            {
                "generatedAt": "2026-03-25T12:19:30Z",
                "reviews": [
                    {
                        "reviewId": "review-figure-1",
                        "projectId": "proj-alpha",
                        "stageId": "figure",
                        "targetKind": "figure-draft",
                        "targetId": "fig-competition-1",
                        "status": "pending",
                        "requestedBy": "Figure Director",
                        "createdAt": "2026-03-25T12:12:00Z",
                        "priority": "high",
                        "summary": "Need caption-ready figure verdict.",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "provider_registry.json",
            {
                "schemaVersion": "catfish.provider-registry.v1",
                "updatedAt": "2026-03-25T12:00:00Z",
                "providers": [
                    {
                        "id": "ucloud-modelverse",
                        "displayName": "UCloud / Modelverse",
                        "enabled": True,
                        "routingWeight": 1.0,
                        "machineIds": ["dev-intern-02"],
                        "modelTiers": {
                            "balanced": {"model": "gpt-5.4", "verified": True},
                            "deep": {"model": "gpt-5.4", "verified": True},
                        },
                    },
                    {
                        "id": "smartaipro",
                        "displayName": "SmartAIPro",
                        "enabled": True,
                        "routingWeight": 0.6,
                        "machineIds": ["dev-intern-02"],
                        "modelTiers": {
                            "balanced": {"model": "gpt-5.4", "verified": False}
                        },
                    },
                ],
            },
        )
        self._write_json(
            system_root / "provider_health.json",
            {
                "schemaVersion": "catfish.provider-health.v1",
                "observedAt": "2026-03-25",
                "providers": [
                    {
                        "providerId": "ucloud-modelverse",
                        "status": "working",
                        "endpointReachable": True,
                        "quotaState": "healthy",
                        "verifiedModels": ["gpt-5.4"],
                    },
                    {
                        "providerId": "smartaipro",
                        "status": "quota-exhausted",
                        "endpointReachable": True,
                        "quotaState": "exhausted",
                        "verifiedModels": [],
                    },
                ],
            },
        )
        self._write_json(
            system_root / "capability_ledger.json",
            {
                "schemaVersion": "catfish.capability-ledger.v1",
                "updatedAt": "2026-03-25T12:00:00Z",
                "entries": [
                    {
                        "providerId": "ucloud-modelverse",
                        "taskCategory": "builder",
                        "difficulty": "high",
                        "reasoningTier": "deep",
                        "parentScore": 0.91,
                        "confidence": 0.95,
                        "recency": "2026-03-25T12:00:00Z",
                        "notes": "Strong implementation provider.",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "catfish_runtime_policy.json",
            {
                "schemaVersion": "catfish.runtime-guardrail.v1",
                "updatedAt": "2026-03-25T12:20:00Z",
                "resourceManager": {
                    "managerId": "resource-manager",
                    "ownedResourceKinds": ["gpu", "storage", "cpu"],
                },
                "budgets": {
                    "rootDir": {
                        "policyId": "root-dir-budget",
                        "path": "/workspace/root",
                        "maxBytes": 20 * 1024 * 1024,
                        "warnBytes": 15 * 1024 * 1024,
                        "actionScript": "du -sb /workspace/root",
                    },
                    "vePfs": {
                        "policyId": "vepfs-budget",
                        "path": "/dev_vepfs/task-root",
                        "maxBytes": 50 * 1024 * 1024 * 1024,
                        "warnBytes": 45 * 1024 * 1024 * 1024,
                        "actionScript": "du -sb /dev_vepfs/task-root",
                    },
                    "cpu": {
                        "policyId": "cpu-budget",
                        "maxPercent": 65.0,
                        "warnPercent": 50.0,
                        "hostReservePercent": 35.0,
                        "actionScript": "python -m catfish_control_center.main --view supervisor",
                    },
                },
                "ownership": {
                    "policyId": "resource-manager-ownership",
                    "resourceKinds": ["gpu", "storage", "cpu"],
                    "actionScript": "python -m catfish_control_center.main --view guardrails --format json",
                },
                "gpu": {
                    "policyId": "gpu-manager-only",
                    "maxSimultaneousOwners": 1,
                    "warnSimultaneousOwners": 1,
                    "actionScript": "python -m catfish_control_center.main --view guardrails",
                },
                "agentDoc": {
                    "policyId": "agentdoc-heartbeat",
                    "requiredCadenceSeconds": 900,
                    "warnCadenceSeconds": 600,
                    "actionScript": "python -m catfish_control_center.main --view recent-events",
                },
                "supervisor": {
                    "workerStallSeconds": 600,
                    "schedulerStallSeconds": 900,
                    "restartCooldownSeconds": 900,
                    "maxRestartsPerWindow": 2,
                    "restartWindowSeconds": 3600,
                    "restartCommand": "catfish-supervisor restart --component {component}",
                },
            },
        )
        self._write_json(
            system_root / "runtime_metrics.json",
            {
                "observedAt": "2026-03-25T12:20:00Z",
                "rootDirUsageBytes": 12 * 1024 * 1024,
                "vePfsUsageBytes": 20 * 1024 * 1024 * 1024,
                "cpuPercent": 42.5,
            },
        )
        self._write_json(
            system_root / "resource_manager_state.json",
            {
                "observedAt": "2026-03-25T12:20:00Z",
                "managerId": "resource-manager",
                "requests": [
                    {
                        "requestId": "req-gpu-builder-a",
                        "agentId": "builder-a",
                        "resourceKind": "gpu",
                        "status": "approved",
                        "approvedBy": "resource-manager",
                    },
                    {
                        "requestId": "req-cpu-builder-a",
                        "agentId": "builder-a",
                        "resourceKind": "cpu",
                        "status": "approved",
                        "approvedBy": "resource-manager",
                    },
                ],
                "allocations": [
                    {
                        "allocationId": "alloc-gpu-0",
                        "resourceKind": "gpu",
                        "status": "active",
                        "ownerId": "resource-manager",
                        "leaseHolder": "builder-a",
                    },
                    {
                        "allocationId": "alloc-cpu-0",
                        "resourceKind": "cpu",
                        "status": "active",
                        "ownerId": "resource-manager",
                        "leaseHolder": "builder-a",
                        "percent": 35.0,
                    },
                    {
                        "allocationId": "alloc-storage-0",
                        "resourceKind": "storage",
                        "status": "active",
                        "ownerId": "resource-manager",
                        "leaseHolder": "builder-a",
                    },
                ],
            },
        )
        self._write_json(
            system_root / "agentdoc_state.json",
            {
                "observedAt": "2026-03-25T12:20:00Z",
                "agents": [
                    {
                        "agentId": "project-director",
                        "lastAgentDocCheckAt": "2026-03-25T12:18:00Z",
                        "lastHeartbeatAt": "2026-03-25T12:19:00Z",
                    },
                    {
                        "agentId": "builder-a",
                        "lastAgentDocCheckAt": "2026-03-25T12:13:30Z",
                        "lastHeartbeatAt": "2026-03-25T12:18:30Z",
                    },
                    {
                        "agentId": "builder-b",
                        "lastAgentDocCheckAt": "2026-03-25T12:14:00Z",
                        "lastHeartbeatAt": "2026-03-25T12:18:20Z",
                    },
                    {
                        "agentId": "figure-a",
                        "lastAgentDocCheckAt": "2026-03-25T12:16:00Z",
                        "lastHeartbeatAt": "2026-03-25T12:18:00Z",
                    },
                    {
                        "agentId": "figure-b",
                        "lastAgentDocCheckAt": "2026-03-25T12:16:30Z",
                        "lastHeartbeatAt": "2026-03-25T12:18:10Z",
                    },
                ],
            },
        )
        self._write_json(
            system_root / "supervisor_state.json",
            {
                "observedAt": "2026-03-25T12:20:00Z",
                "components": {
                    "catfish-worker": {
                        "role": "worker",
                        "status": "running",
                        "healthy": True,
                        "lastHeartbeatAt": "2026-03-25T12:19:40Z",
                        "lastProgressAt": "2026-03-25T12:19:30Z",
                    },
                    "catfish-scheduler": {
                        "role": "scheduler",
                        "status": "running",
                        "healthy": True,
                        "lastHeartbeatAt": "2026-03-25T12:19:50Z",
                        "lastProgressAt": "2026-03-25T12:19:45Z",
                    },
                },
                "restartHistory": [],
            },
        )

        project_root = projects_root / "proj-alpha"
        self._write_json(
            project_root / "manifest.json",
            {
                "projectId": "proj-alpha",
                "label": "Project Alpha",
                "status": "running",
                "owner": "Project Director",
                "activeBranch": "feature/live-runtime",
                "currentStage": "implementation",
                "summary": "Live Catfish integration test project.",
                "branches": [
                    {
                        "branch": "feature/live-runtime",
                        "score": 0.89,
                        "wins": 4,
                        "losses": 1,
                        "state": "leading",
                        "headCommit": "abc1234",
                        "summary": "Primary live integration branch.",
                    },
                    {
                        "branch": "feature/figure-path",
                        "score": 0.74,
                        "wins": 2,
                        "losses": 2,
                        "state": "contending",
                        "headCommit": "def5678",
                        "summary": "Alternative figure-focused branch.",
                    },
                ],
            },
        )
        self._write_json(
            project_root / "runtime_snapshot.json",
            {
                "schema_version": "catfish-runtime/v1",
                "generated_at": "2026-03-25T12:17:00Z",
                "projects": {
                    "proj-alpha": {
                        "project": {
                            "project_id": "proj-alpha",
                            "title": "Project Alpha",
                            "objective": "Keep competition live across implementation and figure stages.",
                            "status": "running",
                        },
                        "root_node_ids": ["project-director"],
                        "nodes": {
                            "project-director": {
                                "node_id": "project-director",
                                "label": "Project Director",
                                "role": "supervisor",
                                "status": "active",
                                "parent_node_id": None,
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "stageId": "implementation",
                                    "branch": "feature/live-runtime",
                                    "summary": "Owns parent-only scoring.",
                                },
                            },
                            "builder-a": {
                                "node_id": "builder-a",
                                "label": "Builder A",
                                "role": "builder",
                                "status": "running",
                                "parent_node_id": "project-director",
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4",
                                },
                                "capability_summaries": {
                                    "implementation": {
                                        "capability": "implementation",
                                        "sample_count": 2,
                                        "average_score": 0.9,
                                        "last_score": 0.92,
                                        "last_summary": "Best patch quality so far.",
                                        "updated_at": "2026-03-25T12:09:00Z",
                                    }
                                },
                                "metadata": {
                                    "stageId": "implementation",
                                    "branch": "feature/live-runtime",
                                    "agent_group": "builder-duo",
                                },
                            },
                            "builder-b": {
                                "node_id": "builder-b",
                                "label": "Builder B",
                                "role": "builder",
                                "status": "running",
                                "parent_node_id": "project-director",
                                "provider_assignment": {
                                    "provider": "smartaipro",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "stageId": "implementation",
                                    "branch": "feature/live-runtime",
                                    "agent_group": "builder-duo",
                                },
                            },
                            "figure-a": {
                                "node_id": "figure-a",
                                "label": "Figure A",
                                "role": "renderer",
                                "status": "active",
                                "parent_node_id": "project-director",
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "stageId": "figure",
                                    "branch": "feature/figure-path",
                                    "agent_group": "renderers",
                                },
                            },
                            "figure-b": {
                                "node_id": "figure-b",
                                "label": "Figure B",
                                "role": "renderer",
                                "status": "active",
                                "parent_node_id": "project-director",
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4-mini",
                                },
                                "metadata": {
                                    "stageId": "figure",
                                    "branch": "feature/figure-path",
                                    "agent_group": "renderers-alt",
                                },
                            },
                        },
                        "competitions": {
                            "comp-impl": {
                                "competition_id": "comp-impl",
                                "parent_node_id": "project-director",
                                "candidate_node_ids": ["builder-a", "builder-b"],
                                "status": "scored",
                                "last_verdict_id": "verdict-impl",
                                "winner_run_id": "run-builder-a",
                                "metadata": {
                                    "stageId": "implementation",
                                    "stageLabel": "Implementation",
                                    "advancementMode": "winner-take-all",
                                    "summary": "Implementation builders compete on patch quality.",
                                },
                            },
                            "comp-fig": {
                                "competition_id": "comp-fig",
                                "parent_node_id": "project-director",
                                "candidate_node_ids": ["figure-a", "figure-b"],
                                "status": "open",
                                "metadata": {
                                    "stageId": "figure",
                                    "stageLabel": "Figure Generation",
                                    "advancementMode": "top-k-survival",
                                    "summary": "Figure candidates remain under active parent review.",
                                },
                            },
                        },
                        "runs": {
                            "run-builder-a": {
                                "run_id": "run-builder-a",
                                "competition_id": "comp-impl",
                                "node_id": "builder-a",
                                "submitted_at": "2026-03-25T12:05:00Z",
                                "status": "completed",
                                "parent_score": 0.92,
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "branch": "feature/live-runtime",
                                    "stageId": "implementation",
                                    "agentGroup": "builder-duo",
                                },
                            },
                            "run-builder-b": {
                                "run_id": "run-builder-b",
                                "competition_id": "comp-impl",
                                "node_id": "builder-b",
                                "submitted_at": "2026-03-25T12:06:00Z",
                                "status": "completed",
                                "parent_score": 0.71,
                                "provider_assignment": {
                                    "provider": "smartaipro",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "branch": "feature/live-runtime",
                                    "stageId": "implementation",
                                    "agentGroup": "builder-duo",
                                },
                            },
                            "run-figure-a": {
                                "run_id": "run-figure-a",
                                "competition_id": "comp-fig",
                                "node_id": "figure-a",
                                "submitted_at": "2026-03-25T12:10:00Z",
                                "status": "completed",
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4",
                                },
                                "metadata": {
                                    "branch": "feature/figure-path",
                                    "stageId": "figure",
                                    "agentGroup": "renderers",
                                },
                            },
                            "run-figure-b": {
                                "run_id": "run-figure-b",
                                "competition_id": "comp-fig",
                                "node_id": "figure-b",
                                "submitted_at": "2026-03-25T12:11:00Z",
                                "status": "completed",
                                "provider_assignment": {
                                    "provider": "ucloud-modelverse",
                                    "model": "gpt-5.4-mini",
                                },
                                "metadata": {
                                    "branch": "feature/figure-path",
                                    "stageId": "figure",
                                    "agentGroup": "renderers-alt",
                                },
                            },
                        },
                        "verdicts": {
                            "verdict-impl": {
                                "verdict_id": "verdict-impl",
                                "competition_id": "comp-impl",
                                "parent_node_id": "project-director",
                                "winner_run_id": "run-builder-a",
                                "score_by_run_id": {
                                    "run-builder-a": 0.92,
                                    "run-builder-b": 0.71,
                                },
                                "submitted_at": "2026-03-25T12:09:00Z",
                                "rationale": "Builder A produced the stronger patch.",
                            }
                        },
                    }
                },
            },
        )
        self._write_jsonl(
            project_root / "events" / "runtime.jsonl",
            [
                {
                    "event_id": "evt-alpha-1",
                    "timestamp": "2026-03-25T12:07:00Z",
                    "level": "info",
                    "kind": "branch-score",
                    "message": "Implementation branch remains in front.",
                    "project_id": "proj-alpha",
                    "branch": "feature/live-runtime",
                },
                {
                    "event_id": "evt-alpha-2",
                    "timestamp": "2026-03-25T12:13:00Z",
                    "level": "warning",
                    "kind": "review-queue",
                    "message": "Figure competition needs parent verdict.",
                    "project_id": "proj-alpha",
                    "agent_id": "project-director",
                },
            ],
        )
        return state_root

    def test_dashboard_renders_route_preview_and_sections(self) -> None:
        snapshot = load_snapshot(self.snapshot_path)
        snapshot = apply_route_preview(
            snapshot,
            config_path=self.route_config_path,
            machine_id="dev-intern-02",
            task_kind="builder",
            difficulty="high",
        )

        rendered = render_dashboard(snapshot)
        self.assertIn("Catfish Control Center Snapshot", rendered)
        self.assertIn("Projects", rendered)
        self.assertIn("Agent Graph / Hierarchy", rendered)
        self.assertIn("Runtime Guardrails", rendered)
        self.assertIn("Supervisor State", rendered)
        self.assertIn("Provider Status", rendered)
        self.assertIn("Branch Scoreboards", rendered)
        self.assertIn("Route Preview", rendered)
        self.assertIn("Current Session (current-session) SELECTED", rendered)
        self.assertIn("tier=deep", rendered)

    def test_load_live_state_builds_competition_review_launch_and_diversity_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = self._build_live_state_root(Path(tmpdir))
            snapshot = load_live_state(state_root)

        self.assertEqual(snapshot.metadata["source"], "state-root")
        self.assertEqual(len(snapshot.projects), 1)
        self.assertEqual(snapshot.projects[0].project_id, "proj-alpha")
        self.assertEqual(snapshot.projects[0].pending_reviews, 2)
        self.assertEqual(snapshot.projects[0].current_stage, "implementation")
        self.assertEqual(len(snapshot.stage_competitions), 2)
        self.assertEqual({item.stage_id for item in snapshot.stage_competitions}, {"implementation", "figure"})
        self.assertEqual(len(snapshot.pending_reviews), 2)
        self.assertTrue(any(item.status == "pending-parent-verdict" for item in snapshot.pending_reviews))
        self.assertTrue(any(item.source == "dispatch" for item in snapshot.launches))
        self.assertTrue(any(item.source == "runtime-run" for item in snapshot.launches))
        self.assertTrue(any(item.capability == "implementation" for item in snapshot.capability_summaries))
        self.assertTrue(any(item.source_kind == "provider" for item in snapshot.capability_summaries))
        self.assertEqual(len(snapshot.diversity_metrics), 2)
        self.assertIsNotNone(snapshot.guardrail_state)
        self.assertEqual(snapshot.guardrail_state.overall_status, "ok")
        self.assertIsNotNone(snapshot.supervisor_state)
        self.assertEqual(snapshot.supervisor_state.overall_status, "healthy")

        provider_states = {item.profile_id: item for item in snapshot.providers}
        self.assertTrue(provider_states["ucloud-modelverse"].available)
        self.assertFalse(provider_states["smartaipro"].available)
        self.assertEqual(provider_states["ucloud-modelverse"].active_launches, 2)

    def test_render_and_json_views_focus_on_live_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = self._build_live_state_root(Path(tmpdir))
            snapshot = load_live_state(state_root)

        competitions_view = render_view(snapshot, "stage-competitions")
        self.assertIn("comp-impl", competitions_view)
        self.assertIn("comp-fig", competitions_view)
        self.assertIn("dominant_stack_share", competitions_view)

        diversity_payload = view_to_dict(snapshot, "diversity-metrics")
        self.assertEqual(len(diversity_payload["diversity_metrics"]), 2)
        figure_metric = next(item for item in diversity_payload["diversity_metrics"] if item["stage_id"] == "figure")
        self.assertEqual(figure_metric["unique_models"], 2)
        self.assertGreaterEqual(figure_metric["wildcard_count"], 1)

        guardrail_payload = view_to_dict(snapshot, "guardrails")
        self.assertEqual(guardrail_payload["guardrail_state"]["overall_status"], "ok")
        supervisor_view = render_view(snapshot, "supervisor")
        self.assertIn("restart_intent=none", supervisor_view)

    def test_cli_accepts_state_root_and_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = self._build_live_state_root(Path(tmpdir))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "--state-root",
                        str(state_root),
                        "--view",
                        "provider-status",
                        "--format",
                        "json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(payload["providers"]), 2)
        self.assertEqual(payload["providers"][0]["profile_id"], "smartaipro")

    def test_snapshot_store_round_trip(self) -> None:
        snapshot = load_snapshot(self.snapshot_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            store = JsonSnapshotStore(path)
            store.save(snapshot)
            reloaded = store.load()

        self.assertEqual(reloaded.generated_at, snapshot.generated_at)
        self.assertEqual(len(reloaded.projects), 2)
        self.assertEqual(reloaded.projects[0].project_id, "catfish-core")

    def test_json_lines_event_store_appends_and_reads_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            store = JsonLinesEventStore(path)
            store.append(
                ControlEvent(
                    event_id="evt-1",
                    timestamp="2026-03-25T10:00:00Z",
                    level="info",
                    kind="heartbeat",
                    message="first",
                )
            )
            store.append(
                ControlEvent(
                    event_id="evt-2",
                    timestamp="2026-03-25T10:05:00Z",
                    level="warning",
                    kind="quota",
                    message="second",
                )
            )

            recent = store.list_recent(limit=1)

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].event_id, "evt-2")

    def test_in_memory_event_store(self) -> None:
        store = InMemoryEventStore()
        store.append(
            ControlEvent(
                event_id="evt-memory",
                timestamp="2026-03-25T10:30:00Z",
                level="info",
                kind="memory",
                message="ok",
            )
        )
        payload = [event.to_dict() for event in store.list_recent()]
        self.assertEqual(payload, [json.loads(json.dumps(payload[0]))])


if __name__ == "__main__":
    unittest.main()
