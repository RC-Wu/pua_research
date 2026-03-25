# ARIS Mainline Merge Record

- Date: 2026-03-25
- Merge branch: `upstream/main`
- Upstream commit merged: `755ecadb4e920d8e479de46f50d3bae911bfb640`
- Merge base: `405eaf52ac48734bd8cb3231a7592689a76a950f`
- Target branch: `codex/catfish-merge-aris`

## Scope

This merge updates the local Codex-first ARIS fork with the latest upstream ARIS mainline while preserving local additions that matter to the Codex execution path and Catfish-oriented branch maintenance.

The upstream update brought in substantial ARIS mainline changes across:

- top-level docs and README content
- new workflow documentation, including Workflow 4 rebuttal material
- Gemini review bridge support
- new skills such as `training-check`, `result-to-claim`, `ablation-planner`, `paper-poster`, `rebuttal`, `formula-derivation`, and `system-profile`
- shared references, templates, watchdog tooling, and refreshed Codex skill overlays

## Conflicts

Only two files required manual conflict resolution:

- `README.md`
- `README_CN.md`

## Resolution Decisions

### Kept from upstream ARIS

- The expanded ARIS project framing, workflow descriptions, setup guidance, feature list, roadmap, community showcase, and recent-news sections.
- The new upstream README material for:
  - Workflow 4 `/rebuttal`
  - Gemini review bridge documentation
  - updated templates and venue/template support
  - added community showcase assets and acceptance examples

### Kept from local Codex/Catfish side

- The Codex-first fork positioning as an additive note instead of replacing the ARIS identity.
- Explicit preservation of the local Codex-native skill tree under `skills/skills-codex/`.
- References to the local-only Codex additions that are expected to stay available in this branch:
  - `agentdoc-startup`
  - `pua-complex-task-method`
  - `remote-codex-subagents`
  - `heartbeat-subagent-template`
  - `final-summary-subagent`
  - `peer-review`
  - `tools/codex_route_preview.py`
- A Codex-first quick-start path for this fork, in addition to the upstream Claude-first quick start.
- Branch-specific links to local docs:
  - `docs/CODEX_PUA_STACK.md`
  - `docs/AGENTDOC_BRIDGE.md`
  - `docs/CODEX_CONTROL_PLANE.md`

### Semantic merge policy used

- Upstream ARIS remained the primary source of truth for product description and README structure.
- Local Codex-first material was reintroduced only where it adds branch-specific context or preserves local entrypoints and docs.
- No local skill trees or overlays were dropped.
- No automatic overwrite was used on the conflicting README content after conflict inspection; the final README content is intentionally blended.

## Catfish Notes

- No preexisting `docs/catfish/` subtree was present before this merge.
- This file creates the Catfish merge record requested for branch tracking.
- No separate Catfish-specific docs scaffolding was found elsewhere in the repository at merge time.

## Residual Risks

- The top-level README files now describe both the upstream ARIS path and the local Codex-first fork path. Future upstream README rewrites may conflict again in the same areas.
- The branch-specific fork note references commit `405eaf5` as the local dev-intern-02 baseline; if this branch later rebases or changes historical narrative, that sentence may need an update.
- The merge was validated with cheap repository-level checks only; no end-to-end workflow execution was performed.

## Recommended Follow-Up

- If README churn continues upstream, consider moving branch-specific fork notes into a dedicated local doc and linking to it from the README to reduce future conflict surface.
- Run a focused smoke test for the local Codex-only additions most likely to regress:
  - `skills/skills-codex/remote-codex-subagents`
  - `skills/skills-codex/agentdoc-startup`
  - `skills/skills-codex/pua-complex-task-method`
  - `tools/codex_route_preview.py`
- If this branch is meant to remain long-lived, consider adding a short README section or badge explicitly stating that both `skills/` and `skills/skills-codex/` are supported and intentionally retained.
