"""Per-command safety checkers for commands that need more than name-trust:
git/gh write-protection, curl destination rules, sed -i, package managers,
start/wt/cmd launchers, and CWD-scoped file operations (cp/mv/touch/ln/chmod).
"""
import os
import re

from . import ai, config
from .learned import add_learned_command, add_learned_subcommand, learned_subcommands
from .log import log_debug
from .paths import (
    is_in_trusted_script_dir, is_path_within_allowed_edits, is_path_within_claude_plugins,
    is_path_within_cwd, is_path_within_git_worktree, is_safe_read_location, read_script_file,
)
from .shell import ASSIGNMENT_ONLY, get_subcommands, shell_tokenize

# ---------------------------------------------------------------- curl --------
CURL_WRITE_FLAGS = {
    '-X', '--request', '-d', '--data', '--data-raw', '--data-binary',
    '--data-urlencode', '-F', '--form', '--form-string', '-T', '--upload-file', '--json',
}
CURL_LOCALHOST_PATTERNS = re.compile(r'https?://(localhost|127\.0\.0\.1)(:[0-9]+)?(/|$|\s)')


def _matches_configured_domain(segment):
    """True if the URL host contains a domain the consumer marked trusted."""
    domains = config.get_config().get('curl_domains', [])
    for domain in domains:
        if re.search(rf'https?://[^\s/]*{re.escape(domain)}', segment):
            return True
    return False


def is_curl_safe(segment):
    """Approve curl to localhost or a configured-trusted domain (any method);
    otherwise allow only read-only (no write flag) requests.

    Rationale: a GET is read-only, and configured corporate domains are treated
    as trusted for reversible work. Writes to arbitrary public URLs are not
    auto-approved.
    """
    if CURL_LOCALHOST_PATTERNS.search(segment) or _matches_configured_domain(segment):
        return True
    return not any(token in CURL_WRITE_FLAGS for token in segment.split())


# ----------------------------------------------------------------- sed --------
SED_INPLACE_PATTERN = re.compile(r'^-[a-zA-Z]*i')


def is_sed_command_safe(seg):
    """Allow sed unless an -i (in-place edit) flag is present."""
    for token in shell_tokenize(seg)[1:]:
        if token.startswith('--'):
            continue
        if SED_INPLACE_PATTERN.match(token):
            return False
    return True


# ----------------------------------------------------------------- git --------
# Allowlist, not denylist: a git command is approved only if its subcommand is
# known read-only or known reversible (the change can be undone — revert a
# commit, delete a branch/tag, reset --soft, etc.). Anything not listed falls
# through to a prompt. Dual-use subcommands (push/branch/reset/...) are approved
# unless they carry a destructive flag.
GIT_GLOBAL_OPTS_WITH_ARG = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix'}

GIT_SAFE_SUBCOMMANDS = {
    # read-only
    'status', 'log', 'diff', 'show', 'remote', 'describe', 'rev-parse', 'rev-list',
    'ls-files', 'ls-remote', 'shortlog', 'blame', 'reflog', 'cat-file', 'for-each-ref',
    'symbolic-ref', 'name-rev', 'grep', 'count-objects', 'merge-base', 'cherry',
    'whatchanged', 'show-ref', 'show-branch',
    # reversible writes (the effect can be undone)
    'add', 'commit', 'stash', 'fetch', 'pull', 'merge', 'revert', 'cherry-pick',
    'worktree', 'config', 'init', 'clone',
}

# Dual-use subcommands: approved unless one of these destructive flags is present.
GIT_CONDITIONAL_SUBCOMMANDS = {
    'push':   {'--force', '-f', '--force-with-lease', '--delete'},
    'branch': {'-D', '-d', '--delete', '--force'},
    'tag':    {'-d', '--delete'},
    'reset':  {'--hard'},
    'switch': {'--discard-changes', '-f', '--force'},
}


def _git_subcommand(tokens):
    """Return (subcommand, args) skipping git's global options, or (None, [])."""
    i = 1
    while i < len(tokens):
        if tokens[i] in GIT_GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if tokens[i].startswith('-'):
            i += 1
            continue
        return tokens[i], tokens[i + 1:]
    return None, []


