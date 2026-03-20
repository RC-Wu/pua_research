from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def profile_issues(profile: dict[str, Any], machine_id: str) -> list[str]:
    issues: list[str] = []
    if not profile.get("enabled", True):
        issues.append("profile-disabled")
    if machine_id not in profile.get("machineIds", []):
        issues.append("machine-not-allowed")

    health = profile.get("health", {})
    available = bool(health.get("available", True))
    verified = bool(health.get("verified", True))
    health_issues = list(health.get("issues", []))
    if not available:
        issues.extend(health_issues or ["auth-unavailable"])
    elif not verified:
        issues.extend(health_issues or ["identity-unverified"])
    else:
        issues.extend(health_issues)

    credit = profile.get("credit", {})
    remaining = float(credit.get("remaining", 0.0))
    reserve_floor = float(credit.get("reserveFloor", 0.0))
    if remaining <= reserve_floor:
        issues.append(f"credit-below-reserve:{remaining}")

    return dedupe(issues)


def profile_score(profile: dict[str, Any]) -> float:
    credit = profile.get("credit", {})
    remaining = float(credit.get("remaining", 0.0))
    weight = max(float(profile.get("routingWeight", 1.0)), 0.01)
    return remaining * weight


def describe_candidate(candidate: dict[str, Any]) -> str:
    issues = candidate["issues"] or ["ok"]
    return f'{candidate["profile"]["id"]}[{", ".join(issues)}]'


def choose_tier_id(routing: dict[str, Any], task_kind: str, difficulty: str) -> str:
    task_map = routing.get("taskKindTierMap", {})
    difficulty_map = routing.get("difficultyTierMap", {})
    return task_map.get(task_kind) or difficulty_map.get(difficulty) or "balanced"


def select_route(
    config: dict[str, Any],
    *,
    machine_id: str,
    task_kind: str,
    difficulty: str,
    requested_profile: str | None,
    locked_profile: str | None,
) -> dict[str, Any]:
    routing = config["routing"]
    candidates: list[dict[str, Any]] = []
    for profile in config.get("profiles", []):
        if machine_id not in profile.get("machineIds", []):
            continue
        issues = profile_issues(profile, machine_id)
        candidates.append(
            {
                "profile": profile,
                "issues": issues,
                "score": profile_score(profile),
            }
        )

    if not candidates:
        raise ValueError(f"No profile can run on {machine_id}")

    healthy = [candidate for candidate in candidates if not candidate["issues"]]
    pinned_profile_id = routing.get("pinProfileId", "")
    pinned = next((candidate for candidate in candidates if candidate["profile"]["id"] == pinned_profile_id), None)
    explicit = next((candidate for candidate in candidates if candidate["profile"]["id"] == requested_profile), None)
    locked = next((candidate for candidate in candidates if candidate["profile"]["id"] == locked_profile), None)

    rationale = [
        f'routing.mode={routing.get("mode", "unknown")}',
        f"machine={machine_id}",
        f"taskKind={task_kind}",
        f"difficulty={difficulty}",
    ]

    chosen: dict[str, Any] | None = healthy[0] if healthy else None

    if locked_profile:
        rationale.append(f"selection=task-lock:{locked_profile}")
        if locked is None:
            raise ValueError(f"Locked profile {locked_profile} cannot run on {machine_id}")
        if locked["issues"]:
            raise ValueError(f"Locked profile is unhealthy: {describe_candidate(locked)}")
        chosen = locked
    elif requested_profile:
        rationale.append(f"selection=explicit:{requested_profile}")
        if explicit is None:
            raise ValueError(f"Requested profile {requested_profile} cannot run on {machine_id}")
        if explicit["issues"]:
            raise ValueError(f"Requested profile is unhealthy: {describe_candidate(explicit)}")
        if explicit["profile"]["id"] != pinned_profile_id and not explicit["profile"].get("allowSelection", False):
            raise ValueError(f"Profile {requested_profile} is not operator-selectable")
        chosen = explicit
    elif bool(routing.get("allowMultiAccount", False)):
        rationale.append("selection=weighted")
        chosen = max(healthy, key=lambda candidate: candidate["score"], default=None)
    else:
        rationale.append(f"selection=pinned:{pinned_profile_id}")
        if pinned is None:
            raise ValueError(f"Pinned profile {pinned_profile_id} cannot run on {machine_id}")
        if pinned["issues"]:
            raise ValueError(f"Pinned profile is unhealthy: {describe_candidate(pinned)}")
        chosen = pinned

    if chosen is None:
        details = "; ".join(describe_candidate(candidate) for candidate in candidates)
        raise ValueError(f"No healthy profile can launch on {machine_id}: {details}")

    tier_id = choose_tier_id(routing, task_kind, difficulty)
    model_tiers = chosen["profile"].get("modelTiers", {})
    tier = model_tiers.get(tier_id)
    if tier is None:
        tier = next(iter(model_tiers.values()), None)
    if tier is None:
        raise ValueError(f'Profile {chosen["profile"]["id"]} defines no model tiers')

    rationale.extend(
        [
            f'profile={chosen["profile"]["id"]}',
            f'credit.remaining={chosen["profile"].get("credit", {}).get("remaining", 0)}',
            f'routing.score={chosen["score"]:.3f}',
            f"tier={tier_id}",
            f'browserMode={tier.get("browserMode", "none")}',
        ]
    )

    return {
        "profileId": chosen["profile"]["id"],
        "machineId": machine_id,
        "tierId": tier_id,
        "model": tier["model"],
        "reasoningEffort": tier["reasoningEffort"],
        "search": bool(tier.get("search", False)),
        "browserMode": tier.get("browserMode", "none"),
        "rationale": rationale,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview Codex account routing and reasoning-tier selection.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--machine", default="dev-intern-02")
    parser.add_argument("--task-kind", default="research")
    parser.add_argument("--difficulty", default="medium")
    parser.add_argument("--profile", default="")
    parser.add_argument("--locked-profile", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_json(args.config)
    route = select_route(
        config,
        machine_id=args.machine,
        task_kind=args.task_kind,
        difficulty=args.difficulty,
        requested_profile=args.profile or None,
        locked_profile=args.locked_profile or None,
    )
    print(json.dumps(route, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
