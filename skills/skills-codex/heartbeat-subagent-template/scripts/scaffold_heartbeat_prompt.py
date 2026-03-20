from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a heartbeat-style remote Codex subagent prompt.")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--note-path", required=True)
    parser.add_argument("--interval-minutes", type=int, default=30)
    parser.add_argument("--task-line", action="append", default=[])
    parser.add_argument("--watch-path", action="append", default=[])
    parser.add_argument("--watch-process", action="append", default=[])
    parser.add_argument("--intervention-rule", action="append", default=[])
    parser.add_argument("--stop-condition", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    return parser


def bullet_lines(items: list[str], fallback: str) -> list[str]:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        values = [fallback]
    return [f"- {item}" for item in values]


def render_prompt(args: argparse.Namespace) -> str:
    lines: list[str] = [
        "# Heartbeat Monitor",
        "",
        f"Work only in `{args.cwd}`.",
        "",
        "This is a long-running heartbeat monitor for a remote task. Stay in a loop until the stop conditions are met or until explicitly stopped.",
        "",
        f"Every {args.interval_minutes} minutes:",
        "",
    ]
    lines.extend(bullet_lines(args.task_line, "Inspect the current task state and update the note."))
    lines.extend(
        [
            "",
            "Always inspect these paths when relevant:",
            "",
        ]
    )
    lines.extend(bullet_lines(args.watch_path, "No explicit watch paths were provided."))
    lines.extend(
        [
            "",
            "Always inspect these processes or command fragments when relevant:",
            "",
        ]
    )
    lines.extend(bullet_lines(args.watch_process, "No explicit watch processes were provided."))
    lines.extend(
        [
            "",
            "Before any restart or repair, follow these intervention rules:",
            "",
        ]
    )
    lines.extend(
        bullet_lines(
            args.intervention_rule,
            "Only restart or relaunch a worker when the failure mode is clear and no equivalent worker is already running.",
        )
    )
    lines.extend(
        [
            "",
            f"Append one timestamped monitoring section to `{args.note_path}` after each pass.",
            "",
            "Each section should include:",
            "- current UTC time and local derived time if helpful",
            "- current status summary",
            "- exact PIDs or confirmation that no relevant process is alive",
            "- key file counts or existence checks",
            "- any intervention taken, with exact commands and paths",
            "- the next expected milestone or blocker",
            "",
            "Stop when all of these are true:",
            "",
        ]
    )
    lines.extend(bullet_lines(args.stop_condition, "The target task is complete and the final note clearly records the completion state."))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_prompt(args), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
