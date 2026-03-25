from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dashboard import render_view, view_to_dict
from .runtime import apply_route_preview, load_live_state, load_snapshot, merge_recent_events
from .storage import JsonLinesEventStore


VIEW_CHOICES = (
    "dashboard",
    "projects",
    "stage-competitions",
    "pending-reviews",
    "provider-status",
    "recent-launches",
    "capability-summaries",
    "diversity-metrics",
    "recent-events",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CatfishResearch live control-center CLI.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--snapshot",
        type=Path,
        help="Path to the materialized control snapshot JSON.",
    )
    source_group.add_argument(
        "--state-root",
        type=Path,
        help="Path to a Catfish state root with system/ and projects/ state files.",
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        help="Optional JSONL event log to merge into the loaded state at render time.",
    )
    parser.add_argument(
        "--event-limit",
        type=int,
        default=8,
        help="How many recent launches/events/capabilities to render in focused views.",
    )
    parser.add_argument(
        "--view",
        choices=VIEW_CHOICES,
        default="dashboard",
        help="Render the full dashboard or a focused operator view.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Render a text view or dump the selected view as JSON.",
    )
    parser.add_argument(
        "--control-plane-config",
        type=Path,
        help="Optional route-preview config that marks the currently selected provider profile.",
    )
    parser.add_argument("--machine", default="dev-intern-02")
    parser.add_argument("--task-kind", default="builder")
    parser.add_argument("--difficulty", default="medium")
    parser.add_argument("--profile", default="")
    parser.add_argument("--locked-profile", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.state_root:
        snapshot = load_live_state(args.state_root)
    else:
        snapshot = load_snapshot(args.snapshot)

    if args.events_file:
        event_store = JsonLinesEventStore(args.events_file)
        snapshot = merge_recent_events(snapshot, event_store.list_recent(limit=args.event_limit))

    if args.control_plane_config:
        snapshot = apply_route_preview(
            snapshot,
            config_path=args.control_plane_config,
            machine_id=args.machine,
            task_kind=args.task_kind,
            difficulty=args.difficulty,
            requested_profile=args.profile or None,
            locked_profile=args.locked_profile or None,
        )

    if args.format == "json":
        print(json.dumps(view_to_dict(snapshot, args.view, event_limit=args.event_limit), ensure_ascii=False, indent=2))
    else:
        print(render_view(snapshot, args.view, event_limit=args.event_limit))
    return 0
