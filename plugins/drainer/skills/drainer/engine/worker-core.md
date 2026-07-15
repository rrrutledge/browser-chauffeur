# drainer worker-core — the procedure EVERY worker follows (one item, one tab)

Shared by all drainer sources (email, Teams, Slack, Trello outreach, …) on any machine. A source's
worker prompt should point here and supply only its **source-specific bits** (where the item data is,
and how to ADVANCE it). Everything below is identical across sources.

Throughout this file, `<skill>` means this drainer skill's root folder — the directory containing
the `engine/` folder this file lives in. Your seed prompt pointed you at
`<skill>/engine/worker-core.md` by absolute path, so you already have it; substitute it into the
`<skill>/scripts/...` commands below.

You are working ONE item to completion in your own context. **Draft-only outbound; never send/post.**
(Sending a reviewed draft is a separate, interactive-only step the user triggers later in the top-level
session on an explicit per-message instruction — it never happens inside a worker or an autonomous drain.)
Read the shared brain → situational-check → DO the action → contact the person in the user's voice →
learn from the send → advance the item.

## Branch on triage: `auto-handle` items run autonomously and never wait
Check your item's `triage` field first. If it is **`auto-handle`**, you are executing a **standing rule**
Russell decided in advance — do the action without presenting or waiting, then record it for the digest:

1. **Read the shared brain (step 0)** and your item's data, then **situational-check (step 2)** — confirm
   the action is still pending and the rule still applies (e.g. the button is still there, not already
   approved). If it's already handled, skip the action and go straight to step 3 below.
2. **Confirm the rule matches.** Re-read your source's **AUTO-HANDLE** section in
   `providers/<source>-provider.md` and verify this item meets the named condition exactly. If anything is
   off — the item looks like a near-miss the rule explicitly excludes, or you're not sure — **do NOT act
   autonomously**: treat it as needs-you instead (present to Russell and wait, per the normal flow below).
3. **Execute the action** autonomously (reversible/safe by definition of the rule — e.g. click the
   approve button). Then **CLEAR the source item** per your provider's CLEAR op (mark read / advance), so
   it doesn't resurface.
4. **Queue a digest entry** describing what you did, so the daily digest shows it under "Auto-handled":
   `node <skill>/scripts/seen-state.js queue-add <runtime_dir> <source> <id> <path to items/<id>.json>`
   (same helper as §2b; `<runtime_dir>` is the parent of the `items/` folder). The captured `items/<id>.json`
   already carries `triage: "auto-handle"`, which is how the digest files it in the Auto-handled section.
   If the action revealed a detail worth recording (the invitee, the requester), note it in a sibling
   `items/<id>.done`-adjacent line or rely on the captured body — keep the digest entry self-explanatory.
5. **Write `.done` immediately** — `items/<id>.done` with a one-line result (e.g.
   "auto-handled: approved workspace invite for <email>"). There is **no presentation and no
   wait-for-acknowledgment**, because nothing was put in front of Russell — the digest is how he learns
   it happened. (Same "silent resolution writes `.done` at once" rule as §6.)
6. **Close up as your very last step**, in this order. An auto-handle item has no one to wait for, so
   anything left open just sits there reading "finished" until Russell checks it by hand — exactly the
   interruption auto-handle exists to avoid.
   1. **Your browser tabs** — if you opened any (clicked a button, read a card in the browser), close
      them: invoke browser-chauffeur to run `chauffeur.py --close-owned`, which closes only the
      tabs your session opened (never the user's, never another session's). Cleaning up your own tabs
      here means they never reach the browser sweep.
   2. **Your session tab** — via the Bash tool, run `python <skill>/scripts/close-session.py`.
      It ends the session the way a clean exit would: it fires the SessionEnd hook event first
      (so the live-session registry drops this session instead of listing it as crash-interrupted
      for resume-sessions to resurrect), then kills this tab's process tree (the hosting PID from
      `CLAUDE_HOST_PID`, set by the user's PowerShell profile when this tab launched).
      Never raw-`taskkill` the host PID — a force-killed session dies before SessionEnd can fire.
      If the script reports `CLAUDE_HOST_PID` is unset (a session launched without loading the
      profile), just stop normally — don't hunt for the process.

   This whole step is **auto-handle only** — needs-you items stay open for the user (see §6 for how they
   close their browser tabs).

