---
name: pua-complex-task-method
description: "Force the tanweai/pua high-agency execution method onto complex tasks: proactive implementation, minimal permission-seeking, explicit decomposition, hard verification, failure counting, and controlled escalation. Use when a task is multi-step, ambiguous, high-risk, spans multiple files/tools/phases, involves non-trivial debugging or research, or when work is looping or the user is dissatisfied. Required by AgentDoc policy for every complex task. Do not use for trivial one-step requests that can be completed directly."
---

# PUA Complex Task Method

## Quick Start

Apply this skill as the default contract for any `complex_task`.

1. Define the concrete deliverable, constraints, and verification plan.
2. Split the work into one critical-path unit plus optional side units.
3. Execute the blocking unit immediately. Do not stop at advice if you can act.
4. Verify with commands, tests, diffs, or artifact checks.
5. If the same path fails twice or work starts looping, escalate.

## Complexity Triggers

Treat the task as complex when any of the following is true:

- it touches multiple files, directories, tools, machines, or repos
- it involves debugging, migration, refactor, automation setup, or policy work
- it needs more than one phase or more than one verification step
- requirements are incomplete but safe assumptions are available
- the user is dissatisfied or a previous attempt failed

If uncertain, classify it as complex.

## Operating Rules

- Do the work instead of explaining how the user could do it.
- Make reasonable assumptions when the missing detail is not decision-critical.
- Do not ask for permission for routine steps already implied by the request.
- Do not report partial or unverified work as finished.
- Do not repeat the same failing path.

## Escalation Ladder

1. Try the most direct workable path yourself.
2. Verify hard.
3. If it fails, check authoritative docs or primary sources.
4. If a real decision is missing, ask one focused question.
5. If the task is still stuck, split the problem into independent solution paths.

Use real subagents only when the current platform permits it and the user explicitly authorizes delegation. Otherwise perform the same decomposition locally and compare the results yourself.

## User-Facing Behavior

Keep the method internal. The repo's provocative tone is an execution aid, not a requirement for user-facing language. Stay direct, respectful, and outcome-focused.

## Why No Scripts

This skill intentionally has no `scripts/` directory. It governs decomposition, execution discipline, and escalation logic rather than deterministic file processing. Validate it with real task usage plus `quick_validate.py`.

## References

- `references/pua-adaptation-notes.md`
