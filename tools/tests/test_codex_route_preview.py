from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "codex_route_preview.py"
SPEC = importlib.util.spec_from_file_location("codex_route_preview", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CodexRoutePreviewTest(unittest.TestCase):
    def base_config(self) -> dict:
        return {
            "routing": {
                "mode": "current-task-locked",
                "pinProfileId": "current-session",
                "allowMultiAccount": True,
                "difficultyTierMap": {"low": "quick", "medium": "balanced", "high": "deep"},
                "taskKindTierMap": {
                    "research": "deep",
                    "builder": "deep",
                    "monitor": "balanced",
                    "summary": "quick",
                    "review": "balanced"
                }
            },
            "profiles": [
                {
                    "id": "current-session",
                    "enabled": True,
                    "allowSelection": False,
                    "routingWeight": 1.0,
                    "machineIds": ["pc", "dev-intern-02"],
                    "credit": {"remaining": 1.0, "reserveFloor": 0.1},
                    "health": {"available": True, "verified": True, "issues": []},
                    "modelTiers": {
                        "quick": {"model": "gpt-5.4", "reasoningEffort": "medium", "search": False, "browserMode": "none"},
                        "balanced": {"model": "gpt-5.4", "reasoningEffort": "high", "search": True, "browserMode": "codex-search"},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "xhigh", "search": True, "browserMode": "codex-search"}
                    }
                },
                {
                    "id": "slot-2",
                    "enabled": True,
                    "allowSelection": True,
                    "routingWeight": 0.5,
                    "machineIds": ["dev-intern-02"],
                    "credit": {"remaining": 0.2, "reserveFloor": 0.1},
                    "health": {"available": True, "verified": True, "issues": []},
                    "modelTiers": {
                        "quick": {"model": "gpt-5.4-mini", "reasoningEffort": "low", "search": False, "browserMode": "none"},
                        "balanced": {"model": "gpt-5.4", "reasoningEffort": "medium", "search": True, "browserMode": "codex-search"},
                        "deep": {"model": "gpt-5.4", "reasoningEffort": "high", "search": True, "browserMode": "codex-search"}
                    }
                }
            ]
        }

    def test_weighted_route_prefers_health_and_score(self) -> None:
        route = MODULE.select_route(
            self.base_config(),
            machine_id="dev-intern-02",
            task_kind="research",
            difficulty="medium",
            requested_profile=None,
            locked_profile=None
        )
        self.assertEqual(route["profileId"], "current-session")
        self.assertEqual(route["tierId"], "deep")
        self.assertEqual(route["reasoningEffort"], "xhigh")

    def test_locked_profile_must_be_healthy(self) -> None:
        config = self.base_config()
        config["profiles"][1]["health"]["available"] = False
        with self.assertRaisesRegex(ValueError, "Locked profile is unhealthy"):
            MODULE.select_route(
                config,
                machine_id="dev-intern-02",
                task_kind="summary",
                difficulty="low",
                requested_profile=None,
                locked_profile="slot-2"
            )


if __name__ == "__main__":
    unittest.main()
