# drainer digest-core — the once-a-day EOD digest procedure (interactive, reviewed)

The fast loop (`engine/poller-core.md`) never clears fyi/junk — it queues them for this digest. The
digest is the **slow loop**: once a day it empties that queue **with Russell in the loop** and
re-surfaces any needs-you item whose worker never finished. It is the opposite of the poller in one
way that governs everything below: **it is interactive and clears nothing without Russell's review.**

Before this interactive session even opens, the launcher (`run-digest.py`) runs one silent,
deterministic step: a CLEAR-verification sweep (`reconcile_cleared`) that checks every needs-you item
already marked `cleared` against the live mailbox, in case a worker's archive call silently failed
despite writing `.done`. Anything still physically present gets reset for a fresh poller pass — no AI,
nothing shown to Russell here. That's a different case from step 4 below (a worker that never finished
at all); this doc's reconciliation section only ever sees the dispatched-but-stale kind.

You are a single digest session in your own tab. Your launcher gave you the runtime facts (runtime_dir,
repo, the seen-state helper path, the providers dir, the provider-health file, and stale_hours).
Everything you read and clear is under `runtime_dir`.

## 0. Provider health — surface any stuck source FIRST (the headless poller can't)

The fast-loop poller runs headless (no console — its output is discarded), so a provider whose
credential expired fails **silently** every cycle and would never reach Russell. This daily digest is
the guaranteed-visible channel that closes that gap. Before anything else:

- Read `<runtime_dir>/provider-health.json` (missing/empty → all providers healthy; say nothing).
  It maps each provider to `{ consecutive_failures, last_error, last_error_kind, last_error_ts,
  last_ok_ts }`.
