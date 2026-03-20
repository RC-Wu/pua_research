from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a final-summary remote Codex subagent prompt.")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--history-path", action="append", default=[])
    parser.add_argument("--output-summary-path", required=True)
    parser.add_argument("--required-section", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    return parser


def bullet_lines(items: list[str], fallback: str) -> list[str]:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        values = [fallback]
    return [f"- {item}" for item in values]


def render_prompt(args: argparse.Namespace) -> str:
    lines: list[str] = [
        "# Final Summary",
        "",
        f"Work only in `{args.cwd}`.",
        "",
        "Read these history paths first:",
        "",
    ]
    lines.extend(bullet_lines(args.history_path, "No explicit history paths were provided."))
    lines.extend(
        [
            "",
            f"Then write one markdown summary to `{args.output_summary_path}`.",
            "",
            "The report must include these sections:",
            "",
        ]
    )
    lines.extend(bullet_lines(args.required_section, "Final outcome"))
    lines.extend(
        [
            "",
            "If anything is incomplete, say exactly what is incomplete and why.",
        ]
    )
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