def is_git_command_safe(segment):
    """True only if the git command is a known read-only or reversible operation
    (allowlist). Unknown subcommands and destructive flags fall through."""
    tokens = shell_tokenize(segment)
    if not tokens or tokens[0] != 'git':
        return True
    subcommand, args = _git_subcommand(tokens)
    if subcommand is None:
        return True
    if subcommand in GIT_SAFE_SUBCOMMANDS:
        return True
    if subcommand in GIT_CONDITIONAL_SUBCOMMANDS:
        return not any(a in GIT_CONDITIONAL_SUBCOMMANDS[subcommand] for a in args)
    if subcommand == 'checkout':
        return not ('.' in args or '--' in args or '-f' in args or '--force' in args)
    if subcommand == 'clean':
        return any(a in ('-n', '--dry-run') for a in args)
    return False


# ------------------------------------------------------------------ gh --------
GH_ALLOWED_SUBCOMMANDS = {
    'pr':       {'view', 'list', 'diff', 'checks', 'create', 'edit', 'close', 'reopen', 'ready', 'comment', 'review'},
    'issue':    {'view', 'list', 'create', 'edit', 'close', 'reopen', 'comment'},
    'repo':     {'view'},
    'run':      {'view', 'list', 'cancel', 'rerun'},
    'release':  {'view', 'list', 'create', 'edit'},
    'workflow': {'view', 'list', 'run'},
}
GH_WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
GH_REVERSIBLE_API_PATTERNS = [
    re.compile(r'/?orgs/[^/]+/teams(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/branches(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/pulls(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/issues(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/labels(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/milestones(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/comments(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/git/refs(?:/|$)'),
    re.compile(r'/?repos/[^/]+/[^/]+/projects(?:/|$)'),
]
# Base AI-approved 'group:action' pairs; the learned store adds more over time.
GH_AI_APPROVED_PAIRS_BASE = {
    '--version:*', 'issue:2>&1', 'label:*', 'org:*', 'pr:merge',
    'project:*', 'repo:clone', 'repo:create', 'repo:edit', 'repo:list',
}


def _gh_approved_pairs():
    return GH_AI_APPROVED_PAIRS_BASE | learned_subcommands('GH_AI_APPROVED_PAIRS')


def is_gh_command_safe(seg):
    tokens = shell_tokenize(seg)
    if len(tokens) < 2:
        return True
    group = tokens[1]
    if group in ('search', 'status', 'browse'):
        return True
    if group == 'auth':
        subs = get_subcommands(seg, skip=2)
        return bool(subs) and subs[0] in ('status', 'token')
    if group == 'api':
        api_url = ''
        method = 'GET'
        i = 2
        while i < len(tokens):
            if tokens[i] in ('--method', '-X') and i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
                continue
            if not tokens[i].startswith('-') and not api_url:
                api_url = tokens[i]
            i += 1
        if method in GH_WRITE_METHODS:
            for pattern in GH_REVERSIBLE_API_PATTERNS:
                if pattern.search(api_url):
                    log_debug(f"gh api {method} approved: reversible endpoint {api_url}")
                    return True
            log_debug(f"gh api {method} denied: non-reversible endpoint {api_url}")
            return False
        return True
    if group in GH_ALLOWED_SUBCOMMANDS:
        subs = get_subcommands(seg, skip=2)
        action = subs[0] if subs else ''
        if action in GH_ALLOWED_SUBCOMMANDS[group]:
            return True
        pair = f'{group}:{action}'
        if pair in _gh_approved_pairs():
            return True
        result = ai.call_ai(_subcommand_prompt('gh', f'{group} {action}', seg))
        if result is True:
            add_learned_subcommand('GH_AI_APPROVED_PAIRS', pair)
        return result is True
    pair = f'{group}:*'
    if pair in _gh_approved_pairs():
        return True
    result = ai.call_ai(_subcommand_prompt('gh', group, seg))
    if result is True:
        add_learned_subcommand('GH_AI_APPROVED_PAIRS', pair)
    return result is True


