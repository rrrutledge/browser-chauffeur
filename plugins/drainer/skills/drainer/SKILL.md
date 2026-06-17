---
skill: drainer
description: Drain human-touch queues to zero — email, Teams, Slack, Trello outreach — with one shared loop. For each item: read the thread, do the action it implies (open a PR, file a ticket, run a check, update a system), draft any reply in the user's voice (draft-only, never sent), then clear the item. Use to drain an inbox/Teams/Slack continuously or run the once-a-day outreach drain. Per-machine sources and context come from .claude/drainer.local.md.
instructions: |-
  ## Drainer

  A **drainer** processes a queue of human-touch items. For each: read the underlying conversation →
  decide the ACTION (reply / do work / nudge / stop / nothing) → DO the doable part now (safe,
  reversible work proceeds; irreversible/outbound-to-others waits for the user's OK) → draft any reply
  in the user's voice **draft-only, never sent** → clear the item. Inbox / outreach / Teams / Slack are
  the **same loop over different sources**.

  ### 1. Load per-machine settings FIRST
  Read **`.claude/drainer.local.md`** in the current project (YAML frontmatter). It supplies everything
  machine/user-specific: `local_dir` (folder holding `context.md` + `providers/`), the source registry
  (`channels`), outreach board config, cadence, and presence settings. If it's missing, copy
  `templates/drainer.local.example.md` to `.claude/drainer.local.md` and help the user fill it in.

  Then read, from `local_dir`:
  - **`context.md`** — the user's world, systems, tracker board, and standing behavioral rules.
  - the relevant **`providers/<channel>-channel.md`** for each active source.

  ### 2. Follow the engine specs (bundled next to this SKILL.md)
  These are canonical and channel-agnostic — do not restate them:
  - **`engine/triage.md`** — the one rubric: classify every item as needs-you / fyi / junk.
  - **`engine/driver-core.md`** — the driver loop (enumerate → triage → serialize one worker per
    needs-you item → digest the fyi/junk). Two modes: continuous full-drain, and once-a-day due-date.
  - **`engine/worker-core.md`** — the per-item worker procedure (read brain → situational-check → do
    the work → draft in voice → learn from the send → advance the item).
  - **`engine/channel-provider.md`** — the interface a provider implements.

  ### 3. Hard rules (always)
  - **Draft-only outbound. Never send, never post, never press Enter to send.** Create drafts
    immediately (reversible); the user edits and sends. Only sending, posting, a permanent purge, or
    destructive system changes wait for explicit OK.
  - **Delete/archive freely without asking** — reversible; narrate each with a one-line reason.
  - **Drafting goes through the `message-draft` skill**, which applies `document-authoring` voice.
    After each send, diff sent-vs-draft and append a lesson to the document-authoring voice loop.
  - **Waiting on someone else → a tracker card** (the user's board, via `trello-outreach`).
  - **Lead with context** in every worker; **no-op items resolve quietly** (no tab, no beep).

  ### Dependencies
  See `DEPENDENCIES.md`. Engine-level: document-authoring, message-draft. Behavioral: trello-outreach.
  Provider/machine-level (only for browser-harvesting machines): browser-chauffeur.

  ### Docs
  `docs/architecture.md` (the model), `docs/extending.md` (the four injected pieces),
  `docs/writing-a-provider.md` (add a source, with a worked Graph example), `docs/background.md`
  (principles & lessons).

  ### Run the outreach utilities (Trello)
  `scripts/trello_queue.py` (today's due cards) and `scripts/trello_advance.py` (nudge/advance/stop)
  read board config from `.claude/drainer.local.md` and credentials from the environment.
---
