#!/usr/bin/env python
"""
PreToolUse hook: approve compound bash commands where every segment
uses commands already trusted in the permissions allow list.

This handles cases like `cd /some/path && grep ... 2>/dev/null` that
trigger Claude Code's built-in safety check even though both `cd` and
`grep` are individually trusted.

Also validates $() command substitutions recursively — if the commands
inside every substitution are all trusted, the whole command is approved.

Additionally analyzes node -e and python -c inline scripts to auto-approve
them if they only perform read-only operations (no file writes, no execution
of external commands, no destructive operations). Uses pattern matching for
obvious cases, and Claude Haiku AI analysis for ambiguous scripts.

For package manager subcommands (yarn, npm, pip, pnpm, bun) and gh subcommands
not in the hardcoded safe lists, falls through to Claude Haiku AI analysis.
If AI approves, the subcommand is automatically added to the appropriate safe
list in this script's source so future runs approve it without any prompt.

Auto-approves file operation commands (mv, cp, touch, ln, chmod) when all
path arguments are within the current working directory, preventing
accidental system-wide changes while allowing normal project work.

Trusted commands are loaded dynamically from ~/.claude/settings.json so
this script stays in sync automatically when the allow list is updated.
"""
import json
import os
import re
import shlex
import sys
import urllib.request
import urllib.error
from datetime import datetime

LOG_FILE = os.path.expanduser('~/.claude/hook-debug.log')

def log_debug(message):
    """Append debug message to log file with timestamp."""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass

SHELL_BUILTINS = {
    '[', '[[', 'basename', 'dirname', 'printf', 'read', 'true', 'false',
}

SAFE_COMMANDS = {
    'awk',
    'base32', 'base64', 'basename', 'bash', 'bc', 'bq', 'bun',
    'cal', 'cat', 'cd', 'claude', 'clip', 'cmp', 'column', 'comm', 'command', 'cut', 'cygpath',
    'date', 'decktape', 'df', 'diff', 'dirname', 'docker', 'du',
    'echo', 'env', 'exec', 'expand', 'explorer', 'export', 'expr',
    'factor', 'file', 'find', 'findstr', 'fmt', 'fold', 'free', 'fsutil',
    'gcloud', 'getconf', 'gh', 'git', 'grep', 'groups',
    'head', 'hexdump', 'hostname',
    'iconv', 'id', 'identify',
    'jobs', 'join', 'jq',
    'kill', 'kubectl',
    'less', 'locale', 'logname', 'look', 'ls', 'lsof',
    'md5sum', 'mkdir', 'more',
    'nc', 'netstat', 'nl', 'npm', 'nproc', 'npx', 'numfmt', 'nvm',
    'od',
    'pandoc', 'paste', 'perl', 'pg_isready', 'pip', 'pnpm', 'printenv', 'ps', 'psql', 'pwd',
    'Read', 'readlink', 'realpath', 'rev', 'rm', 'rmdir',
    'seq', 'sha1sum', 'sha256sum', 'sha512sum', 'sleep', 'sort', 'source', 'stat', 'strings',
    'tac', 'tail', 'tasklist', 'tee', 'test', 'timeout', 'tr', 'tree', 'tty', 'type',
    'uname', 'unexpand', 'uniq', 'unzip', 'uptime', 'users',
    'w', 'wait', 'wc', 'where', 'which', 'who', 'whoami',
    'xargs', 'xxd',
    'yarn', 'yes', 'yt-dlp',
}


def load_trusted_from_settings():
    trusted = set()
    for settings_name in ('settings.json', 'settings.local.json'):
        settings_path = os.path.join(
            os.path.expanduser('~/.claude'), settings_name,
        )
        try:
            with open(settings_path, encoding='utf-8') as f:
                settings = json.load(f)
            allow = settings.get('permissions', {}).get('allow', [])
            for rule in allow:
                m = re.match(r'^Bash\(([a-zA-Z][\w-]*)', rule)
                if m:
                    trusted.add(m.group(1))
        except Exception:
            pass
    return trusted


TRUSTED_COMMANDS = SHELL_BUILTINS | SAFE_COMMANDS | load_trusted_from_settings()

SHELL_BODY_KEYWORDS = {'do', 'then', 'else', 'elif', 'if', 'while', 'until'}

SHELL_STRUCTURE_ONLY = {'for', 'done', 'fi', 'esac', 'case', 'select', 'in'}

NODE_DANGEROUS_PATTERNS = [
    re.compile(r'(?<!\w)exec\s*\('), re.compile(r'(?<!\w)execSync\b'),
    re.compile(r'(?<!\w)spawn\s*\('), re.compile(r'(?<!\w)spawnSync\b'),
    re.compile(r'(?<!\w)fork\s*\('), re.compile(r'(?<!\w)execFile\b'),
    re.compile(r'(?<!\w)system\s*\('),
    re.compile(r'(?<![\w.$])eval\s*\('), re.compile(r'(?<!\w)Function\s*\('),
]

PYTHON_DANGEROUS_PATTERNS = [
    re.compile(r'(?<!\w)subprocess\.'), re.compile(r'(?<!\w)os\.system\b'),
    re.compile(r'(?<!\w)os\.popen\b'),
    re.compile(r'(?<!\w)eval\s*\('), re.compile(r'(?<!\w)exec\s*\('),
    re.compile(r'(?<!\w)compile\s*\('),
    re.compile(r'(?<!\w)__import__\b'),
]

GIT_GLOBAL_OPTS_WITH_ARG = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix'}

SED_INPLACE_PATTERN = re.compile(r'^-[a-zA-Z]*i')

CMD_BATCH_SAFE_PATTERNS = [
    re.compile(r'^@?echo\s+(off|on)\s*$', re.IGNORECASE),
    re.compile(r'^setlocal\b', re.IGNORECASE),
    re.compile(r'^endlocal\b', re.IGNORECASE),
    re.compile(r'^exit\s*/b', re.IGNORECASE),
    re.compile(r'^goto\s+:eof\s*$', re.IGNORECASE),
    re.compile(r'^:[a-zA-Z_]'),   # batch labels
    re.compile(r'^set\s+', re.IGNORECASE),
    re.compile(r'^for\s+%%', re.IGNORECASE),
    re.compile(r'^if\s+', re.IGNORECASE),
    re.compile(r'^echo\b', re.IGNORECASE),
]

GIT_DANGEROUS_SUBCOMMANDS = {
    'push': {'--force', '-f', '--force-with-lease'},
    'reset': {'--hard'},
    'clean': {'-f', '-fd', '-fdx', '-fx'},
    'branch': {'-D'},
    'tag': {'-d', '--delete'},
}

CURL_WRITE_FLAGS = {
    '-X', '--request',
    '-d', '--data', '--data-raw', '--data-binary', '--data-urlencode',
    '-F', '--form', '--form-string',
    '-T', '--upload-file',
    '--json',
}

CURL_LOCALHOST_PATTERNS = re.compile(
    r'https?://(localhost|127\.0\.0\.1)(:[0-9]+)?(/|$|\s)'
)

CURL_WELLSKY_PATTERNS = re.compile(
    r'https?://[^\s]*\.(atlassian\.net|wellskycorp\.sharepoint\.com|wellsky\.io|wellsky\.com)[/"\'\s]'
)


def is_curl_safe(segment):
    """Auto-approve curl to localhost or WellSky corporate domains (any method), or read-only (GET) curl to any URL."""
    if CURL_LOCALHOST_PATTERNS.search(segment):
        return True

    if CURL_WELLSKY_PATTERNS.search(segment):
        return True

    tokens = segment.split()
    for token in tokens:
        if token in CURL_WRITE_FLAGS:
            return False

    return True

# Explicit allowlist of file types `start` may open in their default app.
# Viewable documents, images, media, and plain-text/data files only — no
# executable or script types, which still fall through to a manual prompt.
START_SAFE_EXTENSIONS = {
    # Documents
    '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.pdf', '.rtf', '.odt',
    # Text / data
    '.md', '.txt', '.csv', '.tsv', '.json', '.log', '.xml', '.yaml', '.yml',
    '.html', '.htm',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico', '.tiff',
    # Media
    '.mp4', '.mov', '.webm', '.mp3', '.wav',
}

POWERSHELL_ENV_PATTERN = re.compile(
    r'^powershell\s+-NoProfile\s+-Command\s+"?\[System\.Environment\]::GetEnvironmentVariable\('
)

STANDARD_BASH_VARS = {
    'HOME', 'PATH', 'USER', 'SHELL', 'TERM', 'TMPDIR', 'TMP', 'TEMP',
    'PWD', 'OLDPWD', 'EDITOR', 'VISUAL', 'PAGER', 'MANPATH', 'LANG',
    'LC_ALL', 'LC_CTYPE', 'DISPLAY', 'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE',
    'SSH_AUTH_SOCK', 'SSH_AGENT_PID', 'CLAUDE_CWD', 'PROFILE',
}

SIMPLE_VAR_PATTERN = re.compile(r'^([A-Z][A-Z0-9_]{2,})')


def is_start_safe(seg):
    # Use shell tokenization so quoted paths containing spaces stay intact.
    tokens = shell_tokenize(seg)
    if len(tokens) < 2:
        return False
    # `start` accepts an optional quoted title first (start "" "target"); the
    # real target is the last non-flag token.
    args = [t for t in tokens[1:] if not t.startswith('/')]
    if not args:
        return False
    target = args[-1].strip('"\'')
    if target.startswith('http://') or target.startswith('https://'):
        return True
    _, ext = os.path.splitext(target)
    return ext.lower() in START_SAFE_EXTENSIONS


def is_powershell_safe(seg):
    return bool(POWERSHELL_ENV_PATTERN.match(seg.strip()))


# Windows Terminal subcommands and the flags that consume a following argument.
# Used to locate the program `wt` is actually launching so it can be validated.
WT_SUBCOMMANDS = {
    'new-tab', 'nt', 'split-pane', 'sp', 'focus-tab', 'ft', 'move-focus', 'mf',
    'swap-pane', 'focus-pane', 'fp', 'move-pane', 'mp', 'new-window', 'nw',
}

WT_FLAGS_WITH_ARG = {
    '-d', '--startingDirectory', '--title', '-p', '--profile', '--tabColor',
    '--colorScheme', '-w', '--window', '--size', '--pos', '-s', '--startingDir',
    '--appendCommandLine',
}


def is_wt_safe(seg):
    """Approve a `wt` (Windows Terminal) invocation only if the program it
    launches is itself a trusted command.

    `wt` can spawn any executable as a new tab/pane, so trusting `wt` blanketly
    would bypass the whole hook. Instead we parse past wt's subcommand and its
    option arguments to find the launched program, and require that program's
    name to be in the trusted set — making `wt new-tab ... claude.exe` exactly
    as safe as running `claude` directly, while `wt new-tab cmd /c ...` still
    falls through to a manual prompt.
    """
    tokens = shell_tokenize(seg)
    if len(tokens) < 2:
        return False

    i = 1  # skip wt itself
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
        # First non-flag, non-subcommand token is the program being launched.
        # Everything after it is that program's own arguments.
        return base in TRUSTED_COMMANDS

    # All tokens were wt flags/subcommands with no program to launch (e.g. wt --help).
    return True


