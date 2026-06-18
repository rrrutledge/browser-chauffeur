"""Enforcement = "rewrite into a form I can validate".

A block here does not mean "this is forbidden". It means the command is in a
form whose safety the hook cannot statically determine (heredocs, redirection,
inline scripts, env-var expansion, loops/conditionals/substitutions, ...), so it
asks for an equivalent form that *can* be validated — typically a `.tmp/` Python
script or the Write tool, both of which the hook can read and check.

enforce_bash(command) returns a block-reason string, or None to let the command
proceed to approval. Individual detectors are exposed for unit testing.
"""
import os
import re

from .log import log_debug
from .paths import read_script_file
from .scripts import extract_script_filename
from .shell import ShellTokenizer, first_word, shell_tokenize, split_segments, strip_var_assignment

POWERSHELL_CMDLETS = {
    'Get-ChildItem': 'ls (list) or find (recursive search)',
    'Set-Location': 'cd',
    'Get-Location': 'pwd',
    'Push-Location': 'pushd',
    'Pop-Location': 'popd',
    'New-Item': 'touch (file) or mkdir (directory)',
    'Remove-Item': 'rm',
    'Copy-Item': 'cp',
    'Move-Item': 'mv',
    'Rename-Item': 'mv',
    'Get-Content': 'cat',
    'Set-Content': 'use the Write tool (never redirect in bash)',
    'Add-Content': 'use the Write tool (never redirect in bash)',
    'Clear-Content': 'use the Write tool with empty content',
    'Out-File': 'use the Write tool (never redirect in bash)',
    'Test-Path': 'test -f path (file), test -d path (directory), or [ -e path ] (exists)',
    'Resolve-Path': 'realpath',
    'Get-Item': 'ls or stat',
    'Split-Path': 'dirname (parent) or basename (filename)',
    'Join-Path': 'concatenate path strings directly',
    'Select-Object': 'jq (JSON), awk, or cut (columns)',
    'Where-Object': 'grep',
    'Sort-Object': 'sort',
    'Group-Object': 'sort | uniq -c',
    'Measure-Object': 'wc (lines/words/chars)',
    'Format-Table': 'column -t',
    'Format-List': 'not needed — use raw output directly',
    'Format-Wide': 'not needed — use raw output directly',
    'Select-String': 'grep',
    'Tee-Object': 'tee',
    'Compare-Object': 'diff',
    'Out-String': 'not needed in bash',
    'Out-Null': 'redirect to /dev/null: command > /dev/null 2>&1',
    'Get-Process': 'ps',
    'Stop-Process': 'kill',
    'Start-Process': 'run the command directly',
    'Wait-Process': 'wait',
    'Invoke-Item': 'start',
    'Get-Date': 'date',
    'Write-Host': 'echo',
    'Write-Output': 'echo',
    'Write-Error': 'echo >&2',
    'Write-Warning': 'echo >&2',
    'Write-Information': 'echo',
    'Write-Verbose': 'echo',
    'Write-Debug': 'echo',
    'Clear-Host': 'clear',
    'Get-Variable': 'printenv or env',
    'Set-Variable': 'VAR=value (shell assignment)',
    'Remove-Variable': 'unset VAR',
    'Get-Alias': 'alias',
    'Get-Command': 'which or type',
    'Get-Help': 'man',
    'Get-Member': 'not applicable in bash',
    'Get-Host': 'not needed in bash',
    'Get-Module': 'not applicable in bash',
    'Import-Module': 'not applicable in bash',
    'Invoke-WebRequest': 'curl',
    'Invoke-RestMethod': 'curl (add -s for JSON)',
    'Test-NetConnection': 'ping or nc',
    'ConvertFrom-Json': 'jq',
    'ConvertTo-Json': 'jq',
    'ConvertFrom-Csv': 'awk or write a Python script to .tmp/',
    'ConvertTo-Csv': 'awk or write a Python script to .tmp/',
    'Export-Csv': 'awk or write a Python script to .tmp/',
    'Import-Csv': 'awk or write a Python script to .tmp/',
}