# ------------------------------------------------------ package managers ------
def _subcommand_prompt(command, subcommand, full_segment):
    return (
        f'Is "{command} {subcommand}" a safe, legitimate software development operation?\n\n'
        f'Full command:\n```\n{full_segment}\n```\n\n'
        'Respond with ONLY "SAFE" or "DANGEROUS".\n\n'
        'SAFE: Common build, test, install, format, lint, publish, deploy, or dev workflow operations.\n'
        'DANGEROUS: Operations that could cause irreversible system harm, data exfiltration, or security compromise.\n\n'
        'Response (SAFE or DANGEROUS):'
    )


NPM_SAFE_SUBCOMMANDS = {'audit', 'ci', 'dedupe', 'install', 'list', 'ls', 'outdated', 'prune', 'root', 'run', 'test', 'update'}
YARN_SAFE_SUBCOMMANDS = {
    'add', 'audit', 'backstage-cli', 'bin', 'build:all', 'build:backend',
    'build:frontend', 'check', 'dedupe', 'dev', 'dlx', 'exec', 'explain',
    'husky', 'info', 'install', 'link', 'lint:all', 'lint:fix', 'list',
    'node', 'outdated', 'pack', 'prettier', 'prettier:check', 'prettier:fix',
    'remove', 'run', 'start', 'start-backend', 'test', 'test:all', 'tsc',
    'unlink', 'upgrade', 'why', 'workspace', 'workspaces',
}
PIP_SAFE_SUBCOMMANDS = {'2>&1', 'check', 'freeze', 'install', 'list', 'show', 'uninstall'}
PNPM_SAFE_SUBCOMMANDS = {'install', 'add', 'update', 'remove', 'list', 'outdated', 'prune'}
BUN_SAFE_SUBCOMMANDS = {'install', 'add', 'update', 'remove', 'test'}

PKG_MANAGERS = {
    'npm':  {'safe': NPM_SAFE_SUBCOMMANDS,  'category': 'NPM_SAFE_SUBCOMMANDS',  'cache_clean': True,  'yarn_flags': False},
    'yarn': {'safe': YARN_SAFE_SUBCOMMANDS, 'category': 'YARN_SAFE_SUBCOMMANDS', 'cache_clean': True,  'yarn_flags': True},
    'pip':  {'safe': PIP_SAFE_SUBCOMMANDS,  'category': 'PIP_SAFE_SUBCOMMANDS',  'cache_clean': False, 'yarn_flags': False},
    'pnpm': {'safe': PNPM_SAFE_SUBCOMMANDS, 'category': 'PNPM_SAFE_SUBCOMMANDS', 'cache_clean': False, 'yarn_flags': False},
    'bun':  {'safe': BUN_SAFE_SUBCOMMANDS,  'category': 'BUN_SAFE_SUBCOMMANDS',  'cache_clean': False, 'yarn_flags': False},
}


def _yarn_subcommands(seg):
    tokens = shell_tokenize(seg)
    subs = []
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t.startswith('--') and '=' not in t:
            i += 2
        elif t.startswith('-'):
            i += 1
        else:
            subs.append(t)
            i += 1
    return subs


def is_pkg_manager_safe(seg, manager):
    cfg = PKG_MANAGERS[manager]
    subs = _yarn_subcommands(seg) if cfg['yarn_flags'] else get_subcommands(seg)
    if not subs:
        return False
    if subs[0] in (cfg['safe'] | learned_subcommands(cfg['category'])):
        return True
    if cfg['cache_clean'] and subs[0] == 'cache':
        return len(subs) > 1 and subs[1] == 'clean'
    result = ai.call_ai(_subcommand_prompt(manager, subs[0], seg))
    if result is True:
        add_learned_subcommand(cfg['category'], subs[0])
    return result is True


# --------------------------------------------------------------- start --------
START_SAFE_EXTENSIONS = {
    '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.pdf', '.rtf', '.odt',
    '.md', '.txt', '.csv', '.tsv', '.json', '.log', '.xml', '.yaml', '.yml',
    '.html', '.htm',
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico', '.tiff',
    '.mp4', '.mov', '.webm', '.mp3', '.wav',
}


