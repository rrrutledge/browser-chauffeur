import json
import os
import sys
import time
import datetime

REGISTRY_DIR = os.path.expanduser("~/.claude/session-mgr")
REGISTRY_PATH = os.path.join(REGISTRY_DIR, "live-sessions.json")


def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_registry(registry):
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    tmp_path = REGISTRY_PATH + f".tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    os.replace(tmp_path, REGISTRY_PATH)


def update_registry(mutate):
    for attempt in range(5):
        registry = load_registry()
        mutate(registry)
        try:
            save_registry(registry)
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def find_claude_ancestor_pid():
    """Walk this hook process's own ancestry to find the claude.exe PID that launched it.
    A bare `claude` launch (no --resume/--session-id) exposes its session id neither on its
    command line nor — confirmed empirically — in its own process environment (Claude Code
    only passes CLAUDE_CODE_SESSION_ID to the child processes it spawns, e.g. this hook and
    the Bash tool, never setting it on itself). Recording the launching PID directly lets
    find-orphans.py confirm such a session is still alive by PID liveness instead, sidestepping
    that gap entirely. None if psutil is unavailable or no claude.exe ancestor is found."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        proc = psutil.Process(os.getpid())
        while proc is not None:
            proc = proc.parent()
            if proc is not None and (proc.name() or "").lower() == "claude.exe":
                return proc.pid
    except psutil.Error:
        pass
    return None


def main():
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")

    if not session_id:
        return

    if event == "SessionStart":
        pid = find_claude_ancestor_pid()

        def add(registry):
            registry[session_id] = {
                "cwd": cwd,
                "started_at": datetime.datetime.now().isoformat(),
                "pid": pid,
            }
        update_registry(add)
    elif event == "SessionEnd":
        def remove(registry):
            registry.pop(session_id, None)
        update_registry(remove)


if __name__ == "__main__":
    main()
