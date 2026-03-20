# dev-intern-02 Notes

- Remote live Codex state is under `/dev_vepfs/rc_wu/.codex`.
- The remote user shell does not currently expose `codex` in `PATH`.
- A Linux `codex` binary can be copied from the local VS Code extension into `/dev_vepfs/rc_wu/bin/codex`.
- `vePFS` is usable for storage but should not be assumed executable; copy the binary into `/tmp` before each run.
- Minimal validated smoke sequence in one remote shell:
  - copy stored binary to `/tmp`
  - `chmod +x`
  - `HOME=/dev_vepfs/rc_wu /tmp/<binary> --version`
  - `HOME=/dev_vepfs/rc_wu /tmp/<binary> login status`
  - `HOME=/dev_vepfs/rc_wu /tmp/<binary> exec --skip-git-repo-check ...`
- If `codex exec` complains about repository trust, add `--skip-git-repo-check`.
- The root-managed proxy on `127.0.0.1:7890` can be present but still fail TLS for `api.openai.com` and `chatgpt.com/backend-api/codex/*`.
- A working fallback path is the user-owned Clash binary and config already stored under `/dev_vepfs/rc_wu/software/clash/`.
- The skill now bootstraps that fallback onto `127.0.0.1:27890/27891` via `/dev_vepfs/rc_wu/bin/ensure_codex_proxy.sh` and exports those proxy env vars into worker runs.
- On the current kernel, `workspace-write` hits `bwrap: No permissions to create a new namespace...`; for real write-capable subagents on `dev-intern-02`, use `danger-full-access` or let the skill auto-promote `workspace-write`.
