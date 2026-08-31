---
name: session-shapes
description: The worked catalog behind the "reach for the subagent lever" trigger in the global Handoffs section - the recurring shapes a working session takes, the earliest in-session tell for each, and whether its mechanical middle belongs in a fresh subagent, a context-inheriting fork, or stays live with Russell. Reach for it when a session's shape is ambiguous, when deciding whether a stretch of work should be isolated, or when tuning the trigger itself.
---

# Session shapes: where the mechanical middle belongs

The four levers in the global `~/.claude/CLAUDE.md` "Handoffs & session model default" section say how to reset a session.
This is the catalog beneath the trigger that lives there: the recurring shapes a session takes, the earliest signal each one gives, and where its mechanical stretches go so the main thread never carries them.
Recognition is ambient - the point is to act on a shape the moment it declares itself, without being asked.

## The one fact underneath every shape

A costly session is a handful of genuine human-decision points bracketing wide stretches of mechanical work Russell never watches.
Each such stretch re-enters the main context and is re-read on every later turn, so a session that runs into the hundreds of turns pays for its whole middle hundreds of times over.
The move is to keep each stretch out of the main thread from the start, so the thread holds the conclusion and not the derivation behind it.
Across a recent month of real sessions, effectively all of the token cost sat in main-session context and almost none in subagents, while the top sessions carried three or four human-relevant turns against hundreds of mechanical ones - the subagent lever is the one already sitting unused.

## The in-flight tell, and where the stretch goes

The recognizable moment is the second or third consecutive same-shape mechanical action with no human turn between them:
another Read/Grep/`git show` while the search is still open, another build-and-render round on one artifact, another browser script, another pass over one item of a list.
That run is process, not signal.
Route it by what it needs to do its job:

- **Self-contained from a short brief goes to a fresh subagent.**
  A scoped investigation that returns "the cause is at X, here is the fix."
  An autonomous browser run against an already-signed-in profile that returns pass/fail, a screenshot, and any step staged up to its irreversible button.
  One item of a fan-out.
  A draft a codified skill can regenerate from a few parameters.

- **Needs this session's accumulated state goes to a context-inheriting fork.**
  One more build round on an artifact whose spec has been shifting all conversation.
  A cross-file design too large to hold in a single reading.
  A fork inherits the loaded context cheaply through the shared cache, so it continues from where the thread already is without a hand-written brief.

- **Genuine judgment, a login or click the run cannot perform headless, or the final irreversible press stays live with Russell.**
  The mechanical work bracketing that decision still goes to an isolated agent; only the decision itself stays.

## Reading the shape from the opening

The seed or the first human turn usually names the shape before any tool has run - recognize it there and the middle never bloats in the first place.

- A seed enumerating several independent deliverables ("three improvements, each its own PR") is a **fan-out**: one fresh subagent per item, the way the drainer already scatters one headless worker per inbox item.
- A seed framing one coherent fix ("a durable fix so the config is always read from X") is a **single cross-file design**: one fork behind a plan-mode gate, so the design decision is settled up front and the middle runs as clean execution.
- An "investigate" or "understand" seed whose first human reply is a question back rather than an approval is an **open-ended design conversation**: the discussion stays live with Russell, and every fact-gather or render it spawns goes to a subagent.
- An enumerated task list or a handoff resume is **execution**: isolate the mechanical middle, surface only the decisions and the steps staged up to an irreversible button.

## The six shapes

Each is grounded in a real recurring session on this system.

### 1. Iterative single-artifact workshop loop
Draft, react, revise - the same one artifact reshaped round after round against Russell's running judgment (a mismatch-audit report rebuilt until it said the right thing).
Most of the turns are the mechanical rebuild-and-render between his reviews.
**Routing:** fork-friendly. Each round's build leans on the context accumulated so far, so a fork runs the round and hands back the rendered artifact, while the loop itself stays live because his judgment gates every round.
**Sub-case:** when a codified skill already produces the artifact (a sponsorship agreement from the sponsorship-invoice skill), it is fresh-subagent-friendly - a short brief regenerates the draft.
**Tell:** the first request to build, then iteratively refine, one rich standalone artifact.

### 2. Fan-out over independent items
One small judgment repeated across a list of unrelated items (the drainer over an inbox; a batch of independent PRs).
**Routing:** one fresh subagent per item. The items share no design state, and a per-item seed carries each item's whole context - which is why the drainer runs each as its own headless process rather than a shared session.
**Tell:** an opening that enumerates independent deliverables.

### 3. Single coherent cross-file deliverable
One indivisible design decision spread across several files (making a config read from the merged tree instead of a stale branch).
**Routing:** not fan-outable - the pieces are coupled. Run the whole as one fork behind a plan-mode gate, so the design is approved before the mechanical implementation begins and the middle stays clean.
**Tell:** a single-problem framing, and a first human turn that interrogates the design ("are these files actually checked in, and why does it matter?") before approving.

### 4. Long investigation into a small edit
A wide search - `git show` archaeology, greps, fixture reviews - converging on a tiny diff (finding where a rubric lived, then tuning a few lines of skill prose).
**Routing:** fresh-subagent-friendly, the canonical case. The investigation returns "the cause is at X, here is the fix" or a finished draft PR; the whole retune loop collapses to one hand-back.
**Tell:** the second or third consecutive `git show`/grep/read with no edit yet and no human turn between.

### 5. Autonomous browser multi-step verification
A long series of browser scripts and screenshots whose only durable output is one pass/fail and any staged irreversible step (driving a vehicle-registration portal to the pay button, then confirming a repeating lockout).
**Routing:** fresh-subagent-friendly when the profile is already authenticated - the run returns pass/fail, a screenshot, the step staged up to its button, and any escalation finding.
**Exception:** a run that needs Russell's live logins or in-page clicks partway through cannot detach - it stalls at every gate, so it stays live. The discriminator is whether the run needs live human interaction, not that it drives a browser.
**Tell:** the second or third consecutive browser script plus diagnostic screenshot with no human turn between.

### 6. Open-ended research or design conversation into a deliverable
A question with no bounded deliverable that slowly hardens into one artifact (a Medicaid-care Q&A that became a one-page PDF; this very design study).
**Routing:** the discussion stays live - it is Russell's own learning-and-judgment loop, and only he knows when it has converged. Every fact-gather, web search, and render it spawns goes to a subagent, so the thread holds the conclusions and not the research behind them.
**Tell:** an "investigate/understand" seed, and a first human reply that is a clarifying question back rather than an approval.
When an execution session's human starts asking *why the system behaved as it did* rather than accepting the output, that session is turning into this shape.

## The exit tell: do not outlive the deliverable

A session that has finished its deliverable, or is now only waiting on an external party, pays its full context re-read on every later wake - and a Trello- or drainer-seeded tab left open across multi-day gaps does exactly that.
Re-hand-off at the phase boundary when the work crosses into a sibling task, or park the next step on its Trello card and close when the block is external (as a newsletter session correctly deferred to its card while waiting on sponsors), rather than hold the fat tab open.

## The guardrail this never touches

This is about token and context placement only.
Irreversible actions and genuine judgment calls stay with Russell no matter where the mechanical work runs, exactly as the global "Stage anything irreversible" rule requires - isolating the middle never moves a send, a submit, or a final button off his desk.