Everything below (steps 0–7) is the **needs-you** flow — follow it for every item that is NOT auto-handle.

## 0. Read first (shared brain)
- your machine's local **`context.md`** — the user's world, the systems they act in, where things
  live, and standing behavioral rules (draft immediately; delete/archive freely — reversible, no need
  to ask; etc.). This file is machine-local config, not part of the engine (see `templates/context.example.md`).
- the **Voice learning loop** lives in the **document-authoring skill** — append lessons there after each send (step 5).
- your item's data (source-specific — the captured email/message, or the card data + comments).

## 1. Lead with context — especially in the FINAL message
Assume the user has NOT seen the item and may not have seen any of your earlier messages — they
launched you from a drain with zero memory of the thread, and your opening lines often scroll off
before they look. So the **last message before you yield back** is the one that must carry the
briefing: open it by restating **the incoming item itself, before your conclusion** — who messaged,
what they actually said/asked (quote or paraphrase), and any deadline — then what you did and what's
needed. A reader who sees only your final message must understand *why this was in front of them* from
its opening lines. Lead with the same briefing in your first message too, but the final one is the
guarantee. Never a bare "done, nothing to do."

## 2. Situational-check first
Has it already moved or been handled? (PR merged? request done? they replied and the user already
answered?) That changes the right action. For an unknown mechanism internal to the user's
organization, consult the user's designated internal knowledge source first (if their `context.md`
names one) before asking the user directly.

**Read the whole thread, for any source — not just the one message captured.** A captured item's `url`/
`ts` is a pointer into a conversation, not the conversation itself, whichever source it's from (email,
Slack, Teams, a Trello card's linked message). The state at capture time is stale by the time you act on
it: the contact may have replied since, or — easy to miss — the user may have posted their own follow-up
that changes what's actually being waited on (a clarifying question they asked but hasn't been answered
yet turns a "ready to act" item into a blocked one). Before drafting or deciding the move, pull the full
recent thread/history, not just the linked message, and check both directions. If the user's most recent
message on the thread is already a reply to this sender, the item is done — close it without a new draft.
If it's a question of theirs still unanswered, the item is blocked on the other party, not ready to act.
Each provider's SITUATIONAL-CHECK/CAPTURE section describes how to pull full context for that source (for
email: search sent + inbox in both directions; for Slack: `slack.js --history`, not just `--show` on the
one linked message). **When you DO draft (a reply or a follow-up nudge), thread it off the most recent
message in the thread — even when that latest message is one the user sent.** A follow-up answers where
the conversation actually stands, so quote and thread on the newest message, not an older inbound one;
provider DRAFT-MODE notes how to target a sent message.

**Also check Trello when the item could be outreach** — an introduction, or a reply from a company or
individual who might already be a tracked contact — regardless of which source it arrived on. Read
`<repo>/trello-boards.yaml` (the registry the `trello` source and `trello-outreach` skill use) for an
existing card naming that company or contact. A match means the item is already tracked: reference the
card in what you present (and consider updating it — bump the due date, add a comment) instead of acting
as if this were unstarted outreach. No match → treat it as genuinely new. This isn't source-specific, so
it applies the same way no matter which provider captured the item.

## 2b. If the item is a pointer, open the real content yourself
If your item is a **notification that points to content living elsewhere** — a meeting-recording
notice, a forum "you have a reply" — it is NOT the content, only a pointer. **Go open and read the
underlying message yourself before doing anything else**, using the right tool for that surface.
Reading it is YOUR job; never hand the lookup back to the user ("go read the message yourself").

