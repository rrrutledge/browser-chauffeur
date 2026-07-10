"""Unit tests for the pure parsing/classification helpers — the pieces most
prone to subtle regression during refactoring."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, PLUGIN_DIR)

from safe_compounds.shell import (  # noqa: E402
    ASSIGNMENT_ONLY, extract_substitutions, first_word, has_unquoted_windows_drive_path,
    split_segments, strip_var_assignment,
)
from safe_compounds import config  # noqa: E402
from safe_compounds.commands import (  # noqa: E402
    is_git_command_safe, is_curl_safe, is_sed_command_safe, is_start_safe, is_taskkill_safe,
    strip_safe_redirections,
)
from safe_compounds import procs  # noqa: E402
from safe_compounds.mcp import classify_mcp_tool  # noqa: E402
from safe_compounds.enforce import detect_complex_bash, detect_simple_expansion, detect_cd_compound, enforce_bash  # noqa: E402
from safe_compounds.scripts import check_node_segment, get_block_reason, reset_block_reason  # noqa: E402
from safe_compounds.workflow import classify_workflow_tool  # noqa: E402


def set_config(**kwargs):
    base = {
        "trusted_commands": [], "curl_domains": [], "mcp_blanket_servers": [],
        "mcp_blanket_tools": [], "trusted_script_dirs": [], "workflow_blanket_names": [],
    }
    base.update(kwargs)
    config._CONFIG = base


class TestSplitSegments:
    def test_operators(self):
        assert split_segments("a && b || c ; d | e") == ["a ", " b ", " c ", " d ", " e"]

    def test_quotes_protect_operators(self):
        assert split_segments("echo 'a && b'") == ["echo 'a && b'"]

    def test_double_quotes_protect_pipe(self):
        assert split_segments('echo "x | y"') == ['echo "x | y"']

    def test_newlines_treated_as_whitespace(self):
        # Newlines in multi-line commands should not split segments
        assert split_segments("grep -iE\n      \"pattern\"") == ["grep -iE\n      \"pattern\""]
        # But semicolons should still split
        assert split_segments("echo foo\necho bar; echo baz") == ["echo foo\necho bar", " echo baz"]


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
    # allowlist: known read-only / reversible subcommands pass
    def test_status_ok(self):
        assert is_git_command_safe("git status") is True

    def test_commit_ok(self):
        assert is_git_command_safe("git commit -m x") is True

    def test_push_plain_ok(self):
        assert is_git_command_safe("git push") is True

    def test_reset_soft_ok(self):
        assert is_git_command_safe("git reset --soft HEAD~1") is True

    def test_checkout_branch_ok(self):
        assert is_git_command_safe("git checkout -b feature") is True

    def test_clean_dry_ok(self):
        assert is_git_command_safe("git clean -n") is True

    # destructive flags / unlisted subcommands fall through
    def test_push_force_blocked(self):
        assert is_git_command_safe("git push --force") is False

    def test_reset_hard_blocked(self):
        assert is_git_command_safe("git reset --hard") is False

    def test_checkout_dot_allowed(self):
        assert is_git_command_safe("git checkout .") is True

    def test_branch_delete_allowed(self):
        assert is_git_command_safe("git branch -D old") is True

    def test_clean_force_blocked(self):
        assert is_git_command_safe("git clean -fd") is False

    def test_rebase_allowed(self):
        assert is_git_command_safe("git rebase main") is True

    def test_global_opt_before_subcommand(self):
        assert is_git_command_safe("git -C /repo push --force") is False

    def test_redirect_not_mistaken_for_subcommand(self):
        # A redirect after global opts must not be read as the subcommand;
        # a subcommand-less git invocation is harmless (allow_empty).
        assert is_git_command_safe("git -C dir 2>/dev/null") is True
        assert is_git_command_safe("git -C dir 2> /dev/null") is True
        assert is_git_command_safe("git status 2>/dev/null") is True

    # "git -C <dir>" is not a special form to block: its safety is decided by the
    # subcommand + flags exactly as without -C. enforce_bash must let it through so
    # the subcommand checker can validate it (the shell CWD resets between Bash
    # calls, so "cd <dir> && git ..." is not a usable alternative).
    def test_global_opt_not_blocked_by_enforce(self):
        assert enforce_bash("git -C /repo push -u origin feature") is None
        assert enforce_bash("git -C /repo add file.txt") is None
        assert enforce_bash("git -C /repo commit -m x") is None


class TestCurl:
    def test_localhost(self):
        set_config()
        assert is_curl_safe("curl http://localhost:3000/x") is True

    def test_get_public(self):
        set_config()
        assert is_curl_safe("curl https://example.com") is True

    def test_post_public_blocked(self):
        set_config()
        assert is_curl_safe("curl -X POST https://example.com -d x=1") is False

    def test_post_configured_domain_ok(self):
        set_config(curl_domains=["mycorp.example"])
        assert is_curl_safe('curl -X POST https://api.mycorp.example/x ') is True

    def test_post_unconfigured_domain_blocked(self):
        set_config(curl_domains=["mycorp.example"])
        assert is_curl_safe('curl -X POST https://other.com/x') is False


class TestSed:
    def test_plain(self):
        assert is_sed_command_safe("sed s/a/b/ f") is True

    def test_inplace(self):
        assert is_sed_command_safe("sed -i s/a/b/ f") is False

    def test_inplace_combined(self):
        assert is_sed_command_safe("sed -ni s/a/b/ f") is False


class TestTaskkill:
    def test_self_pid_approved(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /PID 16552 /T /F") is True

    def test_other_pid_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /PID 9999 /T /F") is False

    def test_undetermined_host_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: None)
        assert is_taskkill_safe("taskkill /PID 16552 /T /F") is False

    def test_image_name_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /IM chrome.exe /F") is False

    def test_remote_machine_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /S remotehost /PID 16552 /F") is False

    def test_no_pid_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /F") is False

    def test_non_numeric_pid_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /PID abc /F") is False

    def test_multiple_pids_all_must_match(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /PID 16552 /PID 9999 /F") is False

    def test_case_insensitive_flags(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill /pid 16552 /t /f") is True

    def test_msys_double_slash_approved(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill //PID 16552 //T //F") is True

    def test_msys_double_slash_other_pid_rejected(self, monkeypatch):
        monkeypatch.setattr(procs, "self_tab_host_pid", lambda: 16552)
        assert is_taskkill_safe("taskkill //PID 9999 //T //F") is False


class TestSelfTabHostPid:
    def _snapshot(self):
        # hook.py (pid 100) -> sh.exe (200) -> claude.exe (300) -> powershell.exe
        # (400, the tab host) -> WindowsTerminal.exe (500) -> services.exe (600)
        return {
            100: (200, 'python.exe'),
            200: (300, 'sh.exe'),
            300: (400, 'claude.exe'),
            400: (500, 'powershell.exe'),
            500: (600, 'windowsterminal.exe'),
            600: (0, 'services.exe'),
        }

    def test_finds_immediate_parent_of_claude(self):
        assert procs.self_tab_host_pid(start_pid=100, snapshot=self._snapshot()) == 400

    def test_stops_at_nearest_claude_in_nested_sessions(self):
        snap = self._snapshot()
        # An outer claude.exe further up must not be selected over the inner one.
        snap[500] = (700, 'claude.exe')
        snap[700] = (800, 'powershell.exe')
        assert procs.self_tab_host_pid(start_pid=100, snapshot=snap) == 400

    def test_no_claude_in_chain_returns_none(self):
        snap = self._snapshot()
        del snap[300]
        assert procs.self_tab_host_pid(start_pid=100, snapshot=snap) is None

    def test_empty_snapshot_returns_none(self):
        assert procs.self_tab_host_pid(start_pid=100, snapshot={}) is None

    def test_cycle_returns_none(self):
        snap = {100: (200, 'python.exe'), 200: (100, 'sh.exe')}
        assert procs.self_tab_host_pid(start_pid=100, snapshot=snap) is None


class TestStripSafeRedirections:
    def test_stderr_merge_suffix(self):
        assert strip_safe_redirections('start report.docx 2>&1').strip() == 'start report.docx'

    def test_stderr_merge_before_pipe(self):
        # split_segments() already separates "| head -2" into its own segment;
        # this is the "start ... 2>&1" segment as approve.py sees it.
        assert strip_safe_redirections('start report.docx 2>&1 ').strip() == 'start report.docx'

    def test_devnull_merge(self):
        assert strip_safe_redirections('cmd >/dev/null 2>&1').strip() == 'cmd'

    def test_no_redirect_unchanged(self):
        assert strip_safe_redirections('start report.docx') == 'start report.docx'

    def test_preserves_quoted_spaces(self):
        seg = 'start "" "C:/some dir/My File.docx" 2>&1'
        assert strip_safe_redirections(seg).strip() == 'start "" "C:/some dir/My File.docx"'


class TestStartSafe:
    def test_bare_docx(self):
        assert is_start_safe('start report.docx') is True

    def test_stderr_merge_does_not_defeat_target_check(self):
        # Regression: a trailing "2>&1" used to become the last token, so
        # is_start_safe read it as the launch target and rejected the command.
        assert is_start_safe(strip_safe_redirections('start report.docx 2>&1')) is True

    def test_unsafe_extension_still_rejected_with_redirect(self):
        assert is_start_safe(strip_safe_redirections('start evil.exe 2>&1')) is False


class TestMcp:
    def test_read(self):
        assert classify_mcp_tool("mcp__s__get_thing") is True

    def test_reversible_write(self):
        assert classify_mcp_tool("mcp__s__create_thing") is True

    def test_destructive(self):
        assert classify_mcp_tool("mcp__s__delete_thing") is False

    def test_blanket_server_configured(self):
        set_config(mcp_blanket_servers=["myserver"])
        assert classify_mcp_tool("mcp__myserver__anything") is True

    def test_blanket_server_not_configured(self):
        set_config()
        # 'anything' is not a recognized verb, so without a blanket config it prompts
        assert classify_mcp_tool("mcp__myserver__anything") is False

    def test_unknown_verb(self):
        set_config()
        assert classify_mcp_tool("mcp__s__frobnicate_thing") is False

    def test_blanket_tool_configured(self):
        set_config(mcp_blanket_tools=["mcp__s__frobnicate_thing"])
        assert classify_mcp_tool("mcp__s__frobnicate_thing") is True

    def test_blanket_tool_does_not_affect_other_tools_on_same_server(self):
        set_config(mcp_blanket_tools=["mcp__s__frobnicate_thing"])
        assert classify_mcp_tool("mcp__s__other_thing") is False


class TestWorkflow:
    def test_named_blanket(self):
        set_config(workflow_blanket_names=["code-review"])
        assert classify_workflow_tool({"name": "code-review"}) is True

    def test_named_not_blanket(self):
        set_config(workflow_blanket_names=["code-review"])
        assert classify_workflow_tool({"name": "other"}) is False

    def test_no_config(self):
        set_config()
        assert classify_workflow_tool({"name": "code-review"}) is False

    def test_inline_script_never_blanket_even_if_it_claims_the_name(self):
        # An inline/dynamic script's own text is unverified at call time, so a
        # self-declared meta.name must never grant blanket trust.
        set_config(workflow_blanket_names=["code-review"])
        script = "export const meta = {\n  name: 'code-review',\n  description: 'x',\n}\nlog('hi')"
        assert classify_workflow_tool({"script": script}) is False

    def test_no_name_or_script(self):
        set_config(workflow_blanket_names=["code-review"])
        assert classify_workflow_tool({}) is False


class TestComplexBash:
    def test_subst(self):
        assert detect_complex_bash("echo $(date)")[0] is True

    def test_for(self):
        assert detect_complex_bash("for x in a; do echo $x; done")[0] is True

    def test_until(self):
        assert detect_complex_bash("until grep -q x file; do break; done")[0] is True

    def test_plain(self):
        assert detect_complex_bash("grep x file")[0] is False


class TestSimpleExpansion:
    def test_custom_var(self):
        assert detect_simple_expansion("echo $MYTOKEN") == "MYTOKEN"

    def test_standard_var_ignored(self):
        assert detect_simple_expansion("echo $HOME") is None

    def test_single_quote_ignored(self):
        assert detect_simple_expansion("echo '$MYTOKEN'") is None


class TestCheckNodeSegment:
    def test_check_flag_short_circuits(self):
        # `node --check <file>` only parses for syntax errors, never executes,
        # so it is auto-approved without reading or AI-judging the file.
        set_config()
        assert check_node_segment("node --check path/to/some/script.js") is True

    def test_check_flag_with_extra_spacing(self):
        set_config()
        assert check_node_segment("node  --check  foo.mjs") is True

    def test_unquoted_windows_path_gets_actionable_block(self):
        # A bare C:\...\script.js argument gets its backslashes stripped by
        # shell word-splitting before node ever sees it (real bash does this
        # identically to shlex — it isn't shlex-specific). The missing-file
        # case should be turned into a clear, actionable deny instead of a
        # silent fall-through to a manual prompt.
        set_config()
        reset_block_reason()
        seg = r'node C:\definitely\not\a\real\path\script.js'
        assert check_node_segment(seg) is False
        reason = get_block_reason()
        assert reason is not None
        assert "BLOCKED" in reason
        assert "unquoted" in reason.lower()

    def test_missing_file_without_windows_path_gets_generic_block(self):
        # A plain missing file (no Windows-path hazard) still denies, with the
        # generic "use the full path" message instead of the mangled-path one.
        set_config()
        reset_block_reason()
        assert check_node_segment("node /definitely/not/a/real/script.js") is False
        reason = get_block_reason()
        assert reason is not None
        assert "BLOCKED" in reason
        assert "unquoted" not in reason.lower()
        assert "full absolute path" in reason

    def test_double_quoted_windows_path_not_flagged_as_mangled(self):
        # Double-quoting preserves backslashes, so this isn't the mangled-path
        # hazard — it should fail for the ordinary "file not found" reason.
        set_config()
        reset_block_reason()
        seg = r'node "C:\definitely\not\a\real\path\script.js"'
        assert check_node_segment(seg) is False
        reason = get_block_reason()
        assert reason is not None
        assert "unquoted" not in reason.lower()
        assert "full absolute path" in reason


class TestHasUnquotedWindowsDrivePath:
    def test_bare_path_flagged(self):
        assert has_unquoted_windows_drive_path(r'node C:\Users\russe\script.js') is True

    def test_double_quoted_path_not_flagged(self):
        assert has_unquoted_windows_drive_path(r'node "C:\Users\russe\script.js"') is False

    def test_forward_slash_path_not_flagged(self):
        assert has_unquoted_windows_drive_path('node C:/Users/russe/script.js') is False

    def test_posix_style_path_not_flagged(self):
        assert has_unquoted_windows_drive_path('node /c/Users/russe/script.js') is False

    def test_flags_mid_command_occurrence(self):
        seg = r'node script.js C:\Users\russe\Dev\out'
        assert has_unquoted_windows_drive_path(seg) is True


class TestMissingScriptBlocks(object):
    """A relative script filename that doesn't resolve against CLAUDE_CWD should
    deny with an actionable message (use the full path), not silently fall
    through to a bare approval prompt."""

    def setup_method(self):
        reset_block_reason()

    def test_missing_relative_script_denies_with_full_path_instruction(self, tmp_path):
        set_config()
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert check_node_segment("node gmail.js --search=foo") is False
        reason = get_block_reason()
        assert reason is not None
        assert "BLOCKED" in reason
        assert "gmail.js" in reason
        assert "full absolute path" in reason
        assert str(tmp_path).replace('\\', '/').lower() in reason.replace('\\', '/').lower()

    def test_existing_script_does_not_trip_missing_script_block(self, tmp_path):
        set_config()
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        os.environ['SAFE_COMPOUNDS_DISABLE_AI'] = '1'
        (tmp_path / "script.js").write_text("console.log('hi')", encoding="utf-8")
        try:
            check_node_segment("node script.js")
        finally:
            del os.environ['SAFE_COMPOUNDS_DISABLE_AI']
        # AI is disabled so the verdict is undecided (falls through to a plain
        # prompt), but the missing-script block must not have fired.
        assert get_block_reason() is None


class TestCdCompoundDetection:
    """Test cd followed by more commands in various formats."""

    def test_cd_with_ampersand_other_dir(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound("cd /other/dir && git status") == "/other/dir"

    def test_cd_with_semicolon_other_dir(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound("cd /other/dir; git status") == "/other/dir"

    def test_cd_with_newline_other_dir(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound("cd /other/dir\ngit status") == "/other/dir"

    def test_cd_with_newline_multiline(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        cmd = "cd /other/dir\necho test\ngit status"
        assert detect_cd_compound(cmd) == "/other/dir"

    def test_cd_to_same_dir_not_detected(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound(f"cd {tmp_path} && git status") is None

    def test_cd_alone_not_detected(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound("cd /other/dir") is None

    def test_cd_with_only_whitespace_after_not_detected(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound("cd /other/dir\n  \n\t\n") is None

    def test_cd_quoted_path_with_ampersand(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound('cd "/other/path with spaces" && ls') == "/other/path with spaces"

    def test_cd_quoted_path_with_newline(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert detect_cd_compound('cd "/other/path with spaces"\nls') == "/other/path with spaces"

    def test_original_reported_command(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        cmd = ("cd ~/Dev/rrrutledge/rrrutledge-claude-code-plugins\n"
               'echo "=== 1. restore ==="; git checkout origin/main -- plugins/drainer/drainer_config.py && echo "restored"\n'
               'echo "=== 2. rename ==="; git mv plugins/drainer/outlook-adapter.py plugins/drainer/outlook-rest-adapter.py')
        assert detect_cd_compound(cmd) == "~/Dev/rrrutledge/rrrutledge-claude-code-plugins"


class TestCdCompoundBlocking:
    """Test that enforce_bash blocks cd compound patterns with correct message."""

    def test_block_cd_ampersand(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other/dir && git status")
        assert reason is not None
        assert "BLOCKED" in reason
        assert "NEVER" in reason
        assert "git -C /other/dir" in reason

    def test_block_cd_newline(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other/dir\ngit status")
        assert reason is not None
        assert "BLOCKED" in reason
        assert "NEVER" in reason

    def test_block_message_has_script_examples(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other && python script.py")
        assert "python /other/script.py" in reason
        assert "bash /other/script.sh" in reason

    def test_block_message_has_git_c_flag(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /repo && git status")
        assert "git -C /repo status" in reason
        assert "git -C /repo checkout" in reason

    def test_no_split_bash_calls_advice(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other && git status")
        assert "split into" not in reason.lower()
        assert "two separate Bash tool calls" not in reason

    def test_no_block_cd_alone(self, tmp_path):
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        assert enforce_bash("cd /other/dir") is None


class TestCdCompoundDetection:
    """Test cd followed by more commands in various formats."""

    def test_cd_with_ampersand_other_dir(self, tmp_path):
        """cd /other && cmd should be detected when target != cwd."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound("cd /other/dir && git status")
        assert target == "/other/dir"

    def test_cd_with_semicolon_other_dir(self, tmp_path):
        """cd /other ; cmd should be detected."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound("cd /other/dir; git status")
        assert target == "/other/dir"

    def test_cd_with_newline_other_dir(self, tmp_path):
        """cd /other\\ncmd should be detected (the new case!)."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound("cd /other/dir\ngit status")
        assert target == "/other/dir"

    def test_cd_with_newline_multiline_other_dir(self, tmp_path):
        """cd /other\\ncmd1\\ncmd2 should be detected."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        cmd = """cd /other/dir
