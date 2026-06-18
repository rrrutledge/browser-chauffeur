# Drainer redesign — the continuous keeper

**Date:** 2026-06-17
**Status:** Approved design; ready for implementation planning (Stage 1).
**Plugin:** `drainer` (name kept; "continuous keeper" is the framing, not a rename).

## Motivation

The drainer was designed around an assumption that no longer holds: that checking a
source was **expensive and slow** (a browser instance to drive, AI tokens to spend). That
forced a **batch** model — harvest everything every ~30 minutes, process the batch at
once, collect junk into a periodic digest — because frequent checks were costly.

With **API/MCP providers**, reads are effectively instant and cheap. The batch rationale
is gone. We can move to a **continuous** model that keeps each incoming queue at **zero
un-started actionable items**, all day, in the background.

The goal is not "zero emails at all times." It is: **nothing actionable sits un-started.**
The moment something needs Russell, a worker is already on it; everything else waits for a
once-a-day digest.

## Core concept — two rhythms

**Fast loop (~every 5 minutes, presence-gated).** A headless Claude **poller** harvests
every enabled source, triages each *new* item against the existing rubric, and:

- **needs-you →** immediately spawns a new Claude Code **tab** (a worker, via the `wt`
  launcher) seeded with the captured item, so it starts helping Russell act right away. He
  gets to it whenever he gets to it, alongside his other always-open tabs.
- **fyi / junk →** queued for the end-of-day digest. No tab now.
- Records each dispatched item's id in the **seen-state** store.
- Spawns **no window** when nothing is actionable — idle cycles are silent.

**Slow loop (end of day, one tab).** A **digest tab** walks all queued fyi + junk:

- **fyi →** a Claude summary rich enough that Russell never has to open the email.
- **junk →** grouped, each with a "stop it at the source" proposal (unsubscribe link or a
  filter) so it stops arriving — the best outcome is never receiving it again.
- After review, clears them via each provider's `CLEAR`.
- Also runs the **reconciliation sweep** (see below).

## What changes vs. today's drainer

- The batch `engine/driver-core.md` becomes a **continuous dispatcher** (the poller).
- `engine/triage.md`, `engine/worker-core.md`, and the provider contract **stay** — the
  worker procedure and rubric are unchanged; only *when* and *how* workers are launched
  changes (one tab per needs-you item, spawned live, instead of a serialized batch).
- The junk path changes: junk is **not** silently deleted in the fast loop. It is queued
  and only cleared after Russell sees it in the daily digest (with a source-stop proposal).
- Source-agnostic throughout: Outlook first; Gmail, Trello, and later sources (e.g. SMS)
  are just providers added to the same loop.

## Design tenet — fail safe, never miss

**Better to process an item twice than to miss it once.** Every mechanism is chosen so its
worst-case failure is *redundant work*, never a *dropped item*:

- **Seen-state is a separate file of processed message-ids** (per source), not the
  read/unread flag and not inbox-presence. If Russell marks something read, it still gets
  processed. If a tab crashes, nothing is silently archived away. If the seen-state file is
  lost or corrupt, the worst case is that everything is re-processed — safe.
- **Idempotent workers** make "process twice" harmless: `worker-core`'s situational-check
  ("already handled? does a draft already exist?") means a second pass on the same item
  sees it's done and resolves quietly instead of duplicating.
- **Record-seen-only-after-dispatch:** a message-id is written to seen-state *only after*
  its dispatch succeeds (worker tab spawned, or item queued for digest). A spawn that fails
  mid-cycle leaves the id unrecorded, so the next cycle retries it.

## Components

1. **Poller (fast loop).** Headless Claude on a ~5-minute cron. Each cycle:
   1. **Presence-gate** — away/locked → exit cheaply, no work, no window.
   2. **Acquire overlap-lock** (with a stale-TTL so a crashed poller can't wedge the loop
      forever — a lock older than N minutes is treated as stale and broken).
   3. Read `.claude/drainer.local.md` (enabled providers, cadence, presence) + `context.md`.
   4. For each enabled provider: `AUTH-GLANCE` → `ENUMERATE` candidate items → drop any in
      seen-state → triage the rest → **dispatch** (spawn worker tab for needs-you; capture
      to digest-queue for fyi/junk) → record seen-id after each successful dispatch.
   5. Release the lock.

2. **Seen-state store** (in `runtime_dir`). Two parts: the processed message-ids per
   source, and the **pending-digest queue** (captured fyi/junk items awaiting the EOD
   digest). For needs-you items, the record also tracks status (dispatched → cleared) to
   support reconciliation. Losing it → reprocess (safe).

