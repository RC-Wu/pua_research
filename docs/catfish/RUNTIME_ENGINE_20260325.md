# Catfish Runtime Engine

## Scope

This runtime is a deliberately small core for hierarchical competing agents. It is meant to provide the state model and mutation rules that a future control center can drive, inspect, and persist. It is not a scheduler, queue manager, or UI.

The implementation lives in `tools/catfish_runtime.py` and stays within the standard library so it can be embedded in other repos or wrapped by a higher-level service later.

## Core Models

The runtime exposes machine-readable dataclass models for:

- `Project`: project metadata, top-level resource budget, default provider and model assignment
- `AgentNode`: node identity, parent-child graph, per-node budget, provider assignment, capability summaries
- `Competition`: the parent node, participating child nodes, scoring policy, and latest winner
- `CandidateRun`: a child submission inside a competition, including resource usage and the parent score once judged
- `ParentVerdict`: the parent-authored scoring event for a competition plus capability updates
- `CapabilityUpdate` and `CapabilitySummary`: raw parent feedback and the aggregated state stored on each child
- `ResourceBudget`, `ResourceUsage`, and `ProviderAssignment`: shared value objects used across the models

## Runtime Operations

`CatfishRuntime` supports five mutations:

1. `register_project`
2. `upsert_agent_node`
3. `define_competition`
4. `record_candidate_run`
5. `apply_parent_verdict`

These are enough to model the loop:

1. declare a project and its budgets
2. register a parent node and child agents
3. define which siblings are competing under which parent
4. record candidate runs produced by the children
5. let only the parent score those runs and push capability updates back down

## Parent-Only Scoring Contract

The scoring policy is intentionally strict:

- each competition declares `scoring_policy="parent-only"`
- every candidate in a competition must already be registered as a child of the competition parent
- a `ParentVerdict` is rejected unless its `parent_node_id` exactly matches the competition parent
- each scored run must already exist and belong to that competition

This gives the runtime a concrete, auditable rule for hierarchical selection without introducing cross-agent voting or global ranking logic yet.

## Capability Update Flow

Capability updates are attached to a parent verdict. Each update contains:

- `node_id`
- `capability`
- `score`
- `summary`
- `confidence`

The runtime stores only the aggregated summary on the node:

- sample count
- running average score
- last score
- last textual summary
- last parent node id
- update timestamp

That keeps the hot state compact while preserving enough information for a future UI to show trend lines and the most recent parent judgment.

## Snapshot Shape

`runtime.snapshot()` returns a JSON-serializable structure with:

- `schema_version`
- `generated_at`
- `projects`

Each project snapshot contains:

- the project record
- `root_node_ids`
- `nodes`
- `competitions`
- `runs`
- `verdicts`

The snapshot uses stable ids as map keys so a future control center can diff state cheaply and subscribe to narrow parts of the graph.

## CLI Skeleton

The module also provides a minimal CLI:

```bash
python tools/catfish_runtime.py --ops /path/to/ops.json --project-id proj-alpha
```

The operations file is either:

- a JSON list of operation objects
- or an object with an `operations` list

Supported operation names match the runtime mutation methods. The CLI applies them in order and prints a final snapshot as JSON.

## Intentionally Omitted

The runtime does not yet attempt to solve:

- durable storage or event replay from disk
- asynchronous scheduling
- worker lifecycle management
- retries, leases, or locks
- multi-parent consensus scoring
- UI rendering

Those concerns can be added later around this core without changing the basic state model for projects, nodes, competitions, runs, and parent verdicts.
