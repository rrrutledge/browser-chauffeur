"""Classify EnterWorktree and ExitWorktree tool calls as auto-allowable.

Creating a *new* worktree (no `path`, optional `name`) always lands under
`.claude/worktrees/` -- the tool's own hard-coded default -- so it's approved
unconditionally; there's no destination to check. Relocating into an
*existing* worktree (`path` given) only ever succeeds when that path is
already registered in `git worktree list` for the repo that owns it -- the
tool enforces that itself and refuses otherwise. But Claude Code layers a
second, non-hookable check on top of that: relocating the permission root
into a path outside `.claude/worktrees/` shows the user a manual
confirmation regardless of what this hook decides. A `path` under
`.claude/worktrees/` is approved; anywhere else -- a project's own top-level
`.worktrees/` convention included -- is blocked with a message pointing at
`.claude/worktrees/`, since approving it here would just mean the user hits
that manual dialog anyway with no corrective guidance first.

ExitWorktree takes no path at all -- it only ever acts on the one worktree
this same session entered via EnterWorktree, tracked internally by the
harness, not supplied by the model. `action: "keep"` never deletes anything.
`action: "remove"` mirrors `git branch -d`'s safety contract: the tool
itself refuses when the worktree has uncommitted files or commits that
never made it onto the original branch, unless `discard_changes: true`
forces it through -- so plain removal is reversible (everything it deletes
is already preserved elsewhere) and only the `discard_changes` override,
which knowingly throws work away, needs a human.
"""
from .log import log_debug
from .paths import is_under_claude_worktrees


def classify_enter_worktree(tool_input):
    """Return ('allow'|'block', reason_or_None) for an EnterWorktree tool call."""
    path = tool_input.get('path')
    if path and not is_under_claude_worktrees(path):
        reason = (
            f'BLOCKED: "{path}" is not under .claude/worktrees/. Claude Code shows a '
            'manual, non-hookable confirmation for any EnterWorktree relocation outside that '
            'directory, so this cannot be auto-approved. Move or recreate the worktree under '
            '.claude/worktrees/<name> instead -- EnterWorktree with no path already creates new '
            'worktrees there by default.'
        )
        log_debug(f"EnterWorktree: path outside .claude/worktrees/, blocking: {path!r}")
        return 'block', reason
    log_debug(f"EnterWorktree: approving (path={path!r})")
    return 'allow', None


def classify_exit_worktree(tool_input):
    """Return True to auto-allow an ExitWorktree tool call, False to prompt."""
    action = tool_input.get('action')
    if action == 'keep':
        log_debug("ExitWorktree: action=keep, approving")
        return True
    if action == 'remove':
        if tool_input.get('discard_changes'):
            log_debug("ExitWorktree: discard_changes=True forces past unsaved work, prompting")
            return False
        log_debug("ExitWorktree: plain remove (tool self-refuses on unsaved work), approving")
        return True
    log_debug(f"ExitWorktree: unrecognized action {action!r}, prompting")
    return False
