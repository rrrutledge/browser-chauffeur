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
  `{ id, source, item }`. Each `item` carries `triage` (`fyi` | `junk`), `from`, `subject`,
  `received`, `snippet`, `url`, `messageId`, and `emailFile`. Split it into **fyi** and **junk** by
  `item.triage`.
- **The stale needs-you items:** `node <seen-state.js> stale-list <runtime_dir> <stale_hours>` → a JSON
  array of `{ id, source, ts, ageHours, item }` for every needs-you item still `dispatched` (never
  cleared) and older than `stale_hours`. These are the reconciliation cases — a worker crashed or was
  never finished.
- For richer fyi summaries, read each item's body file (`item.emailFile`, i.e.
  `items/<id>.email.md`) — don't summarize from the snippet alone when the body is right there.

If the queue is empty AND there are no stale items, tell Russell there's nothing to digest and stop.

## 2. fyi — summarize so Russell never has to open the email

Group related fyi items (same thread, same sender, same topic — e.g. a run of GitHub PR
notifications on one PR collapses to one line). For each group write a **rich enough summary that
Russell never needs to open the email**: who/what, the substance (not just the subject), and any
date or number that matters. Link the source with descriptive text per the `document-authoring` voice,
never a bare URL. Order by what's most worth knowing first.

## 3. junk — group by source, each with a source-stop proposal

Group junk by sender/source. For each group, propose **how to stop it arriving again**, in the
provider's **JUNK-LEARNING** priority order (read `<providers_dir>/<source>-provider.md` →
JUNK-LEARNING; for personal-outlook that's: unsubscribe → app notification settings → inbox rule).
Propose, never apply without Russell's OK. Make each proposal concrete (the actual unsubscribe link,
the exact setting, or the exact rule) so Russell can act in one step.

## 4. Reconciliation — re-surface the stale-but-unfinished

List each stale needs-you item with its age, who it's from, the subject, and a one-line note on what
it was waiting for (read its `items/<id>.email.md` if needed). These fell through the cracks; the point
is that they stay visible. For each, offer Russell the choice: **reopen** it (spawn a fresh worker tab
the same way the poller does, or handle it here), or **clear** it as no-longer-needed. Take no
clearing action until he chooses.

## 5. Present, then clear ONLY on Russell's review

Present the whole digest in the terminal — fyi summaries, grouped junk with stop-proposals, and the
stale list — in one readable pass. Then **wait for Russell's go-ahead.** Nothing is disposed of
silently.

On his OK, for **each fyi/junk item he approves clearing**:
1. Read the item's `source` and `messageId` from its `items/<id>.json` (or the queue entry).
2. Run that provider's **CLEAR** op (read `<providers_dir>/<source>-provider.md` → CLEAR; for
   personal-outlook, `node mail.js --delete=<messageId>`, which moves it to Deleted Items —
   reversible; narrate each with a one-line reason).
3. Remove it from the queue: `node <seen-state.js> queue-clear <runtime_dir> <id>`.

For any junk source-stop Russell approves, apply it (unsubscribe / setting / rule) per JUNK-LEARNING.
For a stale needs-you item he wants cleared, run its provider CLEAR and
`node <seen-state.js> clear <runtime_dir> <source> <id>` to mark it cleared in seen-state.

If Russell defers some items, leave them in the queue — they ride to the next digest. Empty only what
he approved.

## Hard rules (carry forward from the engine)

- **Draft-only outbound. Never send, never post.** The digest only summarizes, proposes, and clears
  (delete/archive is reversible). Any reply that a re-surfaced item warrants is drafted, never sent.
- **Clear nothing without Russell's review** — this is the whole point of the digest being interactive.
- **Reversible-only without asking** — CLEAR moves mail to Deleted Items; never a permanent purge.
- **Link to descriptive text, never a bare URL** — route any composed prose through the
  `document-authoring` voice.
