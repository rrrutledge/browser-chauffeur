# drainer driver-core — the driver loop every source's driver follows

A **driver** enumerates its source's queue and works it to empty by delegating each action-item to its
own worker (`worker-core.md`), under a fixed **work-in-progress (WIP) limit** — when the number of
in-flight workers hits the limit, it waits for one to finish before starting the next. The driver does
NOT do an item's work itself. Each source supplies only its **source-specific bits** (how to
enumerate; how to triage; the per-source "advance" = how an item becomes "gone"). Read the local
`context.md` first.

## The loop
1. **Enumerate** the source's queue (source-specific: inbox newest-first / cards due now-or-earlier /
   unread messages / …). Tell the user how many there are.
2. For each item, in order:
   a. **Triage** per `triage.md` into needs-you / fyi / junk.
      - **needs-you** → its own worker (below).
      - **fyi / junk** → never a worker each; collected and cleared in ONE batched **digest** pass.
        Every junk item is also a signal to stop that junk arriving — propose the source's filter/rule
        so future runs spend tokens and attention only on what matters.
   b. **needs-you → run a worker (respecting the WIP limit):**
      - Capture the item to `<runtime>/<source>/items/<id>` (the data the worker reads off disk).
      - Give the worker the generic `providers/worker-prompt.txt` (it follows `engine/worker-core.md`,
        reads `<id>.json` to find its source/provider, advances per the provider's CLEAR, and writes
        `<id>.done` last).
      - Start it if under the WIP limit; otherwise **wait for any in-flight `<id>.done`** to free a
        slot, then start the next. (WIP = 1 means strictly one at a time; a higher limit runs that many
        workers concurrently — one item per window — and the limit bounds how many face the user at once.)
3. Keep going until the queue is empty.
4. **Final summary** to the user: what got workers, what was digested, and any proposed source/filter
   improvements.

## Scheduling
Harvest **every** source on each run at a single interval, chosen for the fastest-arriving source.
Cheap API sources (Trello, Slack, Graph) cost nothing when they have nothing due, so over-polling them
is harmless and avoids any multi-schedule bookkeeping: a due-date source like Trello simply returns its
due-now-or-earlier items (usually none) and advances any that are due. Pick the interval once; let the
slow sources ride along.
