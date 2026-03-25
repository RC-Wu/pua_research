from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "catfish_runtime.py"
SPEC = importlib.util.spec_from_file_location("catfish_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CatfishRuntimeTest(unittest.TestCase):
    def build_runtime(self) -> object:
        return MODULE.CatfishRuntime()

    def register_project_graph(self, runtime: object) -> None:
        runtime.register_project(
            {
                "project_id": "proj-alpha",
                "title": "Alpha",
                "objective": "Rank child agents under a parent selector",
                "resource_budget": {
                    "token_budget": 50000,
                    "usd_budget": 25.0,
                    "wall_time_budget_s": 7200,
                    "max_parallel_children": 2,
                },
                "default_provider_assignment": {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "reasoning_effort": "high",
                    "capabilities": ["planning", "review"],
                },
            }
        )
        runtime.upsert_agent_node(
            "proj-alpha",
            {
                "node_id": "root-parent",
                "role": "supervisor",
                "label": "Root Parent",
                "resource_budget": {"token_budget": 20000},
                "provider_assignment": {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "reasoning_effort": "high",
                },
            },
        )
        runtime.upsert_agent_node(
            "proj-alpha",
            {
                "node_id": "child-a",
                "role": "coder",
                "label": "Child A",
                "parent_node_id": "root-parent",
                "resource_budget": {"token_budget": 10000, "max_parallel_children": 0},
                "provider_assignment": {
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                    "reasoning_effort": "medium",
                },
            },
        )
        runtime.upsert_agent_node(
            "proj-alpha",
            {
                "node_id": "child-b",
                "role": "critic",
                "label": "Child B",
                "parent_node_id": "root-parent",
                "resource_budget": {"token_budget": 10000, "max_parallel_children": 0},
                "provider_assignment": {
                    "provider": "anthropic",
                    "model": "claude-sonnet",
                    "reasoning_effort": "medium",
                },
            },
        )
        runtime.define_competition(
            "proj-alpha",
            {
                "competition_id": "comp-1",
                "parent_node_id": "root-parent",
                "candidate_node_ids": ["child-a", "child-b"],
            },
        )

    def test_snapshot_captures_project_graph(self) -> None:
        runtime = self.build_runtime()
        self.register_project_graph(runtime)

        snapshot = runtime.snapshot(project_id="proj-alpha")
        project_snapshot = snapshot["projects"]["proj-alpha"]

        self.assertEqual(project_snapshot["root_node_ids"], ["root-parent"])
        self.assertEqual(project_snapshot["nodes"]["root-parent"]["child_node_ids"], ["child-a", "child-b"])
        self.assertEqual(
            project_snapshot["project"]["default_provider_assignment"]["model"],
            "gpt-5.4",
        )
        self.assertEqual(
            project_snapshot["competitions"]["comp-1"]["scoring_policy"],
            MODULE.PARENT_ONLY_SCORING,
        )

    def test_parent_verdict_updates_scores_and_capabilities(self) -> None:
        runtime = self.build_runtime()
        self.register_project_graph(runtime)
        runtime.record_candidate_run(
            "proj-alpha",
            {
                "run_id": "run-a1",
                "competition_id": "comp-1",
                "node_id": "child-a",
                "submitted_at": "2026-03-25T00:00:00Z",
                "resource_usage": {
                    "prompt_tokens": 1200,
                    "completion_tokens": 400,
                    "cost_usd": 0.8,
                    "wall_time_s": 18.0,
                },
            },
        )
        runtime.record_candidate_run(
            "proj-alpha",
            {
                "run_id": "run-b1",
                "competition_id": "comp-1",
                "node_id": "child-b",
                "submitted_at": "2026-03-25T00:01:00Z",
                "resource_usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 300,
                    "cost_usd": 0.6,
                    "wall_time_s": 16.0,
                },
            },
        )

        runtime.apply_parent_verdict(
            "proj-alpha",
            {
                "verdict_id": "verdict-1",
                "competition_id": "comp-1",
                "parent_node_id": "root-parent",
                "score_by_run_id": {"run-a1": 0.91, "run-b1": 0.72},
                "capability_updates": [
                    {
                        "node_id": "child-a",
                        "capability": "coding",
                        "score": 0.91,
                        "summary": "Parent preferred stronger patch quality",
                    },
                    {
                        "node_id": "child-b",
                        "capability": "critique",
                        "score": 0.72,
                        "summary": "Useful review depth but weaker final answer",
                    },
                ],
            },
        )

        snapshot = runtime.snapshot(project_id="proj-alpha")
        run_snapshot = snapshot["projects"]["proj-alpha"]["runs"]
        verdict_snapshot = snapshot["projects"]["proj-alpha"]["verdicts"]["verdict-1"]
        child_a = snapshot["projects"]["proj-alpha"]["nodes"]["child-a"]

        self.assertEqual(run_snapshot["run-a1"]["parent_score"], 0.91)
        self.assertEqual(run_snapshot["run-a1"]["verdict_id"], "verdict-1")
        self.assertEqual(verdict_snapshot["winner_run_id"], "run-a1")
        self.assertEqual(child_a["capability_summaries"]["coding"]["sample_count"], 1)
        self.assertAlmostEqual(child_a["capability_summaries"]["coding"]["average_score"], 0.91)

    def test_parent_only_scoring_rejects_non_parent_verdict(self) -> None:
        runtime = self.build_runtime()
        self.register_project_graph(runtime)
        runtime.record_candidate_run(
            "proj-alpha",
            {
                "run_id": "run-a1",
                "competition_id": "comp-1",
                "node_id": "child-a",
                "submitted_at": "2026-03-25T00:00:00Z",
            },
        )

        with self.assertRaisesRegex(ValueError, "does not match competition parent"):
            runtime.apply_parent_verdict(
                "proj-alpha",
                {
                    "verdict_id": "verdict-bad",
                    "competition_id": "comp-1",
                    "parent_node_id": "child-b",
                    "score_by_run_id": {"run-a1": 0.2},
                },
            )

    def test_cli_emits_snapshot_from_operations(self) -> None:
        operations = [
            {
                "op": "register_project",
                "project": {
                    "project_id": "proj-cli",
                    "title": "CLI Project",
                    "resource_budget": {"token_budget": 1000},
                },
            },
            {
                "op": "upsert_agent_node",
                "project_id": "proj-cli",
                "node": {
                    "node_id": "root",
                    "role": "supervisor",
                    "label": "Root",
                },
            },
            {
                "op": "upsert_agent_node",
                "project_id": "proj-cli",
                "node": {
                    "node_id": "child",
                    "role": "coder",
                    "label": "Child",
                    "parent_node_id": "root",
                },
            },
            {
                "op": "define_competition",
                "project_id": "proj-cli",
                "competition": {
                    "competition_id": "comp-cli",
                    "parent_node_id": "root",
                    "candidate_node_ids": ["child"],
                },
            },
            {
                "op": "record_candidate_run",
                "project_id": "proj-cli",
                "run": {
                    "run_id": "run-cli",
                    "competition_id": "comp-cli",
                    "node_id": "child",
                    "submitted_at": "2026-03-25T00:00:00Z",
                },
            },
            {
                "op": "apply_parent_verdict",
                "project_id": "proj-cli",
                "verdict": {
                    "verdict_id": "verdict-cli",
                    "competition_id": "comp-cli",
                    "parent_node_id": "root",
                    "score_by_run_id": {"run-cli": 0.88},
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            ops_path = Path(temp_dir) / "ops.json"
            ops_path.write_text(json.dumps(operations), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = MODULE.main(["--ops", str(ops_path), "--project-id", "proj-cli"])

        snapshot = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(snapshot["projects"]["proj-cli"]["runs"]["run-cli"]["parent_score"], 0.88)


if __name__ == "__main__":
    unittest.main()
