"""Bash segment approval: decide whether one command segment uses only trusted
operations. The orchestrator (hook.py) approves a command when every segment
passes this check."""
from . import commands
from .scripts import check_node_segment, check_python_segment
from .shell import first_word, shell_tokenize

SHELL_BODY_KEYWORDS = {'do', 'then', 'else', 'elif', 'if', 'while', 'until'}
SHELL_STRUCTURE_ONLY = {'for', 'done', 'fi', 'esac', 'case', 'select', 'in'}


def check_shell_keyword(word, seg, trusted):
    """Handle shell structure keywords (if/then/for/...). Returns True when the
    keyword is structural or introduces a trusted command; False otherwise."""
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
    """True if a single command segment uses only trusted operations."""
    seg = seg.strip()
    if not seg or seg.startswith('#'):
        return True

    if not commands.is_output_redirection_safe(seg):
        return False

    word = first_word(seg)

    if word == 'curl':
        return commands.is_curl_safe(seg)
    if word == 'node':
        return check_node_segment(seg)
    if word in ('python', 'python3'):
        return check_python_segment(seg, word)
    if word == 'sed':
        return commands.is_sed_command_safe(seg)
    if word in commands.SUBCOMMAND_TOOLS:
        return commands.check_subcommand_tool(word, seg)
    if word in commands.CWD_FILE_COMMAND_CONFIG:
        return commands.check_cwd_file_command(seg, word)
    if word == 'start':
        return commands.is_start_safe(seg)
    if word == 'powershell':
        return commands.is_powershell_safe(seg)
    if word == 'wt':
        return commands.is_wt_safe(seg, trusted)
    if word.lower().endswith('wt.exe'):
        return commands.is_wt_exe_path_safe(seg)
    if word.lower().endswith('.cmd'):
        tokens = shell_tokenize(seg)
        filepath = tokens[0] if tokens else seg.strip()
        return commands.is_cmd_file_safe(filepath, trusted)

    if check_shell_keyword(word, seg, trusted):
        return True
    if word in trusted:
        return True
    return commands.is_unknown_command_safe(word, seg)
