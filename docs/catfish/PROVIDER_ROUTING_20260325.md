# CatfishResearch Provider Routing

This document defines the provider-routing core added for CatfishResearch on 2026-03-25. The scope is intentionally narrow: provider registry, provider health, capability memory, and route evaluation. It does not depend on `cc-switch`, and it does not attempt to solve full multi-agent orchestration.

## Existing Repo Hooks

Two existing pieces in this repository shape the implementation:

- `tools/codex_route_preview.py` already models task kind and difficulty to reasoning-tier selection.
- `skills/skills-codex/remote-codex-subagents/scripts/remote_codex_subagents.py` already accepts provider override fields:
  - `provider_name`
  - `provider_display_name`
  - `provider_base_url`
  - `provider_wire_api`
  - `provider_env_key`
  - `provider_requires_openai_auth`

The Catfish router emits the same provider payload so it can remain independent of `cc-switch` while still matching the remote launcher’s provider contract later.

## Files

- `assets/router/catfish_provider_registry.json`
  - declarative provider registry and tier mapping
- `assets/router/catfish_provider_health_20260325.json`
  - dated health snapshot for the real status observed on 2026-03-25
- `assets/router/catfish_capability_ledger.json`
  - capability memory used to score future routes
- `tools/catfish_route_core.py`
  - merge registry, health, and ledger into a route decision
- `tools/catfish_route_eval.py`
  - CLI utility for route evaluation and health inspection

## Provider Registry Shape

Each provider carries:

- stable identity
- runtime wire settings
- machine allow-list
- routing weight
- per-tier model defaults
- optional env-backed base URL

The registry currently represents:

- `ucloud-modelverse`
- `smartaipro`
- `molus`

The live 2026-03-25 health model is:

- `ucloud-modelverse`
  - working
  - endpoint reachable
  - Responses API verified
  - verified models: `gpt-5.4`, `gpt-5.3-codex`
- `smartaipro`
  - endpoint reachable
  - quota exhausted
  - route-blocked until quota recovers
- `molus`
  - endpoint reachable
  - quota exhausted
  - route-blocked until quota recovers

## How The Route Is Chosen

The route evaluator first maps task input into a reasoning tier:

| difficulty | tier | reasoning length |
| --- | --- | --- |
| `low` | `quick` | `short` |
| `medium` | `balanced` | `medium` |
| `high` | `deep` | `long` |

Task category can override that default tier:

- `research` -> `deep`
- `builder` -> `deep`
- `monitor` -> `balanced`
- `summary` -> `quick`
- `review` -> `balanced`

After the tier is chosen, each provider is evaluated in three passes:

1. Eligibility
   Providers are rejected if they are disabled, disallowed on the machine, missing the requested tier, or blocked by current health.
2. Health base score
   A healthy reachable provider starts with a higher base score. Quota exhaustion and unreachable endpoints create blocking issues.
3. Capability-memory adjustment
   Matching ledger entries add or subtract score based on task category, difficulty, reasoning tier, reasoning length, parent score similarity, recency, and confidence.

## Parent-Node Scoring

The `parentScore` field is the bridge from upstream task scoring into future provider choice.

Interpretation:

- low parent score
  - the parent node is weak or exploratory
  - prefer cheap or quick routes if the ledger says they work
- mid parent score
  - the parent node is promising but not locked in
  - balanced tiers can win if their ledger history is strong
- high parent score
  - the parent node is important enough to justify expensive reasoning
  - providers with successful deep-task history receive an extra boost

Implementation detail:

- each ledger entry stores one historical `parentScore`
- the evaluator computes similarity between the current parent score and the stored one
- a close match increases that ledger entry’s contribution
- a distant match still counts, but with less weight

That means future provider choice does not only depend on today’s health. It also depends on whether that provider has succeeded before under parent nodes of similar importance.

## Health And Evaluation Utility

Health summary:

```bash
python tools/catfish_route_eval.py health
```

Example route evaluation:

```bash
python tools/catfish_route_eval.py evaluate \
  --machine dev-intern-02 \
  --task-category research \
  --difficulty high \
  --parent-score 0.92
```

The evaluator returns a JSON payload with:

- the chosen provider
- its model and reasoning effort
- provider override fields compatible with the remote subagent launcher
- blocking issues on rejected providers
- top ledger matches that affected the score

## Operational Notes

- `ucloud-modelverse` is the only launchable provider in the 2026-03-25 snapshot.
- `smartaipro` and `molus` remain in the registry so the route layer can recover immediately once their quota state changes.
- Base URLs can be supplied via environment variables so the registry remains usable in repo form without private endpoint leakage.
