---
skill: drainer
description: Drain human-touch queues to zero — Outlook, Teams, Trello outreach — with one shared loop. For each item: read the thread, do the action it implies (open a PR, file a ticket, run a check, update a system), draft any reply in the user's voice (draft-only, never sent), then clear the item. Use to drain the work inbox / Teams / outreach to zero. Per-machine settings come from .claude/drainer.local.md.
instructions: |-
  ## Drainer

  A **drainer** processes a queue of human-touch items. For each: read the underlying conversation →
  decide the ACTION (reply / do work / nudge / stop / nothing) → DO the doable part now (safe,
  reversible work proceeds; irreversible/outbound-to-others waits for the user's OK) → draft any reply
  in the user's voice **draft-only, never sent** → clear the item. Outlook / Teams / outreach are the
  **same loop over different sources**. The goal is to stay at zero: harvest every source on one
  interval (set for the fastest-arriving source); cheap sources like Trello ride along and surface
  cards only when due.

  ### 1. Load per-machine settings FIRST
  Read **`.claude/drainer.local.md`** in the current project (YAML frontmatter): which `providers` are
  active, per-provider config (e.g. Trello board ids), the harvest interval, presence, and `local_dir`
  (a folder holding `context.md`). If it's missing, copy `templates/drainer.local.example.md` to
  `.claude/drainer.local.md` and help the user fill it in.

  Then read `context.md` (from `local_dir`) and the active providers.

  ### 2. Providers
  Providers live in **`providers/`** next to this SKILL.md — enable the ones you want in
  `drainer.local.md`:
  - `providers/outlook-provider.md` — Outlook on the web (browser).
  - `providers/teams-provider.md` — Microsoft Teams on the web (browser).
  - `providers/trello-provider.md` — outreach boards (uses the `trello-outreach` skill).
  To add a new source, write a provider — see `docs/writing-a-provider.md`.

  ### 3. Follow the engine specs (bundled next to this SKILL.md)
  Canonical and source-agnostic — don't restate them:
  - **`engine/triage.md`** — the one rubric: needs-you / fyi / junk (only three; junk → propose a
    filter so it stops arriving).
  - **`engine/driver-core.md`** — the loop (enumerate → triage → workers for needs-you under a WIP
    limit → digest the fyi/junk). Drain to zero, polled as often as new work appears.
  - **`engine/worker-core.md`** — the per-item worker procedure (read brain → situational-check → do
    the work → draft in voice → learn from the send → advance the item).
  - **`engine/provider.md`** — the interface a provider implements.

  ### 4. Hard rules (always)
  - **Draft-only outbound. Never send, never post, never press Enter to send.** Create drafts
    immediately (reversible); the user edits and sends. Only sending, posting, a permanent purge, or
    destructive system changes wait for explicit OK.
  - **Delete/archive freely without asking** — reversible; narrate each with a one-line reason.
  - **Drafting goes through the `message-draft` skill** (it applies `document-authoring` voice). After
    each send, diff sent-vs-draft and append a lesson to the document-authoring voice loop.
  - **Waiting on someone else → a tracker card** only when *you* initiated and the ball is back in
    their court (via the `trello-outreach` skill). If they initiated and you've replied, you're done.
  - **Lead with context** in every worker; items that need nothing right now resolve quietly.

  Sibling skills used: `message-draft`, `document-authoring`, `trello-outreach`, and
  `browser-chauffeur` for the browser providers.

  ### Docs
  `docs/architecture.md` (the model), `docs/extending.md` (settings + adding sources),
  `docs/writing-a-provider.md` (provider contract with the shipped providers as worked examples).
---
