from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from catfish_control_center.guardrails import build_guardrail_state
from catfish_control_center.models import AgentNode, GuardrailState
from catfish_control_center.supervisor import build_supervisor_state


class GuardrailPolicyTest(unittest.TestCase):
    def _policy_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": "catfish.runtime-guardrail.v1",
            "updatedAt": "2026-03-28T01:00:00Z",
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
        }

    def _agents(self) -> list[AgentNode]:
        return [
            AgentNode(
                agent_id="project-director",
                label="Project Director",
                role="supervisor",
                status="active",
                project_id="proj-alpha",
                provider_profile="current-session",
                task_kind="supervisor",
            ),
            AgentNode(
                agent_id="builder-a",
                label="Builder A",
                role="builder",
                status="running",
                project_id="proj-alpha",
                provider_profile="current-session",
                task_kind="implementation",
                parent_id="project-director",
            ),
            AgentNode(
                agent_id="builder-b",
                label="Builder B",
                role="builder",
                status="running",
                project_id="proj-alpha",
                provider_profile="current-session",
                task_kind="implementation",
                parent_id="project-director",
            ),
        ]

    def test_guardrail_state_flags_budget_manager_and_agentdoc_violations(self) -> None:
        guardrail_state = build_guardrail_state(
            policy_payload=self._policy_payload(),
            runtime_metrics={
                "observedAt": "2026-03-28T01:00:00Z",
                "rootDirUsageBytes": 22 * 1024 * 1024,
                "vePfsUsageBytes": 52 * 1024 * 1024 * 1024,
                "cpuPercent": 91.0,
            },
            resource_manager_state={
                "observedAt": "2026-03-28T01:00:00Z",
                "managerId": "resource-manager",
                "requests": [
                    {
                        "requestId": "req-builder-a-gpu",
                        "agentId": "builder-a",
                        "resourceKind": "gpu",
                        "status": "approved",
                        "approvedBy": "builder-a",
                    }
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
                        "allocationId": "alloc-gpu-1",
                        "resourceKind": "gpu",
                        "status": "active",
                        "ownerId": "resource-manager",
                        "leaseHolder": "builder-b",
                    },
                    {
                        "allocationId": "alloc-cpu-direct",
                        "resourceKind": "cpu",
                        "status": "active",
                        "ownerId": "builder-b",
                        "leaseHolder": "builder-b",
                        "percent": 80.0,
                    },
                ],
            },
            agentdoc_state={
                "observedAt": "2026-03-28T01:00:00Z",
                "agents": [
                    {
                        "agentId": "project-director",
                        "lastAgentDocCheckAt": "2026-03-28T00:30:00Z",
                        "lastHeartbeatAt": "2026-03-28T00:58:00Z",
                    },
                    {
                        "agentId": "builder-a",
                        "lastAgentDocCheckAt": "2026-03-28T00:40:00Z",
                        "lastHeartbeatAt": "2026-03-28T00:41:00Z",
                    },
                ],
            },
            agents=self._agents(),
        )

        self.assertIsNotNone(guardrail_state)
        assert guardrail_state is not None
        self.assertEqual(guardrail_state.overall_status, "blocked")

        checks = {check.policy_id: check for check in guardrail_state.checks}
        self.assertEqual(checks["root-dir-budget"].status, "breached")
        self.assertEqual(checks["vepfs-budget"].status, "breached")
        self.assertEqual(checks["cpu-budget"].status, "breached")
        self.assertEqual(checks["resource-manager-ownership"].status, "breached")
        self.assertEqual(checks["gpu-manager-only"].status, "breached")
        self.assertEqual(checks["agentdoc-heartbeat"].status, "breached")
        self.assertIn("builder-b", checks["resource-manager-ownership"].summary)
        self.assertIn("missing=builder-b", checks["agentdoc-heartbeat"].summary)

    def test_supervisor_requests_restart_for_stalled_worker(self) -> None:
        supervisor_state = build_supervisor_state(
            policy_payload=self._policy_payload(),
            supervisor_payload={
                "observedAt": "2026-03-28T01:00:00Z",
                "components": {
                    "catfish-worker": {
                        "role": "worker",
                        "status": "running",
                        "healthy": True,
                        "lastHeartbeatAt": "2026-03-28T00:40:00Z",
                        "lastProgressAt": "2026-03-28T00:39:00Z",
                    },
                    "catfish-scheduler": {
                        "role": "scheduler",
                        "status": "running",
                        "healthy": True,
                        "lastHeartbeatAt": "2026-03-28T00:59:30Z",
                        "lastProgressAt": "2026-03-28T00:59:20Z",
                    },
                },
                "restartHistory": [],
            },
            guardrail_state=None,
        )

        self.assertIsNotNone(supervisor_state)
        assert supervisor_state is not None
        self.assertEqual(supervisor_state.restart_intent, "restart-required")
        self.assertTrue(supervisor_state.restart_allowed)
        self.assertIn("catfish-worker", supervisor_state.restart_command)
        self.assertEqual(supervisor_state.overall_status, "restart-required")

    def test_supervisor_blocks_restart_when_retry_budget_is_exhausted(self) -> None:
        guardrail_state = GuardrailState(
            observed_at="2026-03-28T01:00:00Z",
            overall_status="ok",
            manager_id="resource-manager",
        )
        supervisor_state = build_supervisor_state(
            policy_payload=self._policy_payload(),
            supervisor_payload={
                "observedAt": "2026-03-28T01:00:00Z",
                "components": {
                    "catfish-worker": {
                        "role": "worker",
                        "status": "failed",
                        "healthy": False,
                        "lastHeartbeatAt": "2026-03-28T00:20:00Z",
                        "lastProgressAt": "2026-03-28T00:20:00Z",
                    }
                },
                "restartHistory": [
                    {"startedAt": "2026-03-28T00:20:00Z"},
                    {"startedAt": "2026-03-28T00:40:00Z"},
                ],
            },
            guardrail_state=guardrail_state,
        )

        self.assertIsNotNone(supervisor_state)
        assert supervisor_state is not None
        self.assertEqual(supervisor_state.restart_intent, "restart-blocked")
        self.assertFalse(supervisor_state.restart_allowed)
        self.assertIn("budget exhausted", supervisor_state.restart_reason.lower())
        self.assertEqual(supervisor_state.recent_restart_count, 2)


if __name__ == "__main__":
    unittest.main()
