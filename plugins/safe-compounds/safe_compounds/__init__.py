"""Library modules for the safe-compounds PreToolUse hook.

The hook auto-approves compound bash commands whose every segment uses an
already-trusted command, enforces a set of CLAUDE.md style rules (blocking
heredocs, output redirection, inline scripts, etc.), and classifies MCP and
Write/Edit tool calls. See hook.py for the orchestrator entrypoint.
"""