**Exception: LinkedIn/Facebook "X just messaged you" pointers.** Never drive browser-chauffeur to
linkedin.com or facebook.com for any reason — LinkedIn suspended Russell's account for automation in
July 2026. Pull the deep link out of the notification and present it as a clickable link in the
terminal, routed straight to **needs-you** — Russell clicks it and reads/replies himself; you never
open it.

Give him the **direct destination link, not the Outlook item link**. The notification email's "View
message" button routes through Microsoft's Safe Links wrapper (`safelinks.protection.outlook.com/
?url=...`) with tracking params (`lipi`, `midToken`, `trk`, `trkEmail`, `eid`, `otpToken`, etc.)
appended. Fetch the message's raw HTML body (e.g. via `ms-graph`'s Graph client directly — `mail.js
--show` strips tags and loses hrefs) and pull the `href` on the "View message" button — for LinkedIn
that's the `messaging/thread/...` link, identifiable by `trk=...view_message_button` in the wrapped
URL. Decode the wrapped `url=` query param and drop everything from the `?` onward (the tracking
params aren't needed to open the thread), so what you hand Russell is a bare
`https://www.linkedin.com/comm/messaging/thread/<id>` — not the `outlook.live.com` link to the
notification email itself.

Then, for every other pointer, **triage what you find with `triage.md`** (the same rubric the poller
uses, in this engine/ folder), exactly as if that content had arrived as email:
- **needs-you** → proceed through the steps below; stage any reply draft-only in that surface's composer,
  never send.
- **fyi / junk** → do NOT bug the user. Route it to the digest queue so the daily digest handles it
  (junk also gets a source-stop proposal) instead of being lost: run
  `node <skill>/scripts/seen-state.js queue-add <runtime_dir> <source> <id> <path to items/<id>.json>`
  — `<runtime_dir>` is the parent of the `items/` folder your `<id>.json` lives in, `<source>` is the
  item's `source` field, and the helper sits at `scripts/seen-state.js` under this skill. Then go
  straight to step 6 and write `.done`; leave the source notification for the digest to clear. Then
  **close this tab** (see §2c step 5).

## 2c. Re-triage to FYI after content examination
Lightweight triage can't read the body, so a `needs-you` item may turn out to be FYI once you examine
the content — a spam digest, an automated status notice, a confirmation of something that already
happened. When you read the content and determine no action is needed and there's nothing for Russell
to see, close the tab silently:

1. **CLEAR the source item** per your provider's CLEAR op (archive/mark-read), so it doesn't resurface.
2. **Patch `triage` to `"fyi"`** in the `items/<id>.json` file using the Edit tool before queuing, so
   the digest categorizes it correctly (not as needs-you).
3. **Queue a digest entry**:
   `node <skill>/scripts/seen-state.js queue-add <runtime_dir> <source> <id> <path to items/<id>.json>`
4. **Write `.done` immediately** with a one-line reason (e.g.
   "fyi: spam digest — both messages genuine spam, auto-discarded by Google").
