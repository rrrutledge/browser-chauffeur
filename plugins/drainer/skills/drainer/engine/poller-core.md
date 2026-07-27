# drainer poller-core — the continuous keeper's contract

The drainer runs as a **continuous keeper**: a presence-gated poller runs one short cycle every few
minutes and holds each source at **zero un-started actionable items**. The cycle is a deterministic
algorithm, so it is implemented as a **script** — `scripts/run-poller.py` — not prose an AI re-derives
each run. This doc is the *contract*: what the script does and where AI is (and isn't) used. The full
rationale is in `docs/superpowers/specs/2026-06-17-drainer-continuous-keeper-redesign.md`.

## Where AI is used (and where it isn't)

The script owns everything deterministic. AI is invoked for exactly two things:

1. **One batched triage call per cycle** — `run-poller.py` sends all new items to `claude -p` once and
   gets back a JSON verdict per item (bucket + kind), judged against `engine/triage.md`, the local
   `context.md`, and each provider's AUTO-HANDLE rules. This is the only per-cycle AI cost.
2. **The per-item worker session** — each needs-you (or auto-handle) item opens a worker tab running
   `engine/worker-core.md` (the actual reply/work, draft-only; auto-handle runs the standing rule and
   self-clears without surfacing to the user).

Everything else — presence, enumerate, stable ids, the seen-state check, the concurrency cap, capture,
spawn, record — is code. No AI re-implements the loop.

## What `run-poller.py` does each cycle

`python run-poller.py --repo <project> [--dry-run]`

1. **Presence-gate** (`scripts/presence.py`) — away/locked → exit silently (skipped under `--dry-run`).
2. **Read config** from `<project>/.claude/drainer.local.md`: enabled providers, `runtime_dir`,
   `idle_threshold_seconds`. Also reads `target_open_tabs` from the `DRAINER_TARGET_OPEN_TABS`
   environment variable (default 12) — the only per-cycle throttle in the whole loop (see step 6).
3. **Reconcile** (`reconcile_unhandled()`) — re-queue any email item whose source object is still
   unhandled with no live worker session on it, so it re-enumerates below. See the section after this
   list for the rule and its guards.
4. **Per provider — enumerate everything eligible:** call the provider's enumerate (for outlook-graph,
   `mail.js --list-inbox --json --top=<ENUMERATE_PAGE_SIZE>` — read+unread, newest-first, no time
   window). There is no per-cycle work cap: every cycle asks every source for everything it currently
   has to offer (`ENUMERATE_PAGE_SIZE`, a generous constant in `run-poller.py`, bounds only how many
   rows one API call requests — a technical page size, not a throttle; a backlog bigger than that one
   page just carries into the next cycle). Compute each item's stable id and drop any already in
   seen-state (`scripts/seen-state.js`). Whatever remains all becomes triage/dispatch input this cycle;
   `target_open_tabs` in step 6 is what actually limits how much of it gets worked on at once.
5. **Triage** the new items in one `claude -p` call → bucket (needs-you / auto-handle / fyi / junk) +
   kind + complexity (simple / complex). The triage prompt embeds `engine/triage.md`, the local
   `context.md`, **and each enabled provider's AUTO-HANDLE section** (so the model can recognize a
   standing-rule item; the rules live in the provider docs, surfaced here at triage time).