echo "test"
git status
git commit"""
        target = detect_cd_compound(cmd)
        assert target == "/other/dir"

    def test_cd_to_same_dir_not_detected(self, tmp_path):
        """cd <cwd> && cmd should return None (handled by detect_cd_cwd_prefix)."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound(f"cd {tmp_path} && git status")
        assert target is None

    def test_cd_alone_not_detected(self, tmp_path):
        """Just 'cd /other' with no following commands should return None."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound("cd /other/dir")
        assert target is None

    def test_cd_with_only_whitespace_after_not_detected(self, tmp_path):
        """cd /other\\n\\n (only whitespace after) should return None."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound("cd /other/dir\n  \n\t\n")
        assert target is None

    def test_cd_quoted_path_with_ampersand(self, tmp_path):
        """cd "/path with spaces" && cmd should work."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound('cd "/other/path with spaces" && ls')
        assert target == "/other/path with spaces"

    def test_cd_quoted_path_with_newline(self, tmp_path):
        """cd "/path with spaces"\\ncmd should work."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        target = detect_cd_compound('cd "/other/path with spaces"\nls')
        assert target == "/other/path with spaces"

    def test_original_reported_command(self, tmp_path):
        """The actual command that wasn't blocked but should have been."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        cmd = """cd ~/Dev/rrrutledge/rrrutledge-claude-code-plugins
