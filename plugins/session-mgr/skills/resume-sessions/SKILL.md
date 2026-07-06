---
skill: resume-sessions
description: Find and resume Claude Code sessions that ended abruptly (without an "exit" command). Use when the user asks to resume sessions after a computer restart, crash, or unplanned shutdown, or when they want to recover sessions that weren't properly closed.
instructions: |-
  Find all Claude Code sessions that ended without an explicit "exit" command and launch each one
  in a new Windows Terminal tab for resumption. Skip sessions that are currently open.

  ## Step 1 — Find currently active session IDs

  Run `wmic process where "name='claude.exe'" get CommandLine` and extract every session UUID
  (pattern: `--resume <uuid>` or `--session-id <uuid>`). These are sessions already open in a tab
  and must be excluded from the launch list.

  Write a Python script to `.tmp/find_abrupt_sessions.py` and run it, passing the active IDs as
  a JSON argument or writing them to a temp file first.

  ## Step 2 — Find abrupt sessions

  ```python
  import os, json, sys
  from datetime import datetime

  PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
  active_ids = set(json.loads(sys.argv[1])) if len(sys.argv) > 1 else set()

  abrupt = []

  for project_dir in os.listdir(PROJECTS_DIR):
      full_project = os.path.join(PROJECTS_DIR, project_dir)
      if not os.path.isdir(full_project):
          continue

      for fname in os.listdir(full_project):
          if not fname.endswith(".jsonl"):
              continue
          session_id = fname.replace(".jsonl", "")
          if session_id in active_ids:
              continue

          fpath = os.path.join(full_project, fname)
          title = None
          cwd = None
          last_user_text = None

          try:
              with open(fpath, encoding="utf-8") as f:
                  for line in f:
                      line = line.strip()
                      if not line:
                          continue
                      try:
                          entry = json.loads(line)
                      except json.JSONDecodeError:
                          continue
                      t = entry.get("type")
                      if t == "ai-title" and not title:
                          title = entry.get("aiTitle")
                      if t == "user":
                          if not cwd and entry.get("cwd"):
                              cwd = entry["cwd"]
                          msg = entry.get("message", {})
                          content = msg.get("content") if isinstance(msg, dict) else None
                          if isinstance(content, str) and content.strip():
                              last_user_text = content.strip()
          except Exception:
              continue

          if last_user_text is None:
              continue
          if last_user_text.lower() == "exit":
              continue

          mtime = os.path.getmtime(fpath)
          abrupt.append({
              "session_id": session_id,
              "cwd": cwd,
              "title": title or "(no title)",
              "last_user_text": last_user_text,
              "mtime": mtime,
              "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
          })

  abrupt.sort(key=lambda x: x["mtime"])
  print(json.dumps(abrupt, indent=2))
  ```

  Run: `python .tmp/find_abrupt_sessions.py '<json_array_of_active_ids>'`

  ## Step 3 — Exclude only sessions with clear machine-generated endings

  From the full list, exclude only sessions whose last_user_text matches one of these exact
  machine-generated patterns — do NOT apply any other judgment about whether a session looks
  "complete" or "worth resuming":

  - Proper exit: last_user_text is exactly `<local-command-stdout>Goodbye!</local-command-stdout>`
    or `<local-command-stdout>Bye!</local-command-stdout>`
  - Background task notification: last_user_text starts with `<task-notification>`
  - Automated triage prompt: last_user_text is longer than 500 chars AND contains a JSON array (`[`)

  Launch everything else — short replies, drainer seeds, mid-sentence messages, one-word answers,
  all of it. Do not guess whether the user considered a session finished.

  ## Step 4 — Launch each session in a new WT tab

  For each session in the filtered list, run:

  ```bash
  "$HOME/AppData/Local/Microsoft/WindowsApps/wt.exe" -w 0 new-tab \
    -d "<cwd_with_forward_slashes>" \
    --title "<short title (≤30 chars)>" \
    powershell -NoExit -NoProfile \
    -File "$HOME/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/skills/resume-sessions/scripts/launch-session.ps1" \
    -Resume "<session_id>"
  ```

  Key rules for the wt.exe command:
  - Top-level command is `wt.exe`, NOT `powershell`
  - Use forward-slash drive paths for `-d` and `-File` (e.g. `C:/Users/...`)
  - Backslash paths from `cwd` must be converted to forward slashes
  - `-Resume` accepts only the UUID — no prose needed
  - Keep `--title` short and quote-free (no `"` inside the title string)

  Launch each tab sequentially (the Bash tool runs them one at a time naturally).

  ## Step 5 — Confirm

  Tell the user how many sessions were opened and list the titles. If any sessions were skipped
  because they were already open, mention that count too.

  ## Notes

  - `launch-session.ps1` lives inside this plugin at
    `~/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/skills/resume-sessions/scripts/launch-session.ps1`
    (the command above points there). Its `-Resume` flag runs `claude --resume <session_id>` in the
    correct working directory. The drainer plugin ships a thin resolver of its own that finds the
    newest *installed* copy of this launcher, so drainer workers aren't tied to a working-clone branch.
  - `claude --resume <session_id>` resumes an existing session by its UUID, picking up the full
    conversation history.
  - There are ~1,300 JSONL session files total; the script scans them all but only reads the tail
    of each (last user message), so it completes in a few seconds.
---