6. **Dispatch** (deterministic):
   - **needs-you** → if live Claude Code tabs system-wide (`total_claude_tabs()` — every running
     `claude.exe` process: drainer worker tabs, the drainer itself, and any tab Russell opened by hand)
     is below `target_open_tabs`: capture to `items/<id>.json`, spawn a worker tab (`spawn-tab.cmd`)
     **with an explicit model chosen by complexity** (`worker_model` for simple, `worker_model_complex`
     for complex — so a worker never inherits a 1M-context session default the account can't use), then
     record seen **after** the spawn succeeds. At the target: leave it **unrecorded** so a later cycle
     picks it up (throttle + fail-safe). If the live-tab scan itself fails, the throttle is skipped
     entirely for that cycle (fail-safe: never block dispatch just because tabs couldn't be counted).
   - **auto-handle** → capture + spawn a worker tab too (it needs a browser to act), but the worker runs
     the standing rule autonomously and clears the source right away, so it resolves fast and is
     dispatched unconditionally, never throttled by `target_open_tabs`. It's recorded with its own
     `auto-handle` triage; the worker takes worker-core's auto-handle branch (act → CLEAR → queue a
     digest entry → close up) and never interrupts the user. The digest reports it under "Auto-handled."
   - **fyi / junk** → capture, add to the digest queue (`seen-state.js queue-add`), record seen.
7. **Never clear.** Workers clear needs-you on completion; the daily digest clears fyi/junk after review.

## Reconcile: completion is read off the source, not off a receipt

Before enumerating, each cycle runs `reconcile_unhandled()` - the one place the poller decides whether
dispatched work actually finished. The rule is a single observable condition:

> An item whose source object is still unhandled, with no live worker session on it, is not handled.
> Drop its seen key so it re-enumerates.

The success case needs no signal at all: a worker that finished archived the message, so the message is
gone from the inbox and its item is excluded automatically. What is left is work nobody completed, and
one condition covers every way that happens - the tab was closed, the worker died, or its archive call
silently failed. Because the reconcile runs ahead of the enumerate, anything it re-queues is re-dispatched
in the same cycle.

Three guards keep it from re-queuing work that is fine:

- **the digest queue is excluded** - an fyi/junk item sits in the inbox by design until Russell approves
  clearing it at the daily digest, and never had a worker session
- **a live session guid** (`claude --session-id <guid>`, recorded in `seeds/<id>.prompt.txt.session`)
  means a tab is open on the item: being worked, or parked for Russell. Liveness is the whole test -
  an open tab is left alone however long it's up, so there is no timeout.
- **the launch grace** (`orphan_grace_minutes`) covers the window in which a just-dispatched worker
  hasn't written its `.session` file yet and so briefly looks session-less

Both fail-safes point at reconciling nothing rather than re-queuing live work: a process scan that
can't run skips the cycle, and a provider whose inbox listing fails skips that provider (an empty id
set would otherwise read as "every item is archived"). `reconciled.json` memoizes the items already
proven gone from the inbox, so the scan's per-cycle cost stays flat as seen-state grows; deleting it
just makes the next cycle re-derive the set.

**Email only.** `still_in_inbox_ids()` is implemented on the gmail and outlook-graph adapters and returns
`None` everywhere else, so Slack, Teams, Trello and orphan-sessions are skipped and resurface on their
own source's terms. A source with an inbox deeper than the 500-message listing hides its oldest messages
from the check, which costs a missed catch and never causes a wrong re-queue.

**Per-provider isolation + health.** Each provider's enumerate is wrapped: a failure (expired creds,
IMAP/API blip, or a missing helper at adapter-load) raises a typed `ProviderError` that the poller
catches, so one dead source never aborts the cycle — the others still drain. Every cycle records each
provider's outcome to `<runtime_dir>/provider-health.json` (`consecutive_failures`, `last_error`,
`last_error_kind` [`auth` = transient/self-heals, `config` = deploy error], `last_error_ts`,
`last_ok_ts`). Because the poller is headless, this file is how a silently-dead provider becomes
visible: the daily digest reads it and surfaces any provider with a sustained failure streak so Russell
knows to refresh the credential. (Dry-run doesn't write it — it's often run without the live creds.)

**Dry-run** (`--dry-run`) does steps 1–5 and prints a triage report (counts + per-item bucket + intended
action, including any held at the cap) plus the count of items the reconcile would re-queue, with no
spawns, no queueing, no records, no clears, and no re-queues.

## Fail-safe (why "process twice" is fine, "miss once" never happens)

- Seen-state is a separate id store, not the read/unread flag — losing it re-processes (safe).
- A seen-id is recorded only **after** dispatch succeeds — an aborted cycle loses no item.
- Workers are idempotent: a duplicate tab's situational-check resolves quietly. No overlap lock.
- Completion is observed on the source, never reported: an item is done because its source object is
  handled, so a worker that dies, is closed, or fails its own archive call re-queues rather than vanishing.

## Provider-agnostic orchestration
`run-poller.py` reads which providers are enabled from `drainer.local.md` and **dynamically loads each
one's adapter** from `providers/<name>-adapter.py` (beside its prose `providers/<name>-provider.md`).
An adapter implements `provider_base.ProviderBase` — `enumerate` / `stable_id` / `capture` — and is the
only place a source's mechanics live (for outlook-graph: `mail.js`, the Graph id scheme, the captured
item shape). The poller's loop (drop-seen, cap, triage, dispatch, record) holds no source or tool name;
a provider enabled in config without an adapter file is skipped with a note. New sources (Gmail, Trello,
…) plug in by adding an adapter; the triage rubric, seen-state, cap, and worker flow are unchanged.
