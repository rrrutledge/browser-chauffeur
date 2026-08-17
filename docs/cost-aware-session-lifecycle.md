# Cost-aware compaction, fresh-session, and handoff triggers

Make a Claude Code tab aware of when it has grown expensive, so compaction, a fresh session, or a
handoff happens on its own rhythm instead of waiting for Russell to direct it each time.

This is a design plan, not an implementation.
It ends at the reviewable design plus the exact edits each change would make.

## The problem, in Russell's words

Russell runs Claude Code as a fleet.
The drainer reads his email, Trello, and Slack and launches worker tabs; he keeps 10-14 tabs open at
once and cycles through them, giving whichever tab is in front of him the next direction.
He does not track, per tab, how deep that session has grown or whether it should compact, clear, or
hand off.
All he holds is "the next thing to work on."

He wants the tabs themselves to notice when it is a good moment to compact, start fresh, or hand off,
so it happens without him deciding it each time.
He does not care whether a tab closes and a new one opens in its place - he only ever looks at whichever
tab is open and responds to it.

The reframe at the heart of this:

> When he asks "should we hand off or keep going here?", the answer is too often "keep going, I already
> have the context loaded." That is a capability lens. It should be a cost-efficiency lens.

## What the data already proved

Parsing every Claude Code transcript (`~/.claude/projects/*/*.jsonl`) established the cost shape that
grounds this design:

- **Cache-read is 95.9% of all tokens.** Cost is dominated by re-reading the existing context every turn.
- **CLAUDE.md is a rounding error** - about 9,150 tokens, roughly 5% of cache-read. Trimming it is not
  the lever, so this design does not touch it.
- **The quadratic is real and concentrated.** Per-turn cost climbs from about $0.077 in short sessions
  to about $0.19 in 120-plus-turn sessions. The 471 sessions over 120 turns (2.4% of all sessions)
  drove about 73% of total spend. The longest individual sessions run 800-1,200 turns at $260-$416 each.
  A handful of marathon sessions is the entire cost story.

The dollar figures are Opus-rate estimates and overstate the absolute total, since many tabs run Sonnet.
The proportions and the quadratic curve are rate-independent.

The conclusion the design builds on: the win is capping how large any one session's context is allowed
to grow, through compaction mid-task and through handing off or starting fresh at task boundaries.

## Why the reframe is literally true

Per-turn cost is close to a direct function of the current context-window size, because cache-read
dominates and the whole context is re-read every turn.
That size only ever grows within a session; it never falls without a compaction or a fresh start.

So "I already have the context loaded" names the exact thing that makes continuing expensive.
The loaded context is not a saving carried forward for free - it is a tax paid again on every turn, and
it rises with each turn that adds to it.
A fresh session or a compaction resets that tax to near zero.
The feeling that the loaded context is a reason to stay is precisely the cost that argues to leave.

## Feasibility: the hook surface, verified

Confirmed against the Claude Code hooks documentation and by directly reading a live transcript:

- **The Stop hook receives `transcript_path` and `session_id` on stdin**, alongside `cwd`,
  `permission_mode`, `hook_event_name`, `effort`, and `last_assistant_message`.
  `close-check.py` already runs on every Stop and already reads this stdin, so the measurement input is
  in hand with no new wiring.
- **The transcript is a per-session JSONL** at `~/.claude/projects/<project>/<session-id>.jsonl`.
  Each assistant message line carries `message.usage` with `cache_read_input_tokens`,
  `cache_creation_input_tokens`, `input_tokens`, and `output_tokens`.
  The current context size is readable from a single line: the most recent usage line's
  `cache_read_input_tokens + cache_creation_input_tokens + input_tokens` is what the next turn will
  re-read. There is no need to sum the whole session; a tail read of the last few kilobytes finds that
  line. On a live 473-line transcript the latest usage line reported about 222,660 cache-read tokens,
  the true live context size, from one line.
- **A hook cannot invoke `/compact`.** Hooks may inject context or block, nothing more.
  So the mechanical layer nudges; the reset itself is taken by the model (which can spawn a fresh tab
  and close its own) or by Russell typing `/compact`.
