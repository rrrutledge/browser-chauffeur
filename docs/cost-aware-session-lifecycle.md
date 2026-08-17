# Cost-aware compaction, fresh-session, and handoff triggers

Make a Claude Code tab aware of when it has grown expensive, so compaction, a fresh session, a handoff,
or delegating to a subagent happens on its own rhythm instead of waiting for Russell to direct it.

This is a design plan, not an implementation.
It ends at the reviewable design plus the exact edits each change would make.

## The problem, in Russell's words

Russell runs Claude Code as a fleet.
The drainer reads his email, Trello, and Slack and launches worker tabs; he keeps 10-14 tabs open at
once and cycles through them, giving whichever tab is in front of him the next direction.
He does not track, per tab, how deep that session has grown or whether it should compact, clear, or
hand off.
All he holds is "the next thing to work on."

He wants the tabs themselves to notice when it is a good moment to reset, so it happens without him
deciding it each time.
He does not care whether a tab closes and a new one opens in its place - he only ever looks at whichever
tab is open and responds to it.

The reframe at the heart of this:

> When he asks "should we hand off or keep going here?", the answer is too often "keep going, I already
> have the context loaded." That is a capability lens. It should be a cost-efficiency lens.

## Why the reframe is literally true

Per-turn cost is close to a direct function of the current context-window size, because cache-read
dominates and the whole context is re-read every turn.
That size only ever grows within a session; it never falls without a compaction or a fresh start.

So "I already have the context loaded" names the exact thing that makes continuing expensive.
The loaded context is not a saving carried forward for free - it is a tax paid again on every turn.
A reset drops that tax to near zero.
The feeling that the loaded context is a reason to stay is precisely the cost that argues to leave.

## What the data proved

Parsing every Claude Code transcript (`~/.claude/projects/*/*.jsonl`) established the cost shape:

- **Cache-read is 95.9% of all tokens.** Cost is dominated by re-reading the existing context each turn.
- **CLAUDE.md is a rounding error** - about 9,150 tokens, roughly 5% of cache-read. Trimming it is not
  the lever, so this design does not touch it.
- **The quadratic is real and concentrated.** Per-turn cost climbs from about $0.077 in short sessions
  to about $0.19 in 120-plus-turn sessions. The 471 sessions over 120 turns (2.4% of all sessions)
  drove about 73% of total spend. A handful of marathon sessions is most of the cost story.
- **The signal is cache-read per turn, not turn count.** This design session was only 71 turns yet cost
  about $20. At turn 16 a roughly 250k-token skill loaded to check one number, then rode the re-read
  prefix on every one of the 55 following turns - per-turn cache-read jumped from about 86k to about
  350k tokens and stayed there. A single large early load (a big skill, a browser-chauffeur DOM dump, a
  large file read) builds a heavy fixed prefix that taxes the rest of the session as much as raw length
  does. So the right thing to watch is cache-read per turn, and the right fix for a heavy-prefix session
  is often "this reference is done, shed it," not "you are deep."
- **Which workflows actually run long** (top ~700 sessions by size, about $26k of spend, classified by
  launching message):
  - **Drainer Trello / outreach workers: about 31%**, the single biggest slice. A card turns into
    browser research plus drafting in one long session.
  - **Handoff-chained sessions: about 20%**, and the longest category at about 337 average turns. A
    handoff starts fresh but becomes its own marathon, so handing off once is not enough - handoff
    sessions need the same reset discipline.
  - Drainer outlook-graph about 10%, digest about 8% (about 284 average turns), zoom about 6%, slack
    about 5%, gmail about 4%.
  - **The drainer fleet as a whole is about 64% of the expensive-session cost.** Job applications barely
    register as long-runners.

The dollar figures are Opus-rate estimates and overstate the absolute total, since many tabs run Sonnet.
The proportions and the quadratic curve are rate-independent.

The conclusion: the biggest, most direct win is to fix how the three heaviest workflows manage their own
context, and to back that with a general per-turn nudge for every other session.

## The four levers, and how to choose

The one question underneath every reset is: **how much of this session's loaded context does the next
chunk of work actually need?**

| Lever | What it does to the context | Best when | What it costs you |
| --- | --- | --- | --- |
| **Subagent** | Runs the work in a separate, fully isolated context; only the distilled result returns to the main session, and the main cache is untouched. | A heavy one-off read or investigation you need one answer from (a big skill lookup, a codebase sweep, a DOM dump). Pre-emptive - it stops the prefix from ever bloating. | You lose the subagent's detailed reasoning; you must phrase the delegation narrowly. |
| **Handoff / fresh tab** | Throws everything away except the seed you write; the new tab starts with a near-zero prefix. | The next work is a **different task** that needs little from here, so a short seed captures it. | You author the seed by hand; anything you forget is gone. |
| **/compact** | Summarizes the conversation and replaces the verbatim history with that summary, then continues the same session; the per-turn prefix shrinks. | The **same task** continues but the context is bloated with dead references or failed tries. | The summary is lossy and unrecoverable once run; you steer it only via `/compact <instructions>`. |
| **/clear** | Wipes the conversation in the same tab, no summary carried forward. | Rarely his best tool - a fresh tab is cleaner and keeps nothing he would miss. | Total loss with no summary; only saves opening a new tab. |

