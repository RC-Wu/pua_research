from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
APP_ROOT = REPO_ROOT / "apps" / "catfish-control-center"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from catfish_control_center.models import ModuleScoutCandidate, ModuleScoutContract  # noqa: E402
from catfish_control_center.runtime import evaluate_module_scout_candidate  # noqa: E402


DEFAULT_ALLOWLIST_MANIFEST = REPO_ROOT / "assets" / "external_repos" / "catfish_module_scout_manifest.example.json"
DEFAULT_SCOUT_STATE_NAME = "self_optimization.json"
DEFAULT_SCOUT_PLAN_NAME = "module_scout_run.json"


@dataclass
class MaterializedInstall:
    candidate_id: str
    install_root: str
    status: str
    network_attempted: bool
    source_url: str
    summary: str
    artifacts: list[str]
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scout and safely materialize Catfish external modules.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Evaluate current self-optimization module-scout state.")
    scan.add_argument("--state-root", type=Path, required=True)
    scan.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST_MANIFEST)
    scan.add_argument("--write", action="store_true", help="Write the normalized scout state back to state-root.")
    scan.add_argument("--output", type=Path, default=None)

    install = subparsers.add_parser("install", help="Materialize a bounded install attempt for one candidate.")
    install.add_argument("--state-root", type=Path, required=True)
    install.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST_MANIFEST)
    install.add_argument("--candidate-id", required=True)
    install.add_argument("--scratch-root", type=Path, required=True)
    install.add_argument("--allow-network", action="store_true")
    install.add_argument("--materialize-skill", action="store_true")
    install.add_argument("--output", type=Path, default=None)
    return parser


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else dict(default or {})


def load_scout_state(state_root: Path) -> dict[str, Any]:
    return load_json(state_root / "system" / DEFAULT_SCOUT_STATE_NAME, default={})