- **`PreCompact` fires before both manual and automatic compaction** and distinguishes them via
  `compaction_type` (`manual` or `auto`). It can inject a `systemMessage`.
- **There is no context-percentage hook** and no way to read live context utilization from a hook other
  than through the transcript. Auto-compaction fires only near the hard context limit, far past the
  point where a session has already become expensive per turn. Resetting earlier than that limit is the
  whole point, so this design measures from the transcript rather than relying on auto-compaction.

One honest caveat: the docs describe the transcript format as internal and subject to change across
versions.
The design absorbs this the way `close-check.py` already absorbs every error - any failure to read or
parse the transcript skips the nudge silently rather than blocking the turn.
A missing usage field simply means no nudge that turn, never a broken session.

## The design

### 1. Measurement lives in the Stop hook, and it is cheap

Extend `close-check.py` (the existing Stop / UserPromptSubmit hook) to also measure context depth.
On each Stop that passes its existing once-per-real-turn gate, it:

1. Reads `transcript_path` from stdin.
2. Tail-reads the last few kilobytes, walks backward to the most recent line carrying `message.usage`,
   and computes `C = cache_read_input_tokens + cache_creation_input_tokens + input_tokens`.
3. Maps `C` to a band and compares it against the highest band this session has already reached, stored
   in a per-session state file next to the existing `.reminded` flag
   (`~/.claude/close-check/<session_id>.band`).
4. If `C` has entered a new, higher band, appends a single-line cost nudge to the `additionalContext`
   the hook already injects, and records the new band.

The once-per-real-turn gate is the right cadence: it fires exactly when Russell is about to look at the
tab, which is exactly when a nudge should surface.
The band high-water mark means each threshold nudges once, not every turn after it is crossed.
Any read or parse failure skips the nudge and leaves the close reminder untouched.

### 2. Three bands, grounded in the curve

The quadratic bends up past roughly 100-150 turns, which in context-size terms lands around 150-250k
tokens.
The bands (tunable, and worth revisiting after a week of live nudges):

- **Green, below about 120k tokens.** Continue freely; a turn here is cheap. No nudge.
- **Yellow, about 120k to 250k tokens.** Every turn now re-reads a large context. At the next natural
  boundary, prefer a reset. One nudge on entry.
- **Red, above about 250k tokens.** The session is expensive on every turn and is on the path toward the
  marathon sessions that drove most of the spend. Reset actively. One nudge on entry.

### 3. What is automatic, and what is a nudge

Lean automatic only where the mechanism is already transparent and reversible, and the boundary is clean.

- **Auto-handoff at a clean task boundary is safe to do silently**, because Russell does not track which
  tab is open. When a tab has finished its current item, its context is yellow or red, and the next
  direction is a different task, the model spawns a fresh tab seeded with that new task and closes its
  own. A new tab appears carrying the new work; the deep one closes. The daisy-chain machinery for this
  already exists (`launch-session.ps1` to spawn, `close-session.py` / the `session-mgr:close` skill to
  close, the live-session registry so nothing is orphaned). This design adds the trigger and the
  decision, not the mechanism.
- **Everywhere else it stays a one-line nudge** that Russell or the model can act on: the Stop-hook band
  nudge. Compaction can only be a nudge, since a hook cannot invoke `/compact` and only Russell typing it
  (or auto-compaction at the hard limit) performs it.

The dividing line: an auto-handoff is only safe when the current item is genuinely closed and the next
task is clearly unrelated. Anything mid-task, ambiguous, or still in live back-and-forth gets a nudge,
never a silent action, so a live conversation is never thrown away.

### 4. Detecting "this is a different task now"

The tab reads this from Russell's own message.
Because he cycles tabs and hands each one "the next thing," his next direction in a tab is often
unrelated to what that tab was doing.
When context is yellow or red and the new instruction opens a task unrelated to the current one, that is
the strongest reset signal: a fresh task needs none of the accumulated context, so continuing in the
deep tab pays the full context tax for nothing.

This is a judgment the model makes when it reads the new instruction, not a computation the hook does.
The hook supplies the "you are this deep" signal; the model combines it with "is this the same task?"
to choose compact-in-place versus hand-off.