CMD_REWRITE_MAP = {
    'dir': 'ls (add -la for details, grep "^l" to filter symlinks)',
    'type': 'cat',
    'copy': 'cp',
    'move': 'mv',
    'del': 'rm',
    'rd': 'rmdir',
    'md': 'mkdir',
    'echo': 'echo',
    'set': 'printenv or export VAR=value',
    'where': 'which',
    'findstr': 'grep',
    'icacls': 'stat (permissions)',
}

STANDARD_BASH_VARS = {
    'HOME', 'PATH', 'USER', 'SHELL', 'TERM', 'TMPDIR', 'TMP', 'TEMP',
    'PWD', 'OLDPWD', 'EDITOR', 'VISUAL', 'PAGER', 'MANPATH', 'LANG',
    'LC_ALL', 'LC_CTYPE', 'DISPLAY', 'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE',
    'SSH_AUTH_SOCK', 'SSH_AGENT_PID', 'CLAUDE_CWD', 'PROFILE',
}
SIMPLE_VAR_PATTERN = re.compile(r'^([A-Z][A-Z0-9_]{2,})')


def strip_heredocs(command):
    """Remove heredoc bodies. Returns (cleaned, all_safe) where all_safe is
    None if no heredoc, True if every heredoc is single-quoted, else False."""
    result = command
    found_any = False
    all_safe = True
    while True:
        match = re.search(r'<<\s*(["\']?)(\w+)\1', result)
        if not match:
            break
        found_any = True
        if match.group(1) != "'":
            all_safe = False
        marker = match.group(2)
        heredoc_end = match.end()
        end_match = re.search(rf'\n{re.escape(marker)}(?:\n|$)', result[heredoc_end:])
        if not end_match:
            return command, False
        result = result[:match.start()] + result[heredoc_end + end_match.end():]
    return result, (all_safe if found_any else None)


def detect_powershell_cmdlet(command):
    for seg in split_segments(command):
        word = first_word(seg.strip())
        if word in POWERSHELL_CMDLETS:
            return word, POWERSHELL_CMDLETS[word]
    return None, None


def detect_inline_script(command):
    for seg in split_segments(command):
        word = first_word(seg.strip())
        if word in ('python', 'python3'):
            if '-c' in seg.strip().split():
                return 'python -c', 'Write a .tmp/script.py using the Write tool, then run: python .tmp/script.py'
        elif word == 'node':
            if '-e' in seg.strip().split():
                return 'node -e', 'Write a .tmp/script.js using the Write tool, then run: node .tmp/script.js'
    return None, None


def detect_output_redirection(command):
    for seg in split_segments(command):
        unquoted = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'', '', seg)
        for m in re.finditer(r'(\d*)(>>?)\s*([^\s;&|]+)', unquoted):
            fd = m.group(1)
            target = m.group(3).strip().strip('"\'')
            if fd == '2' and target in ('/dev/null', '&1'):
                continue
            if target == '/dev/null' or target.startswith('&'):
                continue
            return True
    return False


def detect_input_redirection(command):
    for seg in split_segments(command):
        tok = ShellTokenizer(seg)
        while not tok.at_end():
            if tok.consume_escape():
                continue
            if tok.update_quote_state():
                tok.advance()
                continue
            if not tok.in_quotes() and tok.peek() == '<':
                nxt = tok.peek(1)
                if nxt == '<':
                    tok.advance(3 if tok.peek(2) == '<' else 2)
                    continue
                if nxt == '(':
                    tok.advance(2)
                    continue
                prev = tok.pos - 1
                if prev >= 0 and seg[prev].isdigit():
                    tok.advance()
                    continue
                return True
            tok.advance()
    return False


def detect_cd_cwd_prefix(command):
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    m = re.match(r'^cd\s+("([^"]+)"|\'([^\']+)\'|(\S+))\s*(?:&&|;)', command.strip())
    if not m:
        return False
    target = m.group(2) or m.group(3) or m.group(4)
    return os.path.normpath(os.path.expanduser(target)).lower() == os.path.normpath(cwd).lower()


def detect_cd_compound(command):
    """Return the cd target if the command starts with `cd <dir> && <more>` or
    `cd <dir>; <more>` and the target differs from the current working directory."""
    cwd = os.environ.get('CLAUDE_CWD', os.getcwd())
    m = re.match(r'^cd\s+("([^"]+)"|\'([^\']+)\'|(\S+))\s*(?:&&|;)', command.strip())
    if not m:
        return None
    target = m.group(2) or m.group(3) or m.group(4)
    if os.path.normpath(os.path.expanduser(target)).lower() == os.path.normpath(cwd).lower():
        return None
    return target


