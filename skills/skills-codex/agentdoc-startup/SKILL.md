---
name: agentdoc-startup
description: Use when the user says `使用skill启动AgentDoc`, `用skill启动AgentDoc`, `启动AgentDoc`, `start AgentDoc`, asks to load the AgentDoc entry, or wants to begin an AgentDoc-governed task on `PC`, `dev-intern-01`, or `dev-intern-02`. This skill bridges to an external AgentDoc checkout, selects the right startup variant from `Prompt.md`, and treats that block as authoritative for the rest of the turn. AgentDoc itself is intentionally not vendored in this repo.
---

# AgentDoc Startup

## External Dependency

- This repository does not bundle the AgentDoc corpus.
- Expected external AgentDoc roots:
  - `pc_windows`: `F:\InformationAndCourses\Code\AgentDoc`
  - `development_machine`: `/dev_vepfs/rc_wu/AgentDoc`
- If your AgentDoc checkout lives elsewhere, resolve `<AGENTDOC_ROOT>` first and keep using that resolved path.

## Trigger

- Treat `使用skill启动AgentDoc`, `用skill启动AgentDoc`, `启动AgentDoc`, and `start AgentDoc` as immediate startup commands.
- Use this when the task depends on AgentDoc routing, Git hygiene, multi-machine boundaries, or project-doc initialization.
- Do not ask the user to paste `Prompt.md`; load it from the external AgentDoc checkout.

## Startup Flow

1. Resolve `current_machine`, `target_machine`, and scope first.
2. Set `AGENTDOC_ROOT` from the current machine.
3. Immediately open `<AGENTDOC_ROOT>/Prompt.md`.
4. Select the correct startup variant:
   - Variant A: cross-machine or generic startup
   - Variant B: current machine is the development machine
   - Variant C: current machine is the local PC
   - Variant D: initializing docs for an existing project repo
5. Treat the selected `Prompt.md` block as authoritative for the rest of the turn.
6. Run Git preflight before any task work:
   - `git status --short --branch`
   - `git remote -v`
   - `git branch --show-current`
   - `git fetch --all --prune`
   - `git rev-list --left-right --count origin/<branch>...HEAD`
7. If the worktree is dirty, the remote is ahead, or local history is messy, do not pull in place. Prefer an isolated worktree and follow the repo hygiene playbook from AgentDoc.
8. Load docs in this order:
   - `<AGENTDOC_ROOT>/AGENT_DOCS.md`
   - `<AGENTDOC_ROOT>/AGENT_COMMONS.md`
   - matching `ENVIRONMENTS/...` docs
   - matching `POLICIES/...`
   - `ENVIRONMENTS/shared/network_topology_and_collaboration.md` for GitHub, SSH, JumpServer, or cross-machine work
9. If the task hits the Volc forwarding-machine/controller path, load the companion forwarding-machine skill before acting.
10. Route machine wording exactly:
   - `PC` means the local Windows machine
   - `开发机` without an explicit override means `dev-intern-02`
   - `1开发机` means `dev-intern-01`
   - `2开发机` means `dev-intern-02`
   - `旧开发机` means the retired historical machine with explicit scope boundaries
11. Respect write boundaries:
   - `pc_windows_only`: stay under `F:\InformationAndCourses\Code`
   - `development_machine_only`: stay under `/dev_vepfs/rc_wu`
   - `shared`: GitHub sync, SSH, JumpServer, and skill rollout
12. If a project repo lacks docs, initialize:
   - `<project_root>/agent.md`
   - `<project_root>/docs/`
   - `<project_root>/assets/`
   - `<project_root>/sandboxes/<task_id>/`
   - `<AGENTDOC_ROOT>/PROJECTS/<project_name>/PROJECT_DOCS.md`
   - `<AGENTDOC_ROOT>/PROJECTS/<project_name>/PROJECT_COMMONS.md` when the project will recur
13. If the task first touches development-machine storage, disk space, `/shared-dev`, `/dev_vepfs`, `/dev/shm`, or dataset migration, also load the storage-preflight policy and shared-dev semantics runbook.
14. Stay generic until a concrete project is named or discovered.
15. Re-query AgentDoc at every new phase, before the first high-risk operation, and whenever an error, timeout, or performance anomaly appears.
16. Write reusable findings into `outbox/runtime_doc_checkpoints.md` before formal docs.
17. Prefer skill-first capture for reusable workflows instead of leaving them only in dated notes.
18. Finish with verification, quality checks, commit, and push.

## Validation

- The skill loads `Prompt.md` and picks a concrete variant instead of paraphrasing from memory.
- Git preflight includes status, remotes, branch, fetch, and ahead/behind counts.
- The active AgentDoc worktree is clean before any task-ending push.
- Reusable findings land in both runtime checkpoints and canonical docs.

## References

- [`docs/AGENTDOC_BRIDGE.md`](../../../docs/AGENTDOC_BRIDGE.md)
- `<AGENTDOC_ROOT>/AGENT_DOCS.md`
- `<AGENTDOC_ROOT>/AGENT_COMMONS.md`
- `<AGENTDOC_ROOT>/PLAYBOOKS/tools/agentdoc_git_sync_runbook.md`
- `<AGENTDOC_ROOT>/PLAYBOOKS/tools/agentdoc_repo_hygiene_semantic_merge_playbook.md`
- `<AGENTDOC_ROOT>/PLAYBOOKS/tools/agent_startup_prompt_templates.md`
- `<AGENTDOC_ROOT>/Prompt.md`
