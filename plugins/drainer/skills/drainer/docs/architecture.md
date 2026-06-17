# drainer — architecture

A **drainer** takes a queue of human-touch items and, for each: reads the underlying conversation →
figures out the **ACTION** (reply / do work / nudge / stop / nothing) → **does the action** — which
often means actually KICKING OFF the work (open a PR, file a ticket, run a check, update a system),
sometimes BEFORE any reply — and drafts any reply **in the user's voice (draft-only, never send)** →
**advances/clears** the item. The value is figuring out and *doing* the action, not just replying. The
deliverable may be the work itself, not a message. (Irreversible / outbound-to-others steps wait for
the user's explicit OK; safe, reversible work and drafts proceed immediately.)

Inbox / outreach / Teams / Slack / meetings are all the **same loop** with different **sources**. Each
run pulls every item due today-or-earlier and works through them until each is **gone** — "gone" is
per source: an email is **deleted/archived**; a card is **advanced or bumped to a later follow-up
day**. The procedure is identical; the only real difference between sources is **cadence**, and there
are exactly **two modes**:

- **Continuous full-drain** — run the full drain-to-zero loop every ~10–15 min, so the source is
  effectively always at zero. For continuous inbound (email, Teams, Slack); API harvesting keeps the
  queue read cheap enough to run often.
- **Once-a-day due-date drain** — run the same loop once a day over "items due ≤ today," advancing
  each instead of deleting. For due-date sources (Trello outreach).

## Two layers: engine vs. injected

| Engine (this repo — generic) | Injected (each machine, local & gitignored) |
| --- | --- |
| `engine/driver-core.md` — the canonical driver loop | the **providers**: how each source enumerates / captures / clears (API on an API-rich machine; browser as a last resort) |
| `engine/worker-core.md` — the canonical per-item worker procedure | the local **`context.md`** — who the user is, their systems, standing rules |
| `engine/triage.md` — the one classification rubric | the **config** — source registry, board IDs, contact/label vocab, paths, cadence |
| `engine/channel-provider.md` — the provider interface (contract) | **credentials** (Credential Manager / env — never in any repo) |
| `docs/`, `templates/`, generic `utils/` | the orchestration/scheduling glue tuned to the machine |

The engine never contains anything that identifies the user or their organization. See
`docs/extending.md` for exactly where each injected piece plugs in.

## The driver/worker split

- A **driver** enumerates the queue and triages each item; it does NOT do an item's work.
- A **worker** handles ONE item to completion in a fresh context, following `worker-core.md`.
- The driver **serializes**: one item in front of the user at a time, so context stays bounded and
  nothing is half-done. The worker signals completion by writing `items/<id>.done`; the driver blocks
  on that marker before opening the next item.

Prefer a **plain-code controller** as the driver for any API-backed source — the orchestrator is not
an LLM, so it never fills its context however many items there are; the model only does per-item
reasoning inside each worker.

## Triage (the one rubric, shared)

Classify every item by asking **"What does this want the user to do?"** into three buckets — full
rubric in `engine/triage.md`:

- **needs-you** → its **own serialized worker**, one item at a time.
- **fyi / junk** → **never** a worker each; collected and cleared in **one digest pass**, then cleared
  (and junk-learned) on the user's OK. Nothing is disposed of silently.

## Hard behavioral rules (carry these into every machine's `context.md`)

- **Draft-only outbound. Never send, never post, never press Enter to send.** Create drafts
  immediately (reversible); only *sending*, *posting to others*, a *permanent purge*, or *destructive
  system changes* wait for the user's explicit OK.
- **Delete/archive freely without asking** — reversible; narrate each with a one-line reason.
- **Actions-first, situational-check first.** Check whether it's already handled; check the Drafts
  folder before composing.
- **Lead with context** in every worker; **no-op items resolve quietly** (no tab, no beep).
- **One voice brain:** all drafting via `message-draft` (which applies `document-authoring` voice and
  anchors links to descriptive text). After every send, diff sent-vs-draft and append a voice lesson.
- **Waiting on someone else → a tracker card**, always.

## Scheduling requirements (machine-specific glue)

- **Presence-gated** — away/locked → exit cheaply, do nothing.
- **No pile-ups** — an overlap lock.
- **Idle runs make no window and no noise** — a surface appears only for an item to handle or sign-in.
- **Once-a-day sources** use a once-per-day marker.