def write_scout_state(state_root: Path, payload: dict[str, Any]) -> None:
    system_root = state_root / "system"
    system_root.mkdir(parents=True, exist_ok=True)
    (system_root / DEFAULT_SCOUT_STATE_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_allowlist_manifest(path: Path) -> dict[str, Any]:
    return load_json(path, default={"allowed_items": [], "blocked_items": [], "policy": {}})


def build_scout_contracts(state: dict[str, Any], allowlist_manifest: dict[str, Any]) -> list[ModuleScoutContract]:
    contracts = [ModuleScoutContract.from_dict(item) for item in state.get("module_scout_contracts", [])]
    if contracts:
        return contracts

    allowed_items = allowlist_manifest.get("allowed_items", [])
    allowed_source_ids = tuple(str(item.get("source_id", "")) for item in allowed_items if item.get("source_id"))
    safe_modes = tuple(allowlist_manifest.get("policy", {}).get("allowed_install_modes", ["clone-reference", "convert-to-skill"]))
    return [
        ModuleScoutContract(
            contract_id="scout-contract-allowlist",
            module_id="self-optimization/scout",
            module_label="Module Scout",
            capability="implementation",
            allowlist_manifest=str(DEFAULT_ALLOWLIST_MANIFEST),
            allowed_source_ids=allowed_source_ids,
            safe_install_modes=safe_modes,
            max_candidates=int(allowlist_manifest.get("policy", {}).get("max_candidates", 4)),
            require_explicit_allowlist=bool(allowlist_manifest.get("policy", {}).get("require_explicit_allowlist", True)),
            require_human_review=True,
            created_at=allowlist_manifest.get("generated_at", ""),
            summary="Allowlist-driven fallback contract synthesized from manifest.",
        )
    ]


def build_candidate_catalog(
    state: dict[str, Any],
    allowlist_manifest: dict[str, Any],
) -> list[ModuleScoutCandidate]:
    contracts = build_scout_contracts(state, allowlist_manifest)
    existing = [ModuleScoutCandidate.from_dict(item) for item in state.get("module_scout_candidates", [])]
    catalog: dict[str, ModuleScoutCandidate] = {candidate.candidate_id: candidate for candidate in existing}
    allowed_items = allowlist_manifest.get("allowed_items", [])

    for item in allowed_items:
        source_id = str(item.get("source_id", "")).strip()
        if not source_id:
            continue
        repo = str(item.get("repo", "")).strip()
        source_url = f"https://github.com/{repo}" if repo else ""
        preferred_action = str(item.get("preferred_action", "clone-reference")).strip()
        capability = _capability_for_item(item, contracts)
        candidate_id = f"candidate:{source_id}"
        if candidate_id in catalog:
            continue
        catalog[candidate_id] = ModuleScoutCandidate(
            candidate_id=candidate_id,
            contract_id=contracts[0].contract_id,
            source_kind="repo",
            source_id=source_id,
            title=repo.split("/")[-1] if repo else source_id,
            capability=capability,
            source_url=source_url,
            install_policy=preferred_action,
            conversion_target="skill" if preferred_action == "convert-to-skill" else "",
            summary=str(item.get("reason", "")) or "Allowlisted candidate discovered for Catfish self-optimization.",
            metadata={
                "allowed_for": list(item.get("allowed_for", [])),
                "preferred_action": preferred_action,
                "allowlist_reason": str(item.get("reason", "")),
            },
        )

    evaluated: list[ModuleScoutCandidate] = []
    for candidate in catalog.values():
        contract = _contract_for_candidate(contracts, candidate)
        evaluated.append(
            evaluate_module_scout_candidate(
                contract,
                candidate,
                allowlisted_source_ids=set(contract.allowed_source_ids),
            )
        )
    return sorted(evaluated, key=lambda item: (-item.total_score, item.decision, item.candidate_id))


def build_scan_report(state_root: Path, allowlist_manifest_path: Path) -> dict[str, Any]:
    scout_state = load_scout_state(state_root)
    allowlist_manifest = load_allowlist_manifest(allowlist_manifest_path)
    contracts = build_scout_contracts(scout_state, allowlist_manifest)
    candidates = build_candidate_catalog(scout_state, allowlist_manifest)
    report = {
        "schemaVersion": "catfish.module-scout-run.v1",
        "generatedAt": _utc_now(),
        "stateRoot": str(state_root),
        "allowlistManifest": str(allowlist_manifest_path),
        "contracts": [contract.to_dict() for contract in contracts],
        "candidates": [candidate.to_dict() for candidate in candidates],
        "bestCandidateId": candidates[0].candidate_id if candidates else "",
        "queue": list(scout_state.get("queue", [])),
        "summary": _summarize_candidates(candidates),
    }
    return report


def persist_scan_state(state_root: Path, report: dict[str, Any]) -> None:
    scout_state = load_scout_state(state_root)
    scout_state["updatedAt"] = report["generatedAt"]
    scout_state["module_scout_candidates"] = list(report["candidates"])
    scout_state["module_scout_contracts"] = list(report["contracts"])
    scout_state.setdefault("module_scout_runs", [])
    scout_state["module_scout_runs"].append(
        {
            "run_id": f"scan-{report['generatedAt']}",
            "status": "completed",
            "best_candidate_id": report["bestCandidateId"],
            "generated_at": report["generatedAt"],
            "summary": report["summary"]["summary_line"],
        }
    )
    write_scout_state(state_root, scout_state)


def install_candidate(
    state_root: Path,
    allowlist_manifest_path: Path,
    candidate_id: str,
    scratch_root: Path,
    *,
    allow_network: bool,
    materialize_skill: bool,
) -> MaterializedInstall:
    scout_state = load_scout_state(state_root)
    allowlist_manifest = load_allowlist_manifest(allowlist_manifest_path)
    candidates = build_candidate_catalog(scout_state, allowlist_manifest)
    candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise ValueError(f"Unknown candidate_id: {candidate_id}")
    if candidate.decision not in {"attempt-install", "attempt-convert-to-skill"}:
        raise ValueError(f"Candidate {candidate_id} is not eligible for installation: {candidate.decision}")

    scratch_root.mkdir(parents=True, exist_ok=True)
    install_root = scratch_root / _slug(candidate.candidate_id)
    install_root.mkdir(parents=True, exist_ok=True)

    artifacts: list[str] = []
    source_clone_root = install_root / "source"
    network_attempted = False
    error = ""
    if allow_network and candidate.source_url and candidate.install_policy == "clone-reference":
        network_attempted = True
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--no-checkout",
                candidate.source_url,
                str(source_clone_root),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode == 0:
            artifacts.append(str(source_clone_root))
        else:
            error = (result.stderr or result.stdout or "git clone failed").strip()

    if materialize_skill or candidate.conversion_target == "skill":
        skill_root = install_root / "skill"
        skill_root.mkdir(parents=True, exist_ok=True)
        (skill_root / "SKILL.md").write_text(
            _skill_markdown(candidate),
            encoding="utf-8",
        )
        artifacts.append(str(skill_root / "SKILL.md"))

    (install_root / "install_plan.json").write_text(
        json.dumps(
            {
                "candidate": candidate.to_dict(),
                "allow_network": allow_network,
                "materialize_skill": materialize_skill,
                "source_clone_root": str(source_clone_root),
                "artifacts": artifacts,
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts.append(str(install_root / "install_plan.json"))
    status = "installed" if not error else "partial"
    return MaterializedInstall(
        candidate_id=candidate.candidate_id,
        install_root=str(install_root),
        status=status,
        network_attempted=network_attempted,
        source_url=candidate.source_url,
        summary=candidate.summary or "Bounded module-scout install attempt.",
        artifacts=artifacts,
        error=error,
    )


def write_install_report(state_root: Path, install: MaterializedInstall) -> None:
    scout_state = load_scout_state(state_root)
    scout_state.setdefault("module_scout_runs", [])
    scout_state["module_scout_runs"].append(
        {
            "run_id": f"install-{install.candidate_id}",
            "status": install.status,
            "install_root": install.install_root,
            "source_url": install.source_url,
            "generated_at": _utc_now(),
            "summary": install.summary,
        }
    )
    write_scout_state(state_root, scout_state)


def _summarize_candidates(candidates: list[ModuleScoutCandidate]) -> dict[str, Any]:
    if not candidates:
        return {"summary_line": "No module-scout candidates available.", "eligible": 0, "blocked": 0}
    eligible = [candidate for candidate in candidates if candidate.decision in {"attempt-install", "attempt-convert-to-skill"}]
    blocked = [candidate for candidate in candidates if candidate.decision == "reject"]
    top = candidates[0]
    return {
        "summary_line": f"Top candidate {top.candidate_id} scored {top.total_score:.2f} with decision {top.decision}.",
        "eligible": len(eligible),
        "blocked": len(blocked),
    }


def _skill_markdown(candidate: ModuleScoutCandidate) -> str:
    lines = [
        f"# {candidate.title or candidate.candidate_id}",
        "",
        "This skill bundle was materialized by CatfishResearch module scout.",
        "",
        f"- Candidate: `{candidate.candidate_id}`",
        f"- Source: `{candidate.source_url or candidate.source_id}`",
        f"- Capability: `{candidate.capability}`",
        f"- Install policy: `{candidate.install_policy}`",
        f"- Decision: `{candidate.decision}`",
        "",
        "Keep the bundle bounded and review it before any live use.",
    ]
    return "\n".join(lines) + "\n"


def _capability_for_item(item: dict[str, Any], contracts: list[ModuleScoutContract]) -> str:
    allowed_for = [str(entry).strip() for entry in item.get("allowed_for", []) if str(entry).strip()]
    if not allowed_for:
        return contracts[0].capability if contracts else "implementation"
    for contract in contracts:
        if contract.capability in allowed_for:
            return contract.capability
    return allowed_for[0]


def _contract_for_candidate(contracts: list[ModuleScoutContract], candidate: ModuleScoutCandidate) -> ModuleScoutContract:
    for contract in contracts:
        if contract.contract_id == candidate.contract_id:
            return contract
    return contracts[0]


def _slug(value: str) -> str:
    text = value.strip().lower()
    chars: list[str] = []
    last_sep = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            last_sep = False
        elif char in {"-", "_", ".", ":"} and not last_sep:
            chars.append("-")
            last_sep = True
    result = "".join(chars).strip("-")
    return result or "candidate"


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        report = build_scan_report(args.state_root, args.allowlist)
        if args.write:
            persist_scan_state(args.state_root, report)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    install = install_candidate(
        args.state_root,
        args.allowlist,
        args.candidate_id,
        args.scratch_root,
        allow_network=args.allow_network,
        materialize_skill=args.materialize_skill,
    )
    write_install_report(args.state_root, install)
    payload = install.to_dict()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
