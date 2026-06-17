# Drainer — background, principles & lessons

> **Note:** this began as the build brief for the personal machine. The engine is now built and ships
> in this plugin (see `SKILL.md` for usage). Keep this as the **why** — the principles, behavioral
> rules, and hard-won lessons behind the design. The remaining "build" on any machine is its
> **providers** (see `docs/writing-a-provider.md`), not the engine.

**Origin:** distilled from the work-machine build (russ-ai-pod), 2026-06-17.

## What this is

On my work machine I built an automation layer in Claude Code that **drains my
inbound queues to zero** — work email, Microsoft Teams, and my Trello outreach
boards. It runs on a schedule, reads each item, figures out what it actually
wants me to do, *does the doable part*, drafts any reply in my voice, and clears
the item — never sending anything without me.

I want **the same system on my personal machine** for my personal queues. Don't
port the work code line-for-line. Take these requirements and build the best
version *for this machine*, because this machine is fundamentally better suited:
**it has real API / MCP access to almost everything.** The work build leans
heavily on browser automation (browser-chauffeur driving Edge), which is slow,
fragile, and expensive. Here you should reach for APIs/MCP first and treat the
browser as a last resort.

## The core idea (this is the part to preserve)

A **drainer** processes a queue of human-touch items. For each item it:

1. **Reads** the underlying conversation/thread.
2. **Decides the ACTION** — reply / do work / nudge / stop / nothing. The value
   is figuring out and *doing* the action, not just replying. The deliverable is
   often the work itself (open a PR, file a ticket, run a check, update a
   system), sometimes done *before* any reply.
3. **Does the doable part now.** Safe, reversible work proceeds immediately.
   Anything irreversible or outbound-to-others waits for my explicit OK.
4. **Drafts any reply in my voice — draft-only, never send.** Drafts are created
   immediately (a draft is reversible); I edit and send myself.
5. **Clears the item** so it doesn't resurface ("gone" is per-source: an email
   is deleted/archived; a Trello card is advanced or bumped to a later date).

Inbox, Teams, and outreach are **the same loop over different sources.** Build
the loop once; each source is a thin adapter on top.

## Sources to drain (personal)

| Source | Personal access on this machine | Notes |
| --- | --- | --- |
| **Outlook personal mail** | `ms-graph` skill/plugin (Graph API) | Already set up — see `personal-outlook-graph.md`. No browser needed. |
| **Gmail** | Gmail MCP / API | Reply-draft format quirk documented in `~/.claude/CLAUDE.md` § Email reply drafts. |
| **Slack** | Slack API / MCP | If available. |
| **Trello** | Trello REST API | Outreach boards; due-date *is* the queue. |
| **Personal calendar** | Outlook (outlook.live.com) via `ms-graph` | NOT Google Calendar. |

Pick the sources I actually have credentials for; start with whichever is
easiest to prove the loop end-to-end (probably Outlook-via-Graph, since it's
already wired and needs no browser).

## Cadence differs per source (the only real difference between sources)

- **Continuous sources** (email, Teams, Slack) — run **every ~10–15 min**.
- **Due-date sources** (Trello outreach) — run **once a day** (the due-date queue
  only needs a daily look).

Everything else about the loop is identical across sources.

## Architecture requirements (what mattered, not how I coded it)

- **Driver / worker split.** A *driver* enumerates the queue and triages each
  item; a *worker* handles one item to completion. Keep one item in front of me
  at a time (serialized), so context stays bounded and nothing is half-done.
- **Deterministic orchestration where possible.** On the work machine, API-only
  sources (Trello) are orchestrated by a plain **Python controller** — no LLM in
  the orchestration loop, so it never fills its context no matter how many items.
  Use the same principle here: when a source has an API, the enumerate/advance
  layer should be ordinary code, and the LLM only does per-item reasoning.
  **Because this machine has APIs for nearly everything, far more of the system
  can be deterministic code than on the work machine.**
- **Bounded context per item.** Each item handled in a fresh worker context so
  heavy reads don't leak item-to-item.
- **One triage rubric, shared by all sources.** Classify every item by asking
  **"What does this want me to do?"** into three buckets:
  - **needs-you** — something to DO (reply, work, decision, check, delegate, or
    work-then-reply). Gets its own worker.
  - **fyi** — informational, nothing asked. Batched into one digest.
  - **junk** — no info value and no action. Batched into the digest, then
    deleted (and ideally a filter/rule proposed so it stops recurring).
  - Tie-breakers: unsure needs-you/fyi → needs-you; unsure fyi/junk → fyi.
  - "Container" items (e.g. a meeting-recording notification) aren't classified
    themselves — open the linked content and classify what's *inside*.
