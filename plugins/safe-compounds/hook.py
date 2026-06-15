#!/usr/bin/env python
"""PreToolUse hook entrypoint: orchestrates enforcement + approval.

Decision order (preserved from the original single-file hook):
  PowerShell tool  -> deny (use the Bash tool)
  Write / Edit     -> writes.decide_write_edit
  mcp__*           -> mcp.classify_mcp_tool
  Bash             -> enforce.enforce_bash (deny), then per-segment trust (allow)
  anything else    -> defer (no output)

Output uses the current hook schema: an allow/deny permissionDecision, or no
output at all to defer to the normal permission flow (a manual prompt).

Library modules live in safe_compounds/. Set SAFE_COMPOUNDS_DISABLE_AI=1 to
disable Haiku fallbacks; SAFE_COMPOUNDS_TRUSTED_JSON to pin the trusted set.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_compounds import config, paths  # noqa: E402
from safe_compounds.approve import is_segment_trusted  # noqa: E402
from safe_compounds.enforce import enforce_bash  # noqa: E402
from safe_compounds.log import log_debug  # noqa: E402
from safe_compounds.mcp import classify_mcp_tool  # noqa: E402
from safe_compounds.shell import split_segments  # noqa: E402
from safe_compounds.trust import get_trusted  # noqa: E402
from safe_compounds.writes import decide_write_edit  # noqa: E402

POWERSHELL_TOOL_REASON = (
    'BLOCKED: PowerShell tool is disabled per global CLAUDE.md rule '
    '("Always use Bash tool, never PowerShell tool"). Re-issue this command using the Bash tool. '
    'For Windows-specific operations, use bash equivalents or a Python script in .tmp/. If PowerShell '
    'is genuinely required, invoke it from Bash via `powershell -NoProfile -Command "..."`.'
)


def allow():
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}))
    sys.exit(0)


def deny(reason):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
        'permissionDecisionReason': reason}}))
    sys.exit(0)


def defer():
    sys.exit(0)


def handle_bash(command):
    if not command:
        defer()

    log_debug(f"=== Hook evaluating command: {command[:200]}")

    reason = enforce_bash(command)
    if reason:
        log_debug(f"DECISION: Deny (enforce): {reason[:80]}")
        deny(reason)

    segments = split_segments(command)
    non_empty = [s for s in segments if s.strip()]
    if not non_empty:
        defer()

    trusted = get_trusted()
    paths.extract_pending_worktree_paths(non_empty)

    if not all(is_segment_trusted(seg, trusted) for seg in non_empty):
        log_debug("DECISION: Defer (not all segments trusted)")
        defer()

    # No $()-substitution re-check is needed here: enforce_bash() blocks any
    # command containing a $() / backtick substitution before this point, so by
    # the time a command reaches approval it provably has none. (The original
    # single-file hook carried a substitution-trust loop here that was therefore
    # unreachable; extract_substitutions remains in shell.py as a tested helper.)

    log_debug("DECISION: Allow")
    allow()


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        defer()

    config.reset()
    paths.reset_pending_worktree_paths()
    paths.reset_allowed_edit_dirs()

    tool = data.get('tool_name')
    tool_input = data.get('tool_input', {})

    if tool == 'PowerShell':
        log_debug("DECISION: Deny (PowerShell tool)")
        deny(POWERSHELL_TOOL_REASON)

    if tool in ('Write', 'Edit'):
        file_path = tool_input.get('file_path', '')
        decision, reason = decide_write_edit(file_path)
        log_debug(f"DECISION: {decision} Write/Edit: {file_path[:100]}")
        if decision == 'allow':
            allow()
        if decision == 'block':
            deny(reason)
        defer()

    if tool and tool.startswith('mcp__'):
        if classify_mcp_tool(tool):
            log_debug(f"DECISION: Allow MCP tool {tool}")
            allow()
        defer()

    if tool != 'Bash':
        defer()

    handle_bash(tool_input.get('command', ''))


if __name__ == '__main__':
    main()
