"""Classify EnterWorktree and ExitWorktree tool calls as auto-allowable.

Creating a *new* worktree (no `path` given) always lands under
`.claude/worktrees/`, the EnterWorktree equivalent of `git worktree add`
there -- already a trusted git subcommand -- so this case is approved
unconditionally.

Switching into an *existing* worktree (`path` given) is approved only when
that path already lives under `.claude/worktrees/`. A path outside it is
blocked instead of approved, with a message that tells the model to bring
the worktree into `.claude/worktrees/` first with `git worktree move` (which
preserves the branch and any uncommitted work) and retry with the new path --
the same self-correcting pattern used elsewhere in this hook (e.g. the
PowerShell-tool block pointing at Bash).

Claude Code enforces its own permission-root confirmation on top of this --
moving the session's working directory, write access, and project config
counts as a permission-root change, and per Claude Code's own docs only
`bypassPermissions` mode can suppress that prompt; no hook decision can. That
confirmation fires for *any* explicit-`path` EnterWorktree call, including
ones already inside `.claude/worktrees/`, so approving the in-convention
case does not buy a click-free path -- the harness still asks. It's still
the right call: it keeps the operation itself correct (no stray worktree
outside the convention) and skips a redundant hook-issued block on top of
the harness's own prompt.

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


def _under_claude_worktrees(path):
    normalized = path.replace('\\', '/').rstrip('/')
    return normalized.endswith('/.claude/worktrees') or '/.claude/worktrees/' in normalized + '/'


def classify_enter_worktree(tool_input):
    """Return (approved, reason) for an EnterWorktree tool call.

    `reason` is a corrective message when `approved` is False, else None.
    """
    path = tool_input.get('path')
    if not path:
        log_debug("EnterWorktree: no path (creates fresh under .claude/worktrees/), approving")
        return True, None

    if _under_claude_worktrees(path):
        log_debug(f"EnterWorktree: path under .claude/worktrees/ ({path!r}), approving")
        return True, None

    log_debug(f"EnterWorktree: path outside .claude/worktrees/ ({path!r}), blocking with redirect")
    reason = (
        'BLOCKED: "{path}" is outside .claude/worktrees/.\n\n'
        'To keep this worktree\'s branch and any uncommitted work while staying in convention, '
        'move it into place first, then retry EnterWorktree with the new path:\n'
        '  git worktree move "{path}" "$(git rev-parse --show-toplevel)/.claude/worktrees/<name>"\n\n'
        'If there\'s nothing to preserve, call EnterWorktree with `name` (or no arguments) '
        'instead of `path` -- that always creates fresh under .claude/worktrees/.'
    ).format(path=path)
    return False, reason


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
