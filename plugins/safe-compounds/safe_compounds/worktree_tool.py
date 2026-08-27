"""Classify EnterWorktree and ExitWorktree tool calls as auto-allowable.

EnterWorktree is approved unconditionally by this hook, for both its forms.
Creating a *new* worktree (no `path`, optional `name`) is the EnterWorktree
equivalent of `git worktree add` under `.claude/worktrees/`, which is already
a trusted git subcommand. Relocating into an *existing* worktree (`path`
given) only ever succeeds when that path is already registered in `git
worktree list` for the repo that owns it -- the tool enforces that itself
and refuses otherwise -- so a bad or stale path just makes EnterWorktree
error out harmlessly instead of relocating anywhere; there's no destructive
outcome for the hook to gate against. That holds regardless of whether the
path lives under `.claude/worktrees/` or a project's own convention (e.g.
`.worktrees/`) -- the location doesn't matter to this hook's decision.

This hook's "allow" doesn't make the call silent, though. Claude Code
enforces its own confirmation, independent of any hook decision, whenever
the target path falls outside `.claude/worktrees/` -- relocating the
session's working directory, write access, and project config to that
location is treated as a permission-root change. Per Claude Code's own docs,
only `bypassPermissions` mode suppresses that prompt. So a user still sees a
one-time confirmation click when entering an out-of-convention worktree no
matter what this hook decides -- that's the harness working as designed.

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


def classify_enter_worktree(tool_input):
    """Return True to auto-allow an EnterWorktree tool call, False to prompt."""
    log_debug(f"EnterWorktree: approving (path={tool_input.get('path')!r})")
    return True


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
