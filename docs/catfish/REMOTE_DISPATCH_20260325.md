# Catfish Remote Dispatch

## Scope

`tools/catfish_remote_dispatch.py` is the execution bridge between Catfish project/runtime JSON state and the existing remote Codex launcher at `skills/skills-codex/remote-codex-subagents/scripts/remote_codex_subagents.py`.

The bridge does three things:

1. read a Catfish dispatch-state file that includes project metadata, runtime state, and one or more stage requests
2. choose launchable provider routes using the Catfish provider registry, health snapshot, and capability ledger
3. materialize competitive candidate launches, runtime updates, and control-center-compatible state without requiring a new scheduler service

The implementation is file-backed and replayable. Tests validate dry-run planning and launch-spec generation without launching real waves.

## Input Contract

The dispatch tool consumes a JSON object with these top-level keys:

- `project`
- `runtime`
- `stages`

Recommended schema version:

```json
{
  "schemaVersion": "catfish.dispatch-state.v1"
}
```

### `project`

Required or strongly recommended fields:

- `projectId`
- `workspaceRoot`
- `defaultMachineId`
- `launchDefaults`

`launchDefaults` mirrors the remote launcher contract where useful:

- `host`
- `remoteHome`
- `remoteBinaryStore`
- `remoteRunRoot`
- `sandbox`
- `approval`
- `search`
- `skipInstall`
- `addDir`

Optional `agentGroups` define the competitive team bundles the stage planner should mix.

### `runtime`

Supported forms:

- `runtime.operations`
  Use the same operation objects accepted by `tools/catfish_runtime.py`.
- `runtime.snapshot`
  Use a previously materialized Catfish runtime snapshot.

The bridge validates that every stage parent node already exists in this runtime state. It then emits additional operations that can be replayed by `CatfishRuntime`.

### `stages`

Each stage describes one competition cell expansion request. Important fields:

- `stageId`
- `competitionId`
- `parentNodeId`
- `taskCategory`
- `difficulty`
- `parentScore`
- `candidateCount`
- `cwd`
- `promptText` or `promptFile`

Optional stage-level controls:

- `dispatchRunId`
- `branchPrefix`
- `competitionCellPrefix`
- `competitionCellIds`
- `branchIds`
- `machineId`
- `requestedTier`
- `requestedModel`
- `resourceBudget`
- `agentGroups`
- `dispatch`
- `launch`

`dispatch` lets a stage tune diversity pressure:

- `unusedProviderBonus`
- `unusedModelBonus`
- `unusedAgentGroupBonus`
- `providerRepeatPenalty`
- `modelRepeatPenalty`
- `agentGroupRepeatPenalty`
- `bundleRepeatPenalty`

## Competition And Diversity

The bridge does not collapse a stage into one winning provider route. It plans one launch per candidate cell and keeps them as siblings under the same Catfish competition.

For each stage:

1. Catfish provider routing scores all providers using registry policy, dated health, and capability ledger matches.
2. Only launchable providers are kept in the route frontier.
3. The stage agent-group set is crossed with the provider frontier to form provider/model/agent-group bundles.
4. A diversity-aware selector chooses as many bundles as the requested `candidateCount`.

The selector preserves diversity where possible by rewarding:

- providers not yet used in the same stage
- models not yet used in the same stage
- agent groups not yet used in the same stage

It also penalizes repeated provider/model/agent-group bundles. If the frontier is smaller than the requested width, the planner still fills the stage by reusing strong bundles with repeat penalties rather than collapsing the stage to one branch.

Each candidate still receives fallback `route_specs`, ordered with its selected provider first and the remaining launchable providers behind it. That keeps competitive planning separate from runtime failover.

## Outputs

### `plan`

```bash
python3 tools/catfish_remote_dispatch.py \
  --state assets/catfish_dispatch_examples/competitive_builder_state.json \
  plan
```

This prints a JSON plan containing:

- `stagePlans`
- `runtimeOperations`
- `controlSnapshot`

### `generate`

```bash
python3 tools/catfish_remote_dispatch.py \
  --state assets/catfish_dispatch_examples/competitive_builder_state.json \
  generate \
  --output-dir /tmp/catfish_dispatch_plan
```

This writes:

- `dispatch_plan.json`
- `runtime_operations.json`
- `control_snapshot.json`
- one directory per candidate with:
  - `prompt.md`
  - `route_specs.json`
  - `launch_spec.json`

`launch_spec.json` contains the exact command-line invocation for the remote launcher script plus the resolved `agent_root`.

### `launch`

```bash
python3 tools/catfish_remote_dispatch.py \
  --state assets/catfish_dispatch_examples/competitive_builder_state.json \
  launch \
  --output-dir /tmp/catfish_dispatch_launch \
  --dry-run
```

With `--dry-run`, the tool emits the exact remote launcher commands without invoking them. Without `--dry-run`, it calls the current remote launcher script directly.

## Runtime And Control-Center Compatibility

The emitted runtime ops are valid `CatfishRuntime` mutations:

1. `upsert_agent_node` for every planned candidate node
2. `define_competition` for the full candidate sibling set
3. `record_candidate_run` for every planned run

Each run metadata payload includes:

- `branch_id`
- `competition_cell_id`
- `dispatch_wave_id`
- `remote_agent_name`
- `agent_root`
- `selected_provider_id`
- `selected_model`
- `route_specs`

The generated control snapshot uses the existing control-center field names for:

- projects
- agents
- providers
- branches
- events

That means the bridge can feed both the Catfish runtime model and the control-center model without inventing a new intermediate state format.

## Bootstrap Helper

`tools/catfish_project_bootstrap.py` creates a starter dispatch-state file from CLI arguments.

Example:

```bash
python3 tools/catfish_project_bootstrap.py \
  --output /tmp/catfish_state.json \
  --project-id catfish-remote-dispatch \
  --workspace-root /dev_vepfs/rc_wu/repos/pua_research_worktrees_wave3/remote_dispatch \
  --stage-id impl-wave-1 \
  --task-category builder \
  --difficulty high \
  --candidate-count 3 \
  --prompt-text "Implement the execution bridge."
```

The bootstrap helper writes:

- a project record
- a root parent node
- one competitive stage request

This is enough for `catfish_remote_dispatch.py` to plan candidates immediately.

## Example State

The repo includes one concrete example:

- `assets/catfish_dispatch_examples/competitive_builder_state.json`

It targets the current repository layout, uses a single root parent node, and asks for three competing implementation candidates.

## Validation

The test suite for this bridge lives in `tools/tests/test_catfish_remote_dispatch.py`.

The tests cover:

- multi-candidate planning with provider and agent-group diversity
- replayability of emitted runtime operations through `CatfishRuntime`
- launch-spec artifact generation compatible with the remote launcher contract
- bootstrap-state generation that feeds directly into the planner
