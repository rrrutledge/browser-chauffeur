# drainer — architecture

A **drainer** takes a queue of human-touch items and, for each: reads the underlying conversation →
figures out the **ACTION** (reply / do work / nudge / stop / nothing) → **does the action** — which
often means actually KICKING OFF the work (open a PR, file a ticket, run a check, update a system),
sometimes BEFORE any reply — and drafts any reply **in the user's voice (draft-only, never send)** →
**advances/clears** the item. The value is figuring out and *doing* the action, not just replying. The
deliverable may be the work itself, not a message. (Irreversible / outbound-to-others steps wait for
the user's explicit OK; safe, reversible work and drafts proceed immediately.)

Outlook / Teams / outreach are all the **same loop** with different **sources**. "Gone" is per source:
an email is **deleted/archived**; a Teams chat is **marked read**; an outreach card is **advanced or
bumped to a later follow-up day**.

## The continuous keeper (the one model)

The drainer runs as a **continuous keeper**: a presence-gated **poller** runs a short cycle every few
minutes (a ~5-min cron) and holds each source at **zero un-started actionable items** all day.

- **needs-you →** the poller immediately spawns a **worker tab** (up to `max_open_tabs` concurrent,
  default 3), so the user starts acting right away. Beyond the cap, items are held and picked up on a
  later cycle.
- **fyi / junk →** captured to a **digest queue** for a once-a-day readout; nothing is disposed of
  silently in the fast loop.
- **The poller never clears.** The source item is cleared in exactly one place: the worker tab on
  completion (needs-you), or the daily digest after the user reviews it (fyi/junk).

## The poller is code; AI is judgment

The loop — enumerate → drop already-seen → cap → dispatch → record — is a deterministic algorithm, so it
lives in a script (`scripts/run-poller.py`): cheaper and more reliable than asking an AI to follow it
each cycle. AI is used for exactly two things:

- **One batched triage call per cycle** — the needs-you / fyi / junk judgment for all new items, per
  `engine/triage.md`.
- **The per-item worker session** — the actual reply/work, following `engine/worker-core.md`, draft-only.

This is the **poller / worker split**: the poller (the script) enumerates and triages but never does an
item's work; each needs-you item gets its **own worker** that handles it to completion in a fresh
context (its own tab), so context stays bounded and nothing is half-done. The worker signals completion
by writing `items/<id>.done` and clears the source item itself. The poller runs up to `max_open_tabs`
workers at once (it does not serialize); the cap, not a queue, bounds how many face the user.

- **Orphan self-recovery:** a worker tab closed or hung without writing `.done` would hold a cap slot
  forever. Each cycle the poller's `reconcile_stale` sweep (sibling of the `.done` reconciliation) finds
  any needs-you item still dispatched past `stale_hours` and **re-queues** it — drops its seen key so the
  next enumerate re-dispatches a fresh tab — freeing the slot. No retry cap: a finished item resolves by
  the worker writing `.done`, so a re-opened tab converges, and an item no longer present in its source
  simply doesn't re-enumerate.

## Fail-safe, never miss

Every mechanism's worst case is *redundant work*, never a *dropped item*:

- **Seen-state** (`scripts/seen-state.js`) is a separate store of processed message-ids per source — not
  the read/unread flag, not inbox presence. Losing it re-processes items (safe), never hides them.
- **Record-seen-only-after-dispatch** — an id is recorded only after its worker tab spawns or it is
  queued; a failed cycle leaves it unrecorded, so the next cycle retries it.
- **Idempotent workers** — a duplicate tab's situational-check sees the item is already handled and
  resolves quietly. No overlap lock is needed.

## Two layers: the plugin vs. what each machine injects

| In the plugin (generic) | Injected per machine |
| --- | --- |
| `engine/` — poller contract, worker procedure, triage rubric, provider contract; `scripts/` — the deterministic glue | `.claude/drainer.local.md` — which providers are active, per-provider config, `max_open_tabs`, `max_messages_per_cycle`, presence |
| `providers/` — the providers (Outlook, Teams, Trello) | `context.md` (in `local_dir`) — who the user is, their systems, standing rules |
| `docs/`, `templates/` | **credentials** (OS store / env) |

The plugin never contains anything that identifies the user or their organization. See
`docs/extending.md` for where each injected piece plugs in.

## Triage (the one rubric, shared)

Classify every item by asking **"What does this want the user to do?"** into three buckets — the only
three; full rubric in `engine/triage.md`:

- **needs-you** → its **own worker tab** (up to `max_open_tabs` concurrent).
- **fyi / junk** → **never** a worker each; captured to the digest queue and read out once a day
  (the EOD digest), nothing disposed of silently. Every **junk** item is a signal to stop it at the
  source — propose, in priority order, an **unsubscribe**, then the source app's **notification
  settings**, then an **inbox rule**, so future cycles spend tokens and attention only on what matters.

## Hard behavioral rules (carry these into every machine's `context.md`)

- **Draft-only outbound. Never send, never post, never press Enter to send.** Create drafts
  immediately (reversible); only *sending*, *posting to others*, a *permanent purge*, or *destructive
  system changes* wait for the user's explicit OK.
- **Delete/archive freely without asking** — reversible; narrate each with a one-line reason.
- **Actions-first, situational-check first.** Check whether it's already handled; check the Drafts
  folder before composing.
- **Lead with context** in every worker; an item that needs nothing right now resolves quietly.
- **One voice brain:** all drafting via `message-draft` (which applies `document-authoring` voice and
  anchors links to descriptive text). After every send, diff sent-vs-draft and append a voice lesson.
- **Waiting on someone else → a tracker card** when *you* initiated and the ball is back in their
  court (if they initiated and you've replied, you're done).

## Scheduling (machine-specific glue)

- **Presence-gated** — away/locked → exit cheaply, do nothing (`scripts/presence.py`).
- **Idle runs make no window and no noise** — a surface appears only for an item to handle or a sign-in.
- **One interval** for all sources, set for the fastest-arriving one; cheap sources ride along.
- Registered once via `scripts/install-schedule.ps1` (a Scheduled Task running `run-poller.py`).
- **The slow loop is a second task** — `scripts/install-digest-schedule.ps1` registers a once-a-day
  task running `scripts/run-digest.py`, which opens one **interactive** digest tab
  (`engine/digest-core.md`). Unlike the silent poller, the digest is visible and clears nothing until
  the user reviews it. It also runs the **reconciliation sweep**: any needs-you item still
  dispatched-but-uncleared past `stale_hours` is re-surfaced so a crashed or abandoned worker doesn't
  fall through the cracks.
