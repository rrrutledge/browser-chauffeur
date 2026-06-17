# drainer driver-core — the driver loop every source's driver follows

A **driver** enumerates its source's queue and works it to empty, **one item at a time**, by
delegating each action-item to its own worker (`worker-core.md`) and waiting for that worker before
starting the next. The driver does NOT do an item's work itself. Each source supplies only its
**source-specific bits** (how to enumerate; how to triage; the per-source "advance" = how an item
becomes "gone"). Read the local `context.md` first.

## The loop
1. **Enumerate** the source's queue (source-specific: inbox newest-first / cards due now-or-earlier /
   unread messages / …). Tell the user how many there are.
2. For each item, in order:
   a. **Triage** per `triage.md` into needs-you / fyi / junk.
      - **needs-you** → its own worker (below).
      - **fyi / junk** → never a worker each; collected and cleared in ONE batched **digest** pass.
        Every junk item is also a signal to stop that junk arriving — propose the source's filter/rule
        so future runs spend tokens and attention only on what matters.
   b. **needs-you → run ONE worker and SERIALIZE:**
      - Capture the item to `<runtime>/<source>/items/<id>` (the data the worker reads off disk).
      - Give the worker the source's `<channel>-worker-prompt.txt` (follow `engine/worker-core.md`;
        SOURCE=…; data is `<id>.json` + payload; ADVANCE = clear per provider; write `<id>.done` last).
      - **Wait for `<id>.done` before the next item** so exactly one item is in front of the user.
3. Keep going until the queue is empty.
4. **Final summary** to the user: what got workers, what was digested, and any proposed source/filter
   improvements.

## One model, cadence matches arrival
There is one model — **drain to zero, always**. The only variable is how often you re-check, which
should match how often new items arrive:

- **Continuous inbound (email, Teams, Slack)** — items can arrive any time, so re-run the full drain
  on a short interval (~10–15 min). Each run takes the source to zero, so it stays effectively at zero.
- **Due-date outreach (Trello)** — cards only come due on a given day, so there's nothing new to find
  more than once a day; re-check daily and advance each due card (nudge / advance / stop) instead of
  deleting.

Same loop either way — just polled as often as new work appears.