def detect_variable_assignment(command):
    segments = split_segments(command)
    for i, seg in enumerate(segments):
        seg = seg.strip()
        m = re.match(r'^(\w+)=', seg)
        if m:
            if i + 1 < len(segments):
                return m.group(1)
            rest = strip_var_assignment(seg)
            if rest and rest != seg:
                return m.group(1)
    return None


def detect_simple_expansion(command):
    tok = ShellTokenizer(command)
    while not tok.at_end():
        if tok.consume_escape():
            continue
        if tok.update_quote_state():
            tok.advance()
            continue
        if not tok.in_single and tok.peek() == '$':
            nxt = tok.peek(1)
            if nxt in ('(', '{', '?', '#', '@', '*', '!', '-', '$'):
                tok.advance()
                continue
            m = SIMPLE_VAR_PATTERN.match(command[tok.pos + 1:])
            if m and m.group(1) not in STANDARD_BASH_VARS:
                return m.group(1)
        tok.advance()
    return None


def detect_complex_bash(command):
    """Return (is_complex, reason) for patterns that belong in a Python script."""
    tok = ShellTokenizer(command)
    while not tok.at_end():
        if tok.update_quote_state():
            tok.advance()
            continue
        if tok.consume_escape():
            continue
        if not tok.in_single and tok.peek() == '$' and tok.peek(1) == '(':
            return True, "command substitution $()"
        if not tok.in_quotes() and tok.peek() == '`':
            return True, "backtick command substitution"
        tok.advance()

    if re.search(r'\bfor\s+\w+\s+in\b', command):
        return True, "for loop"
    if re.search(r'\bwhile\s+', command):
        return True, "while loop"
    if re.search(r'\bif\s+(\[|\[\[|test\b)', command):
        return True, "if conditional"

    for segment in split_segments(command):
        pipes = 0
        st = ShellTokenizer(segment)
        while not st.at_end():
            if st.update_quote_state():
                st.advance()
                continue
            if st.consume_escape():
                continue
            if not st.in_quotes() and st.peek() == '|' and st.peek(1) != '|':
                pipes += 1
            st.advance()
        if pipes >= 3:
            return True, "complex pipeline with 3+ stages"

    for seg in split_segments(command):
        stripped = seg.strip()
        if stripped.startswith('{') and len(stripped) > 1 and stripped[1] in (' ', '\t', '"', "'"):
            return True, "brace command grouping { ... }"

    return False, None


def _subprocess_in_tmp_python(seg, word):
    """Block .tmp/ python scripts that shell out via subprocess."""
    filename = extract_script_filename(seg, word)
    if filename and ('.tmp/' in filename or '\\.tmp\\' in filename):
        content = read_script_file(filename)
        if content and re.search(r'(?<!\w)subprocess[.\s]', content):
            return filename
    return None


