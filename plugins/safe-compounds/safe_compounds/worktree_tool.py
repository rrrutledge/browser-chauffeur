"""Classify EnterWorktree and ExitWorktree tool calls as auto-allowable.

Entering an *existing* worktree (`path` given) only ever relocates the
session into a directory the tool itself will refuse unless that path is
already registered in `git worktree list` for the repo that owns it -- so
running that same check here, before the tool executes, is enough to prove
the target is a real, git-tracked worktree rather than an arbitrary
model-supplied directory. That holds regardless of whether the path lives
under `.claude/worktrees/` or a project's own convention (e.g. `.worktrees/`)
-- the location doesn't matter, git's own bookkeeping is the proof.

Creating a *new* worktree (no `path`, optional `name`) is the EnterWorktree
equivalent of `git worktree add` under `.claude/worktrees/`, which is already
a trusted git subcommand -- so it's approved unconditionally.

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
import subprocess

from .log import log_debug
from .paths import normalize_path_cross_platform, resolve_against_cwd


def _is_registered_worktree(path):
    resolved = resolve_against_cwd(path)
    try:
        result = subprocess.run(
            ['git', '-C', resolved, 'worktree', 'list', '--porcelain'],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    target = normalize_path_cross_platform(resolved)
    for line in result.stdout.splitlines():
        if line.startswith('worktree '):
            if normalize_path_cross_platform(line[len('worktree '):].strip()) == target:
                return True
    return False


def classify_enter_worktree(tool_input):
    """Return True to auto-allow an EnterWorktree tool call, False to prompt."""
    path = tool_input.get('path')
    if not path:
        log_debug("EnterWorktree: creating new worktree (no path), approving")
        return True
    if _is_registered_worktree(path):
        log_debug(f"EnterWorktree: {path!r} is a registered git worktree, approving")
        return True
    log_debug(f"EnterWorktree: {path!r} not a registered git worktree, prompting")
    return False


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