Two rules make the choice concrete:

1. **Is the state the next work needs cleanly expressible in a short seed?** If yes, hand off - the reset
   is total and the seed is cheap. If it is a big fuzzy working state on the same task (what you tried,
   what failed, the half-built thing), compact - it preserves that automatically where a seed would lose
   fidelity. This is the real answer to "why compact instead of a handoff with the info in it": for
   same-task work you often cannot distill the working state into a seed without losing it.
2. **Can the heavy read be foreseen before it pollutes the prefix?** If yes, delegate it to a subagent so
   it never enters the main context. Subagent delegation beats compaction for one-off work, because a
   compact summary is unrecoverable while a subagent's result stays available as normal context.

## Feasibility: the hook surface, verified

Confirmed against the Claude Code hooks docs and by reading a live transcript:

- **The Stop hook receives `transcript_path` and `session_id` on stdin.** `close-check.py` already runs
  on every Stop and already reads this stdin, so the measurement input is in hand with no new wiring.
- **The transcript is a per-session JSONL** whose assistant lines carry `message.usage` with
  `cache_read_input_tokens`. That field on the most recent usage line is the per-turn re-read size
  directly - a tail read of the last few kilobytes finds it, no summing the whole session. On a live
  473-line transcript the latest line reported about 222,660 cache-read tokens from one line.
- **A hook cannot invoke `/compact`.** Hooks may inject context or block, nothing more. So the hook
  nudges; the reset is taken by the model (which can spawn a fresh tab, close its own, or delegate to a
  subagent) or by Russell typing `/compact`.
- **`PreCompact` fires before both manual and automatic compaction** and distinguishes them via
  `compaction_type`. Auto-compaction only fires near the hard limit (about 90% full), far past the point
  where a session is already expensive per turn, which is why this design measures from the transcript
  and nudges earlier rather than relying on auto-compaction.

One honest caveat: the docs describe the transcript format as internal and subject to change.
The design absorbs this the way `close-check.py` already absorbs every error - any failure to read or
parse the transcript skips the nudge silently rather than blocking the turn.

## Track 1 (primary): fix the three expensive workflows

This is where about 64% of the cost lives, so it leads. Each workflow gets in-session guidance that tells
it when to shed context, keyed to its own natural shape rather than to a generic threshold.

### Drainer Trello / outreach worker (about 31%)

The pattern: a card becomes browser research plus drafting in one long session, and browser-chauffeur
payloads (DOM dumps, screenshots) are the likely per-turn driver.

- **Delegate the research read to a subagent.** The heavy company/contact research - the part that reads
  large pages - returns a short brief. The main worker context never carries the raw pages, only the
  brief it drafts from. This is the single highest-leverage change, because it attacks the heavy-prefix
  cause from Finding A directly.
- **Compact after the research phase, before drafting**, when research stays inline. Same task, but the
  research payload is now dead weight; `/compact focus on the drafted outreach and the contact` sheds it.
- Edit home: `plugins/drainer/skills/drainer/engine/worker-core.md` step 3 (do-the-work), plus the
  Trello provider notes, so the research-then-draft shape carries the delegate-or-compact instruction.

### Handoff-chained sessions (about 20%, the longest)

Handing off once resets the prefix, but the fresh session then grows into its own marathon.

- **Carry the reset discipline into the handoff itself.** The handoff-launch guidance in
  `~/.claude/CLAUDE.md` should say the new session inherits the same compact/re-handoff rule, so a
  chained session compacts at its own phase boundaries and re-hands-off when it crosses into a different
  task rather than running unbounded.
- Edit home: the "Handoffs & session model default" section in `~/.claude/CLAUDE.md`.

### The digest (about 8%, about 284 average turns)

A long linear sweep across many items in one context.

- **Split phases into their own tabs, or compact between phases**, so the whole prior sweep is not
  re-read while working the next item. Where a phase is a self-contained read, delegate it to a subagent
  that returns the summarized items.
- Edit home: the digest engine guidance in the drainer plugin.

## Track 2 (backstop): the generic per-turn cache-read nudge

For every session not covered by a tuned workflow, extend `close-check.py` to measure and nudge.

On each Stop that passes its existing once-per-real-turn gate, the hook:

1. Reads `transcript_path`, tail-reads to the latest `message.usage`, and takes `cache_read_input_tokens`
   as the per-turn re-read size `C`.
2. Maps `C` to a band and compares against the highest band this session has reached, stored next to the
   existing flag file (`~/.claude/close-check/<session_id>.band`).
3. On entering a new higher band, appends one line to the `additionalContext` it already injects, then
   records the band. Any read or parse failure skips the nudge.

