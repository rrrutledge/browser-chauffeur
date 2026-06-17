# drainer driver-core — the driver loop every source's driver follows

A **driver** enumerates its source's queue and works it to empty, **one item at a time**, by
delegating each action-item to its own worker (`worker-core.md`) and waiting for that worker before
starting the next. The driver does NOT do an item's work itself. Each source supplies only its
**source-specific bits** (how to enumerate; how to triage; the per-source "advance" = how an item
becomes "gone"). Read the local `context.md` first.

## The loop
1. **Enumerate** the source's queue (source-specific: inbox newest-first / due cards ≤ today / unread
   messages / …). Tell the user how many there are.
2. For each item, in order:
   a. **Triage** per `triage.md` — does it need a worker (a real action: reply / do work / outreach),
      or is it a no-action item the drain clears without its own worker? No-action classes are
      source-specific (continuous channels: fyi/junk → collected and cleared in ONE batched **digest**
      pass, never a tab each. outreach: no-op → silently bump the due date).
   b. **Action items → spawn ONE worker and SERIALIZE:**
      - Capture the item to `<runtime>/<source>/items/<id>` (the data the worker reads off disk).
      - Write `<id>.prompt.txt` = a THIN worker prompt: "follow `engine/worker-core.md`; SOURCE=…;
        your data is `<id>.json` (+ payload); your ADVANCE = <clear per provider>; write `<id>.done`
        as your final step."
      - Delete any stale `<id>.done`, then spawn the worker.
      - **Wait for `<id>.done` before the next item.** When the driver is a plain-code controller
        (the preferred shape for any source with an API), serialization is handled in code — the
        controller blocks on the file. When the driver is an LLM session, poll a blocking wait.
3. Keep going until the queue is empty.
4. **Final summary** to the user: what got workers, what was disposed inline, and any proposed
   rule / source improvements.

## Executor choice (per source)
- **API-backed sources** → a plain-code controller (no LLM in the orchestration loop), so it never
  fills its context no matter how many items. This is the default and preferred shape on a machine
  with API/MCP access — enumerate, triage, and advance are ordinary code; the model is reserved for
  per-item judgment inside the worker.
- **No-API sources** → the driver may have to be an LLM session (e.g. when enumerating the queue
  itself requires browser reading). Same contract, heavier executor.

## Two modes (the only two)
The same loop runs in exactly two cadences; pick per source:

- **Continuous full-drain (the always-at-zero mode).** Run the full loop every ~10–15 min: a harvester
  sorts the queue into needs-you vs fyi/junk; the controller spawns one serialized worker per
  needs-you item (blocking on each `<id>.done`); then ONE **digest** pass clears all the fyi/junk.
  Because it takes the source to zero each run and runs often, the source is effectively always at
  zero. This is the mode for continuous inbound — email, Teams, Slack. API harvesting keeps the queue
  read cheap, so run the full drain on a short interval.
- **Once-a-day due-date drain.** Run the same loop once a day over "items due ≤ today," advancing each
  (stage / due / stop) instead of deleting. This is the mode for due-date sources — Trello outreach.
