from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "assets" / "router" / "catfish_provider_registry.json"
DEFAULT_HEALTH_PATH = REPO_ROOT / "assets" / "router" / "catfish_provider_health_20260325.json"
DEFAULT_LEDGER_PATH = REPO_ROOT / "assets" / "router" / "catfish_capability_ledger.json"

_DEFAULT_REASONING_LENGTH = {
    "quick": "short",
    "balanced": "medium",
    "deep": "long",
}

_ROUTING_EFFECT_WEIGHTS = {
    "prefer": 1.0,
    "neutral": 0.0,
    "penalize": -0.6,
    "block": -1.0,
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_router_inputs(
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    health_path: Path = DEFAULT_HEALTH_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        load_json(registry_path),
        load_json(health_path),
        load_json(ledger_path),
    )


def choose_reasoning_tier(
    routing: dict[str, Any],
    *,
    task_category: str,
    difficulty: str,
    requested_tier: str | None = None,
) -> str:
    if requested_tier:
        return requested_tier
    task_map = routing.get("taskCategoryTierMap", {})
    difficulty_map = routing.get("difficultyTierMap", {})
    return task_map.get(task_category) or difficulty_map.get(difficulty) or routing.get("defaultTier", "balanced")


def reasoning_length_for_tier(routing: dict[str, Any], tier_id: str) -> str:
    mapping = routing.get("reasoningLengthByTier") or _DEFAULT_REASONING_LENGTH
    return str(mapping.get(tier_id, _DEFAULT_REASONING_LENGTH.get(tier_id, "medium")))


def parse_date_like(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        raise ValueError("Missing date value")
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text)


def recency_weight(entry_recency: object, *, reference_date: date) -> float:
    days = max((reference_date - parse_date_like(entry_recency)).days, 0)
    return 1.0 / (1.0 + (days / 30.0))


def normalize_parent_score(value: object) -> float:
    score = float(value)
    return max(0.0, min(score, 1.0))


def health_index(health_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("providerId")): dict(entry)
        for entry in health_snapshot.get("providers", [])
        if entry.get("providerId")
    }


def model_tier_for_provider(provider: dict[str, Any], tier_id: str) -> dict[str, Any] | None:
    tier = provider.get("modelTiers", {}).get(tier_id)
    if tier is not None:
        return dict(tier)
    model_tiers = provider.get("modelTiers", {})
    if model_tiers:
        first_key = next(iter(model_tiers))
        return dict(model_tiers[first_key])
    return None


