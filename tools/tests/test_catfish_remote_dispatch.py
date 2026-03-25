from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DISPATCH_MODULE = load_module("catfish_remote_dispatch", TOOLS_DIR / "catfish_remote_dispatch.py")
BOOTSTRAP_MODULE = load_module("catfish_project_bootstrap", TOOLS_DIR / "catfish_project_bootstrap.py")
RUNTIME_MODULE = load_module("catfish_runtime_for_dispatch_test", TOOLS_DIR / "catfish_runtime.py")


class CatfishRemoteDispatchTest(unittest.TestCase):
    def make_router_inputs(self) -> tuple[dict, dict, dict]:
        registry = {
            "routing": {
                "mode": "provider-health-capability",
                "defaultMachineId": "dev-intern-02",
                "defaultTier": "balanced",
                "difficultyTierMap": {"low": "quick", "medium": "balanced", "high": "deep"},
                "taskCategoryTierMap": {"builder": "deep", "review": "balanced"},
                "reasoningLengthByTier": {"quick": "short", "balanced": "medium", "deep": "long"},
            },
            "providers": [
                {
                    "id": "alpha-provider",
                    "providerName": "alpha",
                    "displayName": "Alpha Provider",
                    "enabled": True,
                    "machineIds": ["dev-intern-02", "local"],
                    "routingWeight": 1.0,
                    "wireApi": "responses",
                    "envKey": "OPENAI_API_KEY",
                    "baseUrl": "https://alpha.example.com/v1",
                    "requiresOpenAIAuth": False,
                    "modelTiers": {
                        "quick": {"model": "gpt-5.3-codex", "reasoningEffort": "medium", "verified": True},
                        "balanced": {"model": "gpt-5.4-mini", "reasoningEffort": "medium", "verified": True},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "high", "verified": True},
                    },
                },
                {
                    "id": "beta-provider",
                    "providerName": "beta",
                    "displayName": "Beta Provider",
                    "enabled": True,
                    "machineIds": ["dev-intern-02", "local"],
                    "routingWeight": 0.95,
                    "wireApi": "responses",
                    "envKey": "OPENAI_API_KEY",
                    "baseUrl": "https://beta.example.com/v1",
                    "requiresOpenAIAuth": False,
                    "modelTiers": {
                        "quick": {"model": "gpt-5.3-codex", "reasoningEffort": "medium", "verified": True},
                        "balanced": {"model": "gpt-5.4", "reasoningEffort": "high", "verified": True},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "xhigh", "verified": True},
                    },
                },
            ],
        }
        health = {
            "observedAt": "2026-03-25T12:00:00Z",
            "providers": [
                {
                    "providerId": "alpha-provider",
                    "status": "working",
                    "endpointReachable": True,
                    "quotaState": "healthy",
                    "notes": ["alpha healthy"],
                },
                {
                    "providerId": "beta-provider",
                    "status": "working",
                    "endpointReachable": True,
                    "quotaState": "healthy",
                    "notes": ["beta healthy"],
                },
            ],
        }
        ledger = {
            "schemaVersion": "test-ledger/v1",
            "entries": [
                {
                    "id": "alpha-builder-deep",
                    "providerId": "alpha-provider",
                    "taskCategory": "builder",
                    "difficulty": "high",
                    "reasoningTier": "deep",
                    "reasoningLength": "long",
                    "parentScore": 0.82,
                    "recency": "2026-03-24",
                    "confidence": 0.9,
                    "routingEffect": "prefer",
                    "scoreDelta": 0.22,
                    "notes": "Alpha is slightly stronger for builder tasks.",
                },
                {
                    "id": "beta-builder-deep",
                    "providerId": "beta-provider",
                    "taskCategory": "builder",
                    "difficulty": "high",
                    "reasoningTier": "deep",
                    "reasoningLength": "long",
                    "parentScore": 0.82,
                    "recency": "2026-03-24",
                    "confidence": 0.9,
                    "routingEffect": "prefer",
                    "scoreDelta": 0.18,
                    "notes": "Beta is also strong and should remain in the frontier.",
                },
            ],
        }
        return registry, health, ledger

    def make_state(self, temp_dir: str) -> tuple[Path, dict]:
        state = {
            "schemaVersion": "catfish.dispatch-state.v1",
            "project": {
                "projectId": "proj-dispatch",
                "title": "Dispatch Test",
                "workspaceRoot": "/repo/worktree",
                "defaultMachineId": "dev-intern-02",
                "launchDefaults": {
                    "host": "local",
                    "remoteHome": "/dev_vepfs/rc_wu",
                    "remoteBinaryStore": "/dev_vepfs/rc_wu/bin/codex",
                    "remoteRunRoot": "/dev_vepfs/rc_wu/codex_subagents",
                    "sandbox": "danger-full-access",
                    "approval": "never",
                    "search": True,
                    "skipInstall": True,
                    "addDir": ["/repo/worktree"],
                },
            },
            "runtime": {
                "projectId": "proj-dispatch",
                "operations": [
                    {
                        "op": "register_project",
                        "project": {
                            "project_id": "proj-dispatch",
                            "title": "Dispatch Test",
                            "objective": "Bridge planner state into remote launch specs",
                            "resource_budget": {
                                "token_budget": 60000,
                                "usd_budget": 20.0,
                                "wall_time_budget_s": 7200.0,
                                "max_parallel_children": 4,
                            },
                        },
                    },
                    {
                        "op": "upsert_agent_node",
                        "project_id": "proj-dispatch",
                        "node": {
                            "node_id": "root-parent",
                            "role": "supervisor",
                            "label": "Root Parent",
                            "status": "active",
                            "resource_budget": {
                                "token_budget": 24000,
                                "max_parallel_children": 4,
                            },
                        },
                    },
                ],
            },
            "stages": [
                {
                    "stageId": "impl-wave-1",
                    "competitionId": "comp-impl-wave-1",
                    "parentNodeId": "root-parent",
                    "taskCategory": "builder",
                    "difficulty": "high",
                    "parentScore": 0.82,
                    "candidateCount": 3,
                    "cwd": "/repo/worktree",
                    "branchPrefix": "dispatch/impl-wave-1",
                    "dispatchRunId": "dispatch-wave-impl-1",
                    "promptText": "Implement the execution bridge and summarize the outcome.",
                    "agentGroups": [
                        {"agentGroupId": "builder", "label": "Builder", "roles": ["worker"]},
                        {
                            "agentGroupId": "builder-critic",
                            "label": "Builder + Critic",
                            "roles": ["worker", "reviewer"],
                            "scoreBias": 0.03,
                            "promptPrefix": "Include a concise self-critique before the final summary.",
                        },
                    ],
                    "resourceBudget": {
                        "token_budget": 12000,
                        "usd_budget": 4.0,
                        "wall_time_budget_s": 1800.0,
                    },
                }
            ],
        }
        state_path = Path(temp_dir) / "dispatch_state.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state_path, state

    def test_plan_preserves_competition_and_runtime_compatibility(self) -> None:
        registry, health, ledger = self.make_router_inputs()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path, state = self.make_state(temp_dir)
            plan = DISPATCH_MODULE.build_dispatch_plan(
                state,
                registry=registry,
                health_snapshot=health,
                ledger=ledger,
                state_path=state_path,
            )

        self.assertEqual(plan["projectId"], "proj-dispatch")
        self.assertEqual(len(plan["stagePlans"]), 1)
        stage_plan = plan["stagePlans"][0]
        self.assertEqual(stage_plan["candidate_count"], 3)
        self.assertEqual(len(stage_plan["candidates"]), 3)

        provider_ids = [candidate["selected_route"]["provider_id"] for candidate in stage_plan["candidates"]]
        agent_group_ids = [candidate["agent_group"]["agentGroupId"] for candidate in stage_plan["candidates"]]
        branch_ids = [candidate["branch_id"] for candidate in stage_plan["candidates"]]
        competition_cell_ids = [candidate["competition_cell_id"] for candidate in stage_plan["candidates"]]
        self.assertGreaterEqual(len(set(provider_ids)), 2)
        self.assertGreaterEqual(len(set(agent_group_ids)), 2)
        self.assertEqual(len(set(branch_ids)), 3)
        self.assertEqual(len(set(competition_cell_ids)), 3)

        for candidate in stage_plan["candidates"]:
            self.assertEqual(
                candidate["route_specs"][0]["provider_name"],
                candidate["selected_route"]["provider_name"],
            )
            self.assertIn(candidate["competition_cell_id"], candidate["prompt_text"])
            self.assertIn(candidate["branch_id"], candidate["prompt_text"])

        runtime = RUNTIME_MODULE.CatfishRuntime()
        runtime.apply_operations(state["runtime"]["operations"])
        runtime.apply_operations(plan["runtimeOperations"])
        snapshot = runtime.snapshot(project_id="proj-dispatch")
        project_snapshot = snapshot["projects"]["proj-dispatch"]
        self.assertIn("comp-impl-wave-1", project_snapshot["competitions"])
        self.assertEqual(
            len(project_snapshot["competitions"]["comp-impl-wave-1"]["candidate_node_ids"]),
            3,
        )
        self.assertEqual(len(project_snapshot["runs"]), 3)
        for run in project_snapshot["runs"].values():
            self.assertIn("competition_cell_id", run["metadata"])
            self.assertIn("agent_root", run["metadata"])

    def test_generate_writes_launch_specs_with_remote_launcher_contract(self) -> None:
        registry, health, ledger = self.make_router_inputs()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path, state = self.make_state(temp_dir)
            plan = DISPATCH_MODULE.build_dispatch_plan(
                state,
                registry=registry,
                health_snapshot=health,
                ledger=ledger,
                state_path=state_path,
            )
            output_dir = Path(temp_dir) / "generated"
            generated = DISPATCH_MODULE.write_plan_artifacts(plan, output_dir=output_dir)

            self.assertTrue((output_dir / "dispatch_plan.json").exists())
            self.assertTrue((output_dir / "runtime_operations.json").exists())
            self.assertTrue((output_dir / "control_snapshot.json").exists())
            self.assertEqual(len(generated["launch_specs"]), 3)

            first_launch = generated["launch_specs"][0]
            launch_spec_path = Path(first_launch["launch_spec_path"])
            payload = json.loads(launch_spec_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["competition_id"], "comp-impl-wave-1")
            self.assertTrue(payload["prompt_file"].endswith("prompt.md"))
            self.assertTrue(payload["route_specs_file"].endswith("route_specs.json"))
            self.assertIn(str(DISPATCH_MODULE.DEFAULT_REMOTE_LAUNCHER_PATH), payload["launch_command"])
            self.assertIn("--route-spec-file", payload["launch_command"])
            self.assertIn("--prompt-file", payload["launch_command"])
            self.assertIn("dispatch-wave-impl-1", payload["agent_root"])
            self.assertTrue(Path(payload["prompt_file"]).exists())
            self.assertTrue(Path(payload["route_specs_file"]).exists())

            control_snapshot = json.loads((output_dir / "control_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(control_snapshot["projects"][0]["project_id"], "proj-dispatch")
            self.assertEqual(len(control_snapshot["agents"]), 3)
            self.assertEqual(len(control_snapshot["branches"]), 3)
            self.assertEqual(len(control_snapshot["events"]), 3)

    def test_bootstrap_output_feeds_dispatch_planner(self) -> None:
        registry, health, ledger = self.make_router_inputs()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "bootstrapped_state.json"
            args = argparse.Namespace(
                output=output_path,
                project_id="proj-bootstrap",
                title="Bootstrap Project",
                objective="Bootstrap and dispatch a simple competitive stage",
                workspace_root="/repo/bootstrap",
                cwd="/repo/bootstrap",
                machine_id="dev-intern-02",
                host="local",
                remote_home="/dev_vepfs/rc_wu",
                remote_binary_store="/dev_vepfs/rc_wu/bin/codex",
                remote_run_root="/dev_vepfs/rc_wu/codex_subagents",
                sandbox="danger-full-access",
                approval="never",
                search=True,
                skip_install=True,
                add_dir=["/repo/bootstrap"],
                stage_id="bootstrap-stage",
                competition_id="",
                parent_node_id="root-parent",
                parent_role="supervisor",
                parent_label="Bootstrap Root",
                task_category="builder",
                difficulty="high",
                parent_score=0.8,
                candidate_count=2,
                dispatch_run_id="",
                branch_prefix="",
                agent_group=[],
                prompt_file="",
                prompt_text="Bootstrap prompt.",
                token_budget=30000,
                usd_budget=10.0,
                wall_time_budget_s=3600.0,
                child_token_budget=8000,
                child_usd_budget=3.0,
                child_wall_time_budget_s=1200.0,
            )
            state = BOOTSTRAP_MODULE.build_state(args)
            output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            plan = DISPATCH_MODULE.build_dispatch_plan(
                state,
                registry=registry,
                health_snapshot=health,
                ledger=ledger,
                state_path=output_path,
            )

        self.assertEqual(plan["projectId"], "proj-bootstrap")
        self.assertEqual(plan["stagePlans"][0]["candidate_count"], 2)
        self.assertEqual(len(plan["stagePlans"][0]["candidates"]), 2)
        for candidate in plan["stagePlans"][0]["candidates"]:
            self.assertTrue(candidate["candidate_run_id"].startswith("proj-bootstrap-bootstrap-stage"))
            self.assertIn(candidate["agent_group"]["agentGroupId"], {"builder", "builder-critic"})


if __name__ == "__main__":
    unittest.main()