The once-per-real-turn gate is the right cadence - it fires exactly when Russell is about to look at the
tab. The band high-water mark means each threshold nudges once, not every turn after.

The nudge text matches the cause, not just the depth:

- **Heavy prefix from a one-off load** (a big jump in `C` that then persists): "a large reference is
  riding every turn now - `/compact` to drop it, or delegate that kind of lookup to a subagent next time."
- **Genuinely deep, same task**: "this session re-reads a lot each turn - `/compact` if you are mid-task."
- **Deep, and the next ask is a different task**: "hand off to a fresh tab - the new task needs little of
  this context."

### The bands gate the task-switch signal

The primary signal is the task switch, which the model reads from Russell's own next message - his next
direction in a tab is often unrelated to what the tab was doing. The bands decide whether acting on that
boundary is even worth it:

- **Green, below about 120k per-turn cache-read**: continue freely, even across a task switch. Cheap
  enough that a reset is not worth its own overhead.
- **Yellow, about 120k to 250k**: at a boundary, reset. Different task, short-seedable state → hand off.
  Same task, bloated prefix → compact.
- **Red, above about 250k**: expensive every turn and on the marathon path. Reset actively.

Thresholds are a starting point grounded in the curve, meant to be tuned after a week of live nudges.

## What is automatic, and what is a nudge

Lean automatic only where the mechanism is already transparent and the boundary is clean.

- **Silent auto-handoff at a clean drainer boundary** is safe, because Russell does not track which tab is
  open. When a worker has finished its item, its context is yellow or red, and the next direction is a
  clearly different task, the model spawns a fresh seeded tab and closes its own. The daisy-chain
  machinery exists already (`launch-session.ps1`, `close-session.py` / the `session-mgr:close` skill, the
  live-session registry so nothing is orphaned); this design adds only the trigger.
- **Everywhere else it is a one-line nudge** the model or Russell acts on. Compaction is always a nudge,
  since a hook cannot run `/compact`.

The dividing line: auto-handoff only when the current item is genuinely closed and the next task is
clearly unrelated. Anything mid-task, ambiguous, or in live back-and-forth gets a nudge, never a silent
action, so a live conversation is never thrown away.

## Where each change lands

One load-bearing home per rule, so the same guidance is not restated in four places.

| Concern | Home | Change |
| --- | --- | --- |
| Trello/outreach worker sheds research context | `plugins/drainer/skills/drainer/engine/worker-core.md` (step 3) + Trello provider notes | Delegate the heavy research read to a subagent; compact after research before drafting when it stays inline. |
| Digest sheds prior-phase context | drainer digest engine guidance | Split phases across tabs, or compact/delegate between phases. |
| Handoff-chained sessions keep resetting | `~/.claude/CLAUDE.md` "Handoffs & session model default" | The new session inherits the compact/re-handoff rule so a chain does not become a marathon. |
| The cost-lens decision rule (four levers, the two choice rules, the bands) | `~/.claude/CLAUDE.md` (same section) | The single authoritative statement of the framework; the workflow homes reference it rather than restating it. |
| Measure per-turn cache-read every turn, nudge on band crossings | `close-check.py` (OneDrive-backed Stop hook) | Tail-read `transcript_path`, map `cache_read_input_tokens` to a band, high-water file, one-line cause-matched nudge. Fail-safe. |
| The shared brain | drainer `context.md` | No new rule; at most a one-line pointer. It holds machine-world facts, not session-lifecycle behavior. |

## Risks and fail-safes

- **Transcript format drift.** The format is internal and may change. The hook treats any read or parse
  failure as "no nudge this turn," matching `close-check.py`'s posture. A format change degrades the
  feature to silence, not a broken turn.
- **Nudge fatigue.** The band high-water mark fires each threshold once per session. If yellow proves
  noisy, raise it; the bands are meant to be tuned.
- **Auto-handoff losing live context.** Bounded to clean, closed drainer boundaries with a clearly
  unrelated next task; everything else is a nudge, and the live-session registry means no work is dropped
  if a spawn races a close.
- **Compaction is lossy and one-way.** Where a one-off read can be foreseen, prefer a subagent, whose
  result stays recoverable, over compacting it away.

## Rollout order

1. **The Trello/outreach worker change** (subagent-delegate the research read). Biggest single slice,
   self-contained, and it validates the subagent-delegation lever on the workflow that needs it most.
2. **The CLAUDE.md decision framework** (the four levers and the rule), so every session and every handoff
   shares one reasoning model.
3. **The handoff-chain and digest workflow changes**, once the framework is written to reference.
4. **The generic Stop-hook nudge** as the backstop across all other sessions.

## Open questions for Russell

- Band thresholds (120k / 250k per-turn cache-read) are grounded in the curve but are a starting point.
  Ship those and tune after a week?
- Auto-handoff aggressiveness: start nudge-only everywhere, or include the silent drainer auto-handoff
  from the first worker change?