def resolve_provider_base_url(provider: dict[str, Any]) -> tuple[str, str]:
    env_name = str(provider.get("baseUrlEnv") or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value, f"env:{env_name}"
    base_url = str(provider.get("baseUrl") or "").strip()
    if base_url:
        return base_url, "registry"
    return "", "unset"


def provider_blockers(
    provider: dict[str, Any],
    health: dict[str, Any] | None,
    *,
    machine_id: str,
    tier_id: str,
    requested_model: str | None,
) -> list[str]:
    issues: list[str] = []
    if not provider.get("enabled", True):
        issues.append("provider-disabled")
    if machine_id not in provider.get("machineIds", []):
        issues.append("machine-not-allowed")

    tier = model_tier_for_provider(provider, tier_id)
    if tier is None:
        issues.append(f"missing-tier:{tier_id}")
    else:
        model_name = str(tier.get("model") or "").strip()
        if requested_model and model_name != requested_model:
            issues.append(f"requested-model-mismatch:{model_name}")
        if not bool(tier.get("verified", False)) and not health:
            issues.append(f"unverified-tier:{tier_id}")

    if health is None:
        issues.append("missing-health")
        return issues

    if not bool(health.get("endpointReachable", False)):
        issues.append("endpoint-unreachable")
    quota_state = str(health.get("quotaState") or "unknown").strip().lower()
    if quota_state == "exhausted":
        issues.append("quota-exhausted")
    status = str(health.get("status") or "unknown").strip().lower()
    if status in {"blocked", "quota-exhausted"} and "quota-exhausted" not in issues:
        issues.append(f"status:{status}")
    return issues


def health_base_score(health: dict[str, Any] | None) -> float:
    if not health:
        return 0.0
    if not bool(health.get("endpointReachable", False)):
        return 0.0
    quota_state = str(health.get("quotaState") or "unknown").strip().lower()
    status = str(health.get("status") or "unknown").strip().lower()
    if quota_state == "healthy" and status == "working":
        return 1.0
    if quota_state in {"warning", "low"} or status == "degraded":
        return 0.6
    if quota_state == "exhausted":
        return 0.05
    return 0.35


def ledger_match_score(
    entry: dict[str, Any],
    *,
    task_category: str,
    difficulty: str,
    reasoning_tier: str,
    reasoning_length: str,
    parent_score: float,
) -> float:
    def exact_or_any(value: str, target: str) -> float:
        if value == target:
            return 1.0
        if value in {"any", "general", "*"}:
            return 0.35
        return 0.0

    task_factor = exact_or_any(str(entry.get("taskCategory") or ""), task_category)
    difficulty_factor = exact_or_any(str(entry.get("difficulty") or ""), difficulty)
    tier_factor = exact_or_any(str(entry.get("reasoningTier") or ""), reasoning_tier)
    length_factor = exact_or_any(str(entry.get("reasoningLength") or ""), reasoning_length)
    entry_parent = normalize_parent_score(entry.get("parentScore", 0.5))
    parent_factor = max(0.0, 1.0 - abs(entry_parent - parent_score))

    return (
        (0.35 * task_factor)
        + (0.2 * difficulty_factor)
        + (0.2 * tier_factor)
        + (0.05 * length_factor)
        + (0.2 * parent_factor)
    )


def capability_contributions(
    provider_id: str,
    ledger: dict[str, Any],
    *,
    task_category: str,
    difficulty: str,
    reasoning_tier: str,
    reasoning_length: str,
    parent_score: float,
    reference_date: date,
) -> list[dict[str, Any]]:
    entries = []
    for entry in ledger.get("entries", []):
        if str(entry.get("providerId")) != provider_id:
            continue
        match_score = ledger_match_score(
            dict(entry),
            task_category=task_category,
            difficulty=difficulty,
            reasoning_tier=reasoning_tier,
            reasoning_length=reasoning_length,
            parent_score=parent_score,
        )
        confidence = max(0.0, min(float(entry.get("confidence", 1.0)), 1.0))
        freshness = recency_weight(entry.get("recency"), reference_date=reference_date)
        effect = str(entry.get("routingEffect") or "neutral").strip().lower()
        effect_weight = _ROUTING_EFFECT_WEIGHTS.get(effect, 0.0)
        score_delta = float(entry.get("scoreDelta", 0.0))
        contribution = (score_delta + (0.1 * effect_weight)) * match_score * confidence * freshness
        entries.append(
            {
                "id": entry.get("id"),
                "matchScore": round(match_score, 6),
                "freshness": round(freshness, 6),
                "confidence": round(confidence, 6),
                "routingEffect": effect,
                "scoreDelta": score_delta,
                "contribution": round(contribution, 6),
                "notes": entry.get("notes", ""),
            }
        )
    entries.sort(key=lambda item: abs(float(item["contribution"])), reverse=True)
    return entries


def evaluate_provider(
    provider: dict[str, Any],
    health: dict[str, Any] | None,
    ledger: dict[str, Any],
    *,
    machine_id: str,
    task_category: str,
    difficulty: str,
    tier_id: str,
    reasoning_length: str,
    parent_score: float,
    requested_model: str | None,
    reference_date: date,
) -> dict[str, Any]:
    tier = model_tier_for_provider(provider, tier_id)
    blockers = provider_blockers(
        provider,
        health,
        machine_id=machine_id,
        tier_id=tier_id,
        requested_model=requested_model,
    )
    contributions = capability_contributions(
        str(provider.get("id")),
        ledger,
        task_category=task_category,
        difficulty=difficulty,
        reasoning_tier=tier_id,
        reasoning_length=reasoning_length,
        parent_score=parent_score,
        reference_date=reference_date,
    )
    capability_score = sum(float(item["contribution"]) for item in contributions)
    base_score = health_base_score(health) * max(float(provider.get("routingWeight", 1.0)), 0.01)
    total_score = base_score + capability_score
    base_url, base_url_source = resolve_provider_base_url(provider)
    rationale = [
        f"provider={provider.get('id')}",
        f"machine={machine_id}",
        f"taskCategory={task_category}",
        f"difficulty={difficulty}",
        f"tier={tier_id}",
        f"parentScore={parent_score:.2f}",
        f"healthBaseScore={base_score:.3f}",
        f"capabilityScore={capability_score:.3f}",
    ]
    if base_url_source != "unset":
        rationale.append(f"providerBaseUrlSource={base_url_source}")
    if health is not None:
        rationale.append(f"health.status={health.get('status', 'unknown')}")
        rationale.append(f"health.quotaState={health.get('quotaState', 'unknown')}")

    return {
        "provider_id": provider.get("id"),
        "provider_name": provider.get("providerName"),
        "provider_display_name": provider.get("displayName", provider.get("providerName")),
        "provider_base_url": base_url,
        "provider_base_url_env": provider.get("baseUrlEnv", ""),
        "provider_base_url_source": base_url_source,
        "provider_wire_api": provider.get("wireApi", "responses"),
        "provider_env_key": provider.get("envKey", "OPENAI_API_KEY"),
        "provider_requires_openai_auth": bool(provider.get("requiresOpenAIAuth", False)),
        "machineId": machine_id,
        "taskCategory": task_category,
        "difficulty": difficulty,
        "tierId": tier_id,
        "reasoningLength": reasoning_length,
        "reasoningEffort": tier.get("reasoningEffort") if tier else None,
        "model": tier.get("model") if tier else None,
        "health": dict(health or {}),
        "blockers": blockers,
        "baseScore": round(base_score, 6),
        "capabilityScore": round(capability_score, 6),
        "score": round(total_score, 6),
        "matchedLedgerEntries": contributions[:5],
        "rationale": rationale,
    }


def select_provider_route(
    registry: dict[str, Any],
    health_snapshot: dict[str, Any],
    ledger: dict[str, Any],
    *,
    machine_id: str,
    task_category: str,
    difficulty: str,
    parent_score: float,
    requested_tier: str | None = None,
    requested_model: str | None = None,
) -> dict[str, Any]:
    routing = registry.get("routing", {})
    tier_id = choose_reasoning_tier(
        routing,
        task_category=task_category,
        difficulty=difficulty,
        requested_tier=requested_tier,
    )
    reasoning_length = reasoning_length_for_tier(routing, tier_id)
    health_by_provider = health_index(health_snapshot)
    observed_at = parse_date_like(health_snapshot.get("observedAt", date.today().isoformat()))
    normalized_parent_score = normalize_parent_score(parent_score)

    candidates = [
        evaluate_provider(
            dict(provider),
            health_by_provider.get(str(provider.get("id"))),
            ledger,
            machine_id=machine_id,
            task_category=task_category,
            difficulty=difficulty,
            tier_id=tier_id,
            reasoning_length=reasoning_length,
            parent_score=normalized_parent_score,
            requested_model=requested_model,
            reference_date=observed_at,
        )
        for provider in registry.get("providers", [])
    ]
    candidates.sort(key=lambda item: float(item["score"]), reverse=True)

    healthy = [candidate for candidate in candidates if not candidate["blockers"]]
    if not healthy:
        details = "; ".join(
            f"{candidate['provider_id']}[{', '.join(candidate['blockers']) or 'ok'}]"
            for candidate in candidates
        )
        raise ValueError(f"No launchable provider route for {machine_id}: {details}")

    selected = healthy[0]
    return {
        "schemaVersion": "catfish.provider-route.v1",
        "observedAt": health_snapshot.get("observedAt"),
        "ledgerVersion": ledger.get("schemaVersion"),
        "routingMode": routing.get("mode", "unknown"),
        "selected": selected,
        "alternatives": candidates,
    }


def build_health_report(registry: dict[str, Any], health_snapshot: dict[str, Any]) -> dict[str, Any]:
    health_by_provider = health_index(health_snapshot)
    providers: list[dict[str, Any]] = []
    for provider in registry.get("providers", []):
        health = health_by_provider.get(str(provider.get("id")), {})
        blockers = provider_blockers(
            dict(provider),
            health if health else None,
            machine_id=str(registry.get("routing", {}).get("defaultMachineId", "dev-intern-02")),
            tier_id=str(registry.get("routing", {}).get("defaultTier", "balanced")),
            requested_model=None,
        )
        providers.append(
            {
                "provider_id": provider.get("id"),
                "provider_name": provider.get("providerName"),
                "display_name": provider.get("displayName"),
                "status": health.get("status", "missing-health"),
                "endpointReachable": bool(health.get("endpointReachable", False)),
                "quotaState": health.get("quotaState", "unknown"),
                "launchable": not blockers,
                "blockers": blockers,
                "notes": health.get("notes", []),
            }
        )
    return {
        "schemaVersion": "catfish.provider-health-report.v1",
        "observedAt": health_snapshot.get("observedAt"),
        "providers": providers,
    }
