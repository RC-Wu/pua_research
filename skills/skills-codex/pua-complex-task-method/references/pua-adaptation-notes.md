# PUA Adaptation Notes

## Source Snapshot

- Source repo: `https://github.com/tanweai/pua`
- Accessed: `2026-03-19`
- Primary files reviewed:
  - `README.md`
  - `codex/pua/SKILL.md`

The extracted goal is to prevent passive assistant behavior on hard tasks and replace it with an execution-first discipline.

## Extracted Core

- Stop handing doable work back to the user.
- Stop stalling on non-critical missing details when safe assumptions exist.
- Prefer direct implementation and verification over explanatory filler.
- Count repeated failure and escalate instead of looping.
- Split hard work into independent units so the critical path keeps moving.

## Mapping To This Runtime

- In this environment, treat every `complex_task` as a mandatory PUA activation, not only a post-failure recovery step.
- Use real subagents only when platform rules allow them and the user explicitly authorizes delegation.
- When subagents are unavailable, preserve the same mindset by doing local branch decomposition and comparative verification.
- Keep user-facing communication direct and respectful; do not mirror the repo's aggressive rhetoric.

## AgentDoc Integration Points

- Policy: `POLICIES/coding/complex_task_pua_activation_policy.md`
- Startup entry: `Prompt.md`
- Startup templates: `PLAYBOOKS/tools/agent_startup_prompt_templates.md`
- Registry mirror: `PROJECTS/AgentDoc/assets/codex_skill_sync/registry/skills/pua-complex-task-method/`