echo "=== 1. restore drainer_config.py to main ==="; git checkout origin/main -- plugins/drainer/providers/drainer_config.py && echo "restored"
echo "=== 2. rename ==="; git mv plugins/drainer/providers/outlook-adapter.py plugins/drainer/providers/outlook-rest-adapter.py"""
        target = detect_cd_compound(cmd)
        assert target == "~/Dev/rrrutledge/rrrutledge-claude-code-plugins"


class TestCdCompoundBlocking:
    """Test that enforce_bash blocks cd compound patterns with correct message."""

    def test_block_cd_ampersand(self, tmp_path):
        """cd && cmd should be blocked with helpful message."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other/dir && git status")
        assert reason is not None
        assert "BLOCKED" in reason
        assert "cd /other/dir" in reason
        assert "NEVER" in reason
        assert "git -C /other/dir" in reason

    def test_block_cd_newline(self, tmp_path):
        """cd\\ncmd should be blocked with helpful message."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other/dir\ngit status")
        assert reason is not None
        assert "BLOCKED" in reason
        assert "cd /other/dir" in reason
        assert "NEVER" in reason

    def test_block_message_has_script_examples(self, tmp_path):
        """Block message should show how to run scripts from current dir."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other && python script.py")
        assert "python /other/script.py" in reason
        assert "bash /other/script.sh" in reason

    def test_block_message_has_git_c_flag(self, tmp_path):
        """Block message should show git -C alternative."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /repo && git status")
        assert "git -C /repo status" in reason
        assert "git -C /repo checkout" in reason

    def test_no_block_message_about_splitting_bash_calls(self, tmp_path):
        """Block message should NOT suggest splitting into two Bash calls (that doesn't work)."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other && git status")
        assert "split into" not in reason.lower()
        assert "two separate Bash tool calls" not in reason

    def test_no_block_cd_alone(self, tmp_path):
        """Just 'cd /other' should not be blocked."""
        os.environ['CLAUDE_CWD'] = str(tmp_path)
        reason = enforce_bash("cd /other/dir")
        assert reason is None