def is_cmd_file_safe(filepath):
    """Check if a Windows .cmd batch file is safe to run.

    Fast-paths for trusted directories (.claude/skills/, .claude/commands/, .tmp/).
    For other files, parses each line — skipping batch-only constructs and
    checking real commands against the trusted set; falls back to AI for lines
    containing %VAR% expansion that can't be statically resolved.
    """
    filepath = filepath.strip('"\'')
    if is_in_trusted_script_dir(filepath):
        log_debug(f"is_cmd_file_safe: trusted dir, approving: {filepath}")
        return True

    content = read_script_file(filepath)
    if content is None:
        log_debug(f"is_cmd_file_safe: could not read {filepath}")
        return False

    trusted = TRUSTED_COMMANDS | {ASSIGNMENT_ONLY}

    for raw_line in content.splitlines():
        line = raw_line.strip()
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
            log_debug(f"is_cmd_file_safe: %%VAR%% expansion, asking AI: {line[:100]}")
            result = ask_ai_about_script(content, 'batch', filepath)
            return result is True
        if not is_segment_trusted(line, trusted):
            log_debug(f"is_cmd_file_safe: unsafe line: {line[:100]}")
            return False

    log_debug(f"is_cmd_file_safe: all lines safe in {filepath}")
    return True


POWERSHELL_CMDLETS = {
    # File system
    'Get-ChildItem':  'ls (list) or find (recursive search)',
    'Set-Location':   'cd',
    'Get-Location':   'pwd',
    'Push-Location':  'pushd',
    'Pop-Location':   'popd',
    'New-Item':       'touch (file) or mkdir (directory)',
    'Remove-Item':    'rm',
    'Copy-Item':      'cp',
    'Move-Item':      'mv',
    'Rename-Item':    'mv',
    'Get-Content':    'cat',
    'Set-Content':    'use the Write tool (never redirect in bash)',
    'Add-Content':    'use the Write tool (never redirect in bash)',
    'Clear-Content':  'use the Write tool with empty content',
    'Out-File':       'use the Write tool (never redirect in bash)',
    'Test-Path':      'test -f path (file), test -d path (directory), or [ -e path ] (exists)',
    'Resolve-Path':   'realpath',
    'Get-Item':       'ls or stat',
    'Split-Path':     'dirname (parent) or basename (filename)',
    'Join-Path':      'concatenate path strings directly',
    # Text processing
    'Select-Object':  'jq (JSON), awk, or cut (columns)',
    'Where-Object':   'grep',
    'Sort-Object':    'sort',
    'Group-Object':   'sort | uniq -c',
    'Measure-Object': 'wc (lines/words/chars)',
    'Format-Table':   'column -t',
    'Format-List':    'not needed — use raw output directly',
    'Format-Wide':    'not needed — use raw output directly',
    'Select-String':  'grep',
    'Tee-Object':     'tee',
    'Compare-Object': 'diff',
    'Out-String':     'not needed in bash',
    'Out-Null':       'redirect to /dev/null: command > /dev/null 2>&1',
    # Process management
    'Get-Process':    'ps',
    'Stop-Process':   'kill',
    'Start-Process':  'run the command directly',
    'Wait-Process':   'wait',
    'Invoke-Item':    'start',
    # System / environment
    'Get-Date':          'date',
    'Write-Host':        'echo',
    'Write-Output':      'echo',
    'Write-Error':       'echo >&2',
    'Write-Warning':     'echo >&2',
    'Write-Information': 'echo',
    'Write-Verbose':     'echo',
    'Write-Debug':       'echo',
    'Clear-Host':        'clear',
    'Get-Variable':      'printenv or env',
    'Set-Variable':      'VAR=value (shell assignment)',
    'Remove-Variable':   'unset VAR',
    'Get-Alias':         'alias',
    'Get-Command':       'which or type',
    'Get-Help':          'man',
    'Get-Member':        'not applicable in bash',
    'Get-Host':          'not needed in bash',
    'Get-Module':        'not applicable in bash',
    'Import-Module':     'not applicable in bash',
    # Networking
    'Invoke-WebRequest': 'curl',
    'Invoke-RestMethod': 'curl (add -s for JSON)',
    'Test-NetConnection': 'ping or nc',
    # JSON / data
    'ConvertFrom-Json': 'jq',
    'ConvertTo-Json':   'jq',
    'ConvertFrom-Csv':  'awk or write a Python script to .tmp/',
    'ConvertTo-Csv':    'awk or write a Python script to .tmp/',
    'Export-Csv':       'awk or write a Python script to .tmp/',
    'Import-Csv':       'awk or write a Python script to .tmp/',
}

CMD_REWRITE_MAP = {
    'dir':    'ls (add -la for details, grep "^l" to filter symlinks)',
    'type':   'cat',
    'copy':   'cp',
    'move':   'mv',
    'del':    'rm',
    'rd':     'rmdir',
    'md':     'mkdir',
    'echo':   'echo',
    'set':    'printenv or export VAR=value',
    'where':  'which',
    'findstr': 'grep',
    'icacls': 'stat (permissions)',
}


def shell_tokenize(text):
    """Split a command string into tokens using POSIX shell quoting rules."""
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def is_sed_command_safe(seg):
    """Allow sed unless -i (in-place edit) flag is present.

    Catches -i alone, -i with a backup suffix (e.g. -i.bak), and combined
    short flags that include i (e.g. -ni, -rni). Long options (--) are skipped.
    """
    tokens = shell_tokenize(seg)
    for token in tokens[1:]:
        if token.startswith('--'):
            continue
        if SED_INPLACE_PATTERN.match(token):
            return False
    return True


def is_git_command_safe(segment):
    """Check if a git command contains dangerous/destructive flags.

    Parses git global options (like -C <path>) to find the subcommand,
    then checks for dangerous flag combinations per subcommand.
    Case-sensitive token matching prevents false positives (e.g. -F vs -f).
    """
    tokens = shell_tokenize(segment)
    if not tokens or tokens[0] != 'git':
        return True

    i = 1
    while i < len(tokens):
        if tokens[i] in GIT_GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if tokens[i].startswith('-'):
            i += 1
            continue
        break

    if i >= len(tokens):
        return True

    subcommand = tokens[i]
    args = tokens[i + 1:]

    dangerous_flags = GIT_DANGEROUS_SUBCOMMANDS.get(subcommand)
    if dangerous_flags and any(arg in dangerous_flags for arg in args):
        return False

    if subcommand in ('checkout', 'restore') and '.' in args:
        return False

    return True


def get_subcommands(seg, skip=1):
    tokens = shell_tokenize(seg)
    return [t for t in tokens[skip:] if not t.startswith('-')]


GH_ALLOWED_SUBCOMMANDS = {
    'pr':       {'view', 'list', 'diff', 'checks', 'create', 'edit', 'close', 'reopen', 'ready', 'comment', 'review'},
    'issue':    {'view', 'list', 'create', 'edit', 'close', 'reopen', 'comment'},
    'repo':     {'view'},
    'run':      {'view', 'list', 'cancel', 'rerun'},
    'release':  {'view', 'list', 'create', 'edit'},
    'workflow': {'view', 'list', 'run'},
}

GH_WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

# GitHub API endpoints for reversible write operations (resources that can be deleted/closed/reverted)
GH_REVERSIBLE_API_PATTERNS = [
    re.compile(r'/?orgs/[^/]+/teams(?:/|$)'),           # Create/update teams (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/branches(?:/|$)'), # Create branches (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/pulls(?:/|$)'),    # Create/update PRs (can close)
    re.compile(r'/?repos/[^/]+/[^/]+/issues(?:/|$)'),   # Create/update issues (can close)
    re.compile(r'/?repos/[^/]+/[^/]+/labels(?:/|$)'),   # Create labels (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/milestones(?:/|$)'),  # Create milestones (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/comments(?:/|$)'), # Add comments (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/git/refs(?:/|$)'), # Create refs/tags (can delete)
    re.compile(r'/?repos/[^/]+/[^/]+/projects(?:/|$)'), # Create projects (can delete)
]

GH_AI_APPROVED_PAIRS = {'--version:*', 'issue:2>&1', 'label:*', 'org:*', 'pr:merge', 'project:*', 'repo:clone', 'repo:create', 'repo:edit', 'repo:list'}  # 'group:action' pairs approved by AI, e.g. 'pr:merge'


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
        # Extract the API endpoint URL and method
        api_url = ''
        method = 'GET'  # Default method
        i = 2
        while i < len(tokens):
            if tokens[i] in ('--method', '-X') and i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
                continue
            # First non-flag token is likely the endpoint
            if not tokens[i].startswith('-') and not api_url:
                api_url = tokens[i]
            i += 1

        # If it's a write method, check if it's a reversible endpoint
        if method in GH_WRITE_METHODS:
            # Check if the endpoint matches any reversible patterns
            for pattern in GH_REVERSIBLE_API_PATTERNS:
                if pattern.search(api_url):
                    log_debug(f"gh api {method} approved: reversible endpoint {api_url}")
                    return True
            # Write method to non-reversible endpoint - deny
            log_debug(f"gh api {method} denied: non-reversible endpoint {api_url}")
            return False
        # GET or other read-only methods are fine
        return True
    if group in GH_ALLOWED_SUBCOMMANDS:
        subs = get_subcommands(seg, skip=2)
        action = subs[0] if subs else ''
        if action in GH_ALLOWED_SUBCOMMANDS[group]:
            return True
        pair = f'{group}:{action}'
        if pair in GH_AI_APPROVED_PAIRS:
            return True
        result = ask_ai_about_subcommand('gh', f'{group} {action}', seg)
        if result is True:
            GH_AI_APPROVED_PAIRS.add(pair)
            add_to_subcommand_safe_set('GH_AI_APPROVED_PAIRS', pair)
        return result is True
    # Unknown group — check AI-approved pairs then ask AI
    pair = f'{group}:*'
    if pair in GH_AI_APPROVED_PAIRS:
        return True
    result = ask_ai_about_subcommand('gh', group, seg)
    if result is True:
        GH_AI_APPROVED_PAIRS.add(pair)
        add_to_subcommand_safe_set('GH_AI_APPROVED_PAIRS', pair)
    return result is True


NPM_SAFE_SUBCOMMANDS = {'audit', 'ci', 'dedupe', 'install', 'list', 'ls', 'outdated', 'prune', 'root', 'run', 'test', 'update'}


