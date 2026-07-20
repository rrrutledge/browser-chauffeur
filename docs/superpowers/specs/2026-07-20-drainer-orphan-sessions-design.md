# Drainer orphan-sessions source — design

## Problem

When Russell's machine crashes or restarts, every open Claude Code session that hadn't
cleanly exited is lost mid-work. `session-mgr`'s `resume-sessions` skill can find and
relaunch these (via the live-session registry plus a fallback transcript scan), but it's a
manual, on-demand tool — Russell has to remember to run it, and if he does, it dumps every
orphan back open at once with no regard for how many Claude Code tabs are already running.

That collided directly with the drainer: after a crash, the drainer's own `DrainerKeeper`
poller had already re-filled its `target_open_tabs` slots with fresh Slack/Trello/mail
items by the time Russell went to resume his lost work, and resuming all of it on top would
have meant ~24 open tabs at once. The drainer already has a global concurrency cap
(`target_open_tabs`, checked against `total_claude_tabs()` — every live `claude.exe`
process system-wide) that's designed for exactly this kind of contention between sources,
but crash-orphaned sessions aren't a source it knows about.

## Goal

Make "sessions orphaned by a crash" a drainer source, so:
- Orphans are found and resumed automatically on the next poll cycle, no manual step.
- They're dispatched under the same `target_open_tabs` cap as everything else — no
  special-case pileup risk.
- They are the **highest-priority** needs-you item: as tab slots free up, an orphan resume
  wins the slot before a fresh Slack DM, email, or Trello card, so the interrupted-work
  backlog drains before new inbound work is even considered.

Non-goals: this design does not change `target_open_tabs`'s default value, does not touch
the drainer's own *unrelated* `reconcile_orphans()` (which self-heals the drainer's own
dead worker tabs — a different "orphan" than the one this document is about), and does not
remove the manual `resume-sessions` skill.

## Where the plumbing lives

The live-session registry (`~/.claude/session-mgr/live-sessions.json`), the
`SessionStart`/`SessionEnd` hooks that maintain it (`session-mgr`'s `hooks/session_registry.py`
+ `hooks/hooks.json`), the clean self-close primitive (`session-mgr`'s `end-session.py`,
also reachable via `/close`), and the session launcher (`session-mgr`'s
`launch-session.ps1`, which already supports `-Resume <session-id>` → `claude --resume
<guid>`) all live in the **session-mgr** plugin already, and are used by things other than
crash recovery — the handoff launcher and `/close` both depend on `launch-session.ps1` and
`end-session.py` respectively. Session-mgr stays the owner of all of that; it is not
becoming drainer-specific scaffolding.

Drainer's other providers (Outlook, Slack, Trello, Gmail, Teams, Zoom) are all thin wrappers
around something that already exists independently. This source follows the same shape:
session-mgr owns the actual "what makes a session orphaned, how to relaunch it, how to
close it cleanly" plumbing; drainer adds only the automation wrapper that makes the poller
find and dispatch it on a schedule.

## Components

### 1. `find-orphans.py` (new, in `session-mgr`)

Path: `plugins/session-mgr/skills/resume-sessions/scripts/find-orphans.py`

Extracts Steps 1–2 of the existing `resume-sessions` SKILL.md prose (psutil scan of running
`claude.exe` processes for their session IDs; read the live-session registry; diff) into a
real, reusable script instead of a snippet re-authored into `.tmp/` each run. Registry-only
— no fallback transcript scan (decided: cheap and authoritative for anything since the hook
was installed; the fallback scan stays exclusive to the manual skill for now, not run every
5 minutes).

Run directly, it prints JSON to stdout:
```json
[{"session_id": "...", "cwd": "...", "started_at": "2026-07-20T13:04:11Z"}, ...]
```

