"""Unit tests for the pure parsing/classification helpers — the pieces most
prone to subtle regression during refactoring."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, PLUGIN_DIR)

from safe_compounds.shell import (  # noqa: E402
    ASSIGNMENT_ONLY, extract_substitutions, first_word, split_segments, strip_var_assignment,
)
from safe_compounds.commands import is_git_command_safe, is_curl_safe, is_sed_command_safe  # noqa: E402
from safe_compounds.mcp import classify_mcp_tool  # noqa: E402
from safe_compounds.enforce import detect_complex_bash, detect_simple_expansion  # noqa: E402


class TestSplitSegments:
    def test_operators(self):
        assert split_segments("a && b || c ; d | e") == ["a ", " b ", " c ", " d ", " e"]

    def test_quotes_protect_operators(self):
        assert split_segments("echo 'a && b'") == ["echo 'a && b'"]

    def test_double_quotes_protect_pipe(self):
        assert split_segments('echo "x | y"') == ['echo "x | y"']


class TestFirstWord:
    def test_plain(self):
        assert first_word("grep -r foo") == "grep"

    def test_strips_env_assignment(self):
        assert first_word("FOO=bar grep x") == "grep"

    def test_pure_assignment(self):
        assert first_word("FOO=bar") == ASSIGNMENT_ONLY

    def test_path_basename(self):
        assert first_word("/usr/bin/grep x") == "grep"

    def test_exe_suffix(self):
        assert first_word("where.exe python") == "where"

    def test_leading_redirection(self):
        assert first_word("2>/dev/null grep x") == "grep"


class TestStripVarAssignment:
    def test_simple(self):
        assert strip_var_assignment("X=1 echo hi") == "echo hi"

    def test_substitution_value(self):
        assert strip_var_assignment("X=$(date) echo hi") == "echo hi"

    def test_no_assignment(self):
        assert strip_var_assignment("echo hi") == "echo hi"


class TestExtractSubstitutions:
    def test_simple(self):
        assert extract_substitutions("echo $(date)") == ["date"]

    def test_nested(self):
        assert extract_substitutions("echo $(a $(b))") == ["a $(b)"]

    def test_single_quote_suppresses(self):
        assert extract_substitutions("echo '$(date)'") == []


class TestGit:
    def test_status_ok(self):
        assert is_git_command_safe("git status") is True

    def test_push_force_blocked(self):
        assert is_git_command_safe("git push --force") is False

    def test_reset_hard_blocked(self):
        assert is_git_command_safe("git reset --hard") is False

    def test_checkout_dot_blocked(self):
        assert is_git_command_safe("git checkout .") is False

    def test_global_opt_before_subcommand(self):
        assert is_git_command_safe("git -C /repo push --force") is False

    def test_commit_dash_f_not_confused(self):
        # -F is not the dangerous -f
        assert is_git_command_safe("git commit -F msg.txt") is True


class TestCurl:
    def test_localhost(self):
        assert is_curl_safe("curl http://localhost:3000/x") is True

    def test_get_public(self):
        assert is_curl_safe("curl https://example.com") is True

    def test_post_public_blocked(self):
        assert is_curl_safe("curl -X POST https://example.com -d x=1") is False

    def test_post_wellsky_ok(self):
        assert is_curl_safe('curl -X POST https://wellsky.atlassian.net/x ') is True


class TestSed:
    def test_plain(self):
        assert is_sed_command_safe("sed s/a/b/ f") is True

    def test_inplace(self):
        assert is_sed_command_safe("sed -i s/a/b/ f") is False

    def test_inplace_combined(self):
        assert is_sed_command_safe("sed -ni s/a/b/ f") is False


class TestMcp:
    def test_read(self):
        assert classify_mcp_tool("mcp__s__get_thing") is True

    def test_reversible_write(self):
        assert classify_mcp_tool("mcp__s__create_thing") is True

    def test_destructive(self):
        assert classify_mcp_tool("mcp__s__delete_thing") is False

    def test_blanket_server(self):
        assert classify_mcp_tool("mcp__plugin_product-management_atlassian__anything") is True

    def test_unknown_verb(self):
        assert classify_mcp_tool("mcp__s__frobnicate_thing") is False


class TestComplexBash:
    def test_subst(self):
        assert detect_complex_bash("echo $(date)")[0] is True

    def test_for(self):
        assert detect_complex_bash("for x in a; do echo $x; done")[0] is True

    def test_plain(self):
        assert detect_complex_bash("grep x file")[0] is False


class TestSimpleExpansion:
    def test_custom_var(self):
        assert detect_simple_expansion("echo $MYTOKEN") == "MYTOKEN"

    def test_standard_var_ignored(self):
        assert detect_simple_expansion("echo $HOME") is None

    def test_single_quote_ignored(self):
        assert detect_simple_expansion("echo '$MYTOKEN'") is None
