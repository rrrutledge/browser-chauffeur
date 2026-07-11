"""Cross-platform path reasoning for "is this path inside an allowed area?".

On Windows/MSYS, os.getcwd() yields /c/Users/... while commands may use
C:/Users/... — every comparison here normalizes both forms to a canonical
lowercase forward-slash Windows path so the two compare equal.
"""
import itertools
import json
import os
import re
import tempfile

from .log import log_debug


def convert_msys_path_to_windows(path):
    """Convert an MSYS /c/... path to Windows C:/... form (no-op otherwise)."""
    match = re.match(r'^/([a-zA-Z])(/.*)?$', path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        return f'{drive}:{rest}'
    return path


def normalize_path_cross_platform(path):
    """Return a canonical lowercase forward-slash path for comparison."""
    path = os.path.expanduser(path)
    msys = re.match(r'^/([a-zA-Z])/(.*)$', path.replace('\\', '/'))
    if msys:
        path = msys.group(1).upper() + ':/' + msys.group(2)
    path = path.replace('\\', '/')
    path = re.sub(r'(?<!:)/+', '/', path)
    return path.lower().rstrip('/')


def _canonical(path):
    """Full normalization including .. resolution, for prefix comparison."""
    return os.path.normpath(normalize_path_cross_platform(path)).lower().replace('\\', '/')


def _abs_against_cwd(path):
    """Expand ~, then make relative paths absolute against CLAUDE_CWD."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and not re.match(r'^/[a-zA-Z]/', path):
        cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
        path = os.path.join(cwd, path)
    return path


def resolve_against_cwd(path):
    """Public wrapper around _abs_against_cwd, for callers outside this module
    that need to show a resolved path in a message (e.g. a block reason)."""
    return _abs_against_cwd(path)


def path_under(path, base, *, resolve_cwd=True):
    """True if `path` equals or is nested within `base` directory."""
    try:
        if resolve_cwd:
            path = _abs_against_cwd(path)
        path_norm = _canonical(path)
        base_norm = _canonical(base)
        if path_norm == base_norm:
            return True
        prefix = base_norm if base_norm.endswith('/') else base_norm + '/'
        return path_norm.startswith(prefix)
    except Exception:
        return False


def is_in_git_repo(path):
    """True if `path` or any ancestor contains a .git directory."""
    try:
        path = os.path.normpath(path)
        while path:
            if os.path.isdir(os.path.join(path, '.git')):
                return True
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        return False
    except Exception:
        return False


def is_path_within_cwd(path):
    """True if `path` is within (or equal to) CLAUDE_CWD."""
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    return path_under(path, cwd)


def is_safe_read_location(path):
    """True if `path` is under the user's home, Downloads, Desktop, Documents,
    or a system/session temp dir — locations safe to read from as a copy
    source. These are read-only checks: the destination-containment check
    (_dest_allowed) is what keeps the write side safe, so this only needs to
    keep sensitive files (SSH keys, credentials, tokens) out of the source
    set, not lock the source down to "inside the repo"."""
    try:
        home = os.path.expanduser('~')
        bases = [os.path.join(home, sub) if sub else home for sub in ('downloads', 'desktop', 'documents', '')]
        bases += [tempfile.gettempdir(), '/tmp']
        for base in bases:
            if path_under(path, base, resolve_cwd=False) or path_under(_abs_against_cwd(path), base, resolve_cwd=False):
                return True
        return False
    except Exception:
        return False


def is_path_within_claude_plugins(path):
    """True if `path` is within ~/.claude/plugins/ (trusted plugin content)."""
    return path_under(path, os.path.expanduser('~/.claude/plugins'))


# Paths declared by "git worktree add <path>" in the current compound command.
_pending_worktree_paths = set()


def reset_pending_worktree_paths():
    _pending_worktree_paths.clear()


def extract_pending_worktree_paths(segments):
    """Record new worktree paths so cp/mv/mkdir into them can be approved."""
    from .shell import shell_tokenize
    skip_opts = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix'}
    for seg in segments:
        tokens = shell_tokenize(seg.strip()) if seg.strip() else []
        i = 0
        while i < len(tokens) and tokens[i].startswith('-'):
            i += 2 if tokens[i] in skip_opts else 1
        if i >= len(tokens) or tokens[i] != 'git':
            continue
        i += 1
        while i < len(tokens) and tokens[i].startswith('-'):
            i += 2 if tokens[i] in skip_opts else 1
        if i >= len(tokens) or tokens[i] != 'worktree':
            continue
        i += 1
        if i >= len(tokens) or tokens[i] != 'add':
            continue
        i += 1
        while i < len(tokens):
            if tokens[i] in {'-b', '-B', '--reason', '--track'} and i + 1 < len(tokens):
                i += 2
            elif tokens[i].startswith('-'):
                i += 1
            else:
                break
        if i < len(tokens):
            norm = _canonical(tokens[i].strip('\'"'))
            _pending_worktree_paths.add(norm)
            log_debug(f"Recorded pending worktree path: {norm}")


def is_path_within_git_worktree(path):
    """True if `path` is within a worktree declared in this compound command."""
    try:
        path_norm = _canonical(path)
        for wt in _pending_worktree_paths:
            prefix = wt if wt.endswith('/') else wt + '/'
            if path_norm == wt or path_norm.startswith(prefix):
                return True
    except Exception:
        pass
    return False


_ALLOWED_EDIT_DIRS = None


def _load_allowed_edit_dirs():
    """Directories covered by Edit/Write allow rules across settings files."""
    dirs = set()
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    roots = [os.path.expanduser('~/.claude')]
    if cwd:
        roots.append(os.path.join(cwd, '.claude'))
    for root in roots:
        for name in ('settings.json', 'settings.local.json'):
            try:
                with open(os.path.join(root, name), encoding='utf-8') as f:
                    data = json.load(f)
                for rule in data.get('permissions', {}).get('allow', []):
                    m = re.match(r'^(?:Edit|Write)\((.+)\)', rule)
                    if not m:
                        continue
                    raw = os.path.expanduser(m.group(1).strip('"\''))
                    if '*' in raw or '?' in raw:
                        parts = raw.replace('\\', '/').split('/')
                        non_glob = list(itertools.takewhile(
                            lambda p: '*' not in p and '?' not in p, parts))
                        base = '/'.join(non_glob).rstrip('/')
                    else:
                        base = os.path.dirname(raw).rstrip('/')
                    if base:
                        dirs.add(normalize_path_cross_platform(base))
            except Exception:
                pass
    return dirs


def reset_allowed_edit_dirs():
    global _ALLOWED_EDIT_DIRS
    _ALLOWED_EDIT_DIRS = None


def is_path_within_allowed_edits(path):
    """True if `path` is within a dir already covered by an Edit/Write rule."""
    global _ALLOWED_EDIT_DIRS
    if _ALLOWED_EDIT_DIRS is None:
        _ALLOWED_EDIT_DIRS = _load_allowed_edit_dirs()
    for allowed in _ALLOWED_EDIT_DIRS:
        if path_under(path, allowed):
            log_debug(f"is_path_within_allowed_edits: {path!r} under {allowed!r}")
            return True
    return False


def read_script_file(filename):
    """Read a script file (handling /c/ <-> C:/ and CWD-relative paths)."""
    original = filename
    try:
        filename = convert_msys_path_to_windows(filename)
        filename = os.path.expandvars(os.path.expanduser(filename))
        if not os.path.isabs(filename):
            cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
            filename = os.path.join(cwd, filename)
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        log_debug(f"read_script_file failed for {original!r} -> {filename!r}: {type(e).__name__}: {e}")
        return None


# Generic, organization-agnostic directories whose scripts are trusted: the
# temp dir and Claude's own authored content. Consumers add their own plugin
# directories via the "trusted_script_dirs" config key.
TRUSTED_SCRIPT_DIRS = [
    '.tmp/', '/.tmp/', '\\.tmp\\',
    '.claude/',
    'plugins/',
    'scripts/',
]


def is_in_trusted_script_dir(filename):
    """True if the script lives in a known-safe directory (.tmp, .claude, or a
    consumer-configured directory)."""
    from . import config
    resolved = _abs_against_cwd(filename)
    normalized = resolved.replace('\\', '/')
    dirs = TRUSTED_SCRIPT_DIRS + list(config.get_config().get('trusted_script_dirs', []))
    return any(d.replace('\\', '/') in normalized for d in dirs)
