# AgentDoc Bridge

This repository does not vendor AgentDoc. Instead, it bundles the minimum Codex-side bridge needed to consume an external AgentDoc checkout safely.

## Expected External Roots

- Local PC: `F:\InformationAndCourses\Code\AgentDoc`
- Development machine: `/dev_vepfs/rc_wu/AgentDoc`

If your checkout lives elsewhere, resolve `<AGENTDOC_ROOT>` first and substitute that path consistently.

## What The Bridge Preserves

- startup via `Prompt.md` instead of memory-only paraphrase
- Git preflight before task work
- machine naming and routing conventions for `PC`, `dev-intern-01`, and `dev-intern-02`
- workspace write boundaries
- storage-preflight rules before touching `/shared-dev`, `/dev_vepfs`, or `/dev/shm`
- runtime checkpoint capture before formal docs
- preference for reusable skill capture over one-off dated notes

## What The Bridge Does Not Preserve

- the full AgentDoc document library
- project registries or skill sync registries
- secrets or auth material
- any assumption that this repo can replace AgentDoc as your canonical ops notebook

## Research-Oriented AgentDoc Behaviors Kept Here

- startup contract selection from `Prompt.md`
- project-doc initialization guidance for a new repo
- multi-machine routing for local PC vs development machine work
- remote rollout hygiene for GitHub plus SSH flows
- controller and forwarding-machine escalation points

## Practical Use

1. Install the bundled Codex skills from this repo.
2. Keep AgentDoc checked out separately on the machines that need it.
3. Trigger `agentdoc-startup`.
4. Let the skill select the right startup variant from the external `Prompt.md`.
5. Continue the task inside this repo or another project repo, while AgentDoc stays the external policy source of truth.

## Related Files

- [`skills/skills-codex/agentdoc-startup/SKILL.md`](../skills/skills-codex/agentdoc-startup/SKILL.md)
- [`docs/CODEX_PUA_STACK.md`](CODEX_PUA_STACK.md)