def is_npm_command_safe(seg):
    subs = get_subcommands(seg)
    if not subs:
        return False
    if subs[0] in NPM_SAFE_SUBCOMMANDS:
        return True
    if subs[0] == 'cache':
        return len(subs) > 1 and subs[1] == 'clean'
    result = ask_ai_about_subcommand('npm', subs[0], seg)
    if result is True:
        add_to_subcommand_safe_set('NPM_SAFE_SUBCOMMANDS', subs[0])
    return result is True


YARN_SAFE_SUBCOMMANDS = {
    'add', 'audit', 'backstage-cli', 'bin', 'build:all', 'build:backend',
    'build:frontend', 'check', 'dedupe', 'dev', 'dlx', 'exec', 'explain',
    'husky', 'info', 'install', 'link', 'lint:all', 'lint:fix', 'list',
    'node', 'outdated', 'pack', 'prettier', 'prettier:check', 'prettier:fix',
    'remove', 'run', 'start', 'start-backend', 'test', 'test:all', 'tsc',
    'unlink', 'upgrade', 'why', 'workspace', 'workspaces',
}


def is_yarn_command_safe(seg):
    tokens = shell_tokenize(seg)
    subs = []
    i = 1  # skip 'yarn' itself
    while i < len(tokens):
        t = tokens[i]
        if t.startswith('--') and '=' not in t:
            i += 2  # long flag that takes a value argument — skip both
        elif t.startswith('-'):
            i += 1  # boolean flag — skip it
        else:
            subs.append(t)
            i += 1
    if not subs:
        return False
    if subs[0] in YARN_SAFE_SUBCOMMANDS:
        return True
    if subs[0] == 'cache':
        return len(subs) > 1 and subs[1] == 'clean'
    result = ask_ai_about_subcommand('yarn', subs[0], seg)
    if result is True:
        add_to_subcommand_safe_set('YARN_SAFE_SUBCOMMANDS', subs[0])
    return result is True


PIP_SAFE_SUBCOMMANDS = {'2>&1', 'check', 'freeze', 'install', 'list', 'show', 'uninstall'}


def is_pip_command_safe(seg):
    subs = get_subcommands(seg)
    if not subs:
        return False
    if subs[0] in PIP_SAFE_SUBCOMMANDS:
        return True
    result = ask_ai_about_subcommand('pip', subs[0], seg)
    if result is True:
        add_to_subcommand_safe_set('PIP_SAFE_SUBCOMMANDS', subs[0])
    return result is True


PNPM_SAFE_SUBCOMMANDS = {'install', 'add', 'update', 'remove', 'list', 'outdated', 'prune'}


def is_pnpm_command_safe(seg):
    subs = get_subcommands(seg)
    if not subs:
        return False
    if subs[0] in PNPM_SAFE_SUBCOMMANDS:
        return True
    result = ask_ai_about_subcommand('pnpm', subs[0], seg)
    if result is True:
        add_to_subcommand_safe_set('PNPM_SAFE_SUBCOMMANDS', subs[0])
    return result is True


BUN_SAFE_SUBCOMMANDS = {'install', 'add', 'update', 'remove', 'test'}


def is_bun_command_safe(seg):
    subs = get_subcommands(seg)
    if not subs:
        return False
    if subs[0] in BUN_SAFE_SUBCOMMANDS:
        return True
    result = ask_ai_about_subcommand('bun', subs[0], seg)
    if result is True:
        add_to_subcommand_safe_set('BUN_SAFE_SUBCOMMANDS', subs[0])
    return result is True


def detect_powershell_cmdlet(command):
    """Return (cmdlet, bash_alternative) if a PowerShell cmdlet is the first word of any segment."""
    segments = split_segments(command)
    for seg in segments:
        word = first_word(seg.strip())
        if word in POWERSHELL_CMDLETS:
            return word, POWERSHELL_CMDLETS[word]
    return None, None


def detect_inline_script(command):
    """Return (flag_form, alternative) if python -c or node -e is used in any segment."""
    for seg in split_segments(command):
        word = first_word(seg.strip())
        if word in ('python', 'python3'):
            if '-c' in seg.strip().split():
                return 'python -c', 'Write a .tmp/script.py using the Write tool, then run: python .tmp/script.py'
        elif word == 'node':
            if '-e' in seg.strip().split():
                return 'node -e', 'Write a .tmp/script.js using the Write tool, then run: node .tmp/script.js'
    return None, None


class ShellTokenizer:
    """Stateful tokenizer for shell command parsing with quote/escape handling."""

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.in_single = False
        self.in_double = False

    def peek(self, offset=0):
        """Look ahead at character without consuming."""
        idx = self.pos + offset
        return self.text[idx] if idx < len(self.text) else None

    def advance(self, count=1):
        """Move position forward."""
        self.pos = min(self.pos + count, len(self.text))

    def at_end(self):
        """Check if we've reached the end."""
        return self.pos >= len(self.text)

    def consume_escape(self):
        """Handle escape sequences outside single quotes. Returns escaped text or None."""
        if not self.in_single and self.peek() == '\\' and self.peek(1):
            escaped = self.text[self.pos:self.pos+2]
            self.advance(2)
            return escaped
        return None

    def update_quote_state(self):
        """Update quote tracking based on current character. Returns True if was a quote."""
        ch = self.peek()
        if ch == "'" and not self.in_double:
            self.in_single = not self.in_single
            return True
        if ch == '"' and not self.in_single:
            self.in_double = not self.in_double
            return True
        return False

    def in_quotes(self):
        """Check if currently inside any quotes."""
        return self.in_single or self.in_double


def extract_substitutions(cmd):
    """Extract all $(...) command substitutions from a command string.

    Returns a list of the inner command strings. Handles nested substitutions
    and respects quoting (single quotes suppress substitution).
    """
    subs = []
    tokenizer = ShellTokenizer(cmd)

    while not tokenizer.at_end():
        if tokenizer.consume_escape():
            continue

        if tokenizer.update_quote_state():
            tokenizer.advance()
            continue

        # Check for $(...) outside single quotes
        if not tokenizer.in_single and tokenizer.peek() == '$' and tokenizer.peek(1) == '(':
            depth = 1
            start_pos = tokenizer.pos + 2
            inner_tokenizer = ShellTokenizer(cmd[start_pos:])

            while not inner_tokenizer.at_end() and depth > 0:
                if inner_tokenizer.consume_escape():
                    continue
                if inner_tokenizer.update_quote_state():
                    inner_tokenizer.advance()
                    continue

                if not inner_tokenizer.in_quotes():
                    if inner_tokenizer.peek() == '$' and inner_tokenizer.peek(1) == '(':
                        depth += 1
                        inner_tokenizer.advance()
                    elif inner_tokenizer.peek() == ')':
                        depth -= 1
                        if depth == 0:
                            subs.append(cmd[start_pos:start_pos + inner_tokenizer.pos])
                            break

                inner_tokenizer.advance()

            tokenizer.pos = start_pos + inner_tokenizer.pos + 1
            continue

        tokenizer.advance()

    return subs


def split_segments(cmd):
    """Split a compound command into segments by &&, ||, ;, and | operators.

    Only splits on operators outside of single and double quotes.
    """
    segments = []
    current = []
    tokenizer = ShellTokenizer(cmd)

    while not tokenizer.at_end():
        escaped = tokenizer.consume_escape()
        if escaped:
            current.append(escaped)
            continue

        if tokenizer.update_quote_state():
            current.append(tokenizer.peek())
            tokenizer.advance()
            continue

        if not tokenizer.in_quotes():
            two_char = cmd[tokenizer.pos:tokenizer.pos+2]
            if two_char in ('&&', '||'):
                segments.append(''.join(current))
                current = []
                tokenizer.advance(2)
                continue

            if tokenizer.peek() in (';', '|', '\n'):
                segments.append(''.join(current))
                current = []
                tokenizer.advance()
                continue

        current.append(tokenizer.peek())
        tokenizer.advance()

    segments.append(''.join(current))
    return segments


def strip_var_assignment(segment):
    """Strip a leading VAR=value assignment, handling $(…) and quoted values.

    Returns the remainder of the segment after the assignment, or the original
    segment if it doesn't start with an assignment.
    """
    m = re.match(r'^(\w+)=', segment)
    if not m:
        return segment
    i = m.end()
    # Walk over the value, handling $(), quotes, and escapes
    in_sq = False
    in_dq = False
    depth = 0
    while i < len(segment):
        c = segment[i]
        if c == '\\' and i + 1 < len(segment) and not in_sq:
            i += 2
            continue
        if c == "'" and not in_dq and depth == 0:
            in_sq = not in_sq
        elif c == '"' and not in_sq and depth == 0:
            in_dq = not in_dq
        elif not in_sq:
            if segment[i:i+2] == '$(':
                depth += 1
                i += 1
            elif c == ')' and depth > 0:
                depth -= 1
        if not in_sq and not in_dq and depth == 0 and c in (' ', '\t'):
            break
        i += 1
    return segment[i:].strip()


# Sentinel returned by first_word for pure variable assignments (no command).
ASSIGNMENT_ONLY = '__assignment__'


def first_word(segment):
    """Get the executable name from a segment, ignoring redirections and env var assignments."""
    segment = segment.strip()
    # Strip leading env var assignments like FOO=bar or FOO=$(...)
    while re.match(r'^\w+=', segment):
        rest = strip_var_assignment(segment)
        if rest == segment:
            break
        segment = rest
    if not segment:
        return ASSIGNMENT_ONLY
    # Strip leading redirections like 2>/dev/null or >/dev/null
    segment = re.sub(r'^\d*[<>]+\S*\s*', '', segment).strip()
    words = segment.split()
    cmd = words[0] if words else ''
    # Strip surrounding quotes so a fully-quoted invocation
    # ("C:/path/tool.exe") resolves to the tool name.
    cmd = cmd.strip('"\'')
    # Reduce an absolute or relative path to its basename so /usr/bin/grep,
    # ./foo, and quoted Windows paths all match the trusted command list by
    # command identity rather than by the exact path used to invoke them.
    if '/' in cmd or '\\' in cmd:
        cmd = os.path.basename(cmd.replace('\\', '/'))
    # Strip .exe suffix for Windows compatibility (e.g. where.exe -> where)
    if cmd.endswith('.exe'):
        cmd = cmd[:-4]
    # Strip leading subshell parens so "(netstat" is recognized as "netstat"
    cmd = cmd.lstrip('(')
    return cmd