3. **Worker tab.** Spawned via `wt` + `launch-session.ps1` with a seed prompt pointing at
   the captured `items/<id>` file. Runs `engine/worker-core.md` (situational-check → do the
   work → draft-only reply → advance/clear). Idempotent.

4. **EOD digest tab.** Its own cron at day's end. Reads the pending-digest queue → fyi
   summaries + grouped junk-with-source-stop proposals → Russell reviews → on his OK,
   clears each via the provider's `CLEAR` and empties the queue. Then runs reconciliation.

5. **Providers.** Contract unchanged (`AUTH-GLANCE`, `ENUMERATE`, `CAPTURE`, `CLEAR`,
   `JUNK-LEARNING`, `DRAFT-MODE`). `ENUMERATE` returns candidates (read + unread within a
   window); the poller dedups via seen-state.

## Data flow

**Fast cycle:**
`cron → poller → presence? → lock → per provider: enumerate → minus seen-ids → triage each
new → { needs-you: capture + spawn worker tab + record seen-id ; fyi/junk: capture to
digest-queue + record seen-id } → unlock → exit (no window if nothing actionable)`

**End of day:**
`cron → digest tab → read digest-queue → summarize fyi, group junk + propose source-stops →
Russell reviews → on OK: provider CLEAR each + empty queue → reconciliation sweep`

## Error handling & edge cases

- **Presence away/locked** → cheap no-op, no window, no noise.
- **Overlap lock with stale-TTL** → a crashed prior cycle can't wedge the loop; a stale
  lock is broken after N minutes.
- **Provider auth failure** (`AUTH-GLANCE` fails) → surface one sign-in tab for that
  source, skip it this cycle (record no seen-ids for it), keep processing other sources.
- **Duplicate dispatch** (seen-state lost) → the second tab's situational-check sees it's
  handled → quiet resolve. No harm.
- **Stuck item** (a needs-you tab crashes, or Russell never gets to it): it's recorded as
  seen at spawn time, so it won't re-spawn — but it's not done. Because the worker clears
  the source mail only on completion, **an item still in the inbox that was dispatched > X
  hours ago is unfinished.** The daily **reconciliation sweep** (folded into the EOD
  digest) re-surfaces these stale dispatched-but-uncleared items. Fail-safe at the
  *completion* level, not just dispatch.
- **Headless poll failure** → cycle aborts, lock released (or later stale-broken); next
  cycle retries. No item lost.
- **Digest not run / not reviewed** → fyi/junk stay queued (safe); nothing cleared without
  review.

## Scope & staged roadmap

This spec covers the **architecture** and **Stage 1**. Later stages each get their own
spec → plan → build cycle.

- **Stage 0 (in flight — PR #70):** solid `personal-outlook` provider — `ENUMERATE`
  read+unread, `DRAFT-MODE` prefer-reply, and the "always reply to an existing thread over
  a fresh compose" preference saved in the `message-draft` skill.
- **Stage 1:** the continuous Outlook keeper — poller + seen-state + worker-tab spawn,
  presence + overlap-lock. Acceptance: it holds the Outlook inbox at zero un-started
  actionable items hands-free, fail-safe, draft-only.
- **Stage 2:** EOD digest tab — fyi summaries + junk source-stop proposals + the
  reconciliation sweep.
- **Stage 3:** one-time backlog sweep of existing read mail → inbox truly empty.
- **Stage 4+:** Gmail provider; wire Trello into the same loop; then more sources (SMS…).

## Out of scope (YAGNI for now)

- Auto-applying junk filters/unsubscribes (the digest *proposes*; Russell actions them —
  matches his GitHub-unsubscribe instinct).
- Sending anything outbound (draft-only remains absolute).
- SMS and other sources beyond Outlook/Gmail/Trello (named only as future direction).
- Renaming the plugin.

## Behavioral rules carried forward (unchanged)

- **Draft-only outbound. Never send/post.** Drafts created immediately (reversible);
  Russell edits and sends. Only sending/posting/permanent-purge/destructive changes wait
  for explicit OK.
- **Prefer replying to an existing thread** over composing a fresh message (saved as a
  durable preference in `message-draft`).
- **Delete/archive is reversible** — but junk/fyi are cleared only via the reviewed daily
  digest, not silently in the fast loop.
- **Lead with context** in every worker's final message.
- **Waiting on someone else → a tracker card** only when Russell initiated and the ball is
  back in their court.
