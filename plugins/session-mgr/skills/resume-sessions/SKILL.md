---
skill: resume-sessions
description: Find and resume Claude Code sessions that ended abruptly (without an "exit" command) since a given date. Use when the user asks to resume sessions from after a computer restart, crash, or unplanned shutdown, or when they want to recover sessions that weren't properly closed.
instructions: |-
  Find all Claude Code sessions since last Thursday (or the date specified in args) that ended without
  an explicit "exit" command, then launch each one in a new Windows Terminal tab for resumption.

  ## Step 1 — Determine the cutoff date

  Default: the most recent Thursday before today. If args contains a specific date or phrase like
  "since Monday" or "from June 26", parse that instead. Convert to a Unix timestamp for file mtime
  comparison.

  Today's date is always available in the system-reminder context block at the top of the conversation.

  ## Step 2 — Find abrupt sessions

  Write a Python script to `.tmp/find_abrupt_sessions.py` and run it:

  ```python
  import os, json
  from datetime import datetime, timezone

  PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
  CUTOFF = <unix_timestamp_of_cutoff_date>

  abrupt = []

  for project_dir in os.listdir(PROJECTS_DIR):
      full_project = os.path.join(PROJECTS_DIR, project_dir)
      if not os.path.isdir(full_project):
          continue

      for fname in os.listdir(full_project):
          if not fname.endswith(".jsonl"):
              continue
          fpath = os.path.join(full_project, fname)
          mtime = os.path.getmtime(fpath)
          if mtime < CUTOFF:
              continue

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

          session_id = fname.replace(".jsonl", "")
          abrupt.append({
              "session_id": session_id,
              "project_dir": project_dir,
              "cwd": cwd,
              "title": title or "(no title)",
              "last_user_text": last_user_text,
              "mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
          })

  abrupt.sort(key=lambda x: x["mtime"])
  print(json.dumps(abrupt, indent=2))
  ```

  Run with `python ~/.tmp/find_abrupt_sessions.py`.

  ## Step 3 — Filter to interactive sessions

  From the full list, exclude:
  - The current session (check the current session ID if visible, or match on the last_user_text
    being the exact prompt the user just typed in this session)
  - Drainer auto-seeded sessions: last_user_text starts with "Your task instructions are in"
  - Background task notification endings: last_user_text starts with "<task-notification>"
  - Triage prompt endings: last_user_text is very long (>500 chars) and contains JSON arrays
    (these are automated triage payloads, not human input)

  ## Step 4 — Show the user what you found

  Before launching, print a brief summary:
  ```
  Found N sessions to resume:
  1. "Title" — last: "last user text snippet" (Jun 27 17:30, cwd)
  2. ...
  ```

  ## Step 5 — Launch each session in a new WT tab

  For each session in the filtered list, run:

  ```bash
  "$HOME/AppData/Local/Microsoft/WindowsApps/wt.exe" -w 0 new-tab \
    -d "<cwd_with_forward_slashes>" \
    --title "<short title (≤30 chars)>" \
    powershell -NoExit -NoProfile \
    -File "$HOME/OneDrive/Claude/scripts/launch-session.ps1" \
    -Resume "<session_id>"
  ```

  Key rules for the wt.exe command:
  - Top-level command is `wt.exe`, NOT `powershell`
  - Use forward-slash drive paths for `-d` and `-File` (e.g. `C:/Users/...`)
  - Backslash paths from `cwd` must be converted to forward slashes
  - `-Resume` accepts only the UUID — no prose, no quotes needed inside the `-File` invocation
  - Keep `--title` short and quote-free (no `"` inside the title string)

  Launch each tab sequentially with a brief pause (the Bash tool runs them one at a time naturally).

  ## Step 6 — Confirm

  After all tabs are launched, tell the user how many sessions were opened and list the titles.

  ## Step 7 — Create the skill (first time only)

  If this is the first time running and the user asks to create a skill for this, the skill already
  exists at:
  `~/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/skills/resume-sessions/SKILL.md`

  Just confirm it's there and that it will be available after the plugin is reinstalled/updated.

  ## Notes

  - The `launch-session.ps1` `-Resume` flag was added alongside this skill. It runs
    `claude --resume <session_id>` in the correct working directory.
  - `claude --resume <session_id>` resumes an existing session by its UUID, picking up the full
    conversation history.
  - Sessions from the drainer (autonomous email/Teams triage loops) are deliberately excluded —
    the drainer manages its own lifecycle and will re-queue any incomplete items.
---
