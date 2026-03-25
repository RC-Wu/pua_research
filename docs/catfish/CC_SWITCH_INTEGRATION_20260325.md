# CC-Switch Integration Notes

## Latest Stable State Inspected

- Repository tip inspected: `0e3cc0e` on `main` and `origin/main`
- No release tags are present, so the practical stable state is the current `main` tip
- The latest changes harden remote route fallback and provider-level override handling instead of introducing a full control-center product

## What cc-switch Already Solves Well

The current repo already has two useful pieces:

- `tools/codex_route_preview.py` gives deterministic profile selection from machine, task kind, difficulty, credit floor, and health
- `skills/skills-codex/remote-codex-subagents/scripts/remote_codex_subagents.py` already knows how to:
  - inject provider overrides into Codex CLI config
  - bind a provider to an API-key env var or key file
  - rotate to the next route when logs show auth, quota, or rate-limit failures

That is the useful core of `cc-switch` today. The heavier UI and runtime timeline layers are intentionally not in this repo.

## Comparison To Existing Routing In This Repo

Before this integration, the routing story was split:

- the preview tool selected a profile, model tier, and reasoning effort
- the remote launcher handled provider overrides and credential routing
- there was no single Catfish-friendly config shape that could drive both halves

That gap matters more than adding another web UI. CatfishResearch needs one config that can describe provider identity, model tiers, credentials, and health state, then feed both preview and launch-time fallback.

## Implemented Bridge

Added `tools/cc_switch_bridge.py` with three functions exposed as CLI subcommands:

- `export-control-plane`
  - translates a Catfish-style `providers[]` config into the lightweight `routing + profiles[]` shape consumed by `codex_route_preview.py`
- `preview`
  - reuses the existing route-selection logic, then enriches the selected route with provider and credential metadata
- `export-route-specs`
  - emits ordered route specs for `remote_codex_subagents.py --route-spec-file`, with the chosen healthy route first and additional healthy fallbacks after it

Supported Catfish-oriented config fields:

- top-level `routing`
- top-level `tierDefaults` or `tierPresets`
- per-provider `provider`
  - `name`, `displayName`, `baseUrl`, `wireApi`, `requiresOpenaiAuth`
- per-provider `credentials`
  - `envKey`, `keyFile`, `accountKey`
- per-provider `tierOverrides` or `modelTiers`
- per-provider `health`, `credit`, `routingWeight`, `machineIds`, `allowSelection`

This keeps the new work small and lets Catfish use the existing route preview and route-rotation code instead of duplicating it.

## Example Workflow

Preview the selected Catfish route:

```bash
python tools/cc_switch_bridge.py preview \
  --config tools/examples/cc_switch.catfish.example.json \
  --machine dev-intern-02 \
  --task-kind research \
  --difficulty medium
```

Export route specs for the remote launcher:

```bash
python tools/cc_switch_bridge.py export-route-specs \
  --config tools/examples/cc_switch.catfish.example.json \
  --machine dev-intern-02 \
  --task-kind research \
  --difficulty medium > /tmp/catfish-routes.json
```

Then pass that file to the existing launcher:

```bash
python skills/skills-codex/remote-codex-subagents/scripts/remote_codex_subagents.py launch \
  --run-id catfish-demo \
  --agent-name bridge-check \
  --cwd /dev_vepfs/rc_wu/repos/pua_research_worktrees/cc_switch \
  --prompt-text "Smoke test" \
  --route-spec-file /tmp/catfish-routes.json
```

## Borrowed vs Rejected

Borrowed:

- weighted provider selection from remaining credit and routing weight
- health gating before launch
- explicit profile locking and operator-selectable profiles
- provider-specific base URL, env-key, and key-file routing
- fallback route ordering for auth or quota failures
- shared difficulty-to-tier mapping

Rejected for now:

- vendoring a UI-heavy control center
- new persistent health-check daemons or event buses
- a separate credential storage subsystem
- modifying `remote_codex_subagents.py` directly when JSON route specs already provide the integration seam
- copying large upstream structures that do not improve CatfishResearch immediately

## Why This Is The Right Size

This bridge gives CatfishResearch the missing contract between config, preview, and provider fallback while keeping the repo aligned with the lightweight control-plane design already documented in `docs/CODEX_CONTROL_PLANE.md`. It avoids bulk vendoring and only adds the material pieces Catfish can use now.
