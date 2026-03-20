#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path, PurePosixPath


DEFAULT_REMOTE_HOME = "/dev_vepfs/rc_wu"
DEFAULT_REMOTE_BINARY_STORE = f"{DEFAULT_REMOTE_HOME}/bin/codex"
DEFAULT_REMOTE_RUN_ROOT = f"{DEFAULT_REMOTE_HOME}/codex_subagents"
DEFAULT_DEV02_PROXY_HELPER = f"{DEFAULT_REMOTE_HOME}/bin/ensure_codex_proxy.sh"
DEFAULT_DEV02_PROXY_BINARY = f"{DEFAULT_REMOTE_HOME}/software/clash/clash"
DEFAULT_DEV02_PROXY_CONFIG = f"{DEFAULT_REMOTE_HOME}/software/clash/config.yaml"
DEFAULT_DEV02_PROXY_STATE_DIR = f"{DEFAULT_REMOTE_HOME}/cache/tmp"
DEFAULT_DEV02_PROXY_HTTP_PORT = 27890
DEFAULT_DEV02_PROXY_SOCKS_PORT = 27891
DEFAULT_DEV02_PROXY_CONTROLLER_PORT = 29090
SSH_CONNECT_TIMEOUT_SECONDS = 10
SSH_RETRY_ATTEMPTS = 3
SUBPROCESS_NO_WINDOW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def run_local(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        capture_output=True,
        **SUBPROCESS_NO_WINDOW,
    )


def write_stream_text(stream, text: str) -> None:
    if not text:
        return
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        data = text.encode(encoding, errors="replace")
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write(data)
        else:
            stream.write(data.decode(encoding, errors="replace"))
    stream.flush()


