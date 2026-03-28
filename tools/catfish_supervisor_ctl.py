#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from catfish_guardrail_probe import (  # noqa: E402
    resolve_within_state_root,
    write_json_atomic,
)


def load_plan(path: Path | None, plan_json: str | None) -> dict[str, Any]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    if plan_json is not None:
        return json.loads(plan_json)
    payload = sys.stdin.read().strip()
    if not payload:
        raise ValueError("A plan file, plan JSON, or stdin payload is required.")
    return json.loads(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply a Catfish supervisor plan in a file-backed way.")
    parser.add_argument("--state-root", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan-file", type=Path)
    source.add_argument("--plan-json")
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_root = args.state_root.resolve()
    plan = load_plan(args.plan_file, args.plan_json)

    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "decision": plan.get("plan", {}).get("decision", "hold"),
                    "applyable": plan.get("plan", {}).get("applyable", False),
                    "written_files": [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    written_files = []
    payloads = {
        "runtime_metrics": plan.get("runtime_metrics"),
        "supervisor_state": plan.get("supervisor_state"),
    }
    for key, value in payloads.items():
        if value is None:
            continue
        path = resolve_within_state_root(state_root, state_root / "system" / f"{key}.json")
        write_json_atomic(path, value)
        written_files.append(str(path))

    action_record = {
        "status": "applied",
        "decision": plan.get("plan", {}).get("decision", "hold"),
        "written_files": written_files,
    }
    write_json_atomic(resolve_within_state_root(state_root, state_root / "system" / "supervisor_action_plan.json"), action_record)
    written_files.append(str(state_root / "system" / "supervisor_action_plan.json"))
    print(json.dumps(action_record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
