"""Safety analysis for node/python file scripts.

Deny-by-default: a script is auto-approved only when it lives in a trusted
directory (its safety is implied by where it is) or when the AI fallback
affirmatively judges it safe. A script we cannot affirmatively clear falls
through to a prompt — we do not approve arbitrary code just because it lacks
known-bad tokens.

(Inline `python -c` / `node -e` never reach here; enforcement blocks them and
asks for a .tmp/ file instead, which can be read and checked.)
"""
import re

from . import ai, config
from .log import log_debug
from .paths import is_in_trusted_script_dir, read_script_file
from .shell import ASSIGNMENT_ONLY, shell_tokenize
from .trust import get_trusted

# When a script is judged DANGEROUS, the orchestrator turns the silent prompt
# into an actionable block. The reason is stashed here for one hook run; hook.py
# resets it at the start of every invocation.
_last_block_reason = None


def reset_block_reason():
    global _last_block_reason
    _last_block_reason = None


def get_block_reason():
    return _last_block_reason


def _record_block(filename, language, reason):
    global _last_block_reason
    where = f'Script "{filename}"' if filename else f'this inline {language} script'
    detail = f': {reason}' if reason else ''
    _last_block_reason = (
        f'BLOCKED: {where} was judged unsafe to auto-run{detail}. Rewrite it so it only reads '
        'files, writes within the project directory or .tmp/, and shells out only to trusted '
        'commands. If it is legitimately privileged (e.g. a launcher that spawns sessions), add '
        'its directory to the safe-compounds "trusted_script_dirs" config or add a scoped '
        'Bash(...) allow rule for it instead of broadening the script.'
    )


def extract_script_content(segment, flag):
    """Extract the quoted script body following an -e/-c flag, or None."""
    segment = segment.strip()
    for pattern in (rf'{flag}\s*"([^"]*(?:\\.[^"]*)*)"', rf"{flag}\s*'([^']*(?:\\.[^']*)*)'"):
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


def _trusted_domains_phrase():
    domains = config.get_config().get('curl_domains', [])
    if domains:
        return ('the consumer has configured these network domains as trusted for '
                'reads and reversible writes: ' + ', '.join(domains))
    return 'no external network domains are configured as trusted'


def ask_ai_about_script(script, language, command_line=None):
    """Ask Haiku whether a script is safe; returns (verdict, reason) where
    verdict is True/False/None and reason is a one-line string when DANGEROUS."""
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

For network access, {_trusted_domains_phrase()}.

Auto-approve (respond "SAFE") if the script only:
- Reads files or data
- Writes to stdout/stderr (console.log, print, etc.)
- Writes to temp directories (.tmp/, /tmp/, AppData/Local/Temp/) or paths derived from command-line arguments that point to those directories
- Performs harmless computations or data transformations
- Reads environment variables
- Creates parent directories (mkdir) for its output path
- Calls subprocess/exec/spawn with commands from the trusted list above — these are pre-approved
- Performs native file I/O (read, write, create, delete files/dirs) within the current project directory — this is equivalent intent to what trusted commands like git, npm, etc. do during normal development
- Makes network requests (including GET, POST, PUT, DELETE) to the configured trusted domains above

Deny (respond "DANGEROUS") if the script:
- Writes to or deletes files OUTSIDE the project directory or temp directories (e.g. system files, ~/.ssh, other users' files)
- Executes external commands NOT in the trusted list above
- Makes network write requests (POST, PUT, DELETE, etc.) to domains NOT in the configured trusted list
- Uses eval, exec, or other code execution functions to run dynamically-generated code (note: Playwright waitForFunction is safe)
- Modifies system state (chmod/chown on system paths, etc.) outside the project directory

Script:
```{language}
{script}
```

Respond with ONLY "SAFE" or "DANGEROUS: <short reason>":"""
    return ai.call_ai_with_reason(prompt)


def _check_segment(seg, command, language, inline_flag):
    log_debug(f"Checking {language} segment: {seg[:100]}")
    script = extract_script_content(seg, inline_flag)
    if script:
        verdict, reason = ask_ai_about_script(script, language)
        if verdict is False:
            _record_block(None, language, reason)
        return verdict is True
    filename = extract_script_filename(seg, command)
    if filename:
        if is_in_trusted_script_dir(filename):
            log_debug(f"Script in trusted directory, allowing: {filename}")
            return True
        content = read_script_file(filename)
        if content is None:
            return False
        verdict, reason = ask_ai_about_script(content, language, command_line=seg)
        if verdict is False:
            _record_block(filename, language, reason)
        return verdict is True
    # No script to analyze (e.g. `python --version`): nothing unsafe to run.
    return True


def check_node_segment(seg):
    if '--check' in shell_tokenize(seg):
        return True  # syntax-only check, never executes code
    return _check_segment(seg, 'node', 'javascript', '-e')


def check_python_segment(seg, command):
    return _check_segment(seg, command, 'python', '-c')
