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


def main():
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")

    if not session_id:
        return

    if event == "SessionStart":
        def add(registry):
            registry[session_id] = {
                "cwd": cwd,
                "started_at": datetime.datetime.now().isoformat(),
            }
        update_registry(add)
    elif event == "SessionEnd":
        def remove(registry):
            registry.pop(session_id, None)
        update_registry(remove)


if __name__ == "__main__":
    main()