def extract_script_content(segment, flag):
    """Extract script content from -e or -c flag in a command segment.

    Returns the script string if found, or None if not present.
    Handles various quoting styles: -e"...", -e "...", -e'...', -e '...'
    """
    segment = segment.strip()
    patterns = [
        rf'{flag}\s*"([^"]*(?:\\.[^"]*)*)"',
        rf"{flag}\s*'([^']*(?:\\.[^']*)*)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, segment)
        if match:
            return match.group(1)
    return None


def call_ai(prompt):
    """Call Claude Haiku for safety analysis. Returns True (SAFE), False (DANGEROUS), or None (error)."""
    vertex_project = os.environ.get('ANTHROPIC_VERTEX_PROJECT_ID')
    vertex_region = os.environ.get('CLOUD_ML_REGION', 'us-east5')
    if vertex_region == 'us' or vertex_region == 'us-central1':
        vertex_region = 'us-east5'
    anthropic_key = os.environ.get('ANTHROPIC_HOOK_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')

    try:
        if vertex_project:
            log_debug(f"Using Vertex AI (project: {vertex_project}, region: {vertex_region})")
            import subprocess

            gcloud_path = os.path.join(
                os.path.expanduser('~'),
                'AppData', 'Local', 'Google', 'Cloud SDK', 'google-cloud-sdk', 'bin', 'gcloud.cmd'
            )
            if not os.path.exists(gcloud_path):
                gcloud_path = 'gcloud'

            try:
                result = subprocess.run(
                    [gcloud_path, 'auth', 'application-default', 'print-access-token'],
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                if result.returncode != 0:
                    return None
                access_token = result.stdout.strip()
            except Exception:
                return None

            url = f'https://{vertex_region}-aiplatform.googleapis.com/v1/projects/{vertex_project}/locations/{vertex_region}/publishers/anthropic/models/claude-haiku-4-5:rawPredict'

            data = json.dumps({
                "anthropic_version": "vertex-2023-10-16",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": prompt}]
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data, headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            })
        elif anthropic_key:
            data = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": prompt}]
            }).encode('utf-8')

            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=data,
                headers={
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                    'x-api-key': anthropic_key
                }
            )
        else:
            return None

        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result.get('content', [{}])[0].get('text', '').strip().upper()
            is_safe = 'SAFE' in text
            log_debug(f"AI response: {text} -> {'SAFE' if is_safe else 'DANGEROUS'}")
            return is_safe
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
        log_debug(f"AI call failed: {type(e).__name__}: {str(e)[:100]}")
        return None


def ask_ai_about_script(script, language, command_line=None):
    """Use Claude Haiku to analyze if a script is safe to execute."""
    log_debug(f"AI validation requested for {language} script ({len(script)} chars)")

    command_context = ""
    if command_line:
        command_context = f"""
The script is being invoked with this command line:
```
{command_line}
```
Use the command-line arguments to determine where the script actually reads from and writes to.

"""

    trusted_list = ', '.join(sorted(TRUSTED_COMMANDS - {ASSIGNMENT_ONLY}))

    prompt = f"""Analyze this {language} script for safety. Respond with ONLY "SAFE" or "DANGEROUS".
{command_context}
The user has explicitly trusted these commands for direct execution:
{trusted_list}

Auto-approve (respond "SAFE") if the script only:
- Reads files or data
- Writes to stdout/stderr (console.log, print, etc.)
- Writes to temp directories (.tmp/, /tmp/, AppData/Local/Temp/) or paths derived from command-line arguments that point to those directories
- Performs harmless computations or data transformations
- Reads environment variables
- Creates parent directories (mkdir) for its output path
- Calls subprocess/exec/spawn with commands from the trusted list above — these are pre-approved
- Performs native file I/O (read, write, create, delete files/dirs) within the current project directory — this is equivalent intent to what trusted commands like git, npm, etc. do during normal development
- Makes network requests (including GET, POST, PUT, DELETE) to WellSky corporate services (wellskycorp.sharepoint.com, wellsky.atlassian.net, any *.sharepoint.com, any *.atlassian.net) as part of normal work operations

Deny (respond "DANGEROUS") if the script:
- Writes to or deletes files OUTSIDE the project directory or temp directories (e.g. system files, ~/.ssh, other users' files)
- Executes external commands NOT in the trusted list above
- Makes network write requests (POST, PUT, DELETE, etc.) to external/public services that are NOT WellSky corporate domains
- Uses eval, exec, or other code execution functions to run dynamically-generated code (note: Playwright waitForFunction is safe)
- Modifies system state (chmod/chown on system paths, etc.) outside the project directory

Script:
```{language}
{script}
```

Response (SAFE or DANGEROUS):"""

    return call_ai(prompt)


def ask_ai_about_subcommand(command, subcommand, full_segment):
    """Ask AI if an unknown subcommand is a safe, legitimate dev operation."""
    log_debug(f"Unknown {command} subcommand '{subcommand}', asking AI")
    prompt = (
        f'Is "{command} {subcommand}" a safe, legitimate software development operation?\n\n'
        f'Full command:\n```\n{full_segment}\n```\n\n'
        'Respond with ONLY "SAFE" or "DANGEROUS".\n\n'
        'SAFE: Common build, test, install, format, lint, publish, deploy, or dev workflow operations.\n'
        'DANGEROUS: Operations that could cause irreversible system harm, data exfiltration, or security compromise.\n\n'
        'Response (SAFE or DANGEROUS):'
    )
    return call_ai(prompt)


def is_script_safe(script, language, dangerous_patterns, command_line=None):
    """Generic script safety checker with pattern matching and AI fallback.

    Returns True if safe, False otherwise.
    """
    if not script:
        log_debug("Empty script, returning False")
        return False

    found_patterns = [p for p in dangerous_patterns if (p.search(script) if hasattr(p, 'search') else p in script)]
    if found_patterns:
        log_debug(f"Found dangerous patterns: {found_patterns[:5]}")
        ai_result = ask_ai_about_script(script, language, command_line)
        if ai_result is not None:
            log_debug(f"AI decided: {ai_result}")
            return ai_result
        log_debug("AI returned None, defaulting to False")
        return False

    log_debug("No dangerous patterns found, returning True")
    return True


def is_node_script_safe(script, command_line=None):
    return is_script_safe(script, 'javascript', NODE_DANGEROUS_PATTERNS, command_line=command_line)


def is_python_script_safe(script, command_line=None):
    return is_script_safe(script, 'python', PYTHON_DANGEROUS_PATTERNS, command_line=command_line)


def extract_script_filename(segment, command):
    """Extract the script filename from a node/python command.

    Handles commands like:
    - node script.js
    - python script.py
    - node --experimental-modules script.js
    - python -u script.py

    Returns the filename if found, or None if this is an inline script (-e/-c)
    or if no filename can be extracted.
    """
    tokens = shell_tokenize(segment)
    if not tokens or tokens[0].replace('.exe', '') != command:
        return None

    # -m runs a module, not a script file
    if '-m' in tokens:
        return None

    skip_next = False
    for i, token in enumerate(tokens[1:], 1):
        if skip_next:
            skip_next = False
            continue

        if token.startswith('-'):
            if token in ('-e', '-c'):
                return None
            if token in ('-r', '--require', '--loader', '--import'):
                skip_next = True
                continue
            continue

        if not token.startswith('-') and (token.endswith('.js') or token.endswith('.py') or token.endswith('.mjs') or '/' in token or '\\' in token or token.endswith('.ts')):
            return token

    return None


