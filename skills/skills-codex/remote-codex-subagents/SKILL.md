---
name: remote-codex-subagents
description: Launch, monitor, and summarize remote Codex CLI subagents over SSH, especially on `dev-intern-02`, with per-agent prompt files, detached execution, logs, status files, and a reusable run directory layout.
---

# Remote Codex Subagents

## Overview

Use this skill to orchestrate detached `codex exec` workers on a remote Linux machine from the local PC. It is built for the current `dev-intern-02` setup where:

- the live Codex auth state is under `/dev_vepfs/rc_wu/.codex`
- the remote Codex binary is not in `PATH`
- the binary must be stored on `vePFS` but executed from an exec-capable path such as `/tmp`

The skill gives you a stable run layout, a launcher, and status or tail commands so you can split a large task into multiple remote Codex workers without losing logs or outputs.

On `dev-intern-02`, the launcher can also bootstrap a user-owned fallback proxy on `127.0.0.1:27890/27891` from `/dev_vepfs/rc_wu/software/clash/config.yaml` before starting workers, because the root-managed machine proxy on `127.0.0.1:7890` may be present but transport-broken for `chatgpt.com/backend-api/codex/*`.

## When To Use

- you want to launch one or more remote Codex workers on `dev-intern-02`
- a long task should be split into independent subtasks with separate prompts and logs
- you need a recurring heartbeat worker
- you want a final worker that summarizes outputs after all shards finish
- you need a durable audit trail of prompts, pids, logs, and last messages for remote Codex runs

## Run Layout

```text
/dev_vepfs/rc_wu/codex_subagents/<run_id>/<agent_name>/
|- prompt.md
|- launch.json
|- run_agent.sh
|- pid
|- status.json
|- stdout.log
`- last_message.txt
```

Use one `run_id` per orchestration wave. Put each independent worker under its own `agent_name`.

## Workflow

### 1. Install Or Refresh The Remote Binary

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py install \
  --host dev-intern-02
```

This copies the local Linux `codex` binary from the current VS Code extension into `/dev_vepfs/rc_wu/bin/codex`.

### 2. Prepare The Prompt

Prefer a prompt file for non-trivial runs. Include:

- the exact task
- the exact working directory
- expected outputs and file paths
- success criteria
- stopping conditions

### 2.5 Ensure The dev-intern-02 Proxy

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py ensure-proxy \
  --host dev-intern-02
```

### 3. Launch A Detached Worker

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py launch \
  --host dev-intern-02 \
  --run-id 20260320_demo \
  --agent-name shard-000 \
  --cwd /dev_vepfs/rc_wu/project \
  --sandbox danger-full-access \
  --prompt-file /local/path/to/prompt.md
```

By default the launcher:

- sets `HOME=/dev_vepfs/rc_wu` so remote Codex uses `/dev_vepfs/rc_wu/.codex`
- exports `CODEX_HOME=/dev_vepfs/rc_wu/.codex`
- if `OPENAI_API_KEY` is missing but `/dev_vepfs/rc_wu/.codex/aris_primary_api_key.txt` exists, loads the key from that file as a fallback
- copies `/dev_vepfs/rc_wu/bin/codex` to a temp executable under `/tmp`
- ensures the fallback proxy is listening on `127.0.0.1:27890/27891` unless disabled
- auto-promotes `workspace-write` to `danger-full-access` on `dev-intern-02` unless disabled
- runs `codex exec --skip-git-repo-check`
- writes JSON logs to `stdout.log`
- writes the final message to `last_message.txt`
- persists a `status.json`

### 4. Check Status

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py status \
  --host dev-intern-02 \
  --run-id 20260320_demo
```

### 5. Tail Logs

```bash
python <CODEX_HOME>/skills/remote-codex-subagents/scripts/remote_codex_subagents.py tail \
  --host dev-intern-02 \
  --run-id 20260320_demo \
  --agent-name shard-000 \
  --lines 80
```

## Practical Defaults For `dev-intern-02`

- `--host dev-intern-02`
- `--remote-home /dev_vepfs/rc_wu`
- `--remote-binary-store /dev_vepfs/rc_wu/bin/codex`
- `--remote-run-root /dev_vepfs/rc_wu/codex_subagents`
- `--ensure-dev02-proxy`
- `--proxy-http-port 27890`
- `--proxy-socks-port 27891`
- `--sandbox danger-full-access`

## Validation

1. Run `install`.
2. Run `ensure-proxy`.
3. Launch a tiny worker that replies with a fixed token.
4. Run `status`.
5. Run `tail`.
6. Confirm `last_message.txt` contains the expected token.

## References

- `references/dev_intern_02_notes.md`
- [`docs/CODEX_PUA_STACK.md`](../../../docs/CODEX_PUA_STACK.md)
- [`docs/AGENTDOC_BRIDGE.md`](../../../docs/AGENTDOC_BRIDGE.md)

## User-Learned Best Practices & Constraints

> **Auto-Generated Section**: This section is maintained by `skill-evolution-manager`. Do not edit manually.

### User Preferences

- For forwarding-machine tasks, separate controller validation from real training launch: first prove queue-to-done on a tiny smoke, then enqueue the heavier training wave.

### Known Fixes & Workarounds

- When launching `dev-intern-02` workers, explicitly say to use `find` or `grep` or `sed` fallbacks and not assume `rg` or git metadata are available in the remote workspace copy.
- If ML Platform container-log APIs are permission-blocked, validate the forwarding-machine controller by queueing a tiny smoke job and inspecting `jobs/done/*.result.json` plus `logs/jobs/*.log`.
- When several workers share one Volc controller queue, inspect `controller_state.json` first and neutralize conflicting readiness probes before submitting overlapping launch jobs.

### Custom Instruction Injection

When launching remote Codex workers on `dev-intern-02`, say explicitly that `rg` may be unavailable and the repo mirror may not be a git root; tell the worker to use `find` or `grep` or `sed` fallbacks and to inspect shared queue or controller state before submitting launch jobs.
