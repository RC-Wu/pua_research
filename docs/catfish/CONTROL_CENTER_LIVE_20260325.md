# Catfish Control Center Live State

## Purpose

`apps/catfish-control-center` no longer needs a hand-authored snapshot as its only input. It now accepts a Catfish `state-root` and synthesizes a control snapshot from live runtime, scheduler, dispatch, review, provider, and capability files.

The design stays backend-first:

- one CLI
- file-backed state contracts
- no new service dependency
- no rewrite of unrelated runtime or routing code

This keeps the control center usable on `dev-intern-02` today while matching the Catfish architecture docs.

## CLI Surface

Render the full live dashboard:

```bash
python apps/catfish-control-center/main.py \
  --state-root /path/to/catfish-state \
  --view dashboard
```

Render a focused operator view:

```bash
python apps/catfish-control-center/main.py \
  --state-root /path/to/catfish-state \
  --view stage-competitions
```

Dump a single view as JSON:

```bash
python apps/catfish-control-center/main.py \
  --state-root /path/to/catfish-state \
  --view provider-status \
  --format json
```

Supported focused views:

- `projects`
- `stage-competitions`
- `pending-reviews`
- `provider-status`
- `recent-launches`
- `capability-summaries`
- `diversity-metrics`
- `recent-events`

`--snapshot` still works for the older materialized JSON path, but `--state-root` is the live path going forward.

## Live State Contract

The loader expects a Catfish state root with this shape:

```text
<state-root>/
  system/
    scheduler_state.json
    dispatch_queue.json
    review_queue.json
    provider_registry.json
    provider_health.json
    capability_ledger.json
  projects/
    <project_id>/
      manifest.json
      runtime_snapshot.json
      events/
        *.json
        *.jsonl
```

Only `system/` plus `projects/<project_id>/manifest.json` and `runtime_snapshot.json` are important for a minimal live render. Provider files fall back to the repo-level router assets when missing.

## File Semantics

### `system/scheduler_state.json`

Used for:

- provider credit headroom
- reserve floors
- routing weights
- active launch counts
- project active stage and frontier width

### `system/dispatch_queue.json`

Used for:

- recent launches from the dispatcher
- launch status
- provider/model stack per launch

### `system/review_queue.json`

Used for:

- explicit pending review work
- review priority
- review request origin

### `projects/<project_id>/manifest.json`

Used for:

- project label and owner
- current branch and status
- branch scoreboard entries
- project summary

### `projects/<project_id>/runtime_snapshot.json`

Expected to follow the current `tools/catfish_runtime.py` snapshot shape. The control center consumes:

- nodes
- competitions
- runs
- verdicts

This is the main source for stage competition state, runtime launches, and agent capability summaries.

### `projects/<project_id>/events/*`

Used for:

- recent runtime events
- project last-activity timestamps

Both `.json` and `.jsonl` are accepted.

## How Competition Is Surfaced

The control center now surfaces competition as a first-class view instead of flattening everything into one branch scoreboard.

For every runtime competition it derives:

- `project_id`
- `stage_id` and `stage_label`
- parent owner
- advancement mode
- candidate count
- run count
- scored run count
- pending run count
- current winner
- leading score and score spread
- provider/model/agent-group stack mix
- dominant stack share

This means implementation, review, figure, ideation, or any future stage can all appear simultaneously in the control center.

## How Diversity Is Surfaced

The control center now emits a dedicated diversity view derived from each competition’s active stack mix.

For each competition it computes:

- candidate count
- unique providers
- unique models
- unique agent groups
- unique stacks
- dominant stack share
- wildcard count for `top-k-survival` style competitions with real stack variation

This is intentionally stage-local. The operator can see whether a stage is collapsing onto one repeated stack even if the branch scoreboard still looks healthy.

## Pending Review Behavior

Pending reviews come from two sources:

1. explicit review queue entries from `system/review_queue.json`
2. synthetic runtime review items for competitions whose runs exist but still lack a parent verdict

That second class matters because Catfish review pressure is often implicit in the runtime before it is mirrored into a queue.

## Capability Summaries

Capability summaries combine:

- agent capability summaries from runtime node state
- provider capability memories from the Catfish capability ledger

This lets the operator compare child-node judged capability state with provider-level routing memory in one CLI.

## Provider Status

Provider status now merges:

- provider registry metadata
- provider health observations
- scheduler-side budget state
- active launch counts

The rendered view shows:

- health classification
- quota headroom versus reserve floor
- routing weight
- active launches
- verified models
- issues

## Testing

`apps/catfish-control-center/tests/test_control_center.py` now builds a temporary live `state-root` and verifies:

- live state ingestion
- stage competition extraction across multiple stages
- pending review synthesis
- provider status rendering
- recent launch extraction from dispatch and runtime files
- capability summary extraction
- diversity metric computation
- CLI `--state-root` handling