- Report **at the very top of the digest** every provider with `consecutive_failures >= 2` (one stray
  failure is just a blip; a sustained streak means it's stuck). For each, give Russell a one-step fix:
  - Name the provider, when it last drained (`last_ok_ts`) and how many cycles it's been failing.
  - Quote `last_error` and read it as the action to take, keyed off `last_error_kind`:
    - **`auth`** (transient — self-heals once creds are refreshed): name the likely credential and how
      to refresh it. gmail → `GMAIL_APP_PASSWORD`; slack → `SLACK_BOT_TOKEN` / `SLACK_COOKIE_D`;
      outlook-graph → re-auth the ms-graph token cache; trello → `TRELLO_API_KEY` / `TRELLO_TOKEN`.
      All are User-scope env vars — refresh, and the next poller cycle recovers on its own.
    - **`config`** (a helper script/util couldn't be located — won't self-heal): flag it distinctly as a
      deploy problem, not an expired credential — the adapter can't find its `*.js`/util, likely a
      missing or mis-pointed plugin install.
  - Example: *"⚠️ **gmail** hasn't drained since 2026-06-19 14:05 — 38 cycles failing: `gmail enumerate
    failed (auth/IMAP?): …`. Likely an expired GMAIL_APP_PASSWORD (User-scope env var) — refresh it and
    the next cycle recovers."*

This is informational — there's nothing to clear. It just makes a silently-dead provider impossible to
miss. Then continue to the queue below.

## 1. Gather (deterministic — just read state)

**Snapshot once — work the batch, don't chase the queue.** Take the `queue-list` and `stale-list`
results below at the start of the run as *the* batch for this digest, and process only that fixed set.
The headless poller keeps draining in the background — anything it adds *after* this snapshot belongs to
the **next** daily digest, so leave those items to ride. Re-run `queue-list` only to confirm what you've
already cleared, never to pull freshly-arrived items into the current pass. A digest ends when the
snapshot it opened with is handled, not when the live queue happens to read empty.

- **The digest queue:** `node <seen-state.js> queue-list <runtime_dir>` → a JSON array of
  `{ id, source, item }`. Each `item` carries at least `triage` (`fyi` | `junk` | `auto-handle`), `from`,
  `subject`, and `snippet`, plus whatever else that provider's capture recorded (e.g. a `url` and the ids
  its CLEAR needs). Split it by `item.triage` into **fyi**, **junk**, and **auto-handle** (the last is
  what a worker already did on its own — see step 2b).
- **The stale needs-you items:** `node <seen-state.js> stale-list <runtime_dir> <stale_hours>` → a JSON
  array of `{ id, source, ts, ageHours, item }` for every needs-you item still `dispatched` (never
  cleared) and older than `stale_hours`. These are the reconciliation cases — a worker crashed or was
  never finished.
- For richer fyi summaries, read each item's captured body when the provider wrote one (its capture
  writes the body alongside `items/<id>.json`) — don't summarize from the snippet alone when the full
  body is right there.

If the queue is empty AND there are no stale items AND no provider is stuck (step 0), tell Russell
there's nothing to digest and stop. A stuck provider alone is still worth reporting — surface it even
when the queue is otherwise empty.

## 2b. Auto-handled — report what Claude already did (no decision needed)

Items a worker resolved autonomously — either under a provider **AUTO-HANDLE** rule (e.g. an approved
Slack workspace invite) or by finishing a needs-you item's work and self-closing it (§6a of worker-core,
re-tagged `auto-handle` on the way into the queue). The action and the source-clear are **already done**
— this section is purely so Russell *sees* what happened, never to ask him to act. Present it as a distinct **"Auto-handled"**
section (separate from fyi), one line each: what was done and the key detail (e.g. "Approved workspace
invite for *jane@acme.com* (requested by Bob)"). Order most-notable first. On Russell's review these need
**no provider CLEAR** (the worker already cleared the source) — just `queue-clear` them like the rest
(step 5). If something here looks wrong — a rule fired when it shouldn't have — flag it so the AUTO-HANDLE
rule can be tightened; that's the one case where an auto-handled item needs follow-up.

## 2. fyi — summarize so Russell never has to open the item

Group related fyi items (same thread, same sender, same topic — e.g. a run of GitHub PR
notifications on one PR collapses to one line). For each group write a **rich enough summary that
Russell never needs to open the item itself**: who/what, the substance (not just the subject), and any
date or number that matters. Link the source with descriptive text per the `document-authoring` voice,
never a bare URL. Order by what's most worth knowing first.

**Before framing any item as still needing Russell** — an open ask, an awaited reply, anything that
implies he still owes a response — run that provider's **SITUATIONAL-CHECK** first (search Sent +
Drafts; read `<providers_dir>/<source>-provider.md` → SITUATIONAL-CHECK). The captured snippet is the
*original inbound* message, and the conversation has usually moved on. If Russell (or a teammate on his
behalf) already replied after the captured message, present it as **✅ already handled** or drop it from
the summary entirely — never list it as a to-do. Summarize as actionable only what the situational
check confirms is still open. Do not append a speculative "things still to do" list assembled from
unverified captured snippets — that is exactly how an already-answered thread gets re-surfaced as if it
needs attention.

## 3. junk — group by source, each with a source-stop proposal

Group junk by sender/source. For each group, propose **how to stop it arriving again**, following that
item's provider **JUNK-LEARNING** section — read `<providers_dir>/<source>-provider.md` → JUNK-LEARNING
and apply the priority order it defines. Propose, never apply without Russell's OK. Make each proposal
concrete (the actual link, setting, or rule the provider's JUNK-LEARNING points to) so Russell can act
in one step.

This step's proposal, and his go-ahead on it in step 5, approve **building a rule for this type of
junk** — they are not approval of a rule's literal text. When the chosen stop is a mail rule, creating
or appending it always routes through the provider's JUNK-LEARNING section, which in turn requires the
**`mail-filters`** skill's show-literal-rule gate: show Russell the exact phrase(s), the bucket they land
in, and the action, and create only on his explicit OK of that shown text.

## 4. Reconciliation — re-surface the stale-but-unfinished

List each stale needs-you item with its age, who it's from, the subject, and a one-line note on what
it was waiting for (read its captured body if needed). These fell through the cracks; the point
is that they stay visible. For each, offer Russell the choice: **reopen** it (spawn a fresh worker tab
the same way the poller does, or handle it here), or **clear** it as no-longer-needed. Take no
clearing action until he chooses.

## 5. Present, then clear ONLY on Russell's review

Present the whole digest in the terminal — any stuck-provider health alerts (step 0) at the very top,
then the **Auto-handled** section (step 2b), fyi summaries, grouped junk with stop-proposals, and the
stale list — in one readable pass. Then **wait for Russell's go-ahead.** Nothing is disposed of
silently.

For **each auto-handled item** (already actioned + source-cleared by its worker), on his OK just remove
it from the queue: `node <seen-state.js> queue-clear <runtime_dir> <id>` — no provider CLEAR.

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
