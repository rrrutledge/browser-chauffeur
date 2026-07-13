"""End-to-end test for scripts/end-session.py and the drainer's close-session.py resolver.

Runs against the real ~/.claude/session-mgr/live-sessions.json using a unique
throwaway session id (seeded and removed within the test, cleaned up on failure).
Run directly: python plugins/session-mgr/tests/test_end_session.py
"""
import json
import os
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
END_SESSION = os.path.join(PLUGIN_ROOT, "skills", "resume-sessions", "scripts", "end-session.py")
REGISTRY_HOOK = os.path.join(PLUGIN_ROOT, "hooks", "session_registry.py")
CLOSE_SESSION = os.path.abspath(os.path.join(
    PLUGIN_ROOT, "..", "drainer", "skills", "drainer", "scripts", "close-session.py"))
REGISTRY_PATH = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def scrubbed_env(**overrides):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_HOST_PID", "CLAUDE_CODE_SESSION_ID")}
    env.update(overrides)
    return env


def registry_has(session_id):
    if not os.path.exists(REGISTRY_PATH):
        return False
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return session_id in json.load(f)


def fire_event(event, session_id):
    payload = json.dumps({"hook_event_name": event, "session_id": session_id, "cwd": os.getcwd()})
    subprocess.run([sys.executable, REGISTRY_HOOK], input=payload, text=True, check=True)


def test_unset_host_pid_refuses():
    print("test: unset CLAUDE_HOST_PID -> exit 1, no hooks fired")
    result = subprocess.run([sys.executable, END_SESSION], env=scrubbed_env(),
                            capture_output=True, text=True)
    check("exit code 1", result.returncode == 1, f"got {result.returncode}")
    check("explains unset var", "CLAUDE_HOST_PID is unset" in result.stdout, result.stdout)


def test_non_ancestor_pid_refuses():
    print("test: non-ancestor CLAUDE_HOST_PID -> refuses to kill")
    victim = subprocess.Popen(["powershell", "-NoProfile", "-Command", "Start-Sleep -Seconds 30"])
    try:
        result = subprocess.run(
            [sys.executable, END_SESSION],
            env=scrubbed_env(CLAUDE_HOST_PID=str(victim.pid),
                             CLAUDE_CODE_SESSION_ID="test-non-ancestor"),
            capture_output=True, text=True)
        check("exit code 1", result.returncode == 1, f"got {result.returncode}")
        check("explains refusal", "not an ancestor" in result.stdout, result.stdout)
        check("victim still alive", victim.poll() is None)
    finally:
        victim.kill()


def test_self_close_fires_session_end_then_kills():
    print("test: full self-close -> SessionEnd fired (registry entry removed), host tree dead")
    session_id = f"test-end-session-{uuid.uuid4()}"
    fire_event("SessionStart", session_id)
    check("registry seeded", registry_has(session_id))
    try:
        host = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command",
             f"$env:CLAUDE_HOST_PID = $PID; "
             f"$env:CLAUDE_CODE_SESSION_ID = '{session_id}'; "
             f"python '{END_SESSION}'; "
             "Start-Sleep -Seconds 30"],
            env=scrubbed_env())
        deadline = time.time() + 20
        while time.time() < deadline and host.poll() is None:
            time.sleep(0.5)
        check("host process tree killed (did not reach its 30s sleep)", host.poll() is not None)
        check("registry entry removed by SessionEnd hook", not registry_has(session_id))
    finally:
        if registry_has(session_id):
            fire_event("SessionEnd", session_id)


def test_resolver_forwards():
    print("test: drainer close-session.py resolves and forwards to end-session.py")
    result = subprocess.run([sys.executable, CLOSE_SESSION], env=scrubbed_env(),
                            capture_output=True, text=True)
    check("exit code 1 (forwarded unset-var refusal)", result.returncode == 1,
          f"got {result.returncode}")
    check("end-session output came through", "CLAUDE_HOST_PID is unset" in result.stdout,
          result.stdout + result.stderr)


if __name__ == "__main__":
    test_unset_host_pid_refuses()
    test_non_ancestor_pid_refuses()
    test_self_close_fires_session_end_then_kills()
    test_resolver_forwards()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        sys.exit(1)
    print("all tests passed")
