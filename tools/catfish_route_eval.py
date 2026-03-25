from __future__ import annotations

import argparse
import json
from pathlib import Path

from catfish_route_core import (
    DEFAULT_HEALTH_PATH,
    DEFAULT_LEDGER_PATH,
    DEFAULT_REGISTRY_PATH,
    build_health_report,
    load_router_inputs,
    select_provider_route,
)


def add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--health", type=Path, default=DEFAULT_HEALTH_PATH)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CatfishResearch provider routing and health.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Render the current provider health summary.")
    add_common_paths(health_parser)

    eval_parser = subparsers.add_parser("evaluate", help="Choose the current Catfish provider route.")
    add_common_paths(eval_parser)
    eval_parser.add_argument("--machine", default="dev-intern-02")
    eval_parser.add_argument("--task-category", default="research")
    eval_parser.add_argument("--difficulty", default="medium")
    eval_parser.add_argument("--parent-score", type=float, default=0.5)
    eval_parser.add_argument("--reasoning-tier", default="")
    eval_parser.add_argument("--model", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    registry, health_snapshot, ledger = load_router_inputs(args.registry, args.health, args.ledger)

    if args.command == "health":
        payload = build_health_report(registry, health_snapshot)
    else:
        payload = select_provider_route(
            registry,
            health_snapshot,
            ledger,
            machine_id=args.machine,
            task_category=args.task_category,
            difficulty=args.difficulty,
            parent_score=args.parent_score,
            requested_tier=args.reasoning_tier or None,
            requested_model=args.model or None,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
