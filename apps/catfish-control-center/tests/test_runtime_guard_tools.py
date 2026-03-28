from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
PROBE_SCRIPT = TOOLS_DIR / "catfish_guardrail_probe.py"
CTL_SCRIPT = TOOLS_DIR / "catfish_supervisor_ctl.py"


class RuntimeGuardToolTest(unittest.TestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _build_state_root(self, root: Path) -> tuple[Path, Path, Path]:
        state_root = root / "state-root"
        system_root = state_root / "system"
        projects_root = state_root / "projects"
        projects_root.mkdir(parents=True, exist_ok=True)

        root_dir = root / "root-dir"
        vepfs_root = root / "vepfs-root"
        root_dir.mkdir(parents=True, exist_ok=True)
        vepfs_root.mkdir(parents=True, exist_ok=True)
        (root_dir / "trace.txt").write_text("root trace\n", encoding="utf-8")
        (vepfs_root / "artifact.bin").write_bytes(b"1234567890")

        self._write_json(
            system_root / "catfish_runtime_policy.json",
            {
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
            },
        )
        self._write_json(
            system_root / "agentdoc_state.json",
            {
                "observedAt": "2026-03-28T01:00:00Z",
                "agents": [
                    {
                        "agentId": "project-director",
                        "lastAgentDocCheckAt": "2026-03-28T00:59:30Z",
                        "lastHeartbeatAt": "2026-03-28T00:59:40Z",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "resource_manager_state.json",
            {
                "observedAt": "2026-03-28T01:00:00Z",
                "managerId": "resource-manager",
                "requests": [],
                "allocations": [
                    {
                        "allocationId": "alloc-gpu-0",
                        "resourceKind": "gpu",
                        "status": "active",
                        "ownerId": "resource-manager",
                        "leaseHolder": "project-director",
                    }
                ],
            },
        )
        self._write_json(
            system_root / "supervisor_state.json",
            {
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
        )
        return state_root, root_dir, vepfs_root

    def _run(self, script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(cwd or REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_probe_dry_run_reports_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root, root_dir, vepfs_root = self._build_state_root(Path(tmpdir))

            result = self._run(
                PROBE_SCRIPT,
                "--state-root",
                str(state_root),
                "--root-dir",
                str(root_dir),
                "--vepfs-root",
                str(vepfs_root),
                "--cpu-percent",
                "12.5",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["guardrail_state"]["overall_status"], "ok")
            self.assertEqual(payload["supervisor_state"]["restart_intent"], "restart-required")
            self.assertEqual(payload["plan"]["decision"], "restart-requested")
            self.assertFalse((state_root / "system" / "runtime_metrics.json").exists())

    def test_probe_write_flags_persist_runtime_metrics_and_supervisor_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root, root_dir, vepfs_root = self._build_state_root(Path(tmpdir))

            result = self._run(
                PROBE_SCRIPT,
                "--state-root",
                str(state_root),
                "--root-dir",
                str(root_dir),
                "--vepfs-root",
                str(vepfs_root),
                "--cpu-percent",
                "12.5",
                "--write-runtime-metrics",
                "--write-supervisor-state",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "write")
            runtime_metrics_path = state_root / "system" / "runtime_metrics.json"
            supervisor_state_path = state_root / "system" / "supervisor_state.json"
            self.assertTrue(runtime_metrics_path.exists())
            self.assertTrue(supervisor_state_path.exists())
            runtime_metrics = json.loads(runtime_metrics_path.read_text(encoding="utf-8"))
            self.assertGreater(runtime_metrics["rootDirUsageBytes"], 0)
            self.assertGreater(runtime_metrics["vePfsUsageBytes"], 0)

    def test_supervisor_ctl_applies_probe_plan_to_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root, root_dir, vepfs_root = self._build_state_root(Path(tmpdir))

            probe = self._run(
                PROBE_SCRIPT,
                "--state-root",
                str(state_root),
                "--root-dir",
                str(root_dir),
                "--vepfs-root",
                str(vepfs_root),
                "--cpu-percent",
                "12.5",
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            plan_path = Path(tmpdir) / "probe-plan.json"
            plan_path.write_text(probe.stdout, encoding="utf-8")

            ctl = self._run(
                CTL_SCRIPT,
                "--state-root",
                str(state_root),
                "--plan-file",
                str(plan_path),
                "--apply",
            )

            self.assertEqual(ctl.returncode, 0, ctl.stderr)
            payload = json.loads(ctl.stdout)
            self.assertEqual(payload["status"], "applied")
            self.assertTrue((state_root / "system" / "runtime_metrics.json").exists())
            self.assertTrue((state_root / "system" / "supervisor_state.json").exists())


if __name__ == "__main__":
    unittest.main()
