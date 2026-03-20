---
name: heartbeat-subagent-template
description: Scaffold and launch a heartbeat-style remote Codex subagent that periodically checks a long-running task, appends markdown status notes, and only restarts workers when safe.
---

# Heartbeat Subagent Template

## Trigger

- Use this when a long-running remote task needs a heartbeat monitor.
- Use this when you want a Codex subagent to wake on a cadence, inspect logs, processes, or output paths, and append a markdown note.
- Use this together with `remote-codex-subagents` when the monitor should run detached on `dev-intern-02`.

## Inputs

- `cwd`: remote working directory
- `note_path`: markdown note file the heartbeat agent appends to
- `interval_minutes`: polling cadence
- `task_line`: one or more plain-language task statements
- `watch_path`: important files or directories to inspect
- `watch_process`: important processes or command fragments to verify
- `intervention_rule`: guardrails for when restart or repair is allowed
- `stop_condition`: conditions under which the monitor should stop
- `output`: local prompt file path

## Workflow

1. Decide the exact remote `cwd`, note file, cadence, and stop conditions.
2. Generate a prompt file with `scripts/scaffold_heartbeat_prompt.py`.
3. Launch the remote worker with `remote-codex-subagents`.
4. Verify `status` and `tail`.
5. Confirm the note file or stdout shows the first monitoring pass.

## Script Interface

```bash
python <CODEX_HOME>/skills/heartbeat-subagent-template/scripts/scaffold_heartbeat_prompt.py \
  --cwd /remote/repo \
  --note-path /remote/task/heartbeat.md \
  --interval-minutes 30 \
  --task-line "Monitor bucket pipelines" \
  --watch-path /remote/logs \
  --watch-process run_bucket_sequence.py \
  --stop-condition "All final outputs exist" \
  --output /local/path/to/heartbeat_prompt.md
```

## Launch Pattern

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py launch \
  --host dev-intern-02 \
  --run-id <run_id> \
  --agent-name <agent_name> \
  --cwd <cwd> \
  --sandbox danger-full-access \
  --approval never \
  --prompt-file <prompt_file>
```

## Validation

- The scaffold script writes the expected prompt file.
- The launched agent reaches `state=starting` or `running`.
- `tail` shows the first turn beginning.
- The remote markdown note receives a timestamped section, or the log shows a clear first-pass action.

## User-Learned Best Practices & Constraints

> **Auto-Generated Section**: This section is maintained by `skill-evolution-manager`. Do not edit manually.

### User Preferences

- For overnight training monitors, pair the heartbeat subagent with a simpler host-side fallback when the job is important enough that a stalled monitor is unacceptable.

### Known Fixes & Workarounds

- Do not define the stop condition from cache thresholds or controller activity alone; require real training progress such as step advancement, `metrics.csv` creation, checkpoint creation, or validation markers from the target run log.
- For shared Volc controller workflows, the monitor should treat repeated controller misses conservatively and avoid auto-submitting duplicate controller tasks after a single failed status check.

### Custom Instruction Injection

When building a heartbeat prompt for overnight training, define the stop condition around concrete evidence from the target run log or outputs, not around upstream cache preparation or controller liveness alone.
