# Catfish Production Runtime Guard 20260328

This note documents the dry-run-first runtime guard path that supervises CatfishResearch state roots without directly mutating downstream projects.

## Purpose

The production guard layer has two jobs:

1. Inspect a Catfish `state-root` and compute fresh runtime metrics.
2. Derive a file-backed supervisor plan that can be reviewed before any writeback happens.

The guard layer does not restart processes itself. It records restart intent and writes safe state files only when an operator explicitly asks it to.

## Workflow

1. Run the probe in dry-run mode.

```bash
python tools/catfish_guardrail_probe.py \
  --state-root /path/to/catfish-state-root \
  --root-dir /path/to/root-budget-scope \
  --vepfs-root /path/to/vepfs-budget-scope \
  --cpu-percent 12.5
```

2. Review the JSON plan.

The probe reports:

- `runtime_metrics`
- `guardrail_state`
- `supervisor_state`
- `plan`

3. Apply only the safe file-backed state changes when ready.

```bash
python tools/catfish_supervisor_ctl.py \
  --state-root /path/to/catfish-state-root \
  --plan-file /path/to/probe-output.json \
  --apply
```

## Safety Model

- The default mode is dry-run.
- Runtime metrics and supervisor state are written only when explicit flags are present.
- The writer only touches files under the selected `state-root`.
- The control layer does not kill processes, restart containers, or mutate downstream project source trees.

## Observed Limits

- `rootDirUsageBytes` should stay at or below `20 MiB`.
- `vePfsUsageBytes` should stay at or below `50 GiB`.
- CPU budget is controlled through policy and should remain low enough to keep SSH access responsive.
- GPU, storage, and CPU ownership must remain manager-owned in the resource manager state.
- AgentDoc cadence is a first-class guardrail and should be recorded in the state tree.

## Validation

The current test coverage exercises:

- dry-run probing without file writes
- explicit runtime metrics and supervisor-state writeback
- plan application into a state-root with safe file-backed writes