### 5. The decision rule, concrete

The rule that replaces "keep going, I have the context":

1. Read the current context size (the hook surfaces it; the band nudge is the trigger to apply this rule).
2. If the next work is the **same task**:
   - Winding down with little left: just finish. A reset would cost more than it saves.
   - Substantial work remaining and context is yellow or red: `/compact` in place. Compaction keeps the
     needed context and resets the per-turn tax.
3. If the next work is a **different task** and context is yellow or red: hand off to a fresh tab. The
   new task needs none of this context, so paying to carry it is pure waste. At a clean, closed boundary
   this can be the silent auto-handoff; otherwise it is the nudge to hand off.
4. Green context: continue freely regardless of task change. Cheap enough that a reset is not worth its
   own overhead.

The default flips: a long, deep session stops being the path of least resistance, and continuing in one
becomes a choice the tab actively justifies rather than one it falls into.

## Where each change lands

Each rule gets one load-bearing home, so the same guidance is not restated in four places.

| Concern | Home | Change |
| --- | --- | --- |
| Measure context depth every turn, nudge on band crossings | `close-check.py` (OneDrive-backed Stop hook) | Add a tail-read of `transcript_path`, band mapping, a `<session_id>.band` high-water file, and a one-line nudge appended to the existing `additionalContext`. Fail-safe on any read error. |
| The cost-lens decision rule (the reframe, the three bands, compact-vs-handoff, same-vs-different task) | Global `~/.claude/CLAUDE.md` "Handoffs & session model default" section (edit the real target in OneDrive) | Add a subsection reframing keep-vs-handoff as a cost decision, with the crisp rule from section 5. This is the single authoritative statement of the reasoning. |
| The drainer worker's application of it | `plugins/drainer/skills/drainer/engine/worker-core.md` | Where a worker finishes an item and receives an unrelated next task while deep, point at the CLAUDE.md rule and add the drainer-specific auto-handoff trigger. Reference the rule; do not restate it. |
| The shared brain | `~/.claude/drainer/.../drainer-local/context.md` | No new rule. It holds machine-world facts, not session-lifecycle behavior. At most a one-line pointer if worker-core needs it. |

Optional, second phase: a `PreCompact` hook that injects a `systemMessage` noting the session was
compacted and why, so a compaction is visible in the transcript and Russell can see the reset happened.
Not required for the core design.

## Risks and fail-safes

- **Transcript format drift.** The format is internal and may change. Mitigation: the hook treats any
  read or parse failure as "no nudge this turn," never an error, matching `close-check.py`'s existing
  posture. A format change degrades the feature to silence, not to a broken turn.
- **Nudge fatigue.** The band high-water mark fires each threshold once per session, so a deep session
  is not nagged every turn. If the yellow nudge proves noisy in practice, raise its threshold; the bands
  are meant to be tuned after live use.
- **Auto-handoff losing live context.** Bounded to clean, closed boundaries with a clearly unrelated next
  task. Everything else is a nudge. A handoff also seeds the new tab and relies on the live-session
  registry, so no work is dropped even if the spawn races the close.
- **Sonnet tabs.** Absolute dollar figures assume Opus, but the curve and the "reset resets the tax"
  logic hold at any rate, so the design needs no per-model tuning.

## Rollout order

1. The Stop-hook measurement and nudge (`close-check.py`). Self-contained, reversible, observable on the
   next deep session. Ship first and watch the nudges land at real thresholds.
2. The CLAUDE.md decision rule, so the model acts on the nudge with a clear framework.
3. The drainer worker-core auto-handoff trigger, once the nudge and the rule have been seen working
   together.
4. Optional `PreCompact` systemMessage, if a visible record of compaction proves useful.

## Open questions for Russell

- Band thresholds: 120k / 250k are grounded in the curve but are a starting point. Comfortable shipping
  those and tuning after a week?
- Auto-handoff aggressiveness: start with nudge-only everywhere and add silent auto-handoff at drainer
  boundaries in phase 3, or include the silent auto-handoff from the first drainer change?
