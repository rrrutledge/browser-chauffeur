"""Safety analysis for node/python scripts (inline -e/-c and file-based).

Trusted-directory scripts are approved without inspection. Others are scanned
for dangerous patterns (exec/spawn/eval/subprocess/...); a match falls through
to Haiku, which decides given the trusted-command list and the command line.
"""
import re

from . import ai
from .log import log_debug
from .paths import is_in_trusted_script_dir, read_script_file
from .shell import ASSIGNMENT_ONLY, shell_tokenize
from .trust import get_trusted

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


def extract_script_content(segment, flag):
    """Extract the quoted script body following an -e/-c flag, or None."""
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


def extract_script_filename(segment, command):
    """Return the script file passed to node/python, or None for inline (-e/-c)
    scripts or module (-m) invocations."""
    tokens = shell_tokenize(segment)
    if not tokens or tokens[0].replace('.exe', '') != command:
        return None
    if '-m' in tokens:
        return None
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token.startswith('-'):
            if token in ('-e', '-c'):
                return None
            if token in ('-r', '--require', '--loader', '--import'):
                skip_next = True
            continue
        if (token.endswith('.js') or token.endswith('.py') or token.endswith('.mjs')
                or token.endswith('.ts') or '/' in token or '\\' in token):
            return token
    return None


def ask_ai_about_script(script, language, command_line=None):
    """Ask Haiku whether a script is safe; returns True/False/None."""
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
    trusted_list = ', '.join(sorted(get_trusted() - {ASSIGNMENT_ONLY}))
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
    return ai.call_ai(prompt)


def is_script_safe(script, language, dangerous_patterns, command_line=None):
    """True if no dangerous pattern matches; otherwise defer to Haiku."""
    if not script:
        log_debug("Empty script, returning False")
        return False
    found = [p for p in dangerous_patterns if p.search(script)]
    if found:
        log_debug(f"Found dangerous patterns: {found[:5]}")
        result = ask_ai_about_script(script, language, command_line)
        if result is not None:
            return result
        return False
    return True


def _check_segment(seg, command, language, inline_flag, dangerous_patterns):
    log_debug(f"Checking {language} segment: {seg[:100]}")
    script = extract_script_content(seg, inline_flag)
    if script:
        return is_script_safe(script, language, dangerous_patterns)
    filename = extract_script_filename(seg, command)
    if filename:
        if is_in_trusted_script_dir(filename):
            log_debug(f"Script in trusted directory, allowing: {filename}")
            return True
        content = read_script_file(filename)
        if content:
            return is_script_safe(content, language, dangerous_patterns, command_line=seg)
        return False
    return True


def check_node_segment(seg):
    return _check_segment(seg, 'node', 'javascript', '-e', NODE_DANGEROUS_PATTERNS)


def check_python_segment(seg, command):
    return _check_segment(seg, command, 'python', '-c', PYTHON_DANGEROUS_PATTERNS)
