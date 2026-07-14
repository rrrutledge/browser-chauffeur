# drainer — architecture

The map of how a drainer works and *why* it's built this way. This file is orientation; the runtime
contracts are owned by the engine/template files linked at the bottom — read them there, not a
restatement here.

## What a drainer is

A **drainer** takes a queue of human-touch items and, for each: reads the underlying conversation →
figures out the **ACTION** (reply / do work / nudge / stop / nothing) → **does the action** — which
often means actually KICKING OFF the work (open a PR, file a ticket, run a check, update a system),
sometimes BEFORE any reply — and drafts any reply **in the user's voice (draft-only, never send)** →
**advances/clears** the item. The value is figuring out and *doing* the action, not just replying; the
deliverable may be the work itself, not a message. (Irreversible / outbound-to-others steps wait for the
user's explicit OK; safe, reversible work and drafts proceed immediately.)

Outlook / Teams / outreach are all the **same loop** with different **sources**. "Gone" is per source:
an email is deleted/archived; a Teams chat is marked read; an outreach card is advanced or bumped to a
later follow-up day.

## The continuous keeper (the one model)

The drainer runs as a **continuous keeper**: a presence-gated **poller** runs a short cycle every few
minutes (a ~5-min cron) and holds each source at **zero un-started actionable items** all day.

- **needs-you →** the poller immediately spawns a **worker tab** so the user starts acting right away,
  dispatching as fast as possible until the count of live Claude Code tabs system-wide reaches
  `target_open_tabs` (default 12); beyond that, items wait for a later cycle.
- **auto-handle →** a standing-rule item; the poller spawns a worker that acts autonomously, clears the
  source, queues a digest entry, and finishes without interrupting the user.
- **fyi / junk →** captured to a **digest queue** for a once-a-day readout; nothing is disposed of
  silently in the fast loop.
- **The poller never clears.** The source is cleared in exactly one place: the worker tab on completion
  (needs-you), or the daily digest after the user reviews it (fyi/junk).

## The poller is code; AI is judgment

The loop — enumerate → drop already-seen → cap → dispatch → record — is a deterministic algorithm, so it
lives in a script (`scripts/run-poller.py`): cheaper and more reliable than asking an AI to follow it
each cycle. AI is used for exactly two things: **one batched triage call per cycle** (the bucket
judgment for all new items) and **the per-item worker session** (the actual reply/work, draft-only).

This is the **poller / worker split**: the poller enumerates and triages but never does an item's work;
each needs-you item gets its **own worker** that handles it to completion in a fresh context (its own
tab), so context stays bounded and nothing is half-done. The cap, not a queue, bounds how many face the
user.

## Fail-safe, never miss

Every mechanism's worst case is *redundant work*, never a *dropped item*: seen-state is a separate id
store (losing it re-processes, never hides); a seen-id is recorded only **after** dispatch succeeds (an
aborted cycle retries next time); workers are idempotent (a duplicate tab's situational-check resolves
quietly). Orphan recovery follows the same principle — a worker tab closed without writing `.done` is
detected by **liveness** (not a timeout) and re-queued so its slot frees, while an open, live tab is
left alone however long it's up, because it's either being worked or parked for the user.

## Two layers: the plugin vs. what each machine injects

| In the plugin (generic) | Injected per machine |
| --- | --- |
| `engine/` — poller contract, worker procedure, triage rubric, provider contract; `scripts/` — the deterministic glue | `.claude/drainer.local.md` — which providers are active, per-provider config, `target_open_tabs`, `max_messages_per_cycle`, presence |
| `providers/` — the providers (Outlook, Teams, Trello) | `context.md` (in `local_dir`) — who the user is, their systems, standing rules |
| `docs/`, `templates/` | **credentials** (OS store / env) |

The plugin never contains anything that identifies the user or their organization.

## Where the details live (the canonical specs)

Each contract is owned by exactly one file — this doc only points to them:

- **Triage** — the one rubric, *"is there something for the user to do?"* sorted into needs-you /
  auto-handle / fyi / junk → `engine/triage.md`.
- **Poller contract** — enumerate / cap / dispatch / record, seen-state, the orphan sweep →
  `engine/poller-core.md`.
- **Worker procedure** — read brain → situational-check → do → draft → advance → `engine/worker-core.md`.
- **Daily digest** — the once-a-day interactive readout and reconciliation sweep → `engine/digest-core.md`.
- **Provider contract** — the interface a source implements → `engine/provider.md`; to add one, see
  `docs/writing-a-provider.md`.
- **Per-machine behavioral and standing rules** — draft-only outbound, delete/archive freely, lead with
  context, waiting-on-someone → a tracker card, one voice brain — live in `templates/context.example.md`,
  copied into each machine's `context.md`.
- **Scheduling** — two Scheduled Tasks (the fast poller and the once-a-day digest), registered
  version-independently so a routine `claude plugin update` is picked up automatically →
  `scripts/install-schedule.ps1`, `scripts/install-digest-schedule.ps1`, `scripts/launch-drainer.py`.
- **Settings and extension points** → `docs/extending.md`.
