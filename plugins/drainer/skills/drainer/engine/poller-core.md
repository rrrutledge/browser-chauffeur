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
   `target_open_tabs` (default 12), `max_messages_per_cycle` (default 50), `idle_threshold_seconds`.
3. **Per provider — enumerate the new:** call the provider's enumerate (for outlook-graph,
   `mail.js --list-inbox --json --top=<max_messages_per_cycle>` — read+unread, newest-first, **no time
   window**: the keeper drains the whole inbox a batch at a time across cycles). Compute each item's
   stable id, drop any already in seen-state (`scripts/seen-state.js`), and keep up to
   `max_messages_per_cycle` new ones.
4. **Triage** the new items in one `claude -p` call → bucket (needs-you / auto-handle / fyi / junk) +
   kind + complexity (simple / complex). The triage prompt embeds `engine/triage.md`, the local
   `context.md`, **and each enabled provider's AUTO-HANDLE section** (so the model can recognize a
   standing-rule item; the rules live in the provider docs, surfaced here at triage time).
5. **Dispatch** (deterministic):
   - **needs-you** → if live Claude Code tabs system-wide (`total_claude_tabs()` — every running
     `claude.exe` process: drainer worker tabs, the drainer itself, and any tab Russell opened by hand)
     is below `target_open_tabs`: capture to `items/<id>.json`, spawn a worker tab (`spawn-tab.cmd`)
     **with an explicit model chosen by complexity** (`worker_model` for simple, `worker_model_complex`
     for complex — so a worker never inherits a 1M-context session default the account can't use), then
     record seen **after** the spawn succeeds. At the target: leave it **unrecorded** so a later cycle
     picks it up (throttle + fail-safe). If the live-tab scan itself fails, the throttle is skipped
     entirely for that cycle (fail-safe: never block dispatch just because tabs couldn't be counted).
   - **auto-handle** → capture + spawn a worker tab too (it needs a browser to act), but the worker runs
     the standing rule autonomously and writes `.done` immediately, so it self-clears fast and is
     dispatched unconditionally, never throttled by `target_open_tabs`. It's recorded with its own
     `auto-handle` triage; the worker takes worker-core's auto-handle branch (act → CLEAR → queue a
     digest entry → `.done` now) and never interrupts the user. The digest reports it under "Auto-handled."
   - **fyi / junk** → capture, add to the digest queue (`seen-state.js queue-add`), record seen.
6. **Never clear.** Workers clear needs-you on completion; the daily digest clears fyi/junk after review.

**Per-provider isolation + health.** Each provider's enumerate is wrapped: a failure (expired creds,
IMAP/API blip, or a missing helper at adapter-load) raises a typed `ProviderError` that the poller
catches, so one dead source never aborts the cycle — the others still drain. Every cycle records each
provider's outcome to `<runtime_dir>/provider-health.json` (`consecutive_failures`, `last_error`,
`last_error_kind` [`auth` = transient/self-heals, `config` = deploy error], `last_error_ts`,
`last_ok_ts`). Because the poller is headless, this file is how a silently-dead provider becomes
visible: the daily digest reads it and surfaces any provider with a sustained failure streak so Russell
knows to refresh the credential. (Dry-run doesn't write it — it's often run without the live creds.)

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
only place a source's mechanics live (for outlook-graph: `mail.js`, the Graph id scheme, the captured
item shape). The poller's loop (drop-seen, cap, triage, dispatch, record) holds no source or tool name;
a provider enabled in config without an adapter file is skipped with a note. New sources (Gmail, Trello,
…) plug in by adding an adapter; the triage rubric, seen-state, cap, and worker flow are unchanged.
