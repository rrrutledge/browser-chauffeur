# drainer — architecture

A **drainer** takes a queue of human-touch items and, for each: reads the underlying conversation →
figures out the **ACTION** (reply / do work / nudge / stop / nothing) → **does the action** — which
often means actually KICKING OFF the work (open a PR, file a ticket, run a check, update a system),
sometimes BEFORE any reply — and drafts any reply **in the user's voice (draft-only, never send)** →
**advances/clears** the item. The value is figuring out and *doing* the action, not just replying. The
deliverable may be the work itself, not a message. (Irreversible / outbound-to-others steps wait for
the user's explicit OK; safe, reversible work and drafts proceed immediately.)

Outlook / Teams / outreach are all the **same loop** with different **sources**. Each run pulls every
item due **now or earlier** and works through them until each is **gone** — "gone" is per source: an
email is **deleted/archived**; a Teams chat is **marked read**; an outreach card is **advanced or
bumped to a later follow-up day**.

## Scheduling: always at zero
Each run harvests **every** source and works it to zero, on a single interval chosen for the
fastest-arriving source (Outlook/Teams). Because cheap API sources cost nothing when they have nothing
due, slow sources just ride along: a due-date source like Trello returns its due-now-or-earlier cards
(usually none) and advances any that are due.

## Two layers: the plugin vs. what each machine injects

| In the plugin (generic) | Injected per machine |
| --- | --- |
| `engine/` — driver loop, worker procedure, triage rubric, provider contract | `.claude/drainer.local.md` — which providers are active, per-provider config (Trello board ids), interval, presence |
| `providers/` — the providers (Outlook, Teams, Trello) | `context.md` (in `local_dir`) — who the user is, their systems, standing rules |
| `docs/`, `templates/` | **credentials** (OS store / env) |

The plugin never contains anything that identifies the user or their organization. See
`docs/extending.md` for where each injected piece plugs in.

## The driver/worker split

- A **driver** enumerates the queue and triages each item; it does NOT do an item's work.
- A **worker** handles ONE item to completion in a fresh context, following `worker-core.md`.
- The driver **serializes**: one item in front of the user at a time, so context stays bounded and
  nothing is half-done. The worker signals completion by writing `items/<id>.done`; the driver waits
  on that marker before opening the next item.

## Triage (the one rubric, shared)

Classify every item by asking **"What does this want the user to do?"** into three buckets — the only
three; full rubric in `engine/triage.md`:

- **needs-you** → its **own serialized worker**, one item at a time.
- **fyi / junk** → **never** a worker each; collected and cleared in **one digest pass**, nothing
  disposed of silently. Every **junk** item is a signal to stop it at the source — propose the
  source's filter/rule so future runs spend tokens and attention only on what matters.

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

## Scheduling requirements (machine-specific glue)

- **Presence-gated** — away/locked → exit cheaply, do nothing.
- **No pile-ups** — an overlap lock.
- **Idle runs make no window and no noise** — a surface appears only for an item to handle or sign-in.
- **One interval** for all sources, set for the fastest-arriving one; slow/cheap sources ride along.
