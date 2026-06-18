# drainer poller-core — the continuous keeper's contract

The drainer runs as a **continuous keeper**: a presence-gated poller runs one short cycle every few
minutes and holds each source at **zero un-started actionable items**. The cycle is a deterministic
algorithm, so it is implemented as a **script** — `scripts/run-poller.py` — not prose an AI re-derives
each run. This doc is the *contract*: what the script does and where AI is (and isn't) used. The full
rationale is in `docs/superpowers/specs/2026-06-17-drainer-continuous-keeper-redesign.md`.

## Where AI is used (and where it isn't)

The script owns everything deterministic. AI is invoked for exactly two things:

1. **One batched triage call per cycle** — `run-poller.py` sends all new items to `claude -p` once and
   gets back a JSON verdict per item (bucket + kind), judged against `engine/triage.md` and the local
   `context.md`. This is the only per-cycle AI cost.
2. **The per-item worker session** — each needs-you item opens a worker tab running
   `engine/worker-core.md` (the actual reply/work, draft-only).

Everything else — presence, enumerate, stable ids, the seen-state check, the concurrency cap, capture,
spawn, record — is code. No AI re-implements the loop.

## What `run-poller.py` does each cycle

`python run-poller.py --repo <project> [--dry-run]`

1. **Presence-gate** (`scripts/presence.py`) — away/locked → exit silently (skipped under `--dry-run`).
2. **Read config** from `<project>/.claude/drainer.local.md`: enabled providers, `runtime_dir`,
   `max_open_tabs` (default 3), `max_messages_per_cycle` (default 50), `idle_threshold_seconds`.
3. **Per provider — enumerate the new:** call the provider's enumerate (for personal-outlook,
   `mail.js --list-inbox --json --top=<max_messages_per_cycle>` — read+unread, newest-first, **no time
   window**: the keeper drains the whole inbox a batch at a time across cycles). Compute each item's
   stable id, drop any already in seen-state (`scripts/seen-state.js`), and keep up to
   `max_messages_per_cycle` new ones.
4. **Triage** the new items in one `claude -p` call → bucket (needs-you / fyi / junk) + kind +
   complexity (simple / complex).
5. **Dispatch** (deterministic):
   - **needs-you** → if open worker tabs < `max_open_tabs`: capture to `items/<id>.json`, spawn a worker
     tab (`spawn-tab.cmd`) **with an explicit model chosen by complexity** (`worker_model` for simple,
     `worker_model_complex` for complex — so a worker never inherits a 1M-context session default the
     account can't use), then record seen **after** the spawn succeeds. At the cap: leave it
     **unrecorded** so a later cycle picks it up (throttle + fail-safe).
   - **fyi / junk** → capture, add to the digest queue (`seen-state.js queue-add`), record seen.
6. **Never clear.** Workers clear needs-you on completion; the daily digest clears fyi/junk after review.

**Dry-run** (`--dry-run`) does steps 1–4 and prints a triage report (counts + per-item bucket + intended
action, including any held at the cap), with no spawns, no queueing, no records, no clears.

## Fail-safe (why "process twice" is fine, "miss once" never happens)

- Seen-state is a separate id store, not the read/unread flag — losing it re-processes (safe).
- A seen-id is recorded only **after** dispatch succeeds — an aborted cycle loses no item.
- Workers are idempotent: a duplicate tab's situational-check resolves quietly. No overlap lock.

## Provider-agnostic orchestration
`run-poller.py` reads which providers are enabled from `drainer.local.md` and **dynamically loads each
one's adapter** from `providers/<name>-adapter.py` (beside its prose `providers/<name>-provider.md`).
An adapter implements `provider_base.ProviderBase` — `enumerate` / `stable_id` / `capture` — and is the
only place a source's mechanics live (for personal-outlook: `mail.js`, the Graph id scheme, the captured
item shape). The poller's loop (drop-seen, cap, triage, dispatch, record) holds no source or tool name;
a provider enabled in config without an adapter file is skipped with a note. New sources (Gmail, Trello,
…) plug in by adding an adapter; the triage rubric, seen-state, cap, and worker flow are unchanged.
