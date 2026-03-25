from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def ensure_string_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if value.strip()]


def build_agent_groups(raw_groups: list[str]) -> list[dict[str, object]]:
    if not raw_groups:
        return [
            {"agentGroupId": "builder", "label": "Builder", "roles": ["worker"]},
            {
                "agentGroupId": "builder-critic",
                "label": "Builder + Critic",
                "roles": ["worker", "reviewer"],
                "scoreBias": 0.02,
                "promptPrefix": "Include a short self-critique before your final summary.",
            },
        ]

    groups: list[dict[str, object]] = []
    for entry in raw_groups:
        parts = [part.strip() for part in entry.split(":", 2)]
        agent_group_id = parts[0]
        label = parts[1] if len(parts) > 1 and parts[1] else agent_group_id.replace("-", " ").title()
        roles = [role.strip() for role in parts[2].split(",")] if len(parts) > 2 and parts[2] else ["worker"]
        groups.append(
            {
                "agentGroupId": agent_group_id,
                "label": label,
                "roles": [role for role in roles if role],
            }
        )
    return groups


def build_state(args: argparse.Namespace) -> dict[str, object]:
    project_id = args.project_id
    stage_id = args.stage_id
    parent_node_id = args.parent_node_id
    agent_groups = build_agent_groups(args.agent_group)
    prompt_parts: list[str] = []
    if args.prompt_file:
        prompt_parts.append(Path(args.prompt_file).read_text(encoding="utf-8"))
    if args.prompt_text:
        prompt_parts.append(args.prompt_text)
    prompt_text = "\n\n".join(part.strip() for part in prompt_parts if part.strip()).strip()
    if not prompt_text:
        prompt_text = "Implement the requested stage and stop after one complete pass."

    return {
        "schemaVersion": "catfish.dispatch-state.v1",
        "project": {
            "projectId": project_id,
            "title": args.title or project_id,
            "objective": args.objective,
            "workspaceRoot": args.workspace_root,
            "status": "bootstrap",
            "defaultMachineId": args.machine_id,
            "branchPrefix": args.branch_prefix or f"{project_id}/{stage_id}",
            "launchDefaults": {
                "host": args.host,
                "remoteHome": args.remote_home,
                "remoteBinaryStore": args.remote_binary_store,
                "remoteRunRoot": args.remote_run_root,
                "sandbox": args.sandbox,
                "approval": args.approval,
                "search": args.search,
                "skipInstall": args.skip_install,
                "addDir": ensure_string_list(args.add_dir),
            },
            "agentGroups": agent_groups,
        },
        "runtime": {
            "projectId": project_id,
            "operations": [
                {
                    "op": "register_project",
                    "project": {
                        "project_id": project_id,
                        "title": args.title or project_id,
                        "objective": args.objective,
                        "status": "active",
                        "resource_budget": {
                            "token_budget": args.token_budget,
                            "usd_budget": args.usd_budget,
                            "wall_time_budget_s": args.wall_time_budget_s,
                            "max_parallel_children": args.candidate_count,
                        },
                    },
                },
                {
                    "op": "upsert_agent_node",
                    "project_id": project_id,
                    "node": {
                        "node_id": parent_node_id,
                        "role": args.parent_role,
                        "label": args.parent_label or parent_node_id,
                        "status": "active",
                        "resource_budget": {
                            "token_budget": args.token_budget,
                            "max_parallel_children": args.candidate_count,
                        },
                        "metadata": {
                            "workspace_root": args.workspace_root,
                            "bootstrapped_by": "catfish_project_bootstrap",
                        },
                    },
                },
            ],
        },
        "stages": [
            {
                "stageId": stage_id,
                "competitionId": args.competition_id or f"{stage_id}:competition",
                "parentNodeId": parent_node_id,
                "taskCategory": args.task_category,
                "difficulty": args.difficulty,
                "parentScore": args.parent_score,
                "candidateCount": args.candidate_count,
                "cwd": args.cwd or args.workspace_root,
                "branchPrefix": args.branch_prefix or f"{project_id}/{stage_id}",
                "dispatchRunId": args.dispatch_run_id or f"{project_id}-{stage_id}",
                "promptText": prompt_text,
                "agentGroups": agent_groups,
                "resourceBudget": {
                    "token_budget": args.child_token_budget,
                    "usd_budget": args.child_usd_budget,
                    "wall_time_budget_s": args.child_wall_time_budget_s,
                    "max_parallel_children": 0,
                },
            }
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap a Catfish dispatch-state JSON file.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--objective", default="")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--machine-id", default="dev-intern-02")
    parser.add_argument("--host", default="local")
    parser.add_argument("--remote-home", default="/dev_vepfs/rc_wu")
    parser.add_argument("--remote-binary-store", default="/dev_vepfs/rc_wu/bin/codex")
    parser.add_argument("--remote-run-root", default="/dev_vepfs/rc_wu/codex_subagents")
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--approval", default="never")
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--add-dir", action="append", default=[])
    parser.add_argument("--stage-id", default="stage-1")
    parser.add_argument("--competition-id", default="")
    parser.add_argument("--parent-node-id", default="root-parent")
    parser.add_argument("--parent-role", default="supervisor")
    parser.add_argument("--parent-label", default="")
    parser.add_argument("--task-category", default="builder")
    parser.add_argument("--difficulty", default="high")
    parser.add_argument("--parent-score", type=float, default=0.82)
    parser.add_argument("--candidate-count", type=int, default=3)
    parser.add_argument("--dispatch-run-id", default="")
    parser.add_argument("--branch-prefix", default="")
    parser.add_argument("--agent-group", action="append", default=[])
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--prompt-text", default="")
    parser.add_argument("--token-budget", type=int, default=50000)
    parser.add_argument("--usd-budget", type=float, default=20.0)
    parser.add_argument("--wall-time-budget-s", type=float, default=7200.0)
    parser.add_argument("--child-token-budget", type=int, default=12000)
    parser.add_argument("--child-usd-budget", type=float, default=6.0)
    parser.add_argument("--child-wall-time-budget-s", type=float, default=1800.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_state(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "projectId": args.project_id}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