Applies the existing self-close tail check (Step 2's exclusion in the current skill): scan
the last ~30 transcript entries for a `taskkill /PID ... /T /F`, `close-session.py`, or
`end-session.py` invocation among the session's final actions — such a session closed
itself on purpose and is dropped from the registry rather than returned, so a residual
registry entry (written before the session's tooling adopted `end-session.py`, or force-killed
by something else) is never treated as a live orphan.

The `resume-sessions` SKILL.md is updated to call this script for its Steps 1–2 instead of
authoring the inline snippet, so there is exactly one implementation.

### 2. `orphan-sessions-adapter.py` + `orphan-sessions-provider.md` (new, in `drainer`)

Path: `plugins/drainer/skills/drainer/providers/orphan-sessions-adapter.py`

A thin `ProviderBase` implementation, following the same "resolve the newest installed
copy of the real thing" pattern `close-session.py` and the drainer's `launch-session.ps1`
resolver already use elsewhere in this plugin:

- **`enumerate(limit)`** — locate the newest installed `session-mgr` plugin's
  `find-orphans.py` (same version-sort-and-fallback resolver logic as the existing
  `close-session.py`), run it via `subprocess`, parse the JSON. Each returned session
  becomes a candidate item: `{session_id, cwd, started_at}`. `received` is stamped to the
  poll cycle's current time (not `started_at`) — see Priority below for why.
- **`stable_id(item)`** — `orphan-<session_id>-<started_at>`. Baking in `started_at` (not
  just `session_id`) means a session that gets auto-resumed once and later crashes *again*
  produces a new stable id on its second crash (its registry entry's `started_at` changes
  each time `SessionStart` fires), so it resurfaces as a fresh item rather than being
  permanently marked seen after the first resume. This is the same idiom the `trello`
  adapter uses baking a card's go-live date into its id so a recurring follow-up isn't
  seen-state-suppressed forever.
- **`capture(item, iid, runtime_dir)`** — writes `items/<id>.json`:
  `{"id","source":"orphan-sessions","triage":"needs-you","kind":"resume","session_id","cwd","started_at","ts":"<ISO now>"}`.
  Written for the same audit-trail consistency every other source has, even though nothing
  reads it back for this source (no worker, no `.done` — see Dispatch below).

`orphan-sessions-provider.md` documents the id scheme and the CAPTURE shape (mirroring
every other provider doc), and explicitly has no CLEAR / DRAFT-MODE / AUTO-HANDLE sections
— none apply to this source.

### 3. Deterministic pre-triage (change to `run-poller.py`)

Like the existing Trello tautology-bypass ("every active card is needs-you, skip the AI
call"), `orphan-sessions` items are stamped `_bucket = "needs-you"`, `_kind = "resume"`,
`_complexity = "simple"` deterministically in the same pre-triage block, never sent to the
AI triage call. There's no judgment to make — an orphaned session unconditionally needs
resuming.

### 4. Dispatch: `spawn_resume_tab()`, not `spawn_worker()` (change to `run-poller.py`)

Every existing source's needs-you item goes through `spawn_worker()`: write a prompt seed,
launch a *fresh* `claude` session pointed at `worker-core.md` in the drainer's own repo.
That's wrong for this source on two counts — there's no fresh work to seed (the session
already has its full history), and it must reopen in the **orphaned session's own original
`cwd`**, not the drainer's repo.

New `spawn_resume_tab(session_id, cwd, title)` calls a new sibling script,
`spawn-resume-tab.cmd` (next to the existing `spawn-tab.cmd`, same `-w drainer` window
grouping for consistency), which invokes `launch-session.ps1 -Resume <session_id>` with
`--startingDirectory` set to the orphan's own `cwd` — using the `-Resume` flag that already
exists on the launcher and is already forwarded by drainer's thin resolver, just never
exercised by any caller until now.

Title: no subject/who to build one from (unlike every other source), so it's a fixed
pattern instead of reusing `_worker_title()`: `Resume: <basename of cwd>` (e.g. a session
whose `cwd` was `C:/Users/russe/Dev/personal-ai-pod` titles as `Resume: personal-ai-pod`).
The resumed Claude session renames its own tab on its first turn either way, so this is
only the ~1s placeholder before that happens.

No `.done`, no CLEAR: dispatch **is** the entire action for this source. Once
`spawn_resume_tab` succeeds, the item is recorded seen (same fail-safe-after-dispatch
pattern every other source uses) and the drainer's involvement ends — Russell continues in
his own resumed session exactly as if he'd relaunched it himself.

**Launch conventions — nothing about this path is special-cased.** `spawn-resume-tab.cmd`
invokes exactly the same `powershell -NoExit -File <launcher> ...` shape every other spawn
in this codebase uses (`spawn-tab.cmd`, the handoff launcher), so everything that shape
gives you "for free" applies unchanged:
- **`$PROFILE` loads normally** (no `-NoProfile`) → `$env:CLAUDE_HOST_PID` is set, so `/close`
  and `end-session.py` work on a resumed tab exactly like on any other tab.
- **`launch-session.ps1`'s `-Resume` branch sets `$env:BROWSER_CHAUFFEUR_OWNER_PID`** before
  calling `claude`, same as its `-PromptFile`/`-SeedFile` branches — browser tabs the
  resumed session opens are owned by, and cleaned up with, this tab like any other.
- **`claude --resume <guid>` re-fires `SessionStart`** the same as any `claude` launch —
  this is not a step `spawn_resume_tab` has to do itself, it's inherent to `--resume`, and
  it's *why* the registry's `started_at` for that session advances on every resume. That's
  also the fact §2's recurrence-safe `stable_id` scheme depends on: registering fresh on
  resume is what makes a second, later crash of the same session produce a new `started_at`
  and a new id instead of staying permanently seen.
- **No `-Model` override.** Unlike a fresh worker dispatch (which must pin `worker_model`/
  `worker_model_complex` so it doesn't inherit a 1M-context account default), `--resume`
  restores the session's own prior model as part of resuming state, so passing nothing is
  correct — this matches the manual `resume-sessions` skill's own invocation, which also
  passes no `-Model`.
- **Window placement — `-w drainer`, not the manual skill's `-w 0`, and deliberately so.**
  The manual skill uses `-w 0` (whatever window is currently focused) because it's invoked
  by Russell in the moment, in whatever window he's already in. This dispatch is unattended
  automation, the same as every other drainer spawn, so it follows the *drainer's* launch
  convention instead: `-w drainer`, through the existing `provider_base.spawn_tab()` helper
  unchanged. That's not just naming consistency — that helper's foreground-preservation
  logic (read the foreground window before spawning; minimize the drainer window if it
  steals focus from something else Russell was using) is built around tabs landing in a
  known "drainer" window, and only works correctly there. Routing resumes through `-w 0`
  instead would both scatter them unpredictably and silently drop that focus protection.

### 5. Priority ordering (change to `run-poller.py`)

Rather than relying on `received`-timestamp tie-breaking against the global newest-first
sort (fragile — a coincidentally-recent Slack message could still slot ahead), split the
`needs` list explicitly: `orphan-sessions` items are pulled out and dispatched **first**,
ahead of the sorted rest, both counted against the same `live_tabs` / `target_open_tabs`
running total. So:
- Cycle N: 12 tabs already open (at cap) → orphans held at cap exactly like everything else.
- As those 12 finish and tabs close, freed slots go to the orphan-sessions backlog first,
  every cycle, until it's exhausted — *then* normal dispatch (Slack/Trello/mail, newest
  first) resumes.

This is the literal implementation of "highest priority of all, even before an email that
just came in."

## Config

No new knobs needed. `orphan-sessions` is enabled the same way any other provider is —
listed under `providers:` in `.claude/drainer.local.md`.

## Error handling

- `find-orphans.py` unreachable / session-mgr not installed → `ProviderError(kind="config")`
  from the adapter's resolver, caught and isolated by the poller's existing per-provider
  try/except (same as every other adapter-load failure) — one broken provider never aborts
  the cycle for the others, and it's surfaced via `provider-health.json` like any other
  provider fault.
- `find-orphans.py` runs but the registry file is missing/corrupt → treated as "0 orphans
  this cycle" (fail-safe empty, not an error) — mirrors `load_seen`'s existing fail-safe
  pattern for a missing/corrupt `seen.json`.
- `spawn_resume_tab` fails (e.g. `wt.exe` error) → the item is left **unrecorded** exactly
  like a held-at-cap needs-you item, so the next cycle retries it — same fail-safe-after-
  dispatch invariant as `spawn_worker`.
- A session that's actually still running (registry entry present but the process is live)
  is excluded by `find-orphans.py`'s own liveness check before it's ever returned — the
  adapter never sees it as a candidate.

## Out of scope / future work

- Retiring the manual `resume-sessions` skill entirely — left as-is for now; it likely
  becomes a rarely-used on-demand fallback (a machine without the drainer running, or
  wanting an immediate sweep instead of waiting for the next poll cycle) rather than
  something to delete today.
- The fallback full-transcript scan (Step 3 of the current skill) is intentionally not
  wired into the drainer's per-cycle enumerate — it stays exclusive to the manual skill.
  Revisit if registry-only proves to miss real cases in practice.
- No digest-side reporting of "N orphan sessions auto-resumed today" — could be added to
  the daily digest later the same way auto-handle items are reported, but isn't required
  for the core loop.
