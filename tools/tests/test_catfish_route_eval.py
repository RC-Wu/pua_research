from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

MODULE_PATH = TOOLS_DIR / "catfish_route_core.py"
SPEC = importlib.util.spec_from_file_location("catfish_route_core", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CatfishRouteEvalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry, self.health_snapshot, self.ledger = MODULE.load_router_inputs()

    def test_selects_ucloud_when_other_providers_are_quota_blocked(self) -> None:
        payload = MODULE.select_provider_route(
            self.registry,
            self.health_snapshot,
            self.ledger,
            machine_id="dev-intern-02",
            task_category="research",
            difficulty="high",
            parent_score=0.92,
        )
        selected = payload["selected"]
        self.assertEqual(selected["provider_id"], "ucloud-modelverse")
        self.assertEqual(selected["tierId"], "deep")
        self.assertEqual(selected["model"], "gpt-5.4")
        blocked = {
            item["provider_id"]: item["blockers"]
            for item in payload["alternatives"]
            if item["provider_id"] != "ucloud-modelverse"
        }
        self.assertIn("quota-exhausted", blocked["smartaipro"])
        self.assertIn("quota-exhausted", blocked["molus"])

    def test_parent_score_changes_capability_boost(self) -> None:
        high_parent = MODULE.select_provider_route(
            self.registry,
            self.health_snapshot,
            self.ledger,
            machine_id="dev-intern-02",
            task_category="research",
            difficulty="high",
            parent_score=0.92,
        )["selected"]
        low_parent = MODULE.select_provider_route(
            self.registry,
            self.health_snapshot,
            self.ledger,
            machine_id="dev-intern-02",
            task_category="research",
            difficulty="high",
            parent_score=0.1,
        )["selected"]
        self.assertGreater(high_parent["capabilityScore"], low_parent["capabilityScore"])

    def test_health_report_marks_only_ucloud_launchable(self) -> None:
        report = MODULE.build_health_report(self.registry, self.health_snapshot)
        launchable = {item["provider_id"]: item["launchable"] for item in report["providers"]}
        self.assertEqual(launchable["ucloud-modelverse"], True)
        self.assertEqual(launchable["smartaipro"], False)
        self.assertEqual(launchable["molus"], False)


if __name__ == "__main__":
    unittest.main()
