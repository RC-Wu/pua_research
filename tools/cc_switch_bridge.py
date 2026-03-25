from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
ROUTE_PREVIEW_PATH = TOOLS_DIR / "codex_route_preview.py"
ROUTE_PREVIEW_SPEC = importlib.util.spec_from_file_location("codex_route_preview", ROUTE_PREVIEW_PATH)
assert ROUTE_PREVIEW_SPEC and ROUTE_PREVIEW_SPEC.loader
ROUTE_PREVIEW = importlib.util.module_from_spec(ROUTE_PREVIEW_SPEC)
ROUTE_PREVIEW_SPEC.loader.exec_module(ROUTE_PREVIEW)


DEFAULT_ROUTING = {
    "mode": "current-task-locked",
    "pinProfileId": "",
    "allowMultiAccount": True,
    "difficultyTierMap": {
        "low": "quick",
        "medium": "balanced",
        "high": "deep",
    },
    "taskKindTierMap": {
        "research": "deep",
        "builder": "deep",
        "monitor": "balanced",
        "summary": "quick",
        "review": "balanced",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def bool_from_any(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Cannot coerce value to bool: {value!r}")


def normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Expected a string or list of strings, got {type(value).__name__}")


def merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(overlay)
    return merged


def resolve_model_tiers(provider: dict[str, Any], tier_defaults: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    direct_tiers = provider.get("modelTiers") or provider.get("tiers") or {}
    overrides = provider.get("tierOverrides") or {}
    if not isinstance(direct_tiers, dict) or not isinstance(overrides, dict):
        raise ValueError(f'Provider {provider.get("id", "<unknown>")} must define model tiers as objects')

    tier_ids: list[str] = []
    for source in (tier_defaults, direct_tiers, overrides):
        for tier_id in source.keys():
            if tier_id not in tier_ids:
                tier_ids.append(str(tier_id))

    model_tiers: dict[str, dict[str, Any]] = {}
    for tier_id in tier_ids:
        base = dict(tier_defaults.get(tier_id, {}))
        tier = merge_dicts(base, dict(direct_tiers.get(tier_id, {})))
        tier = merge_dicts(tier, dict(overrides.get(tier_id, {})))
        if tier:
            model_tiers[tier_id] = tier

    if not model_tiers:
        raise ValueError(f'Provider {provider.get("id", "<unknown>")} defines no model tiers')

    for tier_id, tier in model_tiers.items():
        if "model" not in tier or "reasoningEffort" not in tier:
            raise ValueError(
                f'Provider {provider.get("id", "<unknown>")} tier {tier_id} must define model and reasoningEffort'
            )

    return model_tiers


def normalize_provider(provider: dict[str, Any], tier_defaults: dict[str, dict[str, Any]]) -> dict[str, Any]:
    profile_id = str(provider.get("id") or "").strip()
    if not profile_id:
        raise ValueError("Each provider must define a non-empty id")

    provider_meta = dict(provider.get("provider") or {})
    credentials = dict(provider.get("credentials") or {})
    health = dict(provider.get("health") or {})

    provider_name = str(
        provider_meta.get("name")
        or provider.get("provider_name")
        or provider.get("providerName")
        or profile_id
    ).strip()
    provider_display_name = str(
        provider_meta.get("displayName")
        or provider_meta.get("display_name")
        or provider.get("provider_display_name")
        or provider.get("providerDisplayName")
        or provider.get("label")
        or provider_name
    ).strip()
    provider_base_url = str(
        provider_meta.get("baseUrl")
        or provider_meta.get("base_url")
        or provider.get("provider_base_url")
        or provider.get("providerBaseUrl")
        or ""
    ).strip()
    provider_wire_api = str(
        provider_meta.get("wireApi")
        or provider_meta.get("wire_api")
        or provider.get("provider_wire_api")
        or provider.get("providerWireApi")
        or "responses"
    ).strip()
    provider_env_key = str(
        credentials.get("envKey")
        or credentials.get("env_key")
        or provider_meta.get("envKey")
        or provider.get("provider_env_key")
        or provider.get("providerEnvKey")
        or "OPENAI_API_KEY"
    ).strip()
    provider_key_file = str(
        credentials.get("keyFile")
        or credentials.get("key_file")
        or provider.get("api_key_file")
        or provider.get("key_file")
        or ""
    ).strip()
    provider_requires_openai_auth = bool_from_any(
        provider_meta.get(
            "requiresOpenaiAuth",
            provider_meta.get(
                "requires_openai_auth",
                provider.get("provider_requires_openai_auth", provider.get("providerRequiresOpenaiAuth")),
            ),
        ),
        default=False,
    )

    account_key = str(
        credentials.get("accountKey")
        or credentials.get("account_key")
        or health.get("accountKey")
        or health.get("account_key")
        or provider.get("accountKey")
        or provider_name
    ).strip()
    health["accountKey"] = account_key
    health["available"] = bool_from_any(health.get("available"), default=True)
    health["verified"] = bool_from_any(health.get("verified"), default=True)
    health["issues"] = normalize_string_list(health.get("issues"))

    credit = dict(provider.get("credit") or {})
    credit["remaining"] = float(credit.get("remaining", 0.0))
    credit["reserveFloor"] = float(credit.get("reserveFloor", 0.0))

    return {
        "id": profile_id,
        "label": str(provider.get("label") or provider_display_name or profile_id),
        "enabled": bool_from_any(provider.get("enabled"), default=True),
        "allowSelection": bool_from_any(provider.get("allowSelection"), default=False),
        "routingWeight": float(provider.get("routingWeight", 1.0)),
        "machineIds": normalize_string_list(provider.get("machineIds")),
        "credit": credit,
        "health": health,
        "modelTiers": resolve_model_tiers(provider, tier_defaults),
        "provider": {
            "name": provider_name,
            "displayName": provider_display_name,
            "baseUrl": provider_base_url,
            "wireApi": provider_wire_api,
            "requiresOpenaiAuth": provider_requires_openai_auth,
        },
        "credentials": {
            "envKey": provider_env_key,
            "keyFile": provider_key_file,
            "accountKey": account_key,
        },
    }


def normalize_cc_switch_config(payload: dict[str, Any]) -> dict[str, Any]:
    routing = merge_dicts(DEFAULT_ROUTING, dict(payload.get("routing") or {}))
    tier_defaults = dict(payload.get("tierDefaults") or payload.get("tierPresets") or {})
    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("The cc-switch config must define a non-empty providers list")

    profiles = [normalize_provider(dict(provider), tier_defaults) for provider in providers]
    if not routing.get("pinProfileId"):
        routing["pinProfileId"] = profiles[0]["id"]
    return {"routing": routing, "profiles": profiles}


def find_profile(config: dict[str, Any], profile_id: str) -> dict[str, Any]:
    for profile in config.get("profiles", []):
        if profile.get("id") == profile_id:
            return profile
    raise ValueError(f"Unknown profile {profile_id}")


def resolve_tier(profile: dict[str, Any], tier_id: str) -> dict[str, Any]:
    model_tiers = dict(profile.get("modelTiers") or {})
    tier = model_tiers.get(tier_id)
    if tier is None:
        tier = next(iter(model_tiers.values()), None)
    if tier is None:
        raise ValueError(f'Profile {profile.get("id", "<unknown>")} defines no model tiers')
    return dict(tier)


def enrich_route(route: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    provider = dict(profile.get("provider") or {})
    credentials = dict(profile.get("credentials") or {})
    health = dict(profile.get("health") or {})
    enriched = dict(route)
    enriched.update(
        {
            "profileLabel": profile.get("label", profile["id"]),
            "accountKey": credentials.get("accountKey") or health.get("accountKey", ""),
            "providerName": provider.get("name", ""),
            "providerDisplayName": provider.get("displayName", ""),
            "providerBaseUrl": provider.get("baseUrl", ""),
            "providerWireApi": provider.get("wireApi", "responses"),
            "providerEnvKey": credentials.get("envKey", "OPENAI_API_KEY"),
            "providerKeyFile": credentials.get("keyFile", ""),
            "providerRequiresOpenaiAuth": bool(provider.get("requiresOpenaiAuth", False)),
        }
    )
    return enriched


def preview_route(
    normalized_config: dict[str, Any],
    *,
    machine_id: str,
    task_kind: str,
    difficulty: str,
    requested_profile: str | None,
    locked_profile: str | None,
) -> dict[str, Any]:
    route = ROUTE_PREVIEW.select_route(
        normalized_config,
        machine_id=machine_id,
        task_kind=task_kind,
        difficulty=difficulty,
        requested_profile=requested_profile,
        locked_profile=locked_profile,
    )
    profile = find_profile(normalized_config, route["profileId"])
    return enrich_route(route, profile)


def candidate_profiles(config: dict[str, Any], machine_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for profile in config.get("profiles", []):
        if machine_id not in profile.get("machineIds", []):
            continue
        candidates.append(
            {
                "profile": profile,
                "issues": ROUTE_PREVIEW.profile_issues(profile, machine_id),
                "score": ROUTE_PREVIEW.profile_score(profile),
            }
        )
    return candidates


def build_route_specs(
    normalized_config: dict[str, Any],
    *,
    machine_id: str,
    task_kind: str,
    difficulty: str,
    requested_profile: str | None,
    locked_profile: str | None,
    include_unhealthy: bool,
) -> list[dict[str, Any]]:
    chosen_route = preview_route(
        normalized_config,
        machine_id=machine_id,
        task_kind=task_kind,
        difficulty=difficulty,
        requested_profile=requested_profile,
        locked_profile=locked_profile,
    )
    tier_id = str(chosen_route["tierId"])
    chosen_profile_id = str(chosen_route["profileId"])

    candidates = candidate_profiles(normalized_config, machine_id)
    if locked_profile:
        candidates = [candidate for candidate in candidates if candidate["profile"]["id"] == chosen_profile_id]
    elif not include_unhealthy:
        candidates = [candidate for candidate in candidates if not candidate["issues"]]

    def sort_key(candidate: dict[str, Any]) -> tuple[int, float, str]:
        return (
            0 if candidate["profile"]["id"] == chosen_profile_id else 1,
            -float(candidate["score"]),
            str(candidate["profile"]["id"]),
        )

    route_specs: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=sort_key):
        profile = candidate["profile"]
        tier = resolve_tier(profile, tier_id)
        provider = dict(profile.get("provider") or {})
        credentials = dict(profile.get("credentials") or {})
        route_specs.append(
            {
                "route_name": profile.get("label") or profile["id"],
                "profile_id": profile["id"],
                "provider_name": provider.get("name", profile["id"]),
                "provider_display_name": provider.get("displayName", provider.get("name", profile["id"])),
                "provider_base_url": provider.get("baseUrl", ""),
                "provider_wire_api": provider.get("wireApi", "responses"),
                "provider_env_key": credentials.get("envKey", "OPENAI_API_KEY"),
                "provider_requires_openai_auth": bool(provider.get("requiresOpenaiAuth", False)),
                "api_key_file": credentials.get("keyFile", ""),
                "model": tier["model"],
                "reasoning_effort": tier["reasoningEffort"],
                "search": bool(tier.get("search", False)),
                "browser_mode": tier.get("browserMode", "none"),
                "score": round(float(candidate["score"]), 6),
                "issues": list(candidate["issues"]),
            }
        )
    return route_specs


def emit_json(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge Catfish cc-switch config into the lightweight Codex control plane.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    def add_common_route_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--config", type=Path, required=True)
        subparser.add_argument("--machine", default="dev-intern-02")
        subparser.add_argument("--task-kind", default="research")
        subparser.add_argument("--difficulty", default="medium")
        subparser.add_argument("--profile", default="")
        subparser.add_argument("--locked-profile", default="")

    export_control_plane = subparsers.add_parser("export-control-plane")
    export_control_plane.add_argument("--config", type=Path, required=True)

    preview = subparsers.add_parser("preview")
    add_common_route_args(preview)

    export_route_specs = subparsers.add_parser("export-route-specs")
    add_common_route_args(export_route_specs)
    export_route_specs.add_argument("--include-unhealthy", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    raw_config = load_json(args.config)
    normalized_config = normalize_cc_switch_config(raw_config)

    if args.cmd == "export-control-plane":
        return emit_json(normalized_config)

    if args.cmd == "preview":
        return emit_json(
            preview_route(
                normalized_config,
                machine_id=args.machine,
                task_kind=args.task_kind,
                difficulty=args.difficulty,
                requested_profile=args.profile or None,
                locked_profile=args.locked_profile or None,
            )
        )

    if args.cmd == "export-route-specs":
        return emit_json(
            build_route_specs(
                normalized_config,
                machine_id=args.machine,
                task_kind=args.task_kind,
                difficulty=args.difficulty,
                requested_profile=args.profile or None,
                locked_profile=args.locked_profile or None,
                include_unhealthy=bool(args.include_unhealthy),
            )
        )

    raise ValueError(f"Unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