def enforce_bash(command):
    """Return a block-reason string for `command`, or None to allow it to
    proceed to approval. Mirrors the legacy block ordering exactly."""
    _, heredocs_found = strip_heredocs(command)
    if heredocs_found is not None:
        return ('BLOCKED: Heredoc syntax (<< EOF) detected. Per CLAUDE.md rules, never use heredocs. '
                'Use the Write tool to create the file, then run it separately.')

    cmdlet, alternative = detect_powershell_cmdlet(command)
    if cmdlet:
        return (f'BLOCKED: PowerShell cmdlet "{cmdlet}" used in Bash command. '
                f'Use bash equivalent instead: {alternative}. '
                'Always use bash commands in the Bash tool, never PowerShell cmdlets.')

    for seg in split_segments(command):
        word = first_word(seg.strip())
        if word == 'powershell':
            from .commands import is_powershell_safe
            if not is_powershell_safe(seg):
                return ('BLOCKED: powershell command in Bash. Rewrite using bash commands or a Python '
                        'script in .tmp/. See ~/.claude/CLAUDE.md for guidelines.')
        if word == 'cmd':
            tokens = shell_tokenize(seg.strip())
            if any(t.lower() in ('/c', '//c') for t in tokens[1:]):
                inner = ''
                for i, t in enumerate(tokens[1:], 1):
                    if t.lower() in ('/c', '//c') and i + 1 < len(tokens):
                        inner = tokens[i + 1].strip().split()[0].lower() if tokens[i + 1].strip() else ''
                        break
                rewrite = CMD_REWRITE_MAP.get(inner, '')
                hint = (f' Use "{rewrite}" instead.' if rewrite
                        else (' Call the Windows utility (e.g. fsutil, icacls) directly in Git Bash without cmd //c.'
                              if inner else ''))
                return ('BLOCKED: cmd /c or cmd //c detected. Windows utilities run directly in Git Bash — '
                        'no cmd wrapper needed.' + hint +
                        ' For bash equivalents of Windows commands see the PowerShell cmdlet map in the hook.')
        if word == 'sed' and re.search(r'\bsed\b.*\s-i\b', seg):
            return ('BLOCKED: "sed -i" destroys files on Windows/MSYS (especially symlinks). '
                    'Use the Edit tool instead.')
        if word in ('python', 'python3'):
            filename = _subprocess_in_tmp_python(seg, word)
            if filename:
                return (f'BLOCKED: Script "{filename}" uses subprocess. Per CLAUDE.md, .tmp/ scripts must use '
                        'client libraries (urllib.request, requests, etc.) instead of subprocess. Rewrite the '
                        'script to make API calls directly with urllib.request or requests, then re-run it.')

    inline_flag, inline_alternative = detect_inline_script(command)
    if inline_flag:
        return (f'BLOCKED: Inline script flag "{inline_flag}" can\'t be validated inline. '
                f'{inline_alternative}')

    if detect_output_redirection(command):
        return ('BLOCKED: Output redirection (> or >>) detected. Per CLAUDE.md rules, never use output '
                'redirection. Use the Write tool to create files instead.')

    if detect_input_redirection(command):
        return ('BLOCKED: Input redirection (<) detected. Per CLAUDE.md rules, do not use input redirection. '
                'Use "cat file | command" instead of "command < file".')

    if detect_cd_cwd_prefix(command):
        return ('BLOCKED: Redundant "cd <cwd> &&" prefix detected. The Bash tool already sets the working '
                'directory to the project root. Remove the cd prefix and run the command directly.')

    cd_target = detect_cd_compound(command)
    if cd_target:
        return (f'BLOCKED: "cd {cd_target}" followed by more commands cannot be safely validated because '
                'the hook cannot resolve relative file paths in the trailing command without knowing the '
                'new working directory. Use an absolute path in the command directly, or split into '
                'two separate Bash tool calls: first "cd {cd_target}", then the command on its own.')

    if re.search(r'\bgit\s+-C\b', command):
        return ('BLOCKED: "git -C <dir>" changes the working directory context, making path validation '
                'unreliable. Per CLAUDE.md rules, use an absolute path in the git command arguments '
                'directly, or split into two separate Bash tool calls: first "cd <dir>", then the git '
                'command on its own.')

    assigned = detect_variable_assignment(command)
    if assigned:
        return (f'BLOCKED: Variable assignment "{assigned}=..." followed by more commands. Per CLAUDE.md rules, '
                'commands with variable assignments must be written as Python scripts to .tmp/ instead. This '
                'makes them analyzable by the hook and easier to debug. Write a Python script that sets the '
                'variable and runs the commands, then run: python .tmp/script_name.py')

    var_name = detect_simple_expansion(command)
    if var_name:
        return (f'BLOCKED: Simple environment variable expansion "${var_name}" detected. Per CLAUDE.md rules, '
                'commands that depend on env vars should be written as Python scripts so they read variables '
                f'via os.environ. Write a Python script to .tmp/ that uses os.environ.get("{var_name}") and '
                'makes the call directly, then run: python .tmp/script_name.py')

    is_complex, reason = detect_complex_bash(command)
    if is_complex:
        return (f'BLOCKED: Command contains {reason}, whose safety cannot be statically validated. Rewrite the '
                'logic as a Python script in .tmp/ (which the hook can read and check) and run it with: '
                'python .tmp/script_name.py')

    return None