def choose_local_linux_binary(explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    root = Path.home() / ".vscode" / "extensions"
    candidates = sorted(
        root.glob("openai.chatgpt-*/bin/linux-x86_64/codex"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No local linux-x86_64 codex binary found under ~/.vscode/extensions")
    return candidates[0].resolve()


def ssh(host: str, remote_cmd: str, *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["ssh", "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}", host, remote_cmd]
    result = run_local(cmd, input_text=input_text, check=False)
    for _ in range(1, SSH_RETRY_ATTEMPTS):
        if result.returncode == 0:
            break
        result = run_local(cmd, input_text=input_text, check=False)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
    return result


def scp_legacy(local_path: Path, host: str, remote_path: str) -> subprocess.CompletedProcess[str]:
    return run_local(["scp", "-O", "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}", str(local_path), f"{host}:{remote_path}"])


def write_remote_text(host: str, remote_path: str, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    cmd = ["ssh", "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}", host, f"cat > {shlex.quote(remote_path)}"]
    proc = subprocess.run(
        cmd,
        input=normalized.encode("utf-8"),
        check=False,
        capture_output=True,
        **SUBPROCESS_NO_WINDOW,
    )
    for _ in range(1, SSH_RETRY_ATTEMPTS):
        if proc.returncode == 0:
            break
        proc = subprocess.run(
            cmd,
            input=normalized.encode("utf-8"),
            check=False,
            capture_output=True,
            **SUBPROCESS_NO_WINDOW,
        )
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args, output=proc.stdout, stderr=proc.stderr)


def should_ensure_dev02_proxy(args: argparse.Namespace) -> bool:
    flag = getattr(args, "ensure_dev02_proxy", None)
    if flag is not None:
        return bool(flag)
    return args.host == "dev-intern-02"


def build_dev02_proxy_env(args: argparse.Namespace) -> dict[str, str]:
    http_proxy = f"http://127.0.0.1:{int(args.proxy_http_port)}"
    all_proxy = f"socks5h://127.0.0.1:{int(args.proxy_socks_port)}"
    no_proxy = "localhost,127.0.0.1,::1"
    return {
        "HTTP_PROXY": http_proxy,
        "HTTPS_PROXY": http_proxy,
        "ALL_PROXY": all_proxy,
        "http_proxy": http_proxy,
        "https_proxy": http_proxy,
        "all_proxy": all_proxy,
        "NO_PROXY": no_proxy,
        "no_proxy": no_proxy,
    }


def effective_sandbox(args: argparse.Namespace) -> str:
    if args.host == "dev-intern-02" and args.sandbox == "workspace-write" and not getattr(
        args, "no_auto_dev02_sandbox_fix", False
    ):
        return "danger-full-access"
    return args.sandbox


def build_remote_proxy_helper(args: argparse.Namespace) -> str:
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        CLASH_HOME={json.dumps(str(PurePosixPath(args.proxy_binary).parent))}
        CLASH_BIN={json.dumps(args.proxy_binary)}
        SOURCE_CFG={json.dumps(args.proxy_config)}
        STATE_DIR={json.dumps(args.proxy_state_dir)}
        TMP_CFG="$STATE_DIR/codex_proxy_{int(args.proxy_http_port)}.yaml"
        LOG_PATH="$STATE_DIR/codex_proxy_{int(args.proxy_http_port)}.log"
        PID_PATH="$STATE_DIR/codex_proxy_{int(args.proxy_http_port)}.pid"
        HTTP_PORT={int(args.proxy_http_port)}
        SOCKS_PORT={int(args.proxy_socks_port)}
        CONTROLLER_PORT={int(args.proxy_controller_port)}

        listeners_ready() {{
          command -v ss >/dev/null 2>&1 || return 1
          ss -lnt 2>/dev/null | grep -q ":$HTTP_PORT " || return 1
          ss -lnt 2>/dev/null | grep -q ":$SOCKS_PORT " || return 1
        }}

        current_pid() {{
          if [ -f "$PID_PATH" ]; then
            cat "$PID_PATH"
          fi
        }}

        running_pid() {{
          local pid
          pid="$(current_pid)"
          if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            printf '%s\\n' "$pid"
            return 0
          fi
          return 1
        }}

        emit_json() {{
          local status="$1"
          local pid
          pid="$(current_pid || true)"
          python3 - <<'PY' "$status" "$pid" "$HTTP_PORT" "$SOCKS_PORT" "$CONTROLLER_PORT" "$TMP_CFG" "$LOG_PATH" "$PID_PATH"
        import json, sys
        payload = {{
          "status": sys.argv[1],
          "pid": sys.argv[2],
          "http_proxy": f"http://127.0.0.1:{{sys.argv[3]}}",
          "all_proxy": f"socks5h://127.0.0.1:{{sys.argv[4]}}",
          "controller": f"127.0.0.1:{{sys.argv[5]}}",
          "config_path": sys.argv[6],
          "log_path": sys.argv[7],
          "pid_path": sys.argv[8],
        }}
        print(json.dumps(payload, ensure_ascii=False))
        PY
        }}

        if [ ! -x "$CLASH_BIN" ]; then
          echo "Missing clash binary: $CLASH_BIN" >&2
          exit 1
        fi
        if [ ! -f "$SOURCE_CFG" ]; then
          echo "Missing clash config: $SOURCE_CFG" >&2
          exit 1
        fi

        mkdir -p "$STATE_DIR"

        if running_pid >/dev/null && listeners_ready; then
          emit_json running
          exit 0
        fi

        python3 - <<'PY' "$SOURCE_CFG" "$TMP_CFG" "$HTTP_PORT" "$SOCKS_PORT" "$CONTROLLER_PORT"
        from pathlib import Path
        import sys

        src = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore").splitlines()
        out: list[str] = []
        for line in src:
            if line.startswith("port:"):
                out.append(f"port: {{sys.argv[3]}}")
            elif line.startswith("socks-port:"):
                out.append(f"socks-port: {{sys.argv[4]}}")
            elif line.startswith("external-controller:"):
                out.append(f"external-controller: 127.0.0.1:{{sys.argv[5]}}")
            elif line.startswith("allow-lan:"):
                out.append("allow-lan: false")
            else:
                out.append(line)
        Path(sys.argv[2]).write_text("\\n".join(out) + "\\n", encoding="utf-8")
        PY

        "$CLASH_BIN" -d "$CLASH_HOME" -f "$TMP_CFG" -t >/dev/null

        if running_pid >/dev/null; then
          kill "$(current_pid)" || true
          sleep 1
        fi

        nohup "$CLASH_BIN" -d "$CLASH_HOME" -f "$TMP_CFG" > "$LOG_PATH" 2>&1 &
        echo $! > "$PID_PATH"
        sleep 4

        if ! listeners_ready; then
          tail -n 120 "$LOG_PATH" >&2 || true
          exit 1
        fi

        emit_json started
        """
    )


def ensure_remote_codex_proxy(args: argparse.Namespace) -> dict[str, object]:
    helper_parent = str(PurePosixPath(args.proxy_helper_path).parent)
    ssh(args.host, f"mkdir -p {shlex.quote(helper_parent)} {shlex.quote(args.proxy_state_dir)}")
    write_remote_text(args.host, args.proxy_helper_path, build_remote_proxy_helper(args))
    ssh(args.host, f"chmod +x {shlex.quote(args.proxy_helper_path)}")
    proc = ssh(args.host, f"bash {shlex.quote(args.proxy_helper_path)}")
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"Proxy bootstrap returned no JSON payload. stdout={proc.stdout!r}")


def build_prompt(args: argparse.Namespace) -> str:
    parts: list[str] = []
    for path in args.prepend_file or []:
        parts.append(Path(path).read_text(encoding="utf-8"))
    if args.prompt_file is not None:
        parts.append(args.prompt_file.read_text(encoding="utf-8"))
    if args.prompt_text:
        parts.append(args.prompt_text)
    prompt = "\n\n".join(part.strip() for part in parts if part.strip()).strip()
    if not prompt:
        raise ValueError("No prompt content provided.")
    return prompt + "\n"


def install(args: argparse.Namespace) -> int:
    local_binary = choose_local_linux_binary(args.local_linux_binary)
    ssh(args.host, f"mkdir -p {shlex.quote(str(PurePosixPath(args.remote_binary_store).parent))}")
    scp_legacy(local_binary, args.host, args.remote_binary_store)
    ssh(args.host, f"chmod 0644 {shlex.quote(args.remote_binary_store)}")
    payload = {
        "host": args.host,
        "local_binary": str(local_binary),
        "remote_binary_store": args.remote_binary_store,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def ensure_proxy(args: argparse.Namespace) -> int:
    if not should_ensure_dev02_proxy(args):
        payload = {
            "status": "skipped",
            "host": args.host,
            "reason": "Proxy bootstrap is only enabled by default for dev-intern-02. Use --ensure-dev02-proxy to force it.",
        }
    else:
        payload = ensure_remote_codex_proxy(args)
        payload["host"] = args.host
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def launch(args: argparse.Namespace) -> int:
    if not args.skip_install:
        install(args)

    proxy_payload: dict[str, object] | None = None
    if should_ensure_dev02_proxy(args):
        proxy_payload = ensure_remote_codex_proxy(args)

    prompt = build_prompt(args)
    agent_root = f"{args.remote_run_root}/{args.run_id}/{args.agent_name}"
    ssh(args.host, f"mkdir -p {shlex.quote(agent_root)}")

    prompt_path = f"{agent_root}/prompt.md"
    wrapper_path = f"{agent_root}/run_agent.sh"
    pid_path = f"{agent_root}/pid"
    status_path = f"{agent_root}/status.json"
    launch_json = f"{agent_root}/launch.json"
    stdout_log = f"{agent_root}/stdout.log"
    last_message = f"{agent_root}/last_message.txt"

    write_remote_text(args.host, prompt_path, prompt)
    launch_payload = {
        "host": args.host,
        "run_id": args.run_id,
        "agent_name": args.agent_name,
        "cwd": args.cwd,
        "sandbox_requested": args.sandbox,
        "sandbox_effective": effective_sandbox(args),
        "remote_home": args.remote_home,
        "remote_binary_store": args.remote_binary_store,
        "remote_run_root": args.remote_run_root,
        "prompt_path": prompt_path,
        "stdout_log": stdout_log,
        "last_message": last_message,
        "status_path": status_path,
    }
    write_remote_text(args.host, launch_json, json.dumps(launch_payload, ensure_ascii=False, indent=2) + "\n")

    exec_flags: list[str] = [
        "--skip-git-repo-check",
        "--color",
        "never",
        "--json",
        "--output-last-message",
        last_message,
        "-s",
        effective_sandbox(args),
        "-C",
        args.cwd,
        "-",
    ]
    if args.model:
        exec_flags = ["--model", args.model, *exec_flags]
    prefix_flags: list[str] = []
    if args.approval:
        prefix_flags.extend(["-a", args.approval])
    if args.search:
        prefix_flags.append("--search")
    env_setup_lines: list[str] = []
    for item in args.unset_env or []:
        env_setup_lines.append(f"unset {shlex.quote(item)} || true")
    if proxy_payload is not None:
        for key, value in build_dev02_proxy_env(args).items():
            env_setup_lines.append(f"export {key}={shlex.quote(value)}")
    for item in args.env or []:
        if "=" not in item:
            raise ValueError(f"Invalid --env value: {item}")
        key, value = item.split("=", 1)
        env_setup_lines.append(f"export {key}={shlex.quote(value)}")
    for add_dir in args.add_dir or []:
        exec_flags = ["--add-dir", add_dir, *exec_flags]
    exec_args = " ".join(shlex.quote(flag) for flag in exec_flags)
    prefix_args = " ".join(shlex.quote(flag) for flag in prefix_flags)
    env_setup = "\n".join(env_setup_lines)

    codex_home = str(PurePosixPath(args.remote_home) / ".codex")

    api_key_file = str(PurePosixPath(codex_home) / "aris_primary_api_key.txt")

    wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
AGENT_ROOT={shlex.quote(agent_root)}
BIN_STORE={shlex.quote(args.remote_binary_store)}
TMP_BIN="/tmp/codex_{args.agent_name}_$$"
PROMPT_PATH={shlex.quote(prompt_path)}
STDOUT_LOG={shlex.quote(stdout_log)}
STATUS_PATH={shlex.quote(status_path)}
LAST_MESSAGE={shlex.quote(last_message)}
CODEX_HOME_PATH={shlex.quote(codex_home)}
API_KEY_FILE={shlex.quote(api_key_file)}
START_TS="$(date -Is)"
python3 - <<'PY' > "$STATUS_PATH"
import json
print(json.dumps({{
  "state": "starting",
  "started_at": "{args.run_id}",
  "agent_name": {json.dumps(args.agent_name)},
  "cwd": {json.dumps(args.cwd)},
  "sandbox_requested": {json.dumps(args.sandbox)},
  "sandbox_effective": {json.dumps(effective_sandbox(args))}
}}, ensure_ascii=False, indent=2))
PY
cp "$BIN_STORE" "$TMP_BIN"
chmod +x "$TMP_BIN"
{env_setup}
if [ -z "${{OPENAI_API_KEY:-}}" ] && [ -f "$API_KEY_FILE" ]; then
  export OPENAI_API_KEY="$(tr -d '\r\n' < "$API_KEY_FILE")"
fi
set +e
HOME={shlex.quote(args.remote_home)} CODEX_HOME="$CODEX_HOME_PATH" "$TMP_BIN" {prefix_args} exec {exec_args} < "$PROMPT_PATH" > "$STDOUT_LOG" 2>&1
RC=$?
set -e
END_TS="$(date -Is)"
python3 - <<'PY' "$STATUS_PATH" "$RC" "$START_TS" "$END_TS"
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {{}}
payload["state"] = "finished"
payload["returncode"] = int(sys.argv[2])
payload["started_at_real"] = sys.argv[3]
payload["finished_at_real"] = sys.argv[4]
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
rm -f "$TMP_BIN"
exit "$RC"
"""
    write_remote_text(args.host, wrapper_path, wrapper)
    ssh(args.host, f"chmod +x {shlex.quote(wrapper_path)}")
    launch_cmd = f"nohup bash {shlex.quote(wrapper_path)} >/dev/null 2>&1 & echo $! > {shlex.quote(pid_path)} && cat {shlex.quote(pid_path)}"
    proc = ssh(args.host, launch_cmd)
    payload = {
        "host": args.host,
        "run_id": args.run_id,
        "agent_name": args.agent_name,
        "pid": proc.stdout.strip(),
        "agent_root": agent_root,
        "prompt_path": prompt_path,
        "stdout_log": stdout_log,
        "last_message": last_message,
        "status_path": status_path,
        "sandbox_requested": args.sandbox,
        "sandbox_effective": effective_sandbox(args),
    }
    if proxy_payload is not None:
        payload["proxy"] = proxy_payload
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def status(args: argparse.Namespace) -> int:
    target = f"{args.remote_run_root}/{args.run_id}"
    list_proc = ssh(args.host, f"find {shlex.quote(target)} -mindepth 1 -maxdepth 1 -type d -printf '%f\\n'", check=False)
    if list_proc.returncode != 0:
        if list_proc.stderr:
            sys.stderr.write(list_proc.stderr)
        return int(list_proc.returncode)
    agent_names = [line.strip() for line in list_proc.stdout.splitlines() if line.strip()]
    for agent_name in agent_names:
        agent_root = f"{target}/{agent_name}"
        status_proc = ssh(args.host, f"cat {shlex.quote(agent_root + '/status.json')}", check=False)
        payload: dict[str, object] = {}
        if status_proc.returncode == 0 and status_proc.stdout.strip():
            payload.update(json.loads(status_proc.stdout))
        pid_proc = ssh(args.host, f"cat {shlex.quote(agent_root + '/pid')}", check=False)
        pid = pid_proc.stdout.strip() if pid_proc.returncode == 0 else ""
        running = False
        if pid:
            running_proc = ssh(args.host, f"ps -p {pid} >/dev/null 2>&1", check=False)
            running = running_proc.returncode == 0
        payload.update(
            {
                "agent_name": agent_name,
                "pid": pid,
                "running": running,
                "agent_root": agent_root,
                "stdout_log": f"{agent_root}/stdout.log",
                "last_message": f"{agent_root}/last_message.txt",
            }
        )
        print(json.dumps(payload, ensure_ascii=False))
    return 0


def tail(args: argparse.Namespace) -> int:
    log_path = f"{args.remote_run_root}/{args.run_id}/{args.agent_name}/stdout.log"
    proc = ssh(args.host, f"tail -n {int(args.lines)} {shlex.quote(log_path)}", check=False)
    write_stream_text(sys.stdout, proc.stdout)
    if proc.stderr:
        write_stream_text(sys.stderr, proc.stderr)
    return int(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Launch and monitor remote Codex subagents over SSH.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default="dev-intern-02")
    common.add_argument("--remote-home", default=DEFAULT_REMOTE_HOME)
    common.add_argument("--remote-binary-store", default=DEFAULT_REMOTE_BINARY_STORE)
    common.add_argument("--remote-run-root", default=DEFAULT_REMOTE_RUN_ROOT)
    common.add_argument("--local-linux-binary", type=Path, default=None)
    common.add_argument("--env", action="append", default=[])
    common.add_argument("--unset-env", action="append", default=[])
    common.add_argument("--proxy-helper-path", default=DEFAULT_DEV02_PROXY_HELPER)
    common.add_argument("--proxy-binary", default=DEFAULT_DEV02_PROXY_BINARY)
    common.add_argument("--proxy-config", default=DEFAULT_DEV02_PROXY_CONFIG)
    common.add_argument("--proxy-state-dir", default=DEFAULT_DEV02_PROXY_STATE_DIR)
    common.add_argument("--proxy-http-port", type=int, default=DEFAULT_DEV02_PROXY_HTTP_PORT)
    common.add_argument("--proxy-socks-port", type=int, default=DEFAULT_DEV02_PROXY_SOCKS_PORT)
    common.add_argument("--proxy-controller-port", type=int, default=DEFAULT_DEV02_PROXY_CONTROLLER_PORT)
    common.add_argument("--ensure-dev02-proxy", dest="ensure_dev02_proxy", action="store_true", default=None)
    common.add_argument("--no-ensure-dev02-proxy", dest="ensure_dev02_proxy", action="store_false")
    common.add_argument("--no-auto-dev02-sandbox-fix", action="store_true")

    p_install = sub.add_parser("install", parents=[common])
    p_install.set_defaults(func=install)

    p_proxy = sub.add_parser("ensure-proxy", parents=[common])
    p_proxy.set_defaults(func=ensure_proxy)

    p_launch = sub.add_parser("launch", parents=[common])
    p_launch.add_argument("--run-id", required=True)
    p_launch.add_argument("--agent-name", required=True)
    p_launch.add_argument("--cwd", required=True)
    p_launch.add_argument("--prompt-file", type=Path, default=None)
    p_launch.add_argument("--prepend-file", type=Path, action="append", default=[])
    p_launch.add_argument("--prompt-text", default="")
    p_launch.add_argument("--add-dir", action="append", default=[])
    p_launch.add_argument("--model", default="")
    p_launch.add_argument("--sandbox", default="workspace-write")
    p_launch.add_argument("--approval", default="never")
    p_launch.add_argument("--search", action="store_true")
    p_launch.add_argument("--skip-install", action="store_true")
    p_launch.set_defaults(func=launch)

    p_status = sub.add_parser("status", parents=[common])
    p_status.add_argument("--run-id", required=True)
    p_status.set_defaults(func=status)

    p_tail = sub.add_parser("tail", parents=[common])
    p_tail.add_argument("--run-id", required=True)
    p_tail.add_argument("--agent-name", required=True)
    p_tail.add_argument("--lines", type=int, default=80)
    p_tail.set_defaults(func=tail)

    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