5. **Close this tab** — via the Bash tool, run `python <skill>/scripts/close-session.py`
   (fires the SessionEnd event, then kills the tab — see the auto-handle branch's close-up step).
   If it reports `CLAUDE_HOST_PID` unset, stop normally.

Do not present anything to Russell. The digest is how he learns about it.

## 3. Do the action (you do the work WITH the user)
Figure out what the item needs and **DO THE WORK in this session**. You are the implementer, not a
task manager. Opening a PR? You open it. Filing a ticket? You file it. Completing a form? You fill it
out together with the user. Analyzing data? You run the analysis. Writing code? You write it. **The
user guides if needed, but you drive the keyboard.**

Complete the work BEFORE moving to step 4 (drafting a reply). The item stays in the queue as your task
list until the underlying deliverable is done — don't advance to step 6 until the work itself is
complete.

Anything irreversible / outbound-to-others waits for the user's explicit OK; safe, reversible work
proceeds immediately.

## 4. Contact the person (draft-only)
**After step 3's work is complete**, when a message is warranted, stage the draft with the
**message-draft** skill in the source's mode — it writes in the user's voice and owns all composer
mechanics, leaving the draft un-sent. NEVER send. Show the draft text in the terminal, then tell the
user to edit + send it themselves and come back when they have.

If no message is needed (automated reminder, pure action item), skip to step 6.

**Deeply personal messages: don't draft — surface them for the user to write.** When the message is
genuinely personal — a friend venting about their job or boss, a hard life update, grief, family or
relationship matters, anything where the right words depend on shared history you don't have — a staged
draft just gets in the way, because there's no way to know exactly what to say. Skip step 4's draft:
present the item with a tight briefing (who, what they said, any question), do any factual legwork they'd
need (look up the answer to a concrete question they asked), and hand it to the user to compose. You can
ask the user what they'd like to say and offer your read if it helps, but the user writes the message.
Logistical or transactional personal notes (scheduling, a quick info request, a thanks) still get a draft
as usual.

## 5. Learn from the send
When the user says they sent it: fetch the sent version, diff it against your draft, and append a
concrete, actionable lesson to the **document-authoring skill's Voice learning loop**. Briefly tell
them what you learned.

## 6. Advance the item (source-specific) + signal done
Only advance when step 3's work is complete — the task/action/deliverable is done. The item is your
task list; it stays in the queue until the work itself is finished, not just until you've drafted a reply.

Clear the item so it doesn't resurface by performing your source's clear/advance — DON'T assume what
that means, read the **CLEAR** op in `providers/<source>-provider.md`.

If you drafted a reply in step 4 but step 3's underlying work isn't done yet, STOP — do NOT clear;
leave the item as-is and write a "paused" marker instead.

If the situational check finds nothing to do right now (an outreach card that's not yet time to follow
up, or a thread where they replied and the user already answered), resolve it quietly — bump the due
date / clear without surfacing a tab or beep.

**Waiting on someone else → tracker card.** Decide by who's holding the conversation:
- *They* initiated and you've now replied → the ball is in their court by default; you're done, no card.
- *You* initiated, they replied, and you've replied again → the ball is back with them and it's easy
  to lose track. Create a follow-up tracker card (the user's board, per `context.md`) before marking
  done, so it stays visible instead of relying on memory.

**Before presenting, check whether there's anything left TO present** — see §6a. If there genuinely
isn't, self-close there instead of continuing below.

Then **present your result to the user** — give the final briefing (per §1: restate the incoming item,
what you did, and any draft you staged). **Write `items/<id>.done` proactively as soon as you judge the
work complete** — the same turn you present is fine; you need not wait for the user to acknowledge. Use a
one-line result (e.g. "completed: filed ticket #1234 and replied", "skipped: <reason>").

`.done` is your **completion signal**: the keeper reads it next cycle to mark the item cleared in
seen-state, which **frees a slot under the concurrency cap** so a new needs-you tab can open. Free that
slot early — it costs nothing. Your session stays open after `.done`, so when the user replies with new
direction you keep working in the same session and update the source/card again as needed; re-writing
`.done` afterward is harmless. The goal is to keep the queue moving, so a fresh tab can open the moment
the work looks done rather than waiting on acknowledgment. (Tab-close can't be detected reliably, so
`.done` is the advance signal.)

## 6a. If the completed work leaves nothing for Russell, self-close like auto-handle
An item can be genuinely `needs-you` at triage time — there really was something to do — and still end
with nothing for Russell to look at, once step 3's work is actually done: a recurring research/bookkeeping
sweep (visit some sources, create or update tracking cards on his own board), a lookup that answered
itself, a form that only needed data he'd already supplied. No pre-existing label or rule predicted this
in advance (that's what `auto-handle` is for, per the branch at the top of this file) — you're only
discovering it now, after doing the work, exactly because some things can't be known until you've done
the situational check or the work itself.

When that's the case, treat the close-out like `auto-handle`'s (steps 4–6 in the branch at the top) even
though this item was never labeled or triaged that way: log what happened somewhere Russell will find it
later — a dated comment on the source item (a Trello card, e.g.), or a digest queue-add. **When you queue
a digest entry, first re-tag the item's `triage` to `"auto-handle"` in `items/<id>.json` (Edit tool)
before the `queue-add` — the same re-tag §2c makes for an FYI downgrade.** This files the entry under the
digest's **"Auto-handled"** section (already done, dismiss-only), so a finished item is shown as handled
rather than resurfacing as a live needs-you. Queue it via
`node <skill>/scripts/seen-state.js queue-add <runtime_dir> <source> <id> <path to items/<id>.json>`,
write `.done` immediately, and close the tab (`python <skill>/scripts/close-session.py`) instead of
presenting-and-waiting.

**This is judgment, not a checklist — hold the same bar the other silent-resolution cases in this file
already use: unsure → stay needs-you and present as normal (§1).** Self-close here only when ALL of
these are unambiguously true:
- the work is genuinely done (step 3's deliverable is complete, not partial or blocked)
- nothing produced awaits Russell's review, edit, or send — no draft was staged for him (if step 4 staged
  one, this rule doesn't apply; go present it as usual)
- no decision remains that only he could make (which option to pursue, whether to escalate, how to word
  something delicate, whether an ambiguous match is good enough)
- nothing outbound-to-others or irreversible is pending his OK

A card whose entire action was safe/reversible bookkeeping on Russell's own systems — nothing sent,
nothing decided that needed him — is the clearest example, and it applies the same way whether or not
the item happened to carry a label; the worker recognizes it from the finished work, every time, with no
per-item setup required. Most needs-you items still end with the normal step 6 presentation — this rule
is narrower than it looks, and reaches only the cases above.

Items you resolve WITHOUT surfacing them for the user's attention — a pointer re-triaged to fyi/junk
(§2b), a content re-triage to FYI (§2c), a situational no-op close (nothing to do right now), or
completed work that left nothing for Russell (§6a) — likewise write `.done` at once AND close the tab
(`python <skill>/scripts/close-session.py`). A silently-resolved tab is just noise in the taskbar;
close it.

**Close your browser tabs when you and the user are truly finished with the item.** If you opened tabs in
the browser (read a card, drove a web composer, clicked through a link), close them as your last act once
the item is genuinely done — the ideal that keeps the browser sweep a rare backstop rather than the norm.
"Done" here is later than `.done`: `.done` frees the queue slot the moment the work looks complete, but
your session stays live, and for most needs-you items the user still has a human step to do — send the
draft you staged, submit the form — and you often have follow-up (learning from the send per §5, a tracker
card) once they confirm. Keep any tab the user still needs open through all that. When they've told you
their part is done and you've finished any follow-up, close the tabs you opened: invoke browser-chauffeur
to run `chauffeur.py --close-owned`, which closes only this session's tabs (never the user's, never
another session's, never the browser's last page). If a tab you opened was never something the user needed
to see — its content is already mirrored where they work (a Slack draft that shows in their own Slack) —
close it as soon as that's clear rather than waiting.

## 7. Improve the source (don't just hoard facts)
If the user had to tell you something you could have known, don't just note it — figure out *where it
should have come from* and improve THAT source so it's findable next time: a system, a skill, or the
internal knowledge source. Only when the shared brain is genuinely the right long-term home does it go
in the local `context.md`; voice feedback goes to the document-authoring skill. The goal is fewer
questions over time because sources got better, not a growing notes pile.
