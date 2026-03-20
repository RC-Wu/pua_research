---
name: final-summary-subagent
description: Scaffold and launch a remote Codex subagent that reads accumulated logs, notes, and output paths for a long-running task, then writes one final markdown summary.
---

# Final Summary Subagent

## Trigger

- Use this when a long-running remote task needs one final summary worker.
- Use this when the task history is spread across multiple markdown notes, logs, and artifact directories.
- Use this together with `remote-codex-subagents` when the summary should be produced on `dev-intern-02`.

## Inputs

- `cwd`: remote working directory
- `history_path`: one or more notes or log paths to read first
- `output_summary_path`: remote markdown file the summary worker writes
- `required_section`: sections that must appear in the final report
- `output`: local prompt file path

## Workflow

1. Decide which notes and logs are canonical history.
2. Generate a prompt file with `scripts/scaffold_summary_prompt.py`.
3. Launch the remote worker with `remote-codex-subagents`.
4. Verify `status` and `tail`.
5. Confirm the remote summary file exists and contains the required sections.

## Script Interface

```bash
python <CODEX_HOME>/skills/final-summary-subagent/scripts/scaffold_summary_prompt.py \
  --cwd /remote/repo \
  --history-path /remote/task/heartbeat.md \
  --output-summary-path /remote/task/final_summary.md \
  --required-section "Final outcome" \
  --required-section "Remaining risks" \
  --output /local/path/to/summary_prompt.md
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
- The launched agent reaches `state=starting` or finishes cleanly.
- The remote summary markdown exists.
- The report includes the required sections.
