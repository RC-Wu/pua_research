# Codex Control Plane

To keep this repository structurally close to ARIS, the full UI-heavy control plane is not vendored here. Instead, this repo ships the core route-preview logic and a portable example config.

## Included Files

- `tools/codex_route_preview.py`
- `tools/examples/control_plane.example.json`
- `tools/tests/test_codex_route_preview.py`

## What The Preview Tool Solves

- selects a launch profile based on machine, task kind, difficulty, credit floor, and health
- maps low, medium, and high difficulty to `quick`, `balanced`, and `deep` tiers
- maps tiers to model, reasoning effort, and search mode
- respects explicit profile choice and task-level profile locks

## Example

```bash
python tools/codex_route_preview.py \
  --config tools/examples/control_plane.example.json \
  --machine dev-intern-02 \
  --task-kind research \
  --difficulty medium
```

## Config Shape

The example config is intentionally small. Each profile carries:

- `machineIds`
- `credit.remaining`
- `credit.reserveFloor`
- `routingWeight`
- `health.available`
- `health.verified`
- `modelTiers.quick|balanced|deep`

That is enough to decide whether a profile is eligible and what tier it should use.

## Why This Is Enough For This Repo

The goal here is to make Codex routing reproducible inside an ARIS-like project without dragging in a separate control-plane product. If you need a persistent web UI, runtime timelines, event buses, or multi-machine session indexing, move up to a dedicated control-plane repo and keep this project as the skill-and-doc layer.
