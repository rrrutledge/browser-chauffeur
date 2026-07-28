"""Classify EnterWorktree tool calls as auto-allowable.

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
