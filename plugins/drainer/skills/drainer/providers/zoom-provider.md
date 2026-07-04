# zoom provider — Zoom AI Companion meeting summaries (REST)

A provider for **Russell's Zoom meetings' AI Companion summaries**. Each finished meeting's summary
carries a `next_steps[]` list; the ones **assigned to Russell** are his action items. The drainer treats
one meeting as **N action items + 1 recap**: the poller loads the sibling **`zoom-adapter.py`**, which
shells to this project's **`scripts/zoom-meeting-notes-rest.js --drainer-list`** and emits one candidate
per Russell action item (recap folded into each for context) plus one recap candidate for the meeting as a
whole. Implements `../engine/provider.md`; classify by `../engine/triage.md`. id prefix: `zoom-`; body
file: `<id>.zoom.md`.

> Two-file provider: the **reading** mechanics (enumerate, fan-out, stable id, capture-writing) live in
> **`zoom-adapter.py`**, which the poller drives. This doc is the **worker-facing** prose — AUTH-GLANCE,
> the captured item shape, SITUATIONAL-CHECK, CLEAR, JUNK-LEARNING, DRAFT-MODE.

## What is an item
- **action-item** — one `next_steps[]` entry whose **assignee** (the "Name:" prefix) is Russell. This is
  the workable thing: draft a reply, do the work, make the intro. `zoomKind: "action-item"`, `stepText`
  set. Default triage is **needs-you** (open-ended commitments that need judgment/work), but let the rubric
  decide — an item that's purely informational or already done is **fyi**.
- **recap** — the "meeting happened, here's the summary" fact for one meeting. Nothing is asked of Russell
  by the recap itself (his action items are their own items), so it is **fyi** → the digest. `zoomKind:
  "recap"`, no `stepText`.

Only next steps whose **assignee prefix** is Russell are captured — a step like "James: share the script
*with Russell*" is James's task and is skipped (the adapter matches Russell in the "Name:" prefix, not
anywhere in the line).

## Config (in `.claude/drainer.local.md` → `providers.zoom`)
Optional integer knobs (all have defaults; the block can be empty `zoom: {}`):
- `lookback_hours` (default **48**) — how far back each poll looks for meetings. Bounds the API cost; a
  summary older than this is assumed already captured (seen-state dedups it anyway).
- `cooldown_minutes` (default **30**) — a summary is treated as **final** only once its
  `summary_last_modified_time` has been quiet this long. The AI Companion keeps refining a summary for
  tens of minutes after a meeting ends; the cooldown stops the drainer from capturing a half-written
  summary and missing next steps added later.
- `poll_interval_minutes` (default **20**) — self-throttle: the template/instance walk is heavy (dozens of
  API calls), so the adapter skips it if it ran within this window and returns no candidates. Nothing is
  lost — seen-state dedups and the cooldown means a just-finished meeting isn't ready yet anyway.

**Auth** is entirely the node script's job (see AUTH-GLANCE) — no credentials in this block.

## AUTH-GLANCE
Auth is handled inside `scripts/zoom-meeting-notes-rest.js` (Zoom OAuth): it reads the access token from
`<repo>/.tmp/zoom-tokens.json` and **auto-refreshes** it (via `scripts/zoom-token-refresh.js` +
`ZOOM_CLIENT_SECRET` from the environment) when it's near expiry — the same flow the manual report uses.
The adapter surfaces any failure as a provider error, so the poller skips zoom this cycle and the daily
digest flags it. If it stays broken:
1. The refresh token expired (~90 days) — the refresh errors with `invalid_grant`. Do a **full
   re-authorization**: per this project's `CLAUDE.md`, run `node .tmp/zoom-oauth-flow3.js
   --cdp-port=9222` (browser-chauffeur Edge on 9222) to mint a fresh token into `.tmp/zoom-tokens.json`.
2. Never surface a raw "token expired" error to the user — refresh (or re-auth) and retry silently.

## CAPTURE (the item shape the worker reads)
The adapter writes these two files for each dispatched item (`zoom-adapter.py` → `capture`):
- `items/<id>.zoom.md` — header (Meeting, When, Summary doc, Task link, MeetingId, StepId) + (for an
  action item) the **This action item** block + the **Meeting recap** + **All next steps** + **Details**.
- `items/<id>.json` — `{ "id","source":"zoom","triage","kind","zoomKind":"action-item|recap","from",`
  `"subject","received","snippet","url","meetingId","meetingTopic","stepId","stepText","bodyFile","ts" }`.

Load-bearing fields: `meetingTopic` + `stepText` (what the action is), `url` (the Zoom Tasks deep link for
an action item — `tasks.zoom.us?meetingId=…&stepId=…` — else the summary doc), `meetingId` (the occurrence
uuid). `stepId` is a convenience only (it lives solely in the summary HTML and can change as the AI refines
the summary) — never treat it as identity.

## SITUATIONAL-CHECK (do this BEFORE drafting or doing the work)
A summary can be hours or days old by the time it's triaged, so the action may already be handled. Before
acting, check whether it's still open:
- If the action is **send/reply to someone** (an intro, an email, a Slack update): search that channel in
  BOTH directions (did Russell already send it? did they already reply?). For email, search the whole
  mailbox including Archive/Deleted — a prior drain may have swept the thread out of the inbox. Only act on
  what's still open; if it's already done, there's nothing to draft — CLEAR it and move on.
- If the action is **do a piece of work** (prepare slides, check a config, fill a template): confirm it
  isn't already done, then do it (or draft/stage what you can) and present the result.

## CLEAR
Zoom exposes **no public API to mark a Tasks step complete** (the `tasks.zoom.us` links are a UI surface,
not a documented write endpoint). So CLEAR for this source is **internal seen-state only**: recording the
item done (the worker writes `<id>.done`, the poller marks it cleared) means it never resurfaces — a new
meeting summary is a new item, so nothing is lost. This is honest and reversible (losing seen-state just
re-surfaces the item; it's never destructive).

The *real* completion of a Zoom action item happens in its own channel — the email got sent, the doc got
written, the config got checked — and is cleared there if that channel is itself a drainer source.
Optionally, if Russell wants his Zoom Tasks board to reflect reality, the worker can open the item's `url`
(the `tasks.zoom.us` deep link) in **browser-chauffeur** and check the step off by hand — offer it, don't
assume it.

## JUNK-LEARNING
N/A — these are AI-curated meeting action items, not inbound noise. There's nothing to unsubscribe from.
(If a whole class of meeting is never actionable, the lever is upstream — turn AI Companion off for it in
Zoom — not a drainer rule.)

## DRAFT-MODE
There's **no Zoom thread to reply into** — a Zoom action item is a commitment, and its channel is whatever
the action implies, not Zoom. So:
- Most action items are **work** (prepare, check, build) or an **outbound message** to someone.
- When the action is a reply/outbound message, draft it through the **`message-draft`** skill in the
  channel the action implies — usually **`outlook`** (work email) for these, or **`slack`** / **`teams`**
  when the action names that surface ("put an update in Slack"). Draft-only; never send.
- A reply is warranted only after any underlying **work** is done — draft about the outcome, not a promise.
