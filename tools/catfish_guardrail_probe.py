#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "apps" / "catfish-control-center"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from catfish_control_center.guardrails import build_guardrail_state  # noqa: E402
from catfish_control_center.runtime import DEFAULT_GUARDRAIL_POLICY_PATH, load_live_state  # noqa: E402
from catfish_control_center.supervisor import build_supervisor_state  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=path.name, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def directory_usage_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        dirs[:] = [item for item in dirs if not (root_path / item).is_symlink()]
        for filename in files:
            file_path = root_path / filename
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def resolve_within_state_root(state_root: Path, candidate: Path) -> Path:
    state_root_resolved = state_root.resolve()
    candidate_resolved = candidate.resolve()
    if candidate_resolved == state_root_resolved or state_root_resolved in candidate_resolved.parents:
        return candidate_resolved
    raise ValueError(f"Path {candidate} is outside state root {state_root}")


def build_runtime_metrics(*, state_root: Path, root_dir: Path, vepfs_root: Path, observed_at: str, cpu_percent: float) -> dict[str, Any]:
    return {
        "observedAt": observed_at,
        "stateRoot": str(state_root.resolve()),
        "rootDirPath": str(root_dir.resolve()),
        "vePfsPath": str(vepfs_root.resolve()),
        "rootDirUsageBytes": directory_usage_bytes(root_dir),
        "vePfsUsageBytes": directory_usage_bytes(vepfs_root),
        "cpuPercent": float(cpu_percent),
    }


def build_probe_payload(
    *,
    state_root: Path,
    root_dir: Path,
    vepfs_root: Path,
    observed_at: str,
    cpu_percent: float,
) -> dict[str, Any]:
    system_root = state_root / "system"
    policy_payload = load_json(system_root / "catfish_runtime_policy.json", load_json(DEFAULT_GUARDRAIL_POLICY_PATH, {}))
    resource_manager_state = load_json(system_root / "resource_manager_state.json", {})
    agentdoc_state = load_json(system_root / "agentdoc_state.json", {})
    supervisor_payload = load_json(system_root / "supervisor_state.json", {})
    snapshot = load_live_state(state_root)
    runtime_metrics = build_runtime_metrics(
        state_root=state_root,
        root_dir=root_dir,
        vepfs_root=vepfs_root,
        observed_at=observed_at,
        cpu_percent=cpu_percent,
    )
    guardrail_state = build_guardrail_state(
        policy_payload=policy_payload,
        runtime_metrics=runtime_metrics,
        resource_manager_state=resource_manager_state,
        agentdoc_state=agentdoc_state,
        agents=list(snapshot.agents),
    )
    supervisor_state = build_supervisor_state(
        policy_payload=policy_payload,
        supervisor_payload=supervisor_payload,
        guardrail_state=guardrail_state,
    )
    plan = build_plan(guardrail_state=guardrail_state, supervisor_state=supervisor_state)
    return {
        "mode": "dry-run",
        "state_root": str(state_root.resolve()),
        "runtime_metrics": runtime_metrics,
        "guardrail_state": guardrail_state.to_dict() if guardrail_state else None,
        "supervisor_state": supervisor_state.to_dict() if supervisor_state else None,
        "plan": plan,
    }


def build_plan(
    *,
    guardrail_state,
    supervisor_state,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    reasons: list[str] = []
    decision = "hold"

    if guardrail_state is not None and guardrail_state.overall_status == "blocked":
        decision = "deny"
        reasons.extend(check.summary for check in guardrail_state.checks if check.blocking)
        actions.append(
            {
                "kind": "deny",
                "summary": "Guardrail blocked. Keep the control plane in file-backed dry-run mode.",
            }
        )

    if supervisor_state is not None:
        if supervisor_state.restart_intent == "restart-required":
            if supervisor_state.restart_allowed:
                if decision != "deny":
                    decision = "restart-requested"
                actions.append(
                    {
                        "kind": "restart-request",
                        "component": supervisor_state.restart_command,
                        "summary": supervisor_state.restart_reason,
                    }
                )
            else:
                decision = "restart-blocked"
                reasons.append(supervisor_state.restart_reason)
                actions.append(
                    {
                        "kind": "restart-denied",
                        "summary": supervisor_state.restart_reason,
                    }
                )

    if not actions:
        actions.append({"kind": "hold", "summary": "No restart or deny action required."})

    return {
        "decision": decision,
        "reasons": reasons,
        "actions": actions,
        "applyable": decision in {"restart-requested", "hold"},
    }


def maybe_write_outputs(*, state_root: Path, payload: dict[str, Any], write_runtime_metrics: bool, write_supervisor_state: bool) -> list[str]:
    written: list[str] = []
    system_root = state_root / "system"
    if write_runtime_metrics:
        path = resolve_within_state_root(state_root, system_root / "runtime_metrics.json")
        write_json_atomic(path, payload["runtime_metrics"])
        written.append(str(path))
    if write_supervisor_state and payload.get("supervisor_state") is not None:
        path = resolve_within_state_root(state_root, system_root / "supervisor_state.json")
        write_json_atomic(path, payload["supervisor_state"])
        written.append(str(path))
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Catfish guardrails and supervisor state.")
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--root-dir", type=Path)
    parser.add_argument("--vepfs-root", type=Path)
    parser.add_argument("--observed-at", default=utc_now())
    parser.add_argument("--cpu-percent", type=float, default=0.0)
    parser.add_argument("--write-runtime-metrics", action="store_true")
    parser.add_argument("--write-supervisor-state", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_root = args.state_root.resolve()
    root_dir = (args.root_dir or state_root).resolve()
    vepfs_root = (args.vepfs_root or state_root).resolve()

    payload = build_probe_payload(
        state_root=state_root,
        root_dir=root_dir,
        vepfs_root=vepfs_root,
        observed_at=args.observed_at,
        cpu_percent=args.cpu_percent,
    )
    written = maybe_write_outputs(
        state_root=state_root,
        payload=payload,
        write_runtime_metrics=args.write_runtime_metrics,
        write_supervisor_state=args.write_supervisor_state,
    )
    payload["mode"] = "write" if written else "dry-run"
    payload["written_files"] = written
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