- **fyi/junk never get a worker each** — collected and cleared in ONE digest
  pass, so I'm never handed a tab per newsletter, but nothing is deleted silently.
- **Drain to zero.** Every run takes the source to empty: each item ends handled
  or cleared. Inbox to literal 0.

## Hard behavioral rules (these are non-negotiable — they're my preferences)

- **Draft-only outbound. Never send, never post, never press Enter to send.**
  I send everything myself. Create drafts immediately (reversible); only
  *sending*, *posting to others*, a *permanent purge*, or *destructive system
  changes* wait for my explicit OK.
- **Delete/archive emails freely without asking** — it's reversible. Narrate each
  deletion with a one-line reason; nothing silent.
- **Actions-first, situational-check first.** Before drafting, ask if there's
  something to DO in a system, and check whether it's already handled (PR merged?
  request already done? they replied and I already answered?). Check the Drafts
  folder before composing — I often have one going.
- **Lead with context in every worker.** Assume I have zero memory of the thread.
  The worker's first message restates the incoming item (who, what they asked,
  any deadline) *before* analysis. Never "done, nothing to do."
- **No-op items resolve quietly** — bump/skip without interrupting me. Only items
  that genuinely need me should surface and beep.
- **Voice is one source of truth.** All drafting goes through the
  **`message-draft`** skill (which applies **`document-authoring`** voice and
  anchors links to descriptive text — never bare URLs in prose). After I send,
  diff the sent version against the draft and append a concrete lesson to the
  document-authoring voice loop. One voice brain, taught by every send.
- **When something is waiting on someone else, create a Trello tracker card** so
  it stays visible — don't rely on memory.

## The shared "brain"

The worker reads a small, durable **context file** at the start of every item:
who I am, the systems I act in, where things live, and these standing
preferences. Keep it **small and stable** — facts, not a growing pile of
per-case playbooks. When I have to tell the system something it could have known,
**improve the source it should have come from** (the system, a skill, a config),
don't just append a note. The brain gets smarter by improving sources, not by
hoarding cases.

## Scheduling / triggering requirements

- **Presence-gated.** If I'm away or the machine is locked, the run should exit
  cheaply and do nothing (especially any browser work, which needs an unlocked
  interactive desktop). Cost is paid only when I'm actually at the keyboard.
- **No pile-ups.** An overlap lock so a slow run doesn't stack on the next tick.
- **Idle runs make no window and no noise.** A visible/notifying surface appears
  only when there's an item to handle or sign-in is needed.
- **Once-a-day sources** use a once-per-day marker so they fire at most daily.

## What's better here than on the work machine (lean into this)

- **APIs/MCP instead of browser automation** for reading queues, enumerating
  items, creating drafts, and advancing state. Browser automation was the single
  biggest source of slowness and flakiness on the work machine — avoid it wherever
  an API exists. The personal machine has API/MCP for Outlook, Gmail, Slack,
  Trello, and calendar, so the browser should be rare-to-never.
- **More deterministic code, less LLM-in-the-loop.** With APIs, enumerate/triage/
  advance can largely be plain scripts; reserve the model for per-item judgment
  and drafting.

## Lessons from the work build (save yourself the rediscovery)

- **Keep the orchestrator non-LLM** for API sources — it never runs out of context.
- **One triage rubric, one voice brain, one shared context file** — don't restate
  rules per source; sources are thin adapters.
- **Draft immediately, send never** is the rule that makes the whole thing safe to
  run unattended.
- **Surface only what needs me.** Digest the fyi/junk; quiet-resolve the no-ops.
  The system's job is to protect my attention, not generate tabs.
- Decide the deliverable per item: **the work is often the deliverable, not a
  message.**

## Suggested build order

1. Stand up the **shared loop + triage rubric + context brain** against ONE
   source with a clean API (Outlook via `ms-graph` is already wired).
2. Prove draft-only + voice loop + clear-to-zero on that source.
3. Add Trello outreach (once-a-day, pure-API queue).
4. Add Gmail / Slack as additional thin adapters.
5. Add presence-gated scheduling last, once the loop is trustworthy by hand.

Build it the way that's cleanest for *this* machine — these are the requirements
and the hard-won lessons, not a blueprint to copy.