def convert_msys_path_to_windows(path):
    """Convert MSYS-style paths (/c/...) to Windows paths (C:/...).

    Returns the converted path, or the original if no conversion needed.
    """
    match = re.match(r'^/([a-zA-Z])(/.*)?$', path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        return f'{drive}:{rest}'
    return path


def read_script_file(filename):
    """Read a script file's contents, handling various path formats.

    Returns the file contents as a string, or None if the file can't be read.
    """
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
        log_debug(f"read_script_file failed for '{original}' (resolved: '{filename}'): {type(e).__name__}: {e}")
        return None


def is_in_git_repo(path):
    """Check if a path is within a git repository.

    Args:
        path: Directory path to check

    Returns:
        True if the path is in a git repo, False otherwise
    """
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


def normalize_path_cross_platform(path):
    """Normalize a path, handling MSYS /c/... <-> Windows C:/... conversion.

    On Windows with Git Bash/MSYS, os.getcwd() returns /c/Users/... while
    commands may use C:/Users/.... This function converts both forms to a
    canonical lowercase Windows-style path for comparison so that cp/mv/ln
    commands with absolute Windows paths are correctly recognized as within CWD.
    """
    path = os.path.expanduser(path)
    # MSYS /c/foo -> C:/foo
    msys_match = re.match(r'^/([a-zA-Z])/(.*)$', path.replace('\\', '/'))
    if msys_match:
        path = msys_match.group(1).upper() + ':/' + msys_match.group(2)
    # Replace backslashes with forward slashes for uniform comparison
    path = path.replace('\\', '/')
    # Collapse repeated slashes (except after drive letter)
    path = re.sub(r'(?<!:)/+', '/', path)
    return path.lower().rstrip('/')


# Paths declared by "git worktree add <path>" in the current compound command.
# Populated before segment-trust checks so cp/mv/mkdir into the new worktree path are approved.
_pending_worktree_paths = set()


def extract_pending_worktree_paths(segments):
    """Scan segments for 'git worktree add <path>' and record the new path."""
    for seg in segments:
        tokens = shlex.split(seg.strip()) if seg.strip() else []
        # strip git global opts: git [-C <dir>] [-c <kv>] worktree add [-b branch] <path>
        i = 0
        while i < len(tokens) and tokens[i].startswith('-'):
            if tokens[i] in {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix'}:
                i += 2
            else:
                i += 1
        if i >= len(tokens) or tokens[i] != 'git':
            continue
        i += 1
        while i < len(tokens) and tokens[i].startswith('-'):
            if tokens[i] in {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix'}:
                i += 2
            else:
                i += 1
        if i >= len(tokens) or tokens[i] != 'worktree':
            continue
        i += 1
        if i >= len(tokens) or tokens[i] != 'add':
            continue
        i += 1
        # skip flags like -b <branch>, -B <branch>, --lock, --detach, --orphan, --reason, --track
        while i < len(tokens):
            if tokens[i] in {'-b', '-B', '--reason', '--track'} and i + 1 < len(tokens):
                i += 2
            elif tokens[i].startswith('-'):
                i += 1
            else:
                break
        if i < len(tokens):
            path = tokens[i].strip('\'"')
            norm = normalize_path_cross_platform(path)
            norm = os.path.normpath(norm).lower().replace('\\', '/')
            _pending_worktree_paths.add(norm)
            log_debug(f"Recorded pending worktree path: {norm}")


def is_path_within_git_worktree(path):
    """Check if a path is within a worktree declared in this compound command."""
    try:
        path_norm = normalize_path_cross_platform(path)
        path_norm = os.path.normpath(path_norm).lower().replace('\\', '/')
        for wt in _pending_worktree_paths:
            wt_prefix = wt if wt.endswith('/') else wt + '/'
            if path_norm == wt or path_norm.startswith(wt_prefix):
                return True
    except Exception:
        pass
    return False


def _load_allowed_edit_dirs():
    """Derive directories covered by Edit/Write rules in all settings.json files.

    For Edit(~/.claude/settings.json) the allowed dir is ~/.claude/.
    For Edit(~/.claude/**) the allowed dir is ~/.claude/.
    """
    import itertools
    dirs = set()
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    search_roots = [os.path.expanduser('~/.claude')]
    if cwd:
        search_roots.append(os.path.join(cwd, '.claude'))
    for root in search_roots:
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


_ALLOWED_EDIT_DIRS = None


def is_path_within_allowed_edits(path):
    """Check if a path is within a directory covered by an Edit/Write permission rule.

    Semantics: if the user already granted Edit(some/file), copying to that
    directory carries the same trust — the destination can be written there anyway.
    """
    global _ALLOWED_EDIT_DIRS
    if _ALLOWED_EDIT_DIRS is None:
        _ALLOWED_EDIT_DIRS = _load_allowed_edit_dirs()
    try:
        path = os.path.expanduser(path)
        if not os.path.isabs(path) and not re.match(r'^/[a-zA-Z]/', path):
            cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
            path = os.path.join(cwd, path)
        path_norm = os.path.normpath(normalize_path_cross_platform(path)).lower().replace('\\', '/')
        for allowed_dir in _ALLOWED_EDIT_DIRS:
            dir_norm = os.path.normpath(allowed_dir).lower().replace('\\', '/')
            dir_prefix = dir_norm if dir_norm.endswith('/') else dir_norm + '/'
            if path_norm == dir_norm or path_norm.startswith(dir_prefix):
                log_debug(f"is_path_within_allowed_edits: {path_norm!r} matches allowed dir {dir_norm!r}")
                return True
    except Exception:
        pass
    return False


def is_path_within_claude_plugins(path):
    """Check if a path is within ~/.claude/plugins/.

    The plugins tree (marketplaces/, cache/) holds authored plugin content that
    is already trusted for script execution. Copying/moving files between its
    subtrees (e.g. syncing an edited SKILL.md from marketplaces/ to cache/) is a
    routine, safe operation regardless of which subdir is the current CWD.
    """
    try:
        path = os.path.expanduser(path)
        if not os.path.isabs(path) and not re.match(r'^/[a-zA-Z]/', path):
            cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
            path = os.path.join(cwd, path)
        path_norm = os.path.normpath(normalize_path_cross_platform(path)).lower().replace('\\', '/')
        plugins_dir = os.path.normpath(
            normalize_path_cross_platform(os.path.expanduser('~/.claude/plugins'))
        ).lower().replace('\\', '/')
        prefix = plugins_dir if plugins_dir.endswith('/') else plugins_dir + '/'
        return path_norm == plugins_dir or path_norm.startswith(prefix)
    except Exception:
        return False


def is_path_within_cwd(path):
    """Check if a path is within the current working directory.

    Args:
        path: Path to check (may be relative or absolute, may contain ~ or ..)

    Returns:
        True if the path is within or equal to CWD, False otherwise.
    """
    try:
        cwd = os.environ.get('CLAUDE_CWD', os.getcwd())

        # Expand user home directory (~)
        path = os.path.expanduser(path)

        # Convert to absolute path if relative
        if not os.path.isabs(path) and not re.match(r'^/[a-zA-Z]/', path):
            path = os.path.join(cwd, path)

        # Normalize both paths through cross-platform normalization so that
        # MSYS (/c/Users/...) and Windows (C:/Users/...) forms compare equal.
        cwd_norm = normalize_path_cross_platform(cwd)
        path_norm = normalize_path_cross_platform(path)

        # Also apply os.path.normpath to resolve .. and redundant separators
        cwd_norm = os.path.normpath(cwd_norm).lower().replace('\\', '/')
        path_norm = os.path.normpath(path_norm).lower().replace('\\', '/')

        # Check if path equals cwd
        if path_norm == cwd_norm:
            return True

        # Ensure cwd ends with separator for proper prefix matching
        # This prevents "/home/user/project" from matching "/home/user/project2"
        if not cwd_norm.endswith('/'):
            cwd_norm = cwd_norm + '/'

        # Check if path starts with cwd (is within cwd)
        return path_norm.startswith(cwd_norm)
    except Exception:
        # If anything goes wrong, don't auto-approve
        return False


def is_output_redirection_safe(segment):
    """Check if output redirection in this segment is safe.

    Safe redirections are those to:
    - Relative paths (no leading /, C:/, etc.)
    - .tmp/ directory
    - Current working directory children

    Unsafe redirections are those to:
    - Absolute paths outside CWD
    - System directories (/etc/, /usr/, /bin/, C:/Windows/, etc.)
    - Important config files (~/.bashrc, ~/.profile, etc.)
    """
    # Extract output redirection target (> file or >> file)
    match = re.search(r'(?:^|[;\|&]|\s)(>>?)\s*([^\s;&|]+)', segment)
    if not match:
        return True  # No output redirection found

    redirect_op = match.group(1)
    target_path = match.group(2).strip()

    # Remove quotes if present
    target_path = target_path.strip('"\'')

    # Safe: Relative paths (don't start with / or drive letter)
    if not re.match(r'^([a-zA-Z]:|/|\\)', target_path):
        return True

    # Safe: Absolute paths starting with .tmp/ (even though regex above should catch this)
    if target_path.startswith('.tmp/') or target_path.startswith('.tmp\\'):
        return True

    # Safe: Absolute paths that contain /.tmp/ or \.tmp\ (temp dir inside a project)
    if '/.tmp/' in target_path or '\\.tmp\\' in target_path or '/.tmp\\' in target_path or '\\.tmp/' in target_path:
        return True

    # Safe: /dev/null (discard output — matches the exemption in detect_output_redirection)
    if target_path == '/dev/null':
        return True

    # Unsafe: Everything else (absolute paths outside CWD)
    return False


TEMP_FILE_NAME_PATTERNS = [
    re.compile(r'[_.-][Tt][Mm][Pp]$'),        # _TMP, -tmp, .tmp suffix
    re.compile(r'[_.-][Tt][Ee][Mm][Pp]$'),    # _TEMP, -temp, .temp suffix
    re.compile(r'^\s*[Tt][Mm][Pp][_.-]'),      # tmp_, tmp-, tmp. prefix
    re.compile(r'^\s*[Tt][Ee][Mm][Pp][_.-]'), # temp_, temp-, temp. prefix
    re.compile(r'[_.-][Ss][Cc][Rr][Aa][Tt][Cc][Hh]$'),    # _scratch suffix
    re.compile(r'[_.-][Ss][Tt][Aa][Gg][Ii][Nn][Gg]$'),    # _staging suffix
]


def looks_like_temp_file_by_name(file_path):
    """Return True if the basename looks like a temporary/staging file."""
    basename = os.path.basename(file_path.replace('\\', '/'))
    for pattern in TEMP_FILE_NAME_PATTERNS:
        if pattern.search(basename):
            return True
    return False


def ask_ai_if_temp_file(file_path):
    """Ask Haiku whether a file path looks like a temp/staging file that belongs in .tmp/.

    Returns True if it looks like a temp file, False/None otherwise.
    """
    log_debug(f"Asking AI if temp file: {file_path[:100]}")
    prompt = (
        f'Does this file path look like a temporary or staging file that should live in a .tmp/ directory '
        f'rather than where it is being written?\n\n'
        f'File path: {file_path}\n\n'
        'Respond with ONLY "YES" or "NO".\n\n'
        'YES: The name suggests it is temporary, staging, scratch, intermediate output, or a workaround '
        '(e.g. commit_msg_staging, _TMP suffix, scratch_output, temp_data, etc.)\n'
        'NO: The name suggests a permanent project artifact.\n\n'
        'Response (YES or NO):'
    )
    try:
        vertex_project = os.environ.get('ANTHROPIC_VERTEX_PROJECT_ID')
        vertex_region = os.environ.get('CLOUD_ML_REGION', 'us-east5')
        if vertex_region in ('us', 'us-central1'):
            vertex_region = 'us-east5'
        anthropic_key = os.environ.get('ANTHROPIC_HOOK_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')

        if vertex_project:
            import subprocess
            gcloud_path = os.path.join(
                os.path.expanduser('~'),
                'AppData', 'Local', 'Google', 'Cloud SDK', 'google-cloud-sdk', 'bin', 'gcloud.cmd'
            )
            if not os.path.exists(gcloud_path):
                gcloud_path = 'gcloud'
            result = subprocess.run(
                [gcloud_path, 'auth', 'application-default', 'print-access-token'],
                capture_output=True, timeout=10, text=True
            )
            if result.returncode != 0:
                return None
            access_token = result.stdout.strip()
            url = (f'https://{vertex_region}-aiplatform.googleapis.com/v1/projects/{vertex_project}'
                   f'/locations/{vertex_region}/publishers/anthropic/models/claude-haiku-4-5:rawPredict')
            data = json.dumps({
                'anthropic_version': 'vertex-2023-10-16',
                'max_tokens': 5,
                'messages': [{'role': 'user', 'content': prompt}]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            })
        elif anthropic_key:
            data = json.dumps({
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 5,
                'messages': [{'role': 'user', 'content': prompt}]
            }).encode('utf-8')
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=data,
                headers={
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                    'x-api-key': anthropic_key,
                }
            )
        else:
            return None

        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result.get('content', [{}])[0].get('text', '').strip().upper()
            is_temp = 'YES' in text
            log_debug(f"AI temp-file check: {text} -> {'YES (temp)' if is_temp else 'NO'}")
            return is_temp
    except Exception as e:
        log_debug(f"AI temp-file check failed: {type(e).__name__}: {str(e)[:100]}")
        return None


TRUSTED_SCRIPT_DIRS = [
    '.tmp/', '/.tmp/', '\\.tmp\\',
    'wellsky-claude-code-plugins/', '/wellsky-claude-code-plugins/',
    'rrrutledge-claude-code-plugins/', '/rrrutledge-claude-code-plugins/',
    '.claude/plugins/',
    '.claude/skills/', '.claude/commands/',
]


def is_in_trusted_script_dir(filename):
    """Return True if the script lives in a known-safe directory (plugins, .tmp)."""
    normalized = filename.replace('\\', '/')
    for d in TRUSTED_SCRIPT_DIRS:
        if d.replace('\\', '/') in normalized:
            return True
    return False


def check_script_segment(seg, command, language, inline_flag, dangerous_patterns):
    """Validate a script command segment (inline or file-based) for any language.

    Trusted-directory scripts are approved without content analysis. Inline scripts
    and file-based scripts outside trusted dirs are checked against dangerous_patterns
    (with AI fallback via is_script_safe).
    """
    log_debug(f"Checking {language} segment: {seg[:100]}")

    script = extract_script_content(seg, inline_flag)
    if script:
        log_debug(f"Found inline {inline_flag} script")
        result = is_script_safe(script, language, dangerous_patterns)
        log_debug(f"Inline script safety check: {result}")
        return result

    filename = extract_script_filename(seg, command)
    if filename:
        log_debug(f"Extracted script filename: {filename}")
        if is_in_trusted_script_dir(filename):
            log_debug(f"Script in trusted directory, allowing: {filename}")
            return True
        file_content = read_script_file(filename)
        if file_content:
            log_debug(f"Successfully read script file ({len(file_content)} bytes)")
            result = is_script_safe(file_content, language, dangerous_patterns, command_line=seg)
            log_debug(f"Script file safety check: {result}")
            return result
        log_debug("Failed to read script file")
        return False

    log_debug(f"No {inline_flag} script or filename found, defaulting to True")
    return True


def check_node_segment(seg):
    return check_script_segment(seg, 'node', 'javascript', '-e', NODE_DANGEROUS_PATTERNS)


def check_python_segment(seg, command):
    return check_script_segment(seg, command, 'python', '-c', PYTHON_DANGEROUS_PATTERNS)


CWD_FILE_COMMAND_CONFIG = {
    'mv': {
        'flags_with_args': {'-S', '--suffix', '-t', '--target-directory'},
        'min_args': 2,
        'skip_args': 0,
    },
    'cp': {
        'flags_with_args': {'-S', '--suffix', '-t', '--target-directory'},
        'min_args': 2,
        'skip_args': 0,
    },
    'touch': {
        'flags_with_args': {'-r', '--reference', '-d', '--date', '-t'},
        'min_args': 1,
        'skip_args': 0,
    },
    'ln': {
        'flags_with_args': {'-t', '--target-directory', '-S', '--suffix'},
        'min_args': 2,
        'skip_args': 0,
    },
    'chmod': {
        'flags_with_args': {'--reference'},
        'min_args': 2,
        'skip_args': 1,
    },
}


def is_safe_read_location(path):
    """Check if a path is in a safe read-only location.

    Safe locations for reading include:
    - Downloads folder
    - Desktop
    - Documents
    - User's home directory (but not system directories)

    Args:
        path: Path to check (may be relative or absolute)

    Returns:
        True if the path is in a safe read location, False otherwise
    """
    try:
        path = os.path.expanduser(path)
        path_norm = os.path.normpath(path).lower()

        home_dir = os.path.expanduser('~').lower()
        downloads_dir = os.path.join(home_dir, 'downloads')
        desktop_dir = os.path.join(home_dir, 'desktop')
        documents_dir = os.path.join(home_dir, 'documents')

        safe_dirs = [downloads_dir, desktop_dir, documents_dir, home_dir]

        for safe_dir in safe_dirs:
            safe_dir_norm = os.path.normpath(safe_dir)
            if not safe_dir_norm.endswith(os.sep):
                safe_dir_norm = safe_dir_norm + os.sep
            if path_norm.startswith(safe_dir_norm) or path_norm == os.path.normpath(safe_dir):
                return True

        return False
    except Exception:
        return False


def check_cwd_file_command(seg, command):
    """Generic checker for file commands that should only operate within CWD.

    For cp command: allows source paths from safe read locations (Downloads, Desktop, etc.)
    but requires destination to be within CWD.

    For other commands: all paths must be within CWD.

    Args:
        seg: Command segment to check
        command: Base command name (must be in CWD_FILE_COMMAND_CONFIG)

    Returns:
        True if all path arguments are within CWD, False otherwise
    """
    config = CWD_FILE_COMMAND_CONFIG.get(command)
    if not config:
        return False

    try:
        tokens = shlex.split(seg)
    except ValueError:
        tokens = seg.split()
    if not tokens or tokens[0].replace('.exe', '') != command:
        return False

    flags_with_args = config['flags_with_args']
    min_args = config['min_args']
    skip_args = config['skip_args']

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
            if token in flags_with_args:
                skip_next = True
            elif '=' in token:
                pass
            i += 1
            continue

        args.append(token)
        i += 1

    if len(args) < min_args:
        log_debug(f"{command} command has insufficient arguments")
        return False

    paths_to_check = args[skip_args:]

    if command in ('cp', 'mv', 'ln') and len(paths_to_check) >= 2:
        source_paths = paths_to_check[:-1]
        dest_path = paths_to_check[-1].strip('"\'')

        if (not is_path_within_cwd(dest_path)
                and not is_path_within_git_worktree(dest_path)
                and not is_path_within_allowed_edits(dest_path)
                and not is_path_within_claude_plugins(dest_path)):
            log_debug(f"{command} destination outside CWD, worktrees, allowed-edit, and plugins dirs: {dest_path}")
            return False

        for source_path in source_paths:
            source_path = source_path.strip('"\'')
            if (not is_path_within_cwd(source_path)
                    and not is_safe_read_location(source_path)
                    and not is_path_within_git_worktree(source_path)
                    and not is_path_within_allowed_edits(source_path)
                    and not is_path_within_claude_plugins(source_path)):
                log_debug(f"{command} source outside CWD, safe read locations, worktrees, allowed-edit, and plugins dirs: {source_path}")
                return False

        log_debug(f"{command} command approved: destination in CWD, worktree, or allowed-edit dir")
        return True

    for path in paths_to_check:
        path = path.strip('"\'')
        if not is_path_within_cwd(path):
            log_debug(f"{command} path outside CWD: {path}")
            return False

    log_debug(f"{command} command approved: all paths within CWD")
    return True


def check_shell_keyword(word, seg, trusted):
    """Handle shell structure keywords (if/then/else/for/etc)."""
    if word in SHELL_STRUCTURE_ONLY:
        return True

    if word in SHELL_BODY_KEYWORDS:
        rest = seg.lstrip()
        if rest.startswith(word):
            rest = rest[len(word):]
            if not rest or rest[0] in (' ', '\t'):
                rest = rest.strip()
        if not rest:
            return True
        return first_word(rest) in trusted

    return False


def is_segment_trusted(seg, trusted):
    """Check if a command segment uses only trusted commands.

    Validates:
    - Output redirection safety
    - Script interpreter commands (node, python)
    - Git destructive operation protection
    - File operations within CWD (mv, cp, touch, ln, chmod)
    - Shell structure keywords
    - General trusted command list
    """
    seg = seg.strip()
    if not seg:
        return True
    if seg.startswith('#'):
        return True

    if not is_output_redirection_safe(seg):
        return False

    word = first_word(seg)

    if word == 'curl':
        return is_curl_safe(seg)

    if word == 'node':
        return check_node_segment(seg)

    if word in ('python', 'python3'):
        return check_python_segment(seg, word)

    if word == 'sed':
        return is_sed_command_safe(seg)

    if word == 'git':
        if not is_git_command_safe(seg):
            return False

    if word in CWD_FILE_COMMAND_CONFIG:
        return check_cwd_file_command(seg, word)

    if word == 'start':
        return is_start_safe(seg)

    if word == 'powershell':
        return is_powershell_safe(seg)

    if word == 'wt':
        return is_wt_safe(seg)

    if word.lower().endswith('.cmd'):
        tokens = shell_tokenize(seg)
        filepath = tokens[0] if tokens else seg.strip()
        return is_cmd_file_safe(filepath)

    if word == 'gh':
        return is_gh_command_safe(seg)

    if word in ('npm', 'yarn', 'pip', 'pnpm', 'bun'):
        return {
            'npm':  is_npm_command_safe,
            'yarn': is_yarn_command_safe,
            'pip':  is_pip_command_safe,
            'pnpm': is_pnpm_command_safe,
            'bun':  is_bun_command_safe,
        }[word](seg)

    if check_shell_keyword(word, seg, trusted):
        return True

    if word in trusted:
        return True

    return is_unknown_command_safe(word, seg)


def add_to_safe_commands(command_name):
    """Add a command to SAFE_COMMANDS in this script's own source file."""
    script_path = os.path.realpath(__file__)
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return False

    match = re.search(r'(SAFE_COMMANDS = \{)([^}]+)(\})', content)
    if not match:
        return False

    existing = set(re.findall(r"'([^']+)'", match.group(2)))
    if command_name in existing:
        return True

    existing.add(command_name)
    sorted_cmds = sorted(existing)

    groups = {}
    for cmd in sorted_cmds:
        groups.setdefault(cmd[0].lower(), []).append(cmd)

    lines = []
    for letter in sorted(groups.keys()):
        lines.append('    ' + ', '.join(f"'{c}'" for c in groups[letter]) + ',')

    new_block = 'SAFE_COMMANDS = {\n' + '\n'.join(lines) + '\n}'
    new_content = content[:match.start()] + new_block + content[match.end():]

    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        log_debug(f"Added '{command_name}' to SAFE_COMMANDS in {script_path}")
        return True
    except Exception as e:
        log_debug(f"Failed to write SAFE_COMMANDS update: {e}")
        return False


def add_to_subcommand_safe_set(set_name, subcommand):
    """Add a subcommand to a *_SAFE_SUBCOMMANDS (or similar) set in this script's source."""
    script_path = os.path.realpath(__file__)
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return False

    # Handle empty set() syntax → convert to set literal
    empty_pat = re.compile(rf'({re.escape(set_name)}\s*=\s*)set\(\)')
    m_empty = empty_pat.search(content)
    if m_empty:
        new_content = (
            content[:m_empty.start(1)]
            + m_empty.group(1)
            + "{'" + subcommand + "'}"
            + content[m_empty.end():]
        )
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            log_debug(f"Added '{subcommand}' to {set_name} (was empty)")
            return True
        except Exception as e:
            log_debug(f"Failed to update {set_name}: {e}")
            return False

    # Handle existing {...} set literal (single or multi-line)
    pattern = re.compile(rf'({re.escape(set_name)}\s*=\s*\{{)(.*?)(\}})', re.DOTALL)
    match = pattern.search(content)
    if not match:
        return False

    body = match.group(2)
    existing = set(re.findall(r"'([^']+)'", body))
    if subcommand in existing:
        return True

    existing.add(subcommand)
    sorted_cmds = sorted(existing)

    if '\n' in body:
        items = [f"'{c}'" for c in sorted_cmds]
        lines = []
        current_line: list[str] = []
        current_len = 4
        for item in items:
            if current_len + len(item) + 2 > 80 and current_line:
                lines.append('    ' + ', '.join(current_line) + ',')
                current_line = [item]
                current_len = 4 + len(item)
            else:
                current_line.append(item)
                current_len += len(item) + 2
        if current_line:
            lines.append('    ' + ', '.join(current_line) + ',')
        new_body = '\n' + '\n'.join(lines) + '\n'
    else:
        new_body = ', '.join(f"'{c}'" for c in sorted_cmds)

    new_block = match.group(1) + new_body + match.group(3)
    new_content = content[:match.start()] + new_block + content[match.end():]

    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        log_debug(f"Added '{subcommand}' to {set_name}")
        return True
    except Exception as e:
        log_debug(f"Failed to update {set_name}: {e}")
        return False


UNKNOWN_CMD_PATTERN = re.compile(r'^[a-zA-Z][\w.-]*$')


def is_unknown_command_safe(command_name, full_segment):
    """Ask AI whether an unrecognized CLI command is a safe dev tool.

    If safe, adds it to SAFE_COMMANDS in this file for future auto-approval.
    """
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

    result = call_ai(prompt)
    if result is True:
        add_to_safe_commands(command_name)
        log_debug(f"AI approved '{command_name}' as safe, added to SAFE_COMMANDS")
        return True

    log_debug(f"AI result for '{command_name}': {result}")
    return False


def strip_heredocs(command):
    """Remove heredoc content from command, keeping only the command structure.

    Returns:
        (cleaned_command, all_safe) where:
        - cleaned_command: command with heredoc content removed
        - all_safe: True if all heredocs are single-quoted (safe), False if any are unsafe, None if no heredocs found
    """
    result = command
    found_any = False
    all_safe = True

    while True:
        match = re.search(r'<<\s*(["\']?)(\w+)\1', result)
        if not match:
            break

        found_any = True
        quote = match.group(1)
        marker = match.group(2)

        if quote != "'":
            all_safe = False

        heredoc_end = match.end()
        end_pattern = rf'\n{re.escape(marker)}(?:\n|$)'
        end_match = re.search(end_pattern, result[heredoc_end:])

        if not end_match:
            return command, False

        before = result[:match.start()]
        after = result[heredoc_end + end_match.end():]
        result = before + after

    return result, (all_safe if found_any else None)


def detect_output_redirection(command):
    """Detect output redirection (> or >>) in any segment.

    Returns True if file output redirection is found.
    Ignores safe stderr patterns like 2>/dev/null and 2>&1.
    """
    for seg in split_segments(command):
        matches = re.finditer(r'(\d*)(>>?)\s*([^\s;&|]+)', seg)
        for m in matches:
            fd = m.group(1)
            target = m.group(3).strip().strip('"\'')
            if fd == '2' and target in ('/dev/null', '&1'):
                continue
            if target == '/dev/null':
                continue
            if target.startswith('&'):
                continue
            return True
    return False


def detect_input_redirection(command):
    """Detect input redirection (<) in any segment.

    Returns True if input redirection from a file is found.
    Ignores heredocs (<< and <<<) and process substitution <().
    """
    for seg in split_segments(command):
        tokenizer = ShellTokenizer(seg)
        while not tokenizer.at_end():
            if tokenizer.consume_escape():
                continue
            if tokenizer.update_quote_state():
                tokenizer.advance()
                continue
            if not tokenizer.in_quotes() and tokenizer.peek() == '<':
                next_ch = tokenizer.peek(1)
                if next_ch == '<':
                    if tokenizer.peek(2) == '<':
                        tokenizer.advance(3)
                    else:
                        tokenizer.advance(2)
                    continue
                if next_ch == '(':
                    tokenizer.advance(2)
                    continue
                prev_pos = tokenizer.pos - 1
                if prev_pos >= 0 and seg[prev_pos].isdigit():
                    tokenizer.advance()
                    continue
                return True
            tokenizer.advance()
    return False


def detect_simple_expansion(command):
    """Detect simple $VAR environment variable expansion outside single quotes.

    Returns the first non-standard variable name found, or None if all vars are standard bash vars.
    """
    tokenizer = ShellTokenizer(command)
    while not tokenizer.at_end():
        if tokenizer.consume_escape():
            continue
        if tokenizer.update_quote_state():
            tokenizer.advance()
            continue
        if not tokenizer.in_single and tokenizer.peek() == '$':
            next_ch = tokenizer.peek(1)
            if next_ch in ('(', '{', '?', '#', '@', '*', '!', '-', '$'):
                tokenizer.advance()
                continue
            rest = command[tokenizer.pos + 1:]
            m = SIMPLE_VAR_PATTERN.match(rest)
            if m:
                var_name = m.group(1)
                if var_name not in STANDARD_BASH_VARS:
                    return var_name
        tokenizer.advance()
    return None


def detect_cd_cwd_prefix(command):
    """Detect commands that start with cd to the current working directory.

    Returns True if the command begins with 'cd <cwd> &&' which is redundant.
    """
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    stripped = command.strip()
    m = re.match(r'^cd\s+("([^"]+)"|\'([^\']+)\'|(\S+))\s*&&', stripped)
    if not m:
        return False
    cd_target = m.group(2) or m.group(3) or m.group(4)
    cd_norm = os.path.normpath(os.path.expanduser(cd_target))
    cwd_norm = os.path.normpath(cwd)
    return cd_norm.lower() == cwd_norm.lower()


def detect_variable_assignment(command):
    """Detect variable assignments (VAR=value) followed by commands using those vars.

    Returns the variable name if found, or None if no assignment detected.
    Only detects assignments that are followed by more commands (&&, ||, ;, |).
    """
    # Look for VAR=value at the start of any segment
    segments = split_segments(command)
    for i, seg in enumerate(segments):
        seg = seg.strip()
        m = re.match(r'^(\w+)=', seg)
        if m:
            var_name = m.group(1)
            # Check if there are more segments after this one (meaning the var might be used)
            if i + 1 < len(segments):
                return var_name
            # Or if the same segment has more commands after the assignment
            rest = strip_var_assignment(seg)
            if rest and rest != seg:
                return var_name
    return None


def detect_complex_bash(command):
    """Detect complex Bash patterns that should be Python scripts instead.

    Returns (is_complex, reason) where:
    - is_complex: True if this should be a Python script
    - reason: Human-readable explanation of what pattern was detected
    """
    # Check for command substitution $() or backticks (outside quotes)
    tokenizer = ShellTokenizer(command)
    while not tokenizer.at_end():
        if tokenizer.update_quote_state():
            tokenizer.advance()
            continue
        if tokenizer.consume_escape():
            continue

        # $() substitution
        if not tokenizer.in_single and tokenizer.peek() == '$' and tokenizer.peek(1) == '(':
            return True, "command substitution $()"

        # Backtick substitution
        if not tokenizer.in_quotes() and tokenizer.peek() == '`':
            return True, "backtick command substitution"

        tokenizer.advance()

    # Check for loops (for, while)
    # Use word boundaries to avoid false positives in strings
    if re.search(r'\bfor\s+\w+\s+in\b', command):
        return True, "for loop"
    if re.search(r'\bwhile\s+', command):
        return True, "while loop"

    # Check for conditionals (if statements)
    if re.search(r'\bif\s+(\[|\[\[|test\b)', command):
        return True, "if conditional"

    # Check for complex pipelines (3+ pipe stages)
    segments = split_segments(command)
    for segment in segments:
        # Count pipe operators in this segment (outside quotes)
        pipe_count = 0
        seg_tokenizer = ShellTokenizer(segment)
        while not seg_tokenizer.at_end():
            if seg_tokenizer.update_quote_state():
                seg_tokenizer.advance()
                continue
            if seg_tokenizer.consume_escape():
                continue
            if not seg_tokenizer.in_quotes() and seg_tokenizer.peek() == '|':
                # Make sure it's not || (logical OR)
                if seg_tokenizer.peek(1) != '|':
                    pipe_count += 1
            seg_tokenizer.advance()

        if pipe_count >= 3:
            return True, "complex pipeline with 3+ stages"

    # Brace command grouping { cmd1; cmd2; } — should be a Python script.
    # Since split_segments() splits on ';', the opening brace lands as the
    # first word of its own segment, making it straightforward to detect.
    for seg in split_segments(command):
        stripped = seg.strip()
        if stripped.startswith('{') and len(stripped) > 1 and stripped[1] in (' ', '\t', '"', "'"):
            return True, "brace command grouping { ... }"

    return False, None


# MCP servers whose every operation is reversible (content can be deleted,
# restored from trash, transitioned back, or otherwise undone). Blanket-approved.
MCP_BLANKET_APPROVE_SERVERS = (
    'plugin_product-management_atlassian',
    'plugin_architect_atlassian',
)

# Leading verbs that mark an MCP tool as read-only (never mutate state).
MCP_READONLY_VERBS = (
    'get', 'list', 'search', 'fetch', 'read', 'view', 'describe', 'query',
    'lookup', 'find', 'show', 'check', 'browse', 'preview', 'inspect',
    'count', 'download', 'status',
)

# Leading verbs that mutate state but are reversible (the change can be undone:
# delete the created item, edit it back, transition it back, etc.).
MCP_REVERSIBLE_WRITE_VERBS = (
    'create', 'add', 'update', 'edit', 'comment', 'transition', 'link',
    'set', 'put', 'post', 'append', 'rename', 'move', 'assign', 'label',
    'tag', 'upsert', 'write', 'attach', 'star', 'watch', 'subscribe',
)

# Leading verbs that are destructive / hard to reverse — fall through to a
# manual prompt rather than auto-approving.
MCP_DESTRUCTIVE_VERBS = (
    'delete', 'remove', 'purge', 'drop', 'destroy', 'trash', 'erase',
    'wipe', 'revoke', 'deactivate', 'disable', 'uninstall', 'unlink',
    'unassign', 'clear', 'reset', 'authenticate', 'authorize',
)


def classify_mcp_tool(tool_name):
    """Decide whether an MCP tool call is reversible enough to auto-approve.

    MCP tool names look like 'mcp__<server>__<operation>'. Whole servers can be
    blanket-approved; otherwise the operation's leading verb decides:
    read-only and reversible-write verbs are approved, destructive or
    unrecognized verbs fall through to a manual prompt.

    Returns True to auto-approve, False to prompt.
    """
    parts = tool_name.split('__')
    server = parts[1] if len(parts) > 1 else ''
    operation = parts[-1] if len(parts) > 2 else ''

    if server in MCP_BLANKET_APPROVE_SERVERS:
        log_debug(f"MCP {tool_name}: server blanket-approved")
        return True

    name = operation.lower()
    verb_match = re.match(r'[a-z]+', name)
    verb = verb_match.group(0) if verb_match else name

    if verb in MCP_DESTRUCTIVE_VERBS or any(name.startswith(v) for v in MCP_DESTRUCTIVE_VERBS):
        log_debug(f"MCP {tool_name}: destructive verb '{verb}', prompting")
        return False
    if verb in MCP_READONLY_VERBS or any(name.startswith(v) for v in MCP_READONLY_VERBS):
        log_debug(f"MCP {tool_name}: read-only verb '{verb}', approving")
        return True
    if verb in MCP_REVERSIBLE_WRITE_VERBS or any(name.startswith(v) for v in MCP_REVERSIBLE_WRITE_VERBS):
        log_debug(f"MCP {tool_name}: reversible-write verb '{verb}', approving")
        return True

    log_debug(f"MCP {tool_name}: unrecognized verb '{verb}', prompting")
    return False


def block(reason):
    print(json.dumps({'decision': 'block', 'reason': reason}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get('tool_name')

    # Block the PowerShell tool entirely — CLAUDE.md says "Always use Bash tool, never PowerShell tool"
    if tool_name == 'PowerShell':
        ps_command = data.get('tool_input', {}).get('command', '')
        log_debug(f"DECISION: Block (PowerShell tool used). Command: {ps_command[:200]}")
        block(
            'BLOCKED: PowerShell tool is disabled per global CLAUDE.md rule '
            '("Always use Bash tool, never PowerShell tool"). '
            'Re-issue this command using the Bash tool. For Windows-specific '
            'operations, use bash equivalents or a Python script in .tmp/. '
            'If PowerShell is genuinely required, invoke it from Bash via '
            '`powershell -NoProfile -Command "..."`.'
        )

    if tool_name in ('Write', 'Edit'):
        file_path = data.get('tool_input', {}).get('file_path', '')
        normalized = file_path.replace('\\', '/')
        cwd = os.environ.get('CLAUDE_CWD', os.getcwd()).replace('\\', '/')
        if not cwd.endswith('/'):
            cwd += '/'

        # Normalize file path relative to CWD
        if normalized.startswith(cwd):
            normalized = normalized[len(cwd):]

        # Always approve .tmp/ files
        if normalized.startswith('.tmp/') or '/.tmp/' in normalized:
            log_debug(f"DECISION: Approve {tool_name} to .tmp/: {file_path[:100]}")
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}))
            sys.exit(0)

        # Always approve edits to skills, commands, and screenshots inside any
        # .claude/ directory — home (~/.claude) or project-local — regardless of
        # git status. These are authored content that should never prompt.
        full_norm = file_path.replace('\\', '/')
        if re.search(r'(^|/)\.claude/(skills|commands|screenshots)/', full_norm):
            log_debug(f"DECISION: Approve {tool_name} to .claude config dir: {file_path[:100]}")
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}))
            sys.exit(0)

        # Pattern-based temp file detection: block and redirect before anything else
        if looks_like_temp_file_by_name(file_path):
            log_debug(f"DECISION: Block {tool_name} — temp file name pattern matched: {file_path[:100]}")
            block(
                f'BLOCKED: "{os.path.basename(file_path.replace(chr(92), "/"))}" looks like a temporary file '
                'but is not in .tmp/. Write it to .tmp/ instead (e.g. .tmp/commit-msg.txt). '
                'Per CLAUDE.md, .tmp/ is the only location for temporary staging files.'
            )

        # In git repos, auto-approve all file operations within CWD (goes through PR review)
        if is_in_git_repo(cwd) and is_path_within_cwd(file_path):
            log_debug(f"DECISION: Approve {tool_name} in git repo: {file_path[:100]}")
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}))
            sys.exit(0)

        # About to fall through to a user prompt — last chance: AI check for temp files
        log_debug(f"{tool_name} not auto-approved — AI temp-file check before prompting")
        if ask_ai_if_temp_file(file_path):
            block(
                f'BLOCKED: "{os.path.basename(file_path.replace(chr(92), "/"))}" looks like a temporary '
                'file but is not in .tmp/. Write it to .tmp/ instead. '
                'Per CLAUDE.md, .tmp/ is the only location for temporary staging files.'
            )
        sys.exit(0)

    # MCP tools: auto-approve reversible operations (reads + reversible writes),
    # let destructive/unrecognized ones fall through to a manual prompt.
    if tool_name and tool_name.startswith('mcp__'):
        if classify_mcp_tool(tool_name):
            log_debug(f"DECISION: Approve MCP tool {tool_name}")
            print(json.dumps({'decision': 'approve'}))
        sys.exit(0)

    if tool_name != 'Bash':
        sys.exit(0)

    command = data.get('tool_input', {}).get('command', '')
    if not command:
        sys.exit(0)

    log_debug(f"=== Hook evaluating command: {command[:200]}")

    # Block all heredocs — per CLAUDE.md, use Write tool instead
    cleaned_command, heredocs_found = strip_heredocs(command)
    if heredocs_found is not None:
        log_debug("DECISION: Block (heredoc detected)")
        block(
            'BLOCKED: Heredoc syntax (<< EOF) detected. '
            'Per CLAUDE.md rules, never use heredocs. '
            'Use the Write tool to create the file, then run it separately.'
        )

    # Check for PowerShell cmdlets — must use bash equivalents
    ps_cmdlet, ps_alternative = detect_powershell_cmdlet(command)
    if ps_cmdlet:
        block(
            f'BLOCKED: PowerShell cmdlet "{ps_cmdlet}" used in Bash command. '
            f'Use bash equivalent instead: {ps_alternative}. '
            'Always use bash commands in the Bash tool, never PowerShell cmdlets.'
        )

    # Single pass: Windows-execution guards and subprocess check
    for seg in split_segments(command):
        word = first_word(seg.strip())

        # Windows execution blocks
        if word == 'powershell' and not is_powershell_safe(seg):
            block(
                'BLOCKED: powershell command in Bash. '
                'Rewrite using bash commands or a Python script in .tmp/. '
                'See ~/.claude/CLAUDE.md for guidelines.'
            )

        if word == 'cmd':
            tokens = shell_tokenize(seg.strip())
            has_c_flag = any(t.lower() in ('/c', '//c') for t in tokens[1:])
            if has_c_flag:
                inner = ''
                for i, t in enumerate(tokens[1:], 1):
                    if t.lower() in ('/c', '//c') and i + 1 < len(tokens):
                        inner = tokens[i + 1].strip().split()[0].lower() if tokens[i + 1].strip() else ''
                        break
                rewrite = CMD_REWRITE_MAP.get(inner, '')
                rewrite_hint = f' Use "{rewrite}" instead.' if rewrite else (
                    f' Call the Windows utility (e.g. fsutil, icacls) directly in Git Bash without cmd //c.'
                    if inner else ''
                )
                block(
                    'BLOCKED: cmd /c or cmd //c detected. Windows utilities run directly in Git Bash — '
                    'no cmd wrapper needed.' + rewrite_hint +
                    ' For bash equivalents of Windows commands see the PowerShell cmdlet map in the hook.'
                )

        if word == 'sed' and re.search(r'\bsed\b.*\s-i\b', seg):
            block(
                'BLOCKED: "sed -i" destroys files on Windows/MSYS (especially symlinks). '
                'Use the Edit tool instead.'
            )

        # .tmp/ scripts must use client libraries, not subprocess
        if word in ('python', 'python3'):
            filename = extract_script_filename(seg, word)
            if filename and ('.tmp/' in filename or '\\.tmp\\' in filename):
                file_content = read_script_file(filename)
                if file_content and re.search(r'(?<!\w)subprocess[.\s]', file_content):
                    log_debug(f"DECISION: Block (subprocess in .tmp/ script: {filename})")
                    block(
                        f'BLOCKED: Script "{filename}" uses subprocess. '
                        'Per CLAUDE.md, .tmp/ scripts must use client libraries '
                        '(urllib.request, requests, etc.) instead of subprocess. '
                        'Rewrite the script to make API calls directly with '
                        'urllib.request or requests, then re-run it.'
                    )

    # Check for inline script flags — must use Write tool + .tmp/ script instead
    inline_flag, inline_alternative = detect_inline_script(command)
    if inline_flag:
        block(
            f'BLOCKED: Inline script flag "{inline_flag}" used in Bash command. '
            f'Per CLAUDE.md rules, inline scripts are not allowed. '
            f'{inline_alternative}'
        )

    # Block output redirection — per CLAUDE.md, use Write tool instead
    if detect_output_redirection(command):
        log_debug("DECISION: Block (output redirection)")
        block(
            'BLOCKED: Output redirection (> or >>) detected. '
            'Per CLAUDE.md rules, never use output redirection. '
            'Use the Write tool to create files instead.'
        )

    # Block input redirection — per CLAUDE.md, use cat file | instead
    if detect_input_redirection(command):
        log_debug("DECISION: Block (input redirection)")
        block(
            'BLOCKED: Input redirection (<) detected. '
            'Per CLAUDE.md rules, do not use input redirection. '
            'Use "cat file | command" instead of "command < file".'
        )

    # Block redundant cd to CWD — Bash tool already sets working directory
    if detect_cd_cwd_prefix(command):
        log_debug("DECISION: Block (cd to CWD prefix)")
        block(
            'BLOCKED: Redundant "cd <cwd> &&" prefix detected. '
            'The Bash tool already sets the working directory to the project root. '
            'Remove the cd prefix and run the command directly.'
        )

    # Check for variable assignments followed by commands — must use Python instead
    assigned_var = detect_variable_assignment(command)
    if assigned_var:
        log_debug(f"DECISION: Block (variable assignment: {assigned_var})")
        block(
            f'BLOCKED: Variable assignment "{assigned_var}=..." followed by more commands. '
            'Per CLAUDE.md rules, commands with variable assignments must be written '
            'as Python scripts to .tmp/ instead. This makes them analyzable by the hook '
            'and easier to debug. Write a Python script that sets the variable and runs '
            'the commands, then run: python .tmp/script_name.py'
        )

    # Check for simple $VAR expansion — use Python scripts with os.environ instead
    var_name = detect_simple_expansion(command)
    if var_name:
        log_debug(f"DECISION: Block (simple expansion ${var_name})")
        block(
            f'BLOCKED: Simple environment variable expansion "${var_name}" detected. '
            'Per CLAUDE.md rules, commands that depend on env vars should be written '
            'as Python scripts so they read variables via os.environ. '
            f'Write a Python script to .tmp/ that uses os.environ.get("{var_name}") '
            'and makes the call directly, then run: python .tmp/script_name.py'
        )

    # Check for complex Bash patterns that should be Python instead
    is_complex, reason = detect_complex_bash(command)
    if is_complex:
        log_debug(f"DECISION: Block (complex bash: {reason})")
        block(
            f'BLOCKED: Command contains {reason}. Per CLAUDE.md rules, complex logic must be '
            'written as a Python script to .tmp/ instead. Please rewrite as a Python script '
            'and run it with: python .tmp/script_name.py'
        )

    segments = split_segments(command)
    non_empty = [s for s in segments if s.strip()]

    if not non_empty:
        sys.exit(0)

    trusted = TRUSTED_COMMANDS | {ASSIGNMENT_ONLY}

    # Pre-scan for "git worktree add <path>" so cp/mv into the new path are trusted.
    extract_pending_worktree_paths(non_empty)

    if not all(is_segment_trusted(seg, trusted) for seg in non_empty):
        log_debug("DECISION: Deny (not all segments trusted)")
        sys.exit(0)

    queue = [command]
    while queue:
        fragment = queue.pop()
        for sub in extract_substitutions(fragment):
            sub_segments = split_segments(sub)
            sub_non_empty = [s for s in sub_segments if s.strip()]
            if not all(is_segment_trusted(seg, trusted) for seg in sub_non_empty):
                log_debug("DECISION: Deny (substitution segments not trusted)")
                sys.exit(0)
            queue.append(sub)

    log_debug("DECISION: Approve")
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}))

    sys.exit(0)


if __name__ == '__main__':
    main()