def is_start_safe(seg):
    tokens = shell_tokenize(seg)
    if len(tokens) < 2:
        return False
    args = [t for t in tokens[1:] if not t.startswith('/')]
    if not args:
        return False
    target = args[-1].strip('"\'')
    if target.startswith('http://') or target.startswith('https://'):
        return True
    _, ext = os.path.splitext(target)
    return ext.lower() in START_SAFE_EXTENSIONS


# ---------------------------------------------------------- powershell --------
POWERSHELL_ENV_PATTERN = re.compile(
    r'^powershell\s+-NoProfile\s+-Command\s+"?\[System\.Environment\]::GetEnvironmentVariable\('
)


def is_powershell_safe(seg):
    return bool(POWERSHELL_ENV_PATTERN.match(seg.strip()))


# ------------------------------------------------------------------ wt --------
WT_SUBCOMMANDS = {
    'new-tab', 'nt', 'split-pane', 'sp', 'focus-tab', 'ft', 'move-focus', 'mf',
    'swap-pane', 'focus-pane', 'fp', 'move-pane', 'mp', 'new-window', 'nw',
}
WT_FLAGS_WITH_ARG = {
    '-d', '--startingDirectory', '--title', '-p', '--profile', '--tabColor',
    '--colorScheme', '-w', '--window', '--size', '--pos', '-s', '--startingDir',
    '--appendCommandLine',
}


def is_wt_safe(seg, trusted):
    """Approve `wt` only if the program it ultimately launches is trusted."""
    tokens = shell_tokenize(seg)
    if len(tokens) < 2:
        return False
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in WT_FLAGS_WITH_ARG:
            i += 2
            continue
        if t.startswith('-'):
            i += 1
            continue
        base = os.path.basename(t.strip('"\'').replace('\\', '/')).lower()
        if base.endswith('.exe'):
            base = base[:-4]
        if base in WT_SUBCOMMANDS:
            i += 1
            continue
        return base in trusted
    return True


# ----------------------------------------------------------- cmd files --------
CMD_BATCH_SAFE_PATTERNS = [
    re.compile(r'^@?echo\s+(off|on)\s*$', re.IGNORECASE),
    re.compile(r'^setlocal\b', re.IGNORECASE),
    re.compile(r'^endlocal\b', re.IGNORECASE),
    re.compile(r'^exit\s*/b', re.IGNORECASE),
    re.compile(r'^goto\s+:eof\s*$', re.IGNORECASE),
    re.compile(r'^:[a-zA-Z_]'),
    re.compile(r'^set\s+', re.IGNORECASE),
    re.compile(r'^for\s+%%', re.IGNORECASE),
    re.compile(r'^if\s+', re.IGNORECASE),
    re.compile(r'^echo\b', re.IGNORECASE),
]


def is_cmd_file_safe(filepath, trusted):
    from .approve import is_segment_trusted
    filepath = filepath.strip('"\'')
    if is_in_trusted_script_dir(filepath):
        return True
    content = read_script_file(filepath)
    if content is None:
        return False
    batch_trusted = trusted | {ASSIGNMENT_ONLY}
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('::') or re.match(r'^rem\b', line, re.IGNORECASE):
            continue
        if line.startswith('@'):
            line = line[1:].strip()
        if any(p.match(line) for p in CMD_BATCH_SAFE_PATTERNS):
            continue
        if re.match(r'^call\s+', line, re.IGNORECASE):
            line = line[5:].strip()
        if '%' in line:
            from .scripts import ask_ai_about_script
            return ask_ai_about_script(content, 'batch', filepath) is True
        if not is_segment_trusted(line, batch_trusted):
            return False
    return True


# -------------------------------------------------- CWD-scoped file ops -------
CWD_FILE_COMMAND_CONFIG = {
    'mv':    {'flags_with_args': {'-S', '--suffix', '-t', '--target-directory'}, 'min_args': 2, 'skip_args': 0},
    'cp':    {'flags_with_args': {'-S', '--suffix', '-t', '--target-directory'}, 'min_args': 2, 'skip_args': 0},
    'touch': {'flags_with_args': {'-r', '--reference', '-d', '--date', '-t'},    'min_args': 1, 'skip_args': 0},
    'ln':    {'flags_with_args': {'-t', '--target-directory', '-S', '--suffix'}, 'min_args': 2, 'skip_args': 0},
    'chmod': {'flags_with_args': {'--reference'},                                'min_args': 2, 'skip_args': 1},
}


