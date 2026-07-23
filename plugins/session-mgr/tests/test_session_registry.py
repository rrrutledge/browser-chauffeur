"""Test for hooks/session_registry.py.

Runs against the real ~/.claude/session-mgr/live-sessions.json using unique throwaway
session ids (seeded and removed within each test, cleaned up on failure).
Run directly: python plugins/session-mgr/tests/test_session_registry.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REGISTRY_HOOK = os.path.join(PLUGIN_ROOT, "hooks", "session_registry.py")
REGISTRY_PATH = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")

spec = importlib.util.spec_from_file_location("session_registry", REGISTRY_HOOK)
session_registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_registry)

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def registry_entry(session_id):
    if not os.path.exists(REGISTRY_PATH):
        return None
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f).get(session_id)


def fire_event(event, session_id):
    payload = json.dumps({"hook_event_name": event, "session_id": session_id, "cwd": os.getcwd()})
    subprocess.run([sys.executable, REGISTRY_HOOK], input=payload, text=True, check=True)


class _FakeProc:
    """Minimal stand-in for a psutil.Process, chained via parent() like the real ancestry walk."""

    def __init__(self, pid, name, parent=None):
        self.pid = pid
        self._name = name
        self._parent = parent

    def name(self):
        return self._name

    def parent(self):
        return self._parent


def test_ancestor_walk_finds_claude_exe():
    print("test: find_claude_ancestor_pid returns the nearest claude.exe ancestor's pid")
    claude = _FakeProc(4242, "claude.exe")
    shell = _FakeProc(999, "powershell.exe", parent=claude)
    hook = _FakeProc(os.getpid(), "python.exe", parent=shell)
    import psutil
    orig_process = psutil.Process
    psutil.Process = lambda pid: hook
    try:
        pid = session_registry.find_claude_ancestor_pid()
        check("found claude.exe pid", pid == 4242, f"got {pid}")
    finally:
        psutil.Process = orig_process


def test_ancestor_walk_returns_none_without_claude_exe():
    print("test: find_claude_ancestor_pid returns None when no ancestor is claude.exe")
    root = _FakeProc(1, "System Idle Process", parent=None)
    shell = _FakeProc(999, "powershell.exe", parent=root)
    hook = _FakeProc(os.getpid(), "python.exe", parent=shell)
    import psutil
    orig_process = psutil.Process
    psutil.Process = lambda pid: hook
    try:
        pid = session_registry.find_claude_ancestor_pid()
        check("no claude.exe ancestor -> None", pid is None, f"got {pid}")
    finally:
        psutil.Process = orig_process


def test_session_start_records_pid_key():
    print("test: SessionStart writes a 'pid' key alongside cwd/started_at")
    session_id = f"test-session-registry-{uuid.uuid4()}"
    fire_event("SessionStart", session_id)
    try:
        entry = registry_entry(session_id)
        check("entry written", entry is not None)
        check("pid key present", bool(entry) and "pid" in entry, f"got {entry}")
    finally:
        fire_event("SessionEnd", session_id)
        check("cleaned up on SessionEnd", registry_entry(session_id) is None)


if __name__ == "__main__":
    test_ancestor_walk_finds_claude_exe()
    test_ancestor_walk_returns_none_without_claude_exe()
    test_session_start_records_pid_key()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        sys.exit(1)
    print("all tests passed")
