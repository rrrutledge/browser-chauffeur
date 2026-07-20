"""find-orphans.py — the registry-confirmed half of crash-recovery detection.

Locates Claude Code sessions that started (SessionStart fired) but never cleanly ended
(no SessionEnd) and aren't currently running. Registry-only: this does NOT run the
resume-sessions skill's fallback scan (every session transcript's tail) — that stays
exclusive to the interactive skill, which calls it as a separate step. This script is
deliberately fast enough to run every drainer poll cycle (a few seconds' work, mostly the
psutil process scan).

Run directly, prints JSON to stdout:
    python find-orphans.py
    [{"session_id": "...", "cwd": "...", "started_at": "2026-07-20T13:04:11.123456"}, ...]

Shared by two callers:
  - the resume-sessions skill (its Step 1, in place of the snippets it used to author fresh
    into .tmp/ each run)
  - the drainer's orphan-sessions-adapter.py, via subprocess, resolved to the newest
    installed copy of this plugin (see that adapter's _find_orphans_script())
"""
import glob
import json
import os
import re
import sys

import psutil

REGISTRY_PATH = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SESSION_RE = re.compile(r"--(?:resume|session-id)\s+([0-9a-fA-F-]{36})")
SELF_CLOSE_RE = re.compile(r"taskkill\s+/PID\s+\S+\s+/T\s+/F|close-session\.py|end-session\.py")


def active_session_ids():
    """Session IDs of every currently-running `claude.exe` process: from its command line
    (--resume/--session-id) or, for a bare launch with neither flag, its own
    CLAUDE_CODE_SESSION_ID environment variable."""
    ids = set()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if (proc.info["name"] or "").lower() != "claude.exe":
            continue
        cmdline_str = " ".join(proc.info["cmdline"] or [])
        m = SESSION_RE.search(cmdline_str)
        if m:
            ids.add(m.group(1))
            continue
        try:
            env = proc.environ()
            sid = env.get("CLAUDE_CODE_SESSION_ID")
            if sid:
                ids.add(sid)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return ids


def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_registry(registry):
    tmp = REGISTRY_PATH + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    os.replace(tmp, REGISTRY_PATH)


def transcript_path(session_id):
    """The session's own .jsonl transcript, wherever it lives under ~/.claude/projects/ (one
    subfolder per project). None if it can't be found."""
    matches = glob.glob(os.path.join(PROJECTS_DIR, "*", f"{session_id}.jsonl"))
    return matches[0] if matches else None


def closed_itself_on_purpose(session_id):
    """True if the session's last ~30 transcript lines show it deliberately closing its own
    tab (a taskkill /T /F, or a close-session.py / end-session.py invocation) — such a
    session dies before SessionEnd can fire, so its registry entry survives even though the
    close was intentional. Missing/unreadable transcript -> False: fail toward including a
    session as an orphan, never toward silently dropping a real one."""
    path = transcript_path(session_id)
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False
    tail = "\n".join(lines[-30:])
    return bool(SELF_CLOSE_RE.search(tail))


def find_confirmed_orphans():
    """Registry entries whose session isn't currently running, minus any that closed
    themselves on purpose. Self-closed entries are pruned from the registry in place (not
    just excluded from the return value) so a later run doesn't re-litigate them — same
    behavior the resume-sessions skill has always documented for this check. Pruning isn't
    wrapped in the retry-on-write-race loop session_registry.py's hook uses: a missed prune
    just means the same (harmless) exclusion happens again next run, never a lost orphan."""
    active = active_session_ids()
    registry = load_registry()
    orphans = []
    to_prune = []
    for session_id, info in registry.items():
        if session_id in active:
            continue
        if closed_itself_on_purpose(session_id):
            to_prune.append(session_id)
            continue
        orphans.append({
            "session_id": session_id,
            "cwd": info.get("cwd"),
            "started_at": info.get("started_at"),
        })
    if to_prune:
        registry = load_registry()
        for sid in to_prune:
            registry.pop(sid, None)
        save_registry(registry)
    return orphans


def main():
    print(json.dumps(find_confirmed_orphans()))


if __name__ == "__main__":
    main()