def _dest_allowed(path):
    return (is_path_within_cwd(path) or is_path_within_git_worktree(path)
            or is_path_within_allowed_edits(path) or is_path_within_claude_plugins(path))


def _source_allowed(path):
    return _dest_allowed(path) or is_safe_read_location(path)


def check_cwd_file_command(seg, command):
    """Approve cp/mv/touch/ln/chmod only when paths stay within CWD (and, for
    sources, safe read locations)."""
    cfg = CWD_FILE_COMMAND_CONFIG.get(command)
    if not cfg:
        return False
    tokens = shell_tokenize(seg)
    if not tokens or tokens[0].replace('.exe', '') != command:
        return False

    args = []
    i = 1
    skip_next = False
    while i < len(tokens):
        token = tokens[i]
        if skip_next:
            skip_next = False
            i += 1
            continue
        if token.startswith('-') and token != '-':
            if token in cfg['flags_with_args']:
                skip_next = True
            i += 1
            continue
        args.append(token)
        i += 1

    if len(args) < cfg['min_args']:
        return False
    paths = args[cfg['skip_args']:]

    if command in ('cp', 'mv', 'ln') and len(paths) >= 2:
        dest = paths[-1].strip('"\'')
        if not _dest_allowed(dest):
            log_debug(f"{command} destination outside allowed areas: {dest}")
            return False
        for src in paths[:-1]:
            if not _source_allowed(src.strip('"\'')):
                log_debug(f"{command} source outside allowed areas: {src}")
                return False
        return True

    for path in paths:
        if not is_path_within_cwd(path.strip('"\'')):
            log_debug(f"{command} path outside CWD: {path}")
            return False
    return True


# ----------------------------------------------- output redirection ----------
def is_output_redirection_safe(segment):
    """True if any > / >> redirect targets a relative path, .tmp/, or /dev/null."""
    match = re.search(r'(?:^|[;\|&]|\s)(>>?)\s*([^\s;&|]+)', segment)
    if not match:
        return True
    target = match.group(2).strip().strip('"\'')
    if not re.match(r'^([a-zA-Z]:|/|\\)', target):
        return True
    if target.startswith('.tmp/') or target.startswith('.tmp\\'):
        return True
    if '/.tmp/' in target or '\\.tmp\\' in target or '/.tmp\\' in target or '\\.tmp/' in target:
        return True
    if target == '/dev/null':
        return True
    return False


# --------------------------------------------------- unknown commands --------
UNKNOWN_CMD_PATTERN = re.compile(r'^[a-zA-Z][\w.-]*$')


def is_unknown_command_safe(command_name, full_segment):
    """Ask Haiku whether an unrecognized CLI tool is a safe dev tool; remember it."""
    if not UNKNOWN_CMD_PATTERN.match(command_name):
        return False
    log_debug(f"Unknown command '{command_name}', asking AI")
    prompt = f"""Is the CLI tool "{command_name}" a safe, common development or productivity tool?

The full command being run is:
```
{full_segment}
```

Respond with ONLY "SAFE" or "DANGEROUS".

SAFE: Well-known open-source or standard CLI tools for software development, build systems, \
document processing, media conversion, linting, formatting, testing, deployment, presentation, etc. \
Examples: webpack, eslint, prettier, tsc, ffmpeg, pandoc, decktape, mocha, jest, esbuild, vite, etc.

DANGEROUS: System administration tools that modify OS state, network attack tools, disk management \
tools, or anything that could cause irreversible system damage. Examples: dd, mkfs, iptables, fdisk, \
format, etc. Also respond DANGEROUS if you don't recognize the tool at all.

Response (SAFE or DANGEROUS):"""
    result = ai.call_ai(prompt)
    if result is True:
        add_learned_command(command_name)
        return True
    return False
