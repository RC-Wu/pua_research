from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "cc_switch_bridge.py"
SPEC = importlib.util.spec_from_file_location("cc_switch_bridge", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CcSwitchBridgeTest(unittest.TestCase):
    def base_config(self) -> dict:
        return {
            "routing": {
                "mode": "current-task-locked",
                "pinProfileId": "openai-primary",
                "allowMultiAccount": True,
                "difficultyTierMap": {"low": "quick", "medium": "balanced", "high": "deep"},
                "taskKindTierMap": {"research": "deep", "summary": "quick"},
            },
            "tierDefaults": {
                "quick": {"search": False, "browserMode": "none"},
                "balanced": {"search": True, "browserMode": "codex-search"},
                "deep": {"search": True, "browserMode": "codex-search"},
            },
            "providers": [
                {
                    "id": "openai-primary",
                    "label": "OpenAI Primary",
                    "enabled": True,
                    "allowSelection": False,
                    "routingWeight": 1.0,
                    "machineIds": ["dev-intern-02", "pc"],
                    "credit": {"remaining": 1.0, "reserveFloor": 0.1},
                    "health": {"available": True, "verified": True, "issues": []},
                    "provider": {
                        "name": "openai",
                        "displayName": "OpenAI",
                        "baseUrl": "https://api.openai.com/v1",
                        "wireApi": "responses",
                    },
                    "credentials": {
                        "envKey": "OPENAI_API_KEY",
                        "keyFile": "/keys/openai-primary.key",
                        "accountKey": "acct-openai-primary",
                    },
                    "tierOverrides": {
                        "quick": {"model": "gpt-5.4-mini", "reasoningEffort": "low"},
                        "balanced": {"model": "gpt-5.4", "reasoningEffort": "high"},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "xhigh"},
                    },
                },
                {
                    "id": "gateway-backup",
                    "label": "Gateway Backup",
                    "enabled": True,
                    "allowSelection": True,
                    "routingWeight": 0.9,
                    "machineIds": ["dev-intern-02"],
                    "credit": {"remaining": 0.7, "reserveFloor": 0.1},
                    "health": {"available": True, "verified": True, "issues": []},
                    "provider": {
                        "name": "catfish_gateway",
                        "displayName": "Catfish Gateway",
                        "baseUrl": "https://catfish-gateway.example.com/v1",
                        "wireApi": "responses",
                    },
                    "credentials": {
                        "envKey": "CATFISH_GATEWAY_KEY",
                        "keyFile": "/keys/catfish-gateway.key",
                        "accountKey": "acct-catfish-gateway",
                    },
                    "modelTiers": {
                        "quick": {"model": "gpt-5.4-mini", "reasoningEffort": "low", "search": False, "browserMode": "none"},
                        "balanced": {"model": "gpt-5.4", "reasoningEffort": "medium", "search": True, "browserMode": "codex-search"},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "high", "search": True, "browserMode": "codex-search"},
                    },
                },
            ],
        }

    def test_preview_includes_provider_and_credential_metadata(self) -> None:
        normalized = MODULE.normalize_cc_switch_config(self.base_config())
        route = MODULE.preview_route(
            normalized,
            machine_id="dev-intern-02",
            task_kind="research",
            difficulty="medium",
            requested_profile=None,
            locked_profile=None,
        )
        self.assertEqual(route["profileId"], "openai-primary")
        self.assertEqual(route["tierId"], "deep")
        self.assertEqual(route["providerName"], "openai")
        self.assertEqual(route["providerEnvKey"], "OPENAI_API_KEY")
        self.assertEqual(route["providerKeyFile"], "/keys/openai-primary.key")
        self.assertEqual(route["accountKey"], "acct-openai-primary")

    def test_export_route_specs_orders_chosen_route_first(self) -> None:
        normalized = MODULE.normalize_cc_switch_config(self.base_config())
        route_specs = MODULE.build_route_specs(
            normalized,
            machine_id="dev-intern-02",
            task_kind="research",
            difficulty="medium",
            requested_profile=None,
            locked_profile=None,
            include_unhealthy=False,
        )
        self.assertEqual([spec["profile_id"] for spec in route_specs], ["openai-primary", "gateway-backup"])
        self.assertEqual(route_specs[0]["model"], "gpt-5.4")
        self.assertEqual(route_specs[0]["reasoning_effort"], "xhigh")

    def test_unhealthy_provider_is_filtered_by_default(self) -> None:
        config = self.base_config()
        config["providers"][1]["health"]["available"] = False
        config["providers"][1]["health"]["issues"] = ["auth-unavailable"]
        normalized = MODULE.normalize_cc_switch_config(config)
        route_specs = MODULE.build_route_specs(
            normalized,
            machine_id="dev-intern-02",
            task_kind="research",
            difficulty="medium",
            requested_profile=None,
            locked_profile=None,
            include_unhealthy=False,
        )
        self.assertEqual([spec["profile_id"] for spec in route_specs], ["openai-primary"])


if __name__ == "__main__":
    unittest.main()
