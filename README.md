# Claude Code Research Skills

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous ML research workflows. These skills orchestrate **cross-model collaboration** — Claude Code drives the research while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer.

## What's Inside

### `/research-review` — Single-Round Deep Review

Get a multi-round critical review of your research from an external LLM with maximum reasoning depth.

**What it does:**
1. Automatically gathers your project context (narrative docs, experiment results, memory files)
2. Sends a comprehensive briefing to the external reviewer (xhigh reasoning)
3. Facilitates iterative dialogue — push back on criticisms, request experiment designs, get claims matrices
4. Documents everything in a self-contained review file

**Trigger:** `"review my research"`, `"help me review"`, `"get external review"`

### `/auto-review-loop` — Autonomous Multi-Round Review-Fix Loop

The main event. Autonomously loops: **review → implement fixes → re-review**, until the reviewer gives a positive assessment or 4 rounds are reached.

**What it does:**
1. Gets a scored review (1-10) with ranked weaknesses
2. Automatically implements fixes — writes code, runs experiments on remote GPUs, rewrites narratives
3. Re-submits to the reviewer with updated results
4. Repeats until score threshold is met or max rounds exhausted
5. Logs every round in a cumulative `AUTO_REVIEW.md`

**Trigger:** `"auto review loop"`, `"review until it passes"`

## Score Progression (Real Run)

A real 4-round run on an ML research project, going from borderline reject to submission-ready:

![Score Progression](auto_review_score_curve.png)

| Round | Score | Key Change |
|-------|-------|------------|
| Initial | 5.0/10 | Borderline reject |
| Round 1 | 6.5/10 | Added standard metrics, discovered metric decoupling |
| Round 2 | 6.8/10 | Key claim failed to reproduce, pivoted narrative |
| Round 3 | 7.0/10 | Large seed study killed main improvement claim |
| Round 4 | **7.5/10** | Diagnostic evidence solidified, **submission ready** |

The loop autonomously ran 20+ GPU experiments, rewrote the paper's narrative framing, and killed claims that didn't hold up — all without human intervention.

## Setup

### Prerequisites

1. [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
2. [Codex CLI](https://github.com/openai/codex) installed and configured as MCP server:
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```

### Install Skills

Copy the skill directories to your Claude Code skills folder:

```bash
# Global (available in all projects)
cp -r skills/research-review ~/.claude/skills/
cp -r skills/auto-review-loop ~/.claude/skills/

# Or project-local (available only in one project)
cp -r skills/research-review .claude/skills/
cp -r skills/auto-review-loop .claude/skills/
```

### Usage

In Claude Code:

```
> /research-review my diffusion model paper
> /auto-review-loop ML paper on training dynamics
```

### Auto-Allow (Optional)

To run the auto-review loop without clicking permission prompts, add these to your `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__codex__codex-reply",
      "Write",
      "Edit",
      "Skill(auto-review-loop)"
    ]
  }
}
```

## How It Works

```
┌─────────────────────────────────────────────────┐
│                 Claude Code                      │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │  Read     │    │  Write   │    │  SSH to  │   │
│  │  project  │───▶│  code &  │───▶│  GPU     │   │
│  │  context  │    │  scripts │    │  server  │   │
│  └──────────┘    └──────────┘    └──────────┘   │
│       │                               │          │
│       ▼                               ▼          │
│  ┌──────────────────────────────────────────┐    │
│  │         Codex MCP (External LLM)         │    │
│  │                                          │    │
│  │  Round 1: "Score 5/10. Weaknesses: ..."  │    │
│  │  Round 2: "Score 6.5. Better, but ..."   │    │
│  │  Round 3: "Score 7.0. Almost there..."   │    │
│  │  Round 4: "Score 7.5. Ready."            │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

The key insight: **Claude Code handles execution** (reading files, writing code, running experiments, collecting results) while **the external LLM handles evaluation** (scoring, identifying weaknesses, suggesting fixes). This separation creates a genuine feedback loop — neither model is grading its own work.

## Customization

The skills are plain Markdown files. Customize by editing:

- **`MAX_ROUNDS`** — increase for more thorough iteration (default: 4)
- **`POSITIVE_THRESHOLD`** — adjust the stop condition score
- **Prioritization rules** — change compute limits, what fixes to skip
- **Prompt templates** — tailor the review persona and evaluation criteria
- **`allowed-tools`** — restrict or expand what the skill can do

## License

MIT
