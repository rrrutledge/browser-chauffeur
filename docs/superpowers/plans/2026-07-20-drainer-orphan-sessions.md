# Drainer Orphan-Sessions Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make crash-orphaned Claude Code sessions a drainer source that auto-resumes them, highest priority, under the drainer's existing `target_open_tabs` cap.

**Architecture:** A new shared script `find-orphans.py` in `session-mgr` (which already owns the live-session registry, the launch/close primitives, and the manual `resume-sessions` skill) does registry-only crash detection. A thin `orphan-sessions-adapter.py` in `drainer` shells out to it, following the same version-pinned resolver pattern `close-session.py` already uses to reach `session-mgr`. `run-poller.py` gets a deterministic pre-triage bypass (like the existing `trello` one), a new `spawn_resume_tab()` dispatch path (uses `launch-session.ps1 -Resume`, unlike every other source's fresh-worker `spawn_worker()`), and an explicit priority split so orphan items dispatch before the rest of the needs-you queue every cycle.

**Tech Stack:** Python 3 (stdlib + `psutil`), PowerShell 5.1, Windows Terminal (`wt.exe`), batch (`.cmd`).

## Global Constraints

- Windows-only: PowerShell 5.1 syntax, `.cmd` batch launchers, `wt.exe` — matches every other file touched.
- Python stdlib + `psutil` only, no PyYAML — matches `run-poller.py`'s existing constraint.
- No new `.claude/drainer.local.md` config knobs — `orphan-sessions` is enabled the same way any other provider is, just an entry under `providers:`.
- Registry-only crash detection in the shared script — no fallback full-transcript scan; that stays exclusive to the manual `resume-sessions` skill.
- No pytest — this repo's Python tests are hand-rolled runners (`check()` + `PASS`/`FAIL` print, `sys.exit(1)` on failure), run directly via `python <test file>`. Follow `plugins/session-mgr/tests/test_end_session.py`'s exact style; do not introduce pytest for these new tests.
- Version bumps are minor, not patch (new features, not fixes), per this repo's `CLAUDE.md`: `session-mgr` `1.4.0` → `1.5.0`, `drainer` `1.41.0` → `1.42.0`.
- Spec: `docs/superpowers/specs/2026-07-20-drainer-orphan-sessions-design.md` (already committed on this branch) — read it before starting if anything below is unclear on the *why*.

---

## File Structure

**session-mgr plugin:**
- Create: `plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py` — the shared detection script.
- Create: `plugins/session-mgr/tests/test_find_orphans.py` — its test.
- Modify: `plugins/session-mgr/skills/resume-sessions/SKILL.md` — Steps 1-2 call the shared script instead of inline snippets.
- Modify: `plugins/session-mgr/.claude-plugin/plugin.json` — version bump.

**drainer plugin:**
- Create: `plugins/drainer/skills/drainer/providers/orphan-sessions-adapter.py` — thin `ProviderBase` wrapper.
- Create: `plugins/drainer/skills/drainer/providers/orphan-sessions-provider.md` — worker-facing prose (mostly N/A sections, documented as such).
- Create: `plugins/drainer/tests/test_orphan_sessions_adapter.py` — adapter test (new `tests/` dir for this plugin, following the pattern already established in `session-mgr`/`safe-compounds`).
- Create: `plugins/drainer/skills/drainer/scripts/spawn-resume-tab.cmd` — sibling of `spawn-tab.cmd`, resume mode.
- Modify: `plugins/drainer/skills/drainer/scripts/run-poller.py` — pre-triage bypass, `spawn_resume_tab()`, priority split, dry-run output.
- Modify: `plugins/drainer/skills/drainer/templates/drainer.local.example.md` — document the new provider entry.
- Modify: `plugins/drainer/.claude-plugin/plugin.json` — version bump.

---

### Task 1: `find-orphans.py` — shared crash-detection script (session-mgr)

**Files:**
- Create: `plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py`
- Test: `plugins/session-mgr/tests/test_find_orphans.py`

**Interfaces:**
- Produces: `active_session_ids() -> set[str]`, `load_registry() -> dict`, `save_registry(dict) -> None`, `transcript_path(session_id: str) -> str | None`, `closed_itself_on_purpose(session_id: str) -> bool`, `find_confirmed_orphans() -> list[dict]` (each dict: `{"session_id", "cwd", "started_at"}`). Run as a script, prints that list as JSON to stdout. Consumed by Task 3's adapter (via subprocess) and Task 2's rewritten SKILL.md.

- [ ] **Step 1: Write the failing test**

Create `plugins/session-mgr/tests/test_find_orphans.py`:

```python
"""Test for scripts/find-orphans.py.

Runs against the real ~/.claude/session-mgr/live-sessions.json using unique throwaway
session ids (seeded and removed within each test, cleaned up on failure).
Run directly: python plugins/session-mgr/tests/test_find_orphans.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
FIND_ORPHANS = os.path.join(PLUGIN_ROOT, "skills", "resume-sessions", "scripts", "find-orphans.py")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

spec = importlib.util.spec_from_file_location("find_orphans", FIND_ORPHANS)
find_orphans = importlib.util.module_from_spec(spec)
spec.loader.exec_module(find_orphans)

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def seed_registry_entry(session_id, cwd="C:/fake/repo"):
    registry = find_orphans.load_registry()
    registry[session_id] = {"cwd": cwd, "started_at": "2026-07-20T00:00:00"}
    find_orphans.save_registry(registry)


def remove_registry_entry(session_id):
    registry = find_orphans.load_registry()
    registry.pop(session_id, None)
    find_orphans.save_registry(registry)


def test_confirmed_orphan_returned():
    print("test: a registry entry with no matching live process is returned as an orphan")
    session_id = f"test-find-orphans-{uuid.uuid4()}"
    seed_registry_entry(session_id)
    orig_active = find_orphans.active_session_ids
    find_orphans.active_session_ids = lambda: set()  # nothing running
    try:
        orphans = find_orphans.find_confirmed_orphans()
        ids = {o["session_id"] for o in orphans}
        check("orphan present", session_id in ids, f"got {ids}")
        match = next((o for o in orphans if o["session_id"] == session_id), None)
        check("cwd carried through", bool(match) and match["cwd"] == "C:/fake/repo")
    finally:
        find_orphans.active_session_ids = orig_active
        remove_registry_entry(session_id)


def test_live_process_excluded():
    print("test: a registry entry whose session IS currently running is excluded")
    session_id = f"test-find-orphans-{uuid.uuid4()}"
    seed_registry_entry(session_id)
    orig_active = find_orphans.active_session_ids
    find_orphans.active_session_ids = lambda: {session_id}  # pretend it's running
    try:
        orphans = find_orphans.find_confirmed_orphans()
        ids = {o["session_id"] for o in orphans}
        check("not returned", session_id not in ids, f"got {ids}")
    finally:
        find_orphans.active_session_ids = orig_active
        remove_registry_entry(session_id)


def test_self_closed_tail_excluded_and_pruned():
    print("test: a session whose transcript tail shows a deliberate self-close is excluded and pruned")
    session_id = f"test-find-orphans-{uuid.uuid4()}"
    seed_registry_entry(session_id)
    project_dir = os.path.join(PROJECTS_DIR, f"test-find-orphans-{uuid.uuid4()}")
    os.makedirs(project_dir, exist_ok=True)
    transcript = os.path.join(project_dir, f"{session_id}.jsonl")
    with open(transcript, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "text": "running close-session.py now"}) + "\n")
    orig_active = find_orphans.active_session_ids
    find_orphans.active_session_ids = lambda: set()
    try:
        orphans = find_orphans.find_confirmed_orphans()
        ids = {o["session_id"] for o in orphans}
        check("excluded from results", session_id not in ids, f"got {ids}")
        registry = find_orphans.load_registry()
        check("pruned from registry", session_id not in registry)
    finally:
        find_orphans.active_session_ids = orig_active
        remove_registry_entry(session_id)
        os.remove(transcript)
        os.rmdir(project_dir)


def test_cli_prints_json():
    print("test: run as a script prints a JSON array to stdout")
    result = subprocess.run([sys.executable, FIND_ORPHANS], capture_output=True, text=True)
    check("exit code 0", result.returncode == 0, f"got {result.returncode}: {result.stderr}")
    try:
        parsed = json.loads(result.stdout)
        check("stdout is a JSON list", isinstance(parsed, list), result.stdout[:200])
    except json.JSONDecodeError:
        check("stdout is valid JSON", False, result.stdout[:200])


if __name__ == "__main__":
    test_confirmed_orphan_returned()
    test_live_process_excluded()
    test_self_closed_tail_excluded_and_pruned()
    test_cli_prints_json()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        sys.exit(1)
    print("all tests passed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python plugins/session-mgr/tests/test_find_orphans.py`
Expected: crashes immediately at the `importlib` load (top of the file) with `FileNotFoundError` or similar, because `find-orphans.py` doesn't exist yet.

- [ ] **Step 3: Write `find-orphans.py`**

Create `plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py`:

```python
"""find-orphans.py — the registry-confirmed half of crash-recovery detection.

Locates Claude Code sessions that started (SessionStart fired) but never cleanly ended
(no SessionEnd) and aren't currently running. Registry-only: this does NOT run the
resume-sessions skill's fallback scan (every session transcript's tail) — that stays
exclusive to the interactive skill, which calls it as a separate step. This script is
deliberately fast enough to run every drainer poll cycle (a few seconds' work, mostly the
psutil process scan).

Run directly, prints JSON to stdout:
    python find-orphans.py
    [{"session_id": "...", "cwd": "...", "started_at": "2026-07-20T13:04:11.123456"}, ...]

Shared by two callers:
  - the resume-sessions skill (its Step 1, in place of the snippets it used to author fresh
    into .tmp/ each run)
  - the drainer's orphan-sessions-adapter.py, via subprocess, resolved to the newest
    installed copy of this plugin (see that adapter's _find_orphans_script())
"""
import glob
import json
import os
import re
import sys

import psutil

REGISTRY_PATH = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SESSION_RE = re.compile(r"--(?:resume|session-id)\s+([0-9a-fA-F-]{36})")
SELF_CLOSE_RE = re.compile(r"taskkill\s+/PID\s+\S+\s+/T\s+/F|close-session\.py|end-session\.py")


def active_session_ids():
    """Session IDs of every currently-running `claude.exe` process: from its command line
    (--resume/--session-id) or, for a bare launch with neither flag, its own
    CLAUDE_CODE_SESSION_ID environment variable."""
    ids = set()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if (proc.info["name"] or "").lower() != "claude.exe":
            continue
        cmdline_str = " ".join(proc.info["cmdline"] or [])
        m = SESSION_RE.search(cmdline_str)
        if m:
            ids.add(m.group(1))
            continue
        try:
            env = proc.environ()
            sid = env.get("CLAUDE_CODE_SESSION_ID")
            if sid:
                ids.add(sid)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return ids


def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_registry(registry):
    tmp = REGISTRY_PATH + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    os.replace(tmp, REGISTRY_PATH)


def transcript_path(session_id):
    """The session's own .jsonl transcript, wherever it lives under ~/.claude/projects/ (one
    subfolder per project). None if it can't be found."""
    matches = glob.glob(os.path.join(PROJECTS_DIR, "*", f"{session_id}.jsonl"))
    return matches[0] if matches else None


def closed_itself_on_purpose(session_id):
    """True if the session's last ~30 transcript lines show it deliberately closing its own
    tab (a taskkill /T /F, or a close-session.py / end-session.py invocation) — such a
    session dies before SessionEnd can fire, so its registry entry survives even though the
    close was intentional. Missing/unreadable transcript -> False: fail toward including a
    session as an orphan, never toward silently dropping a real one."""
    path = transcript_path(session_id)
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False
    tail = "\n".join(lines[-30:])
    return bool(SELF_CLOSE_RE.search(tail))


def find_confirmed_orphans():
    """Registry entries whose session isn't currently running, minus any that closed
    themselves on purpose. Self-closed entries are pruned from the registry in place (not
    just excluded from the return value) so a later run doesn't re-litigate them — same
    behavior the resume-sessions skill has always documented for this check. Pruning isn't
    wrapped in the retry-on-write-race loop session_registry.py's hook uses: a missed prune
    just means the same (harmless) exclusion happens again next run, never a lost orphan."""
    active = active_session_ids()
    registry = load_registry()
    orphans = []
    to_prune = []
    for session_id, info in registry.items():
        if session_id in active:
            continue
        if closed_itself_on_purpose(session_id):
            to_prune.append(session_id)
            continue
        orphans.append({
            "session_id": session_id,
            "cwd": info.get("cwd"),
            "started_at": info.get("started_at"),
        })
    if to_prune:
        registry = load_registry()
        for sid in to_prune:
            registry.pop(sid, None)
        save_registry(registry)
    return orphans


def main():
    print(json.dumps(find_confirmed_orphans()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python plugins/session-mgr/tests/test_find_orphans.py`
Expected: `all tests passed`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py plugins/session-mgr/tests/test_find_orphans.py
git commit -m "feat(session-mgr): add find-orphans.py, shared crash-detection script"
```

---

### Task 2: Rewire `resume-sessions` SKILL.md to call the shared script

**Files:**
- Modify: `plugins/session-mgr/skills/resume-sessions/SKILL.md`

**Interfaces:**
- Consumes: Task 1's `find-orphans.py` (path, `active_session_ids()`).
- Produces: nothing new — this task only removes duplication in the skill's own prose.

The skill's steps are inside a YAML literal block scalar (`instructions: |-` in the frontmatter), 2-space-indented throughout. Read the file first, then apply the following edits exactly (preserve the 2-space indentation on every replaced line).

- [ ] **Step 1: Replace old Steps 1+2 with the new merged Step 1**

Find this exact block (old Steps 1 and 2, including the closing "Registry entries are self-healing" paragraph, right before "## Step 3"):

```
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

```

Replace it with:

```
  ## Step 1 — Find confirmed orphans (shared script)

  Run the shared detection script instead of hand-authoring the scan:

  ```bash
  python "$HOME/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py"
  ```

  It does what this step used to do by hand, in two parts:
  1. Scans running `claude.exe` processes for their session ID — from `--resume`/
     `--session-id` on the command line, or (for a bare launch with neither flag)
     `CLAUDE_CODE_SESSION_ID` in the process's own environment.
  2. Reads the live-session registry (`~/.claude/session-mgr/live-sessions.json` — a dict of
     `{session_id: {cwd, started_at}}` for every session that has started but not cleanly
     ended, maintained by this plugin's `SessionStart`/`SessionEnd` hooks) and returns every
     entry whose session isn't in the active set from part 1. A hard crash or forced restart
     never triggers `SessionEnd`, so any such entry is a **confirmed** interrupted session —
     no content heuristics needed to decide whether to include it.

  It also applies the self-close tail check before returning anything: a session that ends
  itself by force-killing its own tab dies before the harness can fire `SessionEnd`, so its
  registry entry survives even though the close was deliberate. The proper self-close
  primitive (`scripts/end-session.py`, next to the launcher) fires the SessionEnd hooks first
  and can't leave this residue, but entries written before a session's tooling adopted it —
  or by any independently-authored force-kill — still can. The script scans each candidate's
  last ~30 transcript entries for a `taskkill /PID <pid> /T /F`, or a `close-session.py` /
  `end-session.py` invocation, among the session's final actions; a match means it closed
  itself on purpose, so the script excludes it from the output AND deletes its entry from
  `live-sessions.json` (so a later run doesn't re-litigate it) — you don't need to re-check
  this by hand.

  Prints a JSON array to stdout: `[{"session_id", "cwd", "started_at"}, ...]`. Everything in
  this list is confirmed — go straight to the launch list (Step 3) for these; do not apply
  Step 2's `last_user_text` exclusion rules to them (those are for the fallback scan only,
  next section) — the registry already proved they were still open.

  Registry entries are self-healing: resuming a session re-fires `SessionStart` (re-adding
  it), and a later clean exit fires `SessionEnd` (removing it) — so nothing needs manual
  pruning beyond what the script already does for self-closed sessions.

```

- [ ] **Step 2: Renumber the fallback scan to Step 2 and reuse the shared `active_session_ids()`**

Find:

```
  ## Step 3 — Fallback scan for sessions the registry doesn't cover

  The registry only covers sessions started after this hook was installed. For completeness (and
  as a safety net if a registry write ever fails), also run the content-heuristic scan below, then
  merge its results with Step 2's, de-duplicating by session ID.

  ```python
  import os, json
  from datetime import datetime

  PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
  already_found = confirmed.keys() | active_ids  # from Steps 1-2
```

Replace with:

```
  ## Step 2 — Fallback scan for sessions the registry doesn't cover

  The registry only covers sessions started after this hook was installed. For completeness (and
  as a safety net if a registry write ever fails), also run the content-heuristic scan below, then
  merge its results with Step 1's, de-duplicating by session ID.

  ```python
  import importlib.util
  import os, json
  from datetime import datetime

  PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
  # Reuse Step 1's script for the active-process scan rather than re-implementing it —
  # step1_orphans is the JSON list Step 1's `python find-orphans.py` call printed.
  spec = importlib.util.spec_from_file_location(
      "find_orphans",
      os.path.expanduser("~/Dev/rrrutledge/rrrutledge-claude-code-plugins/plugins/session-mgr/"
                          "skills/resume-sessions/scripts/find-orphans.py"))
  find_orphans = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(find_orphans)
  active_ids = find_orphans.active_session_ids()
  confirmed_ids = {o["session_id"] for o in step1_orphans}
  already_found = confirmed_ids | active_ids  # from Step 1
```

- [ ] **Step 3: Fix the exclusions section's cross-reference to the old Step 2**

Find:

```
  - Deliberate self-close: the transcript tail shows the session killing its own tab — the same
    self-close tail check Step 2 applies to registry entries (a `taskkill /PID <pid> /T /F` or a
    `close-session.py` / `end-session.py` invocation among its final actions)
```

Replace with:

```
  - Deliberate self-close: the transcript tail shows the session killing its own tab — the same
    self-close tail check Step 1's find-orphans.py applies to registry entries (a
    `taskkill /PID <pid> /T /F` or a `close-session.py` / `end-session.py` invocation among its
    final actions)
```

- [ ] **Step 4: Renumber the launch step and fix its merge instruction**

Find:

```
  ## Step 4 — Launch each session in a new WT tab

  Merge Step 2 (registry-confirmed) and Step 3 (fallback, after exclusions) into one list,
  de-duplicated by session ID. For each session in that list, run:
```

Replace with:

```
  ## Step 3 — Launch each session in a new WT tab

  Merge Step 1 (registry-confirmed) and Step 2 (fallback, after exclusions) into one list,
  de-duplicated by session ID. For each session in that list, run:
```

- [ ] **Step 5: Renumber the confirm step**

Find:

```
  ## Step 5 — Confirm
```

Replace with:

```
  ## Step 4 — Confirm
```

- [ ] **Step 6: Fix the Notes section's reference to the old Step 2**

Find:

```
  - The live-session registry (`hooks/session_registry.py`, wired in `hooks/hooks.json`) is what
    makes Step 2 authoritative instead of another heuristic. It only reflects sessions started
    since the hook was installed — plan on the fallback scan doing more of the work until the
    registry has enough history built up.
```

Replace with:

```
  - The live-session registry (`hooks/session_registry.py`, wired in `hooks/hooks.json`) is what
    makes Step 1's find-orphans.py authoritative instead of another heuristic. It only reflects
    sessions started since the hook was installed — plan on the fallback scan doing more of the
    work until the registry has enough history built up.
```

- [ ] **Step 7: Verify the doc is internally consistent**

Read the whole file back. Confirm: exactly 4 steps (`## Step 1` through `## Step 4`), no remaining reference to a "Step 5", and the only mention of `.tmp/find_active_sessions.py` (the old hand-authored path) is gone.

- [ ] **Step 8: Commit**

```bash
git add plugins/session-mgr/skills/resume-sessions/SKILL.md
git commit -m "docs(session-mgr): resume-sessions calls the shared find-orphans.py"
```

---

### Task 3: `orphan-sessions` drainer provider (adapter + prose + test)

**Files:**
- Create: `plugins/drainer/skills/drainer/providers/orphan-sessions-adapter.py`
- Create: `plugins/drainer/skills/drainer/providers/orphan-sessions-provider.md`
- Create: `plugins/drainer/tests/test_orphan_sessions_adapter.py`

**Interfaces:**
- Consumes: Task 1's `find-orphans.py` (subprocess, JSON stdout), `provider_base.ProviderBase` / `ProviderError` / `slug` (from `plugins/drainer/skills/drainer/scripts/provider_base.py`, already in the repo).
- Produces: `Provider` class (`name = "orphan-sessions"`) with `enumerate(limit)`, `stable_id(item)`, `capture(item, iid, runtime_dir)` — consumed by Task 4's `run-poller.py` changes. Captured item fields Task 4 relies on: `item["session_id"]`, `item["cwd"]`, `item["started_at"]`, `item["received"]`.

- [ ] **Step 1: Write the failing test**

Create `plugins/drainer/tests/test_orphan_sessions_adapter.py`:

```python
"""Test for providers/orphan-sessions-adapter.py's resolver + find-orphans.py integration.

Runs against the real ~/.claude/session-mgr/live-sessions.json using a unique throwaway
session id (seeded and removed within the test). Run directly:
    python plugins/drainer/tests/test_orphan_sessions_adapter.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
ADAPTER = os.path.join(PLUGIN_ROOT, "skills", "drainer", "providers", "orphan-sessions-adapter.py")
REGISTRY_HOOK = os.path.abspath(os.path.join(
    PLUGIN_ROOT, "..", "session-mgr", "hooks", "session_registry.py"))
REGISTRY_PATH = os.path.expanduser("~/.claude/session-mgr/live-sessions.json")

spec = importlib.util.spec_from_file_location("orphan_sessions_adapter", ADAPTER)
adapter_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter_mod)

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def fire_event(event, session_id, cwd="C:/fake/repo"):
    payload = json.dumps({"hook_event_name": event, "session_id": session_id, "cwd": cwd})
    subprocess.run([sys.executable, REGISTRY_HOOK], input=payload, text=True, check=True)


def registry_has(session_id):
    if not os.path.exists(REGISTRY_PATH):
        return False
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return session_id in json.load(f)


def test_resolver_finds_find_orphans():
    print("test: adapter resolver locates a real find-orphans.py")
    script = adapter_mod._find_orphans_script()
    check("path exists", os.path.isfile(script), script)
    check("correct filename", os.path.basename(script) == "find-orphans.py", script)


def test_enumerate_returns_seeded_orphan():
    print("test: enumerate() surfaces a seeded registry entry via the real find-orphans.py")
    session_id = f"test-adapter-{uuid.uuid4()}"
    fire_event("SessionStart", session_id, cwd="C:/fake/repo/adapter-test")
    try:
        provider = adapter_mod.Provider()
        items = provider.enumerate(50)
        ids = {it["session_id"] for it in items}
        check("seeded orphan present", session_id in ids, f"got {len(items)} items")
        match = next((it for it in items if it["session_id"] == session_id), None)
        check("cwd carried through", bool(match) and match["cwd"] == "C:/fake/repo/adapter-test")
        check("stable_id is deterministic",
              bool(match) and provider.stable_id(match) == provider.stable_id(match))
    finally:
        if registry_has(session_id):
            fire_event("SessionEnd", session_id)


def test_capture_writes_json():
    print("test: capture() writes items/<id>.json with the documented shape")
    provider = adapter_mod.Provider()
    item = {"session_id": "abc-123", "cwd": "C:/fake/repo", "started_at": "2026-07-20T00:00:00",
            "_bucket": "needs-you", "_kind": "resume"}
    iid = provider.stable_id(item)
    with tempfile.TemporaryDirectory() as runtime_dir:
        json_file = provider.capture(item, iid, runtime_dir)
        check("file created", os.path.isfile(json_file))
        with open(json_file, encoding="utf-8") as f:
            record = json.load(f)
        check("source field", record.get("source") == "orphan-sessions")
        check("session_id carried", record.get("session_id") == "abc-123")
        check("triage needs-you", record.get("triage") == "needs-you")


if __name__ == "__main__":
    test_resolver_finds_find_orphans()
    test_enumerate_returns_seeded_orphan()
    test_capture_writes_json()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        sys.exit(1)
    print("all tests passed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python plugins/drainer/tests/test_orphan_sessions_adapter.py`
Expected: crashes at the `importlib` load, `FileNotFoundError` — the adapter doesn't exist yet.

- [ ] **Step 3: Write the adapter**

Create `plugins/drainer/skills/drainer/providers/orphan-sessions-adapter.py`:

```python
"""orphan-sessions poller adapter — crash-recovered Claude Code sessions, highest priority.

A thin ProviderBase wrapper, same shape as every other drainer provider, but around
something session-mgr already owns rather than an external service: the live-session
registry, the SessionStart/SessionEnd hooks that maintain it, and the crash-detection logic
in find-orphans.py. This adapter locates and shells out to the newest INSTALLED session-mgr
plugin's find-orphans.py (the same version-pinned resolver pattern the drainer's
close-session.py already uses to reach session-mgr's end-session.py) rather than
re-implementing any registry/liveness logic here.

Unlike every other source, this one has no draft/reply/CLEAR cycle — resuming a session's
own tab IS the whole action. See orphan-sessions-provider.md for the (empty) worker-facing
contract, and run-poller.py for the dedicated spawn_resume_tab() dispatch path and the
deterministic pre-triage bypass (this source never reaches the AI triage call).

id scheme: `orphan-<session_id>-<slug(started_at)>` — see stable_id() for why started_at
(not just session_id) is baked into the id. No body file — capture() writes only
`<id>.json`.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, slug  # noqa: E402

_REL_FIND_ORPHANS = os.path.join("skills", "resume-sessions", "scripts", "find-orphans.py")


def _parse_version(name):
    try:
        return tuple(int(p) for p in name.split("."))
    except ValueError:
        return (0, 0, 0)


def _find_orphans_script():
    """Locate the newest INSTALLED session-mgr plugin's find-orphans.py — same version-sort
    resolver pattern as the drainer's close-session.py, so this adapter is never tied to a
    floating working-clone branch of session-mgr. Falls back to the working-clone path when
    no installed copy exists yet (a fresh dev machine)."""
    base = os.path.expanduser(os.path.join(
        "~", ".claude", "plugins", "cache", "rrrutledge-claude-code-plugins", "session-mgr"))
    if os.path.isdir(base):
        for version in sorted(os.listdir(base), key=_parse_version, reverse=True):
            candidate = os.path.join(base, version, _REL_FIND_ORPHANS)
            if os.path.isfile(candidate):
                return candidate
    # From plugins/drainer/skills/drainer/providers up to plugins/, then into session-mgr.
    fallback = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
        "session-mgr", _REL_FIND_ORPHANS))
    if os.path.isfile(fallback):
        return fallback
    raise ProviderError(
        "Could not locate session-mgr's find-orphans.py (no installed copy and no "
        "working-clone fallback).", kind="config")


class Provider(ProviderBase):
    name = "orphan-sessions"

    def enumerate(self, limit):
        script = _find_orphans_script()
        try:
            result = subprocess.run(
                [sys.executable, script], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ProviderError(f"orphan-sessions: failed running find-orphans.py: {e}",
                                kind="auth")
        if result.returncode != 0:
            raise ProviderError(
                f"orphan-sessions: find-orphans.py exited {result.returncode}: "
                f"{result.stderr.strip()[:300]}", kind="auth")
        try:
            orphans = json.loads(result.stdout or "[]")
        except ValueError as e:
            raise ProviderError(f"orphan-sessions: find-orphans.py returned invalid JSON: {e}",
                                kind="auth")
        items = []
        for o in orphans[:limit]:
            items.append({
                "session_id": o.get("session_id"),
                "cwd": o.get("cwd"),
                "started_at": o.get("started_at"),
                # Orders MULTIPLE simultaneous orphans against each other (newest crash
                # first) within run-poller.py's dedicated orphan-dispatch pass —
                # cross-source priority is enforced structurally there (orphans dispatch
                # before the rest of needs-you), not by this timestamp.
                "received": o.get("started_at") or "",
            })
        return items

    def stable_id(self, item):
        # Baking started_at into the id (not just session_id) means a session already
        # auto-resumed once, that later crashes AGAIN, gets a fresh id on its second crash —
        # SessionStart re-fires on resume, advancing started_at — so it resurfaces as a new
        # item instead of staying permanently seen after the first resume. Same idiom the
        # trello adapter uses baking a card's go-live date into its id.
        stamp = slug(item.get("started_at"), 32) or "unknown"
        return f"{self.name}-{item.get('session_id')}-{stamp}"

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        record = {
            "id": iid,
            "source": self.name,
            "triage": item.get("_bucket", "needs-you"),
            "kind": item.get("_kind", "resume"),
            "session_id": item.get("session_id"),
            "cwd": item.get("cwd"),
            "started_at": item.get("started_at"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
```

- [ ] **Step 4: Write the provider prose**

Create `plugins/drainer/skills/drainer/providers/orphan-sessions-provider.md`:

```markdown
# orphan-sessions provider — crash-recovered Claude Code sessions (highest priority)

A provider for sessions the live-session registry confirms were interrupted by a crash or
forced restart (never fired `SessionEnd`) and aren't currently running. Implements
`../engine/provider.md`'s adapter contract; classify by `../engine/triage.md` — though in
practice this source skips AI triage entirely (see below). id prefix: `orphan-`.

## Not like the other sources: no worker, no CLEAR, no draft
Every other provider's needs-you item opens a **fresh** worker tab that reads
`../engine/worker-core.md` and drafts a reply. This source is different: resuming the
session (via `run-poller.py`'s dedicated `spawn_resume_tab()`, using `launch-session.ps1
-Resume <session_id>` in the session's own original `cwd`) IS the entire action. Russell
continues in his own resumed conversation from there — there is nothing for a worker to
read, act on, or clear, because the "item" isn't a message waiting for a reply, it's
Russell's own interrupted work. Because of this, the sections below that a normal
provider's worker would use are N/A rather than omitted (per `../engine/provider.md`'s "MUST
define" contract) — the sections still exist so it's clear they were considered, not
forgotten.

## AUTH-GLANCE
N/A — no external account to sign into. The registry
(`~/.claude/session-mgr/live-sessions.json`) and running-process scan this source reads are
local to the machine.

## Deterministic triage (not an AUTH-GLANCE-adjacent judgment call)
Every enumerated item is unconditionally `needs-you` — an orphaned session unconditionally
needs resuming, no judgment involved. `run-poller.py`'s pre-triage block stamps
`_bucket="needs-you"`, `_kind="resume"`, `_complexity="simple"` for every `orphan-sessions`
item before the AI triage call, the same tautology-bypass the `trello` adapter gets for its
always-needs-you due cards, so this source never reaches the AI triage call at all.

## CAPTURE (needs-you)
`items/<id>.json`: `{"id","source":"orphan-sessions","triage":"needs-you","kind":"resume",`
`"session_id","cwd","started_at","ts":"<ISO now>"}`. No body file — there's nothing to
display beyond the session's own `cwd` and crash time; the resumed session carries its own
full history once reopened.

## CLEAR
N/A — there is no source-side state to advance or mark read. Dispatch (successfully
launching the resume tab) is recorded as seen the same fail-safe-after-dispatch way every
other source's needs-you item is; there is no separate CLEAR step because there is no
separate source state pointing back at this item once the tab is open.

## JUNK-LEARNING
N/A — a crash-orphaned session is never junk; there's no inbound noise to teach a filter
against.

## DRAFT-MODE
N/A — this source never drafts anything. Resuming reopens Russell's own prior conversation;
whatever he does inside it (including any drafting) is that resumed session's own business,
unrelated to this provider.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python plugins/drainer/tests/test_orphan_sessions_adapter.py`
Expected: `all tests passed`, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add plugins/drainer/skills/drainer/providers/orphan-sessions-adapter.py plugins/drainer/skills/drainer/providers/orphan-sessions-provider.md plugins/drainer/tests/test_orphan_sessions_adapter.py
git commit -m "feat(drainer): add orphan-sessions provider adapter"
```

---

### Task 4: `run-poller.py` dispatch changes + `spawn-resume-tab.cmd` + example config

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/spawn-resume-tab.cmd`
- Modify: `plugins/drainer/skills/drainer/scripts/run-poller.py`
- Modify: `plugins/drainer/skills/drainer/templates/drainer.local.example.md`

**Interfaces:**
- Consumes: Task 3's `Provider` (`name = "orphan-sessions"`), captured item fields `session_id`/`cwd`.
- Produces: `spawn_resume_tab(session_id: str, cwd: str, repo: str) -> None` in `run-poller.py` — no other task depends on it; this is the final piece of the dispatch chain.

- [ ] **Step 1: Write `spawn-resume-tab.cmd`**

Create `plugins/drainer/skills/drainer/scripts/spawn-resume-tab.cmd`:

```batch
@echo off
REM spawn-resume-tab.cmd - open ONE Windows Terminal tab RESUMING an existing Claude session.
REM Called from run-poller.py via:  subprocess.Popen(["cmd","/c", spawn-resume-tab.cmd, TITLE, CWD, SESSIONID])
REM
REM   %1 TITLE      initial tab title (the resumed Claude session renames the tab itself once it starts)
REM   %2 CWD        the session's OWN original working directory (NOT the drainer's repo) —
REM                 launch-session.ps1's -Resume branch just runs `claude --resume <id>`, so the
REM                 process's starting directory is what determines where the resumed session lands.
REM   %3 SESSIONID  the session's guid to resume (launch-session.ps1 -Resume <SESSIONID>)
set "TITLE=%~1"
set "CWD=%~2"
set "SESSIONID=%~3"
set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
REM Resolver shipped NEXT TO this file in the installed plugin (%~dp0) — same pattern as
REM spawn-tab.cmd: never launched from whatever branch a dev clone happens to sit on.
set "LAUNCHER=%~dp0launch-session.ps1"
REM Same "-w drainer" window as every other drainer-spawned tab, deliberately — this is
REM unattended automation like any other drainer dispatch (not Russell invoking the manual
REM resume-sessions skill, which uses -w 0), and provider_base.spawn_tab's foreground-
REM preservation logic only works correctly when new tabs land in this known window.
REM No -Model: `claude --resume` restores the session's own prior model as part of resuming
REM state, so passing nothing is correct (matches the manual resume-sessions skill's own
REM invocation, which also passes no -Model).
"%WT%" -w drainer new-tab --title "%TITLE%" --startingDirectory "%CWD%" powershell -NoExit -File "%LAUNCHER%" -Resume "%SESSIONID%"
```

- [ ] **Step 2: Extend the deterministic pre-triage bypass in `run-poller.py`**

In `plugins/drainer/skills/drainer/scripts/run-poller.py`, find:

```python
    pre_triaged = []
    correctly_junked = []
    ai_triage = []
    for it in all_new:
        if it["_source"] == "trello":
            # The adapter only enumerates cards in play — due now-or-earlier, or with no due date at all.
            # A due card's moment has arrived ("the due date IS the queue"); an undated card is on the
            # board precisely because it needs a look — at minimum to give it a date — so it must not be
            # sidelined to the digest. Either way the answer is needs-you, so skip the AI call: it's a
            # tautology the model sometimes gets wrong (it mis-filed undated cards to fyi).
            it["_bucket"], it["_kind"] = "needs-you", "work"
            it["_complexity"] = "simple"
            pre_triaged.append(it)
        else:
            ai_triage.append(it)
```

Replace with:

```python
    pre_triaged = []
    correctly_junked = []
    ai_triage = []
    for it in all_new:
        if it["_source"] == "trello":
            # The adapter only enumerates cards in play — due now-or-earlier, or with no due date at all.
            # A due card's moment has arrived ("the due date IS the queue"); an undated card is on the
            # board precisely because it needs a look — at minimum to give it a date — so it must not be
            # sidelined to the digest. Either way the answer is needs-you, so skip the AI call: it's a
            # tautology the model sometimes gets wrong (it mis-filed undated cards to fyi).
            it["_bucket"], it["_kind"] = "needs-you", "work"
            it["_complexity"] = "simple"
            pre_triaged.append(it)
        elif it["_source"] == "orphan-sessions":
            # An orphaned session unconditionally needs resuming — no judgment to make, so
            # this skips the AI call the same way trello's due cards do.
            it["_bucket"], it["_kind"] = "needs-you", "resume"
            it["_complexity"] = "simple"
            pre_triaged.append(it)
        else:
            ai_triage.append(it)
```

- [ ] **Step 3: Add `spawn_resume_tab()` next to `spawn_worker()`**

In the same file, find:

```python
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    spawn_tab([spawn_cmd, _worker_title(iid, json_file), repo, prompt_file, worker_model, summary_file],
              cwd=repo)


# ---------------------------------------------------------------------------- the cycle
```

Replace with:

```python
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    spawn_tab([spawn_cmd, _worker_title(iid, json_file), repo, prompt_file, worker_model, summary_file],
              cwd=repo)


def spawn_resume_tab(session_id, cwd, repo):
    """Dispatch an orphan-sessions item: reopen an existing session via `claude --resume
    <session_id>`, in ITS OWN original `cwd` (not the drainer's repo) — unlike every other
    source, there's no prompt seed to write; the session already has its full history."""
    base = os.path.basename((cwd or "").rstrip("/\\")) or session_id[:8]
    title = f"Resume: {base}"
    title = re.sub(r'[&<>|%"^]', " ", title)
    title = re.sub(r"\s+", " ", title).strip()[:50] or f"resume:{session_id[:8]}"
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-resume-tab.cmd")
    spawn_tab([spawn_cmd, title, cwd or repo, session_id], cwd=repo)


# ---------------------------------------------------------------------------- the cycle
```

- [ ] **Step 4: Split the needs-you list so orphan-sessions dispatches first**

In the same file, find:

```python
    needs = sorted(
        (it for it in needs_and_others if it["_bucket"] == "needs-you"),
        key=lambda it: it.get("received") or "",
        reverse=True,
    )
```

Replace with:

```python
    needs_you_items = [it for it in needs_and_others if it["_bucket"] == "needs-you"]
    # orphan-sessions dispatches FIRST, ahead of every other source, explicitly — not via
    # received-timestamp tie-breaking (a coincidentally-recent Slack message could still
    # slot ahead of that). As tab slots free up cycle over cycle, they go to the
    # orphan-sessions backlog before any fresh Slack/Trello/mail item, until it's drained.
    orphan_needs = sorted(
        (it for it in needs_you_items if it["_source"] == "orphan-sessions"),
        key=lambda it: it.get("received") or "",
        reverse=True,
    )
    other_needs = sorted(
        (it for it in needs_you_items if it["_source"] != "orphan-sessions"),
        key=lambda it: it.get("received") or "",
        reverse=True,
    )
    needs = orphan_needs + other_needs
```

- [ ] **Step 5: Branch the live dispatch loop on source**

In the same file, find:

```python
    for it in needs:
        provider = prov[it["_source"]]
        iid = it["_id"]
        if live_tabs is not None and live_tabs >= cfg["target_open_tabs"]:
            held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
            continue
        model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        spawn_worker(iid, json_file, repo, cfg["runtime_dir"], model, cfg["local_dir"])
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "needs-you")
        if live_tabs is not None:
            live_tabs += 1
        dispatched += 1
```

Replace with:

```python
    for it in needs:
        provider = prov[it["_source"]]
        iid = it["_id"]
        if live_tabs is not None and live_tabs >= cfg["target_open_tabs"]:
            held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
            continue
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        if it["_source"] == "orphan-sessions":
            spawn_resume_tab(it["session_id"], it["cwd"], repo)
        else:
            model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
            spawn_worker(iid, json_file, repo, cfg["runtime_dir"], model, cfg["local_dir"])
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "needs-you")
        if live_tabs is not None:
            live_tabs += 1
        dispatched += 1
```

- [ ] **Step 6: Make the dry-run print loop handle orphan-sessions items**

In the same file, find:

```python
        print("  needs-you (newest-first globally):")
        tabs = live_tabs
        for it in needs:
            held = tabs is not None and tabs >= cfg["target_open_tabs"]
            if not held and tabs is not None:
                tabs += 1
            model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
            action = "HOLD (at cap)" if held else f"spawn worker [{it['_complexity']} -> {model}]"
            print(f"    [{it['_source']:20}] {it['_id']}  ->  {action}\n"
                  f"        {it.get('received')} | {it.get('from')} | {it.get('subject')}")
```

Replace with:

```python
        print("  needs-you (orphan-sessions first, then newest-first):")
        tabs = live_tabs
        for it in needs:
            held = tabs is not None and tabs >= cfg["target_open_tabs"]
            if not held and tabs is not None:
                tabs += 1
            if it["_source"] == "orphan-sessions":
                action = "HOLD (at cap)" if held else "spawn resume tab"
                print(f"    [{it['_source']:20}] {it['_id']}  ->  {action}\n"
                      f"        {it.get('received')} | cwd={it.get('cwd')} | session={it.get('session_id')}")
                continue
            model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
            action = "HOLD (at cap)" if held else f"spawn worker [{it['_complexity']} -> {model}]"
            print(f"    [{it['_source']:20}] {it['_id']}  ->  {action}\n"
                  f"        {it.get('received')} | {it.get('from')} | {it.get('subject')}")
```

- [ ] **Step 7: Document the provider in the example config**

In `plugins/drainer/skills/drainer/templates/drainer.local.example.md`, find:

```
providers:
  outlook: {}                    # work Outlook on the web (browser) — no config, just sign in
```

Replace with:

```
providers:
  orphan-sessions: {}         # crash-recovered Claude Code sessions (session-mgr) — no config; always dispatches first
  outlook: {}                    # work Outlook on the web (browser) — no config, just sign in
```

- [ ] **Step 8: Manual verification — dry-run against a seeded orphan**

This exercises the whole chain (Task 1 → Task 3 → this task) end to end without touching any real project's live `drainer.local.md`. Run each of these in order:

Create a scratch config (adjust the path if you'd rather use a different scratch directory):

```bash
mkdir -p /tmp/drainer-orphan-scratch/.claude
```

Write `/tmp/drainer-orphan-scratch/.claude/drainer.local.md`:

```
providers:
  orphan-sessions: {}
runtime_dir: .tmp/drainer
```

Seed a throwaway orphan (same technique the tests use):

```bash
python -c "import json,subprocess,sys,uuid; sid=f'test-dryrun-{uuid.uuid4()}'; print(sid); subprocess.run([sys.executable, 'plugins/session-mgr/hooks/session_registry.py'], input=json.dumps({'hook_event_name':'SessionStart','session_id':sid,'cwd':'C:/fake/scratch-repo'}), text=True, check=True)"
```

Note the printed `sid`, then run:

```bash
python plugins/drainer/skills/drainer/scripts/run-poller.py --repo /tmp/drainer-orphan-scratch --dry-run
```

Expected: output includes a line under `needs-you (orphan-sessions first, then newest-first):` showing `[orphan-sessions ...] orphan-<sid>-... -> spawn resume tab`, with `cwd=C:/fake/scratch-repo`.

Clean up the seeded entry (replace `<sid>` with the value printed above):

```bash
python -c "import json,subprocess,sys; subprocess.run([sys.executable, 'plugins/session-mgr/hooks/session_registry.py'], input=json.dumps({'hook_event_name':'SessionEnd','session_id':'<sid>'}), text=True, check=True)"
```

- [ ] **Step 9: Commit**

```bash
git add plugins/drainer/skills/drainer/scripts/spawn-resume-tab.cmd plugins/drainer/skills/drainer/scripts/run-poller.py plugins/drainer/skills/drainer/templates/drainer.local.example.md
git commit -m "feat(drainer): dispatch orphan-sessions items first, via -Resume"
```

---

### Task 5: Version bumps

**Files:**
- Modify: `plugins/session-mgr/.claude-plugin/plugin.json`
- Modify: `plugins/drainer/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing consumed by later tasks — this is the final task.

- [ ] **Step 1: Bump session-mgr's version**

In `plugins/session-mgr/.claude-plugin/plugin.json`, change:

```json
  "version": "1.4.0",
```

to:

```json
  "version": "1.5.0",
```

- [ ] **Step 2: Bump drainer's version**

In `plugins/drainer/.claude-plugin/plugin.json`, change:

```json
  "version": "1.41.0",
```

to:

```json
  "version": "1.42.0",
```

- [ ] **Step 3: Verify both files are still valid JSON**

Run: `python -c "import json; json.load(open('plugins/session-mgr/.claude-plugin/plugin.json')); json.load(open('plugins/drainer/.claude-plugin/plugin.json')); print('both valid')"`
Expected: `both valid`

- [ ] **Step 4: Commit**

```bash
git add plugins/session-mgr/.claude-plugin/plugin.json plugins/drainer/.claude-plugin/plugin.json
git commit -m "chore: minor version bump for session-mgr and drainer (new orphan-sessions feature)"
```
