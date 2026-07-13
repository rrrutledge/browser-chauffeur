"""End this Claude Code session the way a clean exit would, then close its tab.

A session that force-kills its own host process (`taskkill /T /F`) dies before
Claude Code can fire the SessionEnd hook event, so anything wired to that event
never runs. In particular the live-session registry (hooks/session_registry.py)
keeps the session listed as open, and resume-sessions later resurrects a tab
that closed itself on purpose — and every resurrection re-registers it, so the
stale entry comes back forever.

This script is the correct self-close primitive. It fires this plugin's
SessionEnd hooks exactly as the harness would — the same commands from
hooks/hooks.json, the same JSON payload on stdin — rather than presuming what
the event does, and only then kills the hosting process tree.

Usage, from inside the session that wants to close (via the Bash tool):

    python "<this file>"

Everything needed comes from the session's own environment:

    CLAUDE_CODE_SESSION_ID — set by Claude Code for its child processes
    CLAUDE_HOST_PID        — the tab's hosting PID, set by the user's
                             PowerShell profile when the tab launched

If CLAUDE_HOST_PID is unset (a session launched without loading the profile),
nothing is fired and the exit code is 1: there is no tab to kill, the session
keeps running, and the real SessionEnd fires whenever it actually ends.
"""
import json
import os
import subprocess
import sys

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "..", ".."))
HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
DEFAULT_HOOK_TIMEOUT = 10


def host_pid_is_ancestor(host_pid):
    """The only PID this script may kill is the one hosting its own tab — the
    same self-target rule safe-compounds proves for a literal `taskkill /PID`.
    Walk our own ancestry to confirm the claimed host is really upstream of us,
    so a stale or hand-set CLAUDE_HOST_PID can never take down an unrelated
    process."""
    try:
        import psutil
    except ImportError:
        print("end-session: psutil unavailable — cannot verify the host PID is "
              "this tab's own ancestor; refusing to kill. Close the tab manually.")
        return False
    try:
        proc = psutil.Process(os.getpid())
        while proc is not None:
            if proc.pid == host_pid:
                return True
            proc = proc.parent()
    except psutil.Error:
        pass
    return False


def fire_session_end(session_id):
    """Run every SessionEnd hook command from this plugin's hooks.json with the
    payload the harness itself would send."""
    try:
        with open(HOOKS_JSON, encoding="utf-8") as f:
            hooks_config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"end-session: could not read {HOOKS_JSON} ({e}); no hooks fired.")
        return

    payload = json.dumps({
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "cwd": os.getcwd(),
        "reason": "self_close",
    })

    for matcher_group in hooks_config.get("hooks", {}).get("SessionEnd", []):
        for hook in matcher_group.get("hooks", []):
            if hook.get("type") != "command":
                continue
            command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN_ROOT)
            timeout = hook.get("timeout", DEFAULT_HOOK_TIMEOUT)
            try:
                subprocess.run(command, shell=True, input=payload, text=True,
                               timeout=timeout, check=False)
                print(f"end-session: fired SessionEnd hook: {command}")
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"end-session: SessionEnd hook failed ({e}): {command}")


def main():
    host_pid = os.environ.get("CLAUDE_HOST_PID")
    if not host_pid or not host_pid.isdigit():
        print("end-session: CLAUDE_HOST_PID is unset — no tab to close. "
              "Stop normally instead; SessionEnd will fire on the real exit.")
        return 1

    if not host_pid_is_ancestor(int(host_pid)):
        print(f"end-session: PID {host_pid} is not an ancestor of this process — "
              "refusing to kill it. Close the tab manually.")
        return 1

    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        fire_session_end(session_id)
    else:
        print("end-session: CLAUDE_CODE_SESSION_ID is unset — killing the tab "
              "without firing SessionEnd (nothing to deregister it by).")

    print(f"end-session: killing host process tree (PID {host_pid}).")
    subprocess.run(["taskkill", "/PID", host_pid, "/T", "/F"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
