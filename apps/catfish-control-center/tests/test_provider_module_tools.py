from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


WORKTREE_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = WORKTREE_ROOT / "apps" / "catfish-control-center"
TOOLS_DIR = WORKTREE_ROOT / "tools"
for path in (APP_ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from catfish_control_center.runtime import load_live_state  # noqa: E402
from catfish_module_scout import build_scan_report, install_candidate, persist_scan_state, load_scout_state  # noqa: E402
from catfish_provider_doctor import build_provider_doctor_report, write_state_root  # noqa: E402


class ProviderModuleToolTests(unittest.TestCase):
    def test_provider_doctor_writes_route_preview_and_load_live_state_uses_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            with patch.dict(
                os.environ,
                {
                    "CATFISH_PROVIDER_UCLOUD_BASE_URL": "https://env.example.invalid/v1",
                    "OPENAI_API_KEY": "unit-test-key",
                },
                clear=True,
            ):
                report = build_provider_doctor_report(
                    json.loads((WORKTREE_ROOT / "assets" / "router" / "catfish_provider_registry.json").read_text(encoding="utf-8")),
                    json.loads((WORKTREE_ROOT / "assets" / "router" / "catfish_provider_health_20260325.json").read_text(encoding="utf-8")),
                    json.loads((WORKTREE_ROOT / "assets" / "router" / "catfish_capability_ledger.json").read_text(encoding="utf-8")),
                    machine_id="dev-intern-02",
                    task_category="builder",
                    difficulty="medium",
                    parent_score=0.7,
                )
            self.assertEqual(report["selectedProviderId"], "ucloud-modelverse")
            self.assertEqual(report["routePreview"]["profileId"], "ucloud-modelverse")
            self.assertTrue(report["routePreview"]["providerBaseUrlSource"].startswith("env:"))

            write_state_root(state_root, report)
            snapshot = load_live_state(state_root)
            self.assertIsNotNone(snapshot.route_preview)
            assert snapshot.route_preview is not None
            self.assertEqual(snapshot.route_preview["profileId"], "ucloud-modelverse")
            selected = [provider for provider in snapshot.providers if provider.selected]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].profile_id, "ucloud-modelverse")

    def test_module_scout_scans_allowlisted_candidates_and_materializes_skill_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state-root"
            system_root = state_root / "system"
            system_root.mkdir(parents=True, exist_ok=True)
            allowlist_path = WORKTREE_ROOT / "assets" / "external_repos" / "catfish_module_scout_manifest.example.json"
            scout_state_path = WORKTREE_ROOT / "assets" / "router" / "catfish_self_optimization_queue.example.json"
            scout_state = json.loads(scout_state_path.read_text(encoding="utf-8"))
            (system_root / "self_optimization.json").write_text(
                json.dumps(scout_state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = build_scan_report(state_root, allowlist_path)
            self.assertEqual(report["bestCandidateId"], "candidate:promptfoo")
            self.assertGreaterEqual(report["summary"]["eligible"], 1)
            persist_scan_state(state_root, report)

            persisted = load_scout_state(state_root)
            self.assertIn("module_scout_runs", persisted)
            self.assertEqual(persisted["module_scout_runs"][-1]["best_candidate_id"], "candidate:promptfoo")

            install = install_candidate(
                state_root,
                allowlist_path,
                "candidate:promptfoo",
                Path(tmp) / "scratch",
                allow_network=False,
                materialize_skill=True,
            )
            self.assertEqual(install.candidate_id, "candidate:promptfoo")
            self.assertEqual(install.status, "installed")
            self.assertTrue((Path(install.install_root) / "skill" / "SKILL.md").exists())
            self.assertTrue((Path(install.install_root) / "install_plan.json").exists())

    def test_module_scout_requires_review_before_installing_queued_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state-root"
            system_root = state_root / "system"
            system_root.mkdir(parents=True, exist_ok=True)
            allowlist_path = WORKTREE_ROOT / "assets" / "external_repos" / "catfish_module_scout_manifest.example.json"
            scout_state = {
                "module_scout_contracts": [
                    {
                        "contract_id": "scout-contract-implementation",
                        "module_id": "scheduler/implementation-builder",
                        "module_label": "Implementation Builder",
                        "capability": "implementation",
                        "allowlist_manifest": "assets/external_repos/catfish_module_scout_manifest.example.json",
                        "allowed_source_ids": ["promptfoo"],
                        "safe_install_modes": ["clone-reference", "convert-to-skill"],
                        "max_candidates": 4,
                        "require_explicit_allowlist": True,
                        "require_human_review": True,
                        "created_at": "2026-03-28T09:58:00Z",
                        "summary": "Only allowlisted modules may move from scouting into trial installation.",
                    }
                ],
                "module_scout_candidates": [
                    {
                        "candidate_id": "candidate:promptfoo",
                        "contract_id": "scout-contract-implementation",
                        "source_kind": "repo",
                        "source_id": "promptfoo",
                        "title": "promptfoo",
                        "capability": "implementation",
                        "source_url": "https://github.com/promptfoo/promptfoo",
                        "install_policy": "clone-reference",
                        "conversion_target": "skill",
                        "summary": "Useful but still needs explicit review.",
                        "metadata": {
                            "novelty_score": 0.55,
                            "quality_score": 0.55,
                            "fit_score": 0.55,
                            "operational_score": 0.55,
                        },
                    }
                ],
            }
            (system_root / "self_optimization.json").write_text(
                json.dumps(scout_state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = build_scan_report(state_root, allowlist_path)
            self.assertEqual(report["candidates"][0]["decision"], "queue-for-review")
            self.assertEqual(report["summary"]["eligible"], 0)

            with self.assertRaisesRegex(ValueError, "not eligible for installation"):
                install_candidate(
                    state_root,
                    allowlist_path,
                    "candidate:promptfoo",
                    Path(tmp) / "scratch",
                    allow_network=False,
                    materialize_skill=True,
                )


if __name__ == "__main__":
    unittest.main()
