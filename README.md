# pua_research

Codex-first ARIS fork for autonomous research workflows.

This repository is based on the remote ARIS working tree that was live on `dev-intern-02` at commit `405eaf5`. It keeps the original ARIS directory layout (`docs/`, `skills/`, `mcp-servers/`, `tools/`) while making Codex the default executor and bundling the extra orchestration layer that was living in the user's local and remote setup.

## What This Fork Adds

- `agentdoc-startup`
  - bridge to an external AgentDoc checkout without vendoring AgentDoc itself
- `pua-complex-task-method`
  - high-agency execution discipline for complex tasks
- `remote-codex-subagents`
  - detached remote Codex workers over SSH, especially for `dev-intern-02`
- `heartbeat-subagent-template`
  - recurring monitor prompts for long-running tasks
- `final-summary-subagent`
  - final-report workers that roll up logs and notes
- `peer-review`
  - structured manuscript and grant review
- account-aware routing and difficulty-to-reasoning tier preview via `tools/codex_route_preview.py`

The original ARIS research workflows and Codex skill set remain in place.

## Quick Start

```bash
git clone https://github.com/RC-Wu/pua_research.git
cd pua_research

mkdir -p ~/.codex/skills
cp -r skills/skills-codex/* ~/.codex/skills/

npm install -g @openai/codex
codex setup
codex
```

Recommended entrypoints:

- `Use skill agentdoc-startup`
- `Use skill pua-complex-task-method`
- `/idea-discovery "your research direction"`
- `/experiment-bridge`
- `/auto-review-loop "your paper topic or scope"`
- `/paper-writing "NARRATIVE_REPORT.md"`
- `/research-pipeline "your research direction"`
- `Use skill peer-review`

## Key Docs

- [`docs/CODEX_PUA_STACK.md`](docs/CODEX_PUA_STACK.md)
- [`docs/AGENTDOC_BRIDGE.md`](docs/AGENTDOC_BRIDGE.md)
- [`docs/CODEX_CONTROL_PLANE.md`](docs/CODEX_CONTROL_PLANE.md)
- [`docs/CODEX_CLAUDE_REVIEW_GUIDE.md`](docs/CODEX_CLAUDE_REVIEW_GUIDE.md)
- [`docs/CURSOR_ADAPTATION.md`](docs/CURSOR_ADAPTATION.md)
- [`docs/MODELSCOPE_GUIDE.md`](docs/MODELSCOPE_GUIDE.md)

## Repo Layout

- `skills/`
  - upstream ARIS skill tree plus Codex-native skills under `skills/skills-codex/`
- `mcp-servers/`
  - ARIS MCP integrations, including the Codex/Claude review bridge
- `docs/`
  - upstream ARIS docs plus the PUA and AgentDoc bridge docs added in this fork
- `tools/`
  - upstream tooling plus the portable control-plane route preview helper

## AgentDoc Note

AgentDoc is intentionally not bundled here. This repo only packages the bridge skill and the public-facing guidance needed to consume an external AgentDoc checkout safely.

Expected external AgentDoc roots:

- local PC: `F:\InformationAndCourses\Code\AgentDoc`
- development machine: `/dev_vepfs/rc_wu/AgentDoc`

## Compatibility

- The Codex-first path is the default.
- The original ARIS-style docs and workflows are still present.
- `skills/skills-codex-claude-review/` remains available if you want Codex execution plus Claude review as an overlay instead of the fully Codex-first path.
