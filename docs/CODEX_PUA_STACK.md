# Codex PUA Stack

This repository packages the remote ARIS working tree that was live on `dev-intern-02` at commit `405eaf5` and keeps the original ARIS layout intact. The added layer is Codex-first orchestration: PUA execution discipline, AgentDoc startup bridging, remote subagents, heartbeat monitoring, final-summary workers, peer review, and account-aware routing.

## Bundled Extensions

- `skills/skills-codex/agentdoc-startup`
  - loads an external AgentDoc checkout, selects the correct startup variant from `Prompt.md`, and enforces Git preflight plus machine routing
- `skills/skills-codex/pua-complex-task-method`
  - forces high-agency execution for multi-phase tasks
- `skills/skills-codex/remote-codex-subagents`
  - launches detached remote `codex exec` workers over SSH
- `skills/skills-codex/heartbeat-subagent-template`
  - scaffolds recurring monitor prompts for long-running tasks
- `skills/skills-codex/final-summary-subagent`
  - scaffolds final-report workers that roll up notes and logs
- `skills/skills-codex/peer-review`
  - structured manuscript and grant review with checklists and reporting-standard references

## What Is Deliberately Not Bundled

- the full AgentDoc corpus
- AgentDoc secrets, local registries, or machine-specific auth state
- your private `~/.codex` profiles

This repo provides the bridge points and public docs, but AgentDoc remains an external dependency.

## Codex-First Routing Model

The route-selection layer maps task intent to reasoning depth:

| difficulty | tier | default reasoning |
| --- | --- | --- |
| `low` | `quick` | `medium` |
| `medium` | `balanced` | `high` |
| `high` | `deep` | `xhigh` |

Task kind can override difficulty. A common default is:

- `research` -> `deep`
- `builder` -> `deep`
- `monitor` -> `balanced`
- `summary` -> `quick`
- `review` -> `balanced`

Use [`docs/CODEX_CONTROL_PLANE.md`](CODEX_CONTROL_PLANE.md) and `tools/codex_route_preview.py` to preview the final profile, model, reasoning effort, and browser or search mode before launch.

## Remote Execution Pattern

1. Install skills into `~/.codex/skills`.
2. Use `remote-codex-subagents` to launch the main worker.
3. If the task is long-running, generate a heartbeat prompt and launch a monitor worker.
4. When the run finishes, launch a final-summary worker to roll up logs and notes.

This gives you:

- one run root per wave
- one prompt and one status file per agent
- detached execution on `dev-intern-02`
- auditable logs and last-message capture

## Recommended Install

```bash
git clone https://github.com/RC-Wu/pua_research.git
cd pua_research
mkdir -p ~/.codex/skills
cp -r skills/skills-codex/* ~/.codex/skills/
```

After installation:

- start with `agentdoc-startup` when AgentDoc routing matters
- apply `pua-complex-task-method` on any multi-step task
- use the ARIS research workflows as usual
- reach for `peer-review` when the output needs reviewer-style feedback rather than internal critique
