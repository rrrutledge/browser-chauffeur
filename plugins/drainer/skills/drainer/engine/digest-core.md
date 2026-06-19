# drainer digest-core — the once-a-day EOD digest procedure (interactive, reviewed)

The fast loop (`engine/poller-core.md`) never clears fyi/junk — it queues them for this digest. The
digest is the **slow loop**: once a day it empties that queue **with Russell in the loop** and
re-surfaces any needs-you item whose worker never finished. It is the opposite of the poller in one
way that governs everything below: **it is interactive and clears nothing without Russell's review.**

You are a single digest session in your own tab. Your launcher gave you the runtime facts (runtime_dir,
repo, the seen-state helper path, the providers dir, and stale_hours). Everything you read and clear is
under `runtime_dir`.

## 1. Gather (deterministic — just read state)

- **The fyi/junk queue:** `node <seen-state.js> queue-list <runtime_dir>` → a JSON array of
  `{ id, source, item }`. Each `item` carries at least `triage` (`fyi` | `junk`), `from`, `subject`,
  and `snippet`, plus whatever else that provider's capture recorded (e.g. a `url` and the ids its
  CLEAR needs). Split it into **fyi** and **junk** by `item.triage`.
- **The stale needs-you items:** `node <seen-state.js> stale-list <runtime_dir> <stale_hours>` → a JSON
  array of `{ id, source, ts, ageHours, item }` for every needs-you item still `dispatched` (never
  cleared) and older than `stale_hours`. These are the reconciliation cases — a worker crashed or was
  never finished.
- For richer fyi summaries, read each item's captured body when the provider wrote one (its capture
  writes the body alongside `items/<id>.json`) — don't summarize from the snippet alone when the full
  body is right there.

If the queue is empty AND there are no stale items, tell Russell there's nothing to digest and stop.

## 2. fyi — summarize so Russell never has to open the item

Group related fyi items (same thread, same sender, same topic — e.g. a run of GitHub PR
notifications on one PR collapses to one line). For each group write a **rich enough summary that
Russell never needs to open the item itself**: who/what, the substance (not just the subject), and any
date or number that matters. Link the source with descriptive text per the `document-authoring` voice,
never a bare URL. Order by what's most worth knowing first.

## 3. junk — group by source, each with a source-stop proposal

Group junk by sender/source. For each group, propose **how to stop it arriving again**, following that
item's provider **JUNK-LEARNING** section — read `<providers_dir>/<source>-provider.md` → JUNK-LEARNING
and apply the priority order it defines. Propose, never apply without Russell's OK. Make each proposal
concrete (the actual link, setting, or rule the provider's JUNK-LEARNING points to) so Russell can act
in one step.

## 4. Reconciliation — re-surface the stale-but-unfinished

List each stale needs-you item with its age, who it's from, the subject, and a one-line note on what
it was waiting for (read its captured body if needed). These fell through the cracks; the point
is that they stay visible. For each, offer Russell the choice: **reopen** it (spawn a fresh worker tab
the same way the poller does, or handle it here), or **clear** it as no-longer-needed. Take no
clearing action until he chooses.

## 5. Present, then clear ONLY on Russell's review

Present the whole digest in the terminal — fyi summaries, grouped junk with stop-proposals, and the
stale list — in one readable pass. Then **wait for Russell's go-ahead.** Nothing is disposed of
silently.

On his OK, for **each fyi/junk item he approves clearing**:
1. Read the item's `source` and ids from its `items/<id>.json` (or the queue entry).
2. Run that provider's **CLEAR** op — read `<providers_dir>/<source>-provider.md` → CLEAR and use
   exactly what it specifies; narrate each with a one-line reason. CLEAR is reversible by design
   (never a permanent purge).
3. Remove it from the queue: `node <seen-state.js> queue-clear <runtime_dir> <id>`.

For any junk source-stop Russell approves, apply it per that provider's JUNK-LEARNING.
For a stale needs-you item he wants cleared, run its provider CLEAR and
`node <seen-state.js> clear <runtime_dir> <source> <id>` to mark it cleared in seen-state.

If Russell defers some items, leave them in the queue — they ride to the next digest. Empty only what
he approved.

## Hard rules (carry forward from the engine)

- **Draft-only outbound. Never send, never post.** The digest only summarizes, proposes, and clears
  (delete/archive is reversible). Any reply that a re-surfaced item warrants is drafted, never sent.
- **Clear nothing without Russell's review** — this is the whole point of the digest being interactive.
- **Reversible-only without asking** — every provider's CLEAR is reversible by design; never a permanent purge.
- **Link to descriptive text, never a bare URL** — route any composed prose through the
  `document-authoring` voice.
