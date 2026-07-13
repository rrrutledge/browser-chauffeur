---
skill: resume-sessions
description: Find and resume Claude Code sessions that ended abruptly (without an "exit" command). Use when the user asks to resume sessions after a computer restart, crash, or unplanned shutdown, or when they want to recover sessions that weren't properly closed.
instructions: |-
  Find all Claude Code sessions that ended without an explicit "exit" command and launch each one
  in a new Windows Terminal tab for resumption. Skip sessions that are currently open.

  ## Step 1 — Find currently active sessions

  Write and run a Python script (`.tmp/find_active_sessions.py`) that uses `psutil` to enumerate
  `claude.exe` processes and resolve each one's session ID:

  ```python
  import psutil, re, json

  SESSION_RE = re.compile(r"--(?:resume|session-id)\s+([0-9a-fA-F-]{36})")
  active_ids = set()

  for proc in psutil.process_iter(["pid", "name", "cmdline"]):
      if (proc.info["name"] or "").lower() != "claude.exe":
          continue
      cmdline_str = " ".join(proc.info["cmdline"] or [])
      m = SESSION_RE.search(cmdline_str)
      if m:
          active_ids.add(m.group(1))
          continue
      # Bare launches (no --resume/--session-id on the command line) still set
      # CLAUDE_CODE_SESSION_ID in their environment — read it directly so these
      # aren't missed and later double-launched.
      try:
          env = proc.environ()
          sid = env.get("CLAUDE_CODE_SESSION_ID")
          if sid:
              active_ids.add(sid)
      except (psutil.AccessDenied, psutil.NoSuchProcess):
          pass

  print(json.dumps(sorted(active_ids)))
  ```

  This closes the gap the command-line regex alone has: a session started without an explicit
  `--resume`/`--session-id` flag (e.g. a fresh `claude` launch) has no ID in its command line, but
  its environment always carries `CLAUDE_CODE_SESSION_ID`.

  ## Step 2 — Read the live-session registry (authoritative source)

  This plugin's `SessionStart`/`SessionEnd` hooks maintain
  `~/.claude/session-mgr/live-sessions.json` — a dict of `{session_id: {cwd, started_at}}` for
  every session that has started but not cleanly ended. A hard crash or forced restart never
  triggers `SessionEnd`, so any entry left in this file whose ID is *not* in the Step 1 active set
  is a **confirmed** interrupted session — no content heuristics needed to decide whether to
  include it.

  ```python
  import json, os

  registry_path = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")
  registry = {}
  if os.path.exists(registry_path):
      with open(registry_path, encoding="utf-8") as f:
          registry = json.load(f)

  confirmed = {sid: info for sid, info in registry.items() if sid not in active_ids}
  ```

  Sessions found this way go straight to the launch list (Step 4) — pull `title` and
  `last_user_text` for the confirmation message by reading the tail of that session's transcript
  the same way Step 3 does, but do not apply any of Step 3's `last_user_text` exclusion rules to
  them; the registry already proved they were still open.

  ### The one check that DOES apply to registry entries: the self-close tail check

  A session that ends itself by force-killing its own tab dies before the harness can fire
  `SessionEnd`, so its registry entry survives even though the close was deliberate.
  The proper self-close primitive (`scripts/end-session.py`, next to the launcher) fires the
  SessionEnd hooks first and can't leave this residue, but entries written before a session's
  tooling adopted it — or by any independently-authored force-kill — still can.
  So before launching a registry-confirmed session, scan its last ~30 transcript entries: a
  `taskkill /PID <pid> /T /F`, or a `close-session.py` / `end-session.py` invocation, among the
  session's final actions means it closed itself on purpose.
  Do not launch it, and delete its entry from `live-sessions.json` so later scans don't
  re-litigate it.
  (Resuming such a session is worse than a false positive: it re-registers on `SessionStart`,
  and if it force-kills itself again the stale entry reappears on every future run.)

  Registry entries are self-healing: resuming a session re-fires `SessionStart` (re-adding it),
  and a later clean exit fires `SessionEnd` (removing it) — so nothing needs manual pruning.

  ## Step 3 — Fallback scan for sessions the registry doesn't cover

  The registry only covers sessions started after this hook was installed. For completeness (and
  as a safety net if a registry write ever fails), also run the content-heuristic scan below, then
  merge its results with Step 2's, de-duplicating by session ID.

  ```python
  import os, json
  from datetime import datetime

  PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
  already_found = confirmed.keys() | active_ids  # from Steps 1-2

  abrupt = []

  for project_dir in os.listdir(PROJECTS_DIR):
      full_project = os.path.join(PROJECTS_DIR, project_dir)
      if not os.path.isdir(full_project):
          continue

      for fname in os.listdir(full_project):
          if not fname.endswith(".jsonl"):
              continue
          session_id = fname.replace(".jsonl", "")
          if session_id in already_found:
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
  ```

  ### Exclusions — apply only these, and only in this fallback scan

  Exclude a session found by the fallback scan only if its last_user_text matches one of these
  exact machine-generated patterns — do NOT apply any other judgment about whether a session looks
  "complete" or "worth resuming":

  - Proper exit: last_user_text is exactly `<local-command-stdout>Goodbye!</local-command-stdout>`
    or `<local-command-stdout>Bye!</local-command-stdout>`
  - Automated triage prompt: last_user_text starts with `You are the drainer poller's triage step`
    (a self-contained classification job that completes and ends on its own — never a live
    conversation to resume)
  - Deliberate self-close: the transcript tail shows the session killing its own tab — the same
    self-close tail check Step 2 applies to registry entries (a `taskkill /PID <pid> /T /F` or a
    `close-session.py` / `end-session.py` invocation among its final actions)

  Do **not** exclude sessions whose last message is a `<task-notification>` block. A pending
  task-notification means a background action (a Monitor watch, a browser-chauffeur command, etc.)
  never reported back — that is itself evidence of an interrupted session, not a reason to skip it.
  This used to be an exclusion rule; it was wrong; e.g., a session mid-way through replying to a
  recruiter DM about a job posting had its background browser action killed by a restart, and got
  silently skipped because the notification looked machine-generated. A `<status>killed</status>`
  field inside the notification is an especially strong signal the restart is exactly what
  interrupted it. If the notification instead shows a passive timeout (e.g. "Monitor timed out —
  re-arm if needed") and you want extra confidence before launching a whole tab for it, it's fine
  to spot-check whether the underlying thing being watched (a PR, a deployment) is already resolved
  — but default to including it; do not silently drop it.

  Launch everything else — short replies, drainer seeds, mid-sentence messages, one-word answers,
  all of it. Do not guess whether the user considered a session finished.

  ## Step 4 — Launch each session in a new WT tab

  Merge Step 2 (registry-confirmed) and Step 3 (fallback, after exclusions) into one list,
  de-duplicated by session ID. For each session in that list, run:

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

  Tell the user how many sessions were opened and list the titles, noting how many came from the
  registry (confirmed) versus the fallback scan (heuristic). If any sessions were skipped because
  they were already open, mention that count too.

  ## Notes

  - `launch-session.ps1` lives inside this plugin at
    `~/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/skills/resume-sessions/scripts/launch-session.ps1`
    (the command above points there). Its `-Resume` flag runs `claude --resume <session_id>` in the
    correct working directory. The drainer plugin ships a thin resolver of its own that finds the
    newest *installed* copy of this launcher, so drainer workers aren't tied to a working-clone branch.
  - `claude --resume <session_id>` resumes an existing session by its UUID, picking up the full
    conversation history.
  - There are ~1,300 JSONL session files total; the fallback scan reads all of them but only the
    tail of each (last user message), so it completes in a few seconds.
  - The live-session registry (`hooks/session_registry.py`, wired in `hooks/hooks.json`) is what
    makes Step 2 authoritative instead of another heuristic. It only reflects sessions started
    since the hook was installed — plan on the fallback scan doing more of the work until the
    registry has enough history built up.
  - `scripts/end-session.py` (next to the launcher) is the correct way for a session to close its
    own tab: it fires this plugin's SessionEnd hooks with the same payload the harness would send,
    then taskkills the hosting process tree. Anything that instructs a session to self-close
    should route through it (the drainer forwards via its own thin resolver,
    `close-session.py`) — a raw `taskkill` of the host PID skips SessionEnd and strands a
    registry entry.
---
