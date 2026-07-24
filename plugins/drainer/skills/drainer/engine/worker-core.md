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
   Make the entry self-explanatory on its own - if the action revealed a detail worth recording (the
   invitee, the requester), put it in the entry text rather than leaving it to the captured body.
   There is **no presentation and no wait-for-acknowledgment**, because nothing was put in front of
   Russell - the digest is how he learns it happened.
5. **Close up as your very last step**, in this order. An auto-handle item has no one to wait for, so
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

   This whole step is **auto-handle only** — a needs-you item never closes up front like this; it stays
   open through the conversation and only closes once the work and any follow-up are genuinely finished
   (see §6 for how it closes its browser tabs and its own session tab at that point).

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

**Always include the item's own deep link alongside the restated text**, every captured item carries
one (`url` in `items/<id>.json` — a Slack permalink, Teams deep link, email `webLink`, Trello
`shortUrl`). Surfacing it costs nothing and means the user can click straight to the source and act
there himself instead of waiting on you — exactly what he'll often prefer for something he can answer
in a line or two. Put it right next to the paraphrase, not buried at the end.

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

**One captured conversation can hold several distinct open asks - group them, then handle each.**
When a chat source keys one item per conversation (a DM, a group chat, an unread channel, a subscribed
thread), the messages waiting since the user's last read may be several separate tasks or one topic typed
across rapid-fire messages - and it takes judgment to tell which. The item stands for the **whole unread
span**, not the single message it is keyed to, so **start by grouping** the unread messages into distinct
asks:
messages that are one train of thought (someone typing fast, or refining the same request across a few
lines) collapse into a single ask; messages on genuinely different topics ("update the graphics" / "post
the case study" / "remove that line") are separate asks. Topic is what decides it, and the timestamps in
the span are a useful tiebreaker: messages seconds or minutes apart lean toward one train of thought, while
a gap of hours or days (you just hadn't drained in a while) leans toward separate asks. You may end with
one group or several - that grouping is your call, made from reading the span. Then handle **each group as its own unit**, exactly as
you would a standalone message or email: do the work, draft any reply. The item is done only when **every**
group is completed, staged as a draft/PR, or explicitly tracked on a follow-up card (per the host
`context.md`), and your reply covers all of them. An ask you leave for "a later item that'll come around"
never comes around: the next section explains why clearing the item drops it for good.

**Email is the same judgment with different mechanics.** A quick "oh, and one more thing" follow-up email
is real, so the one-ask-or-several question applies to email too - but our email sources key one item per
message, so that follow-up arrives as its own item and clearing one email never drops another. So the grouping
here is lighter: when the situational check pulls the thread and you see two of the sender's messages close
together, decide whether they're one ask to answer once or two to handle separately, and don't fire a second
near-duplicate reply for what is really one thing. The load-bearing group-and-guard-before-clearing logic
above is for the chat sources, where several messages collapse into one item behind a single read cursor.

**An ask can hop channels — follow it, don't just re-read where it started.** The channel that carried
the item is not necessarily the channel that carries its resolution. Two patterns to watch for, on any
source:
- **"DM me your X" inside a group chat/channel names a different, private thread** — a 1:1 DM, not the
  group conversation you're already reading. Open that specific 1:1 (e.g. Slack's `conversations.open`
  with the contact's user id resolves it even when you don't already know the channel id) before
  concluding they haven't answered.
- **"Connect person A with person B" is usually carried out over email**, even when the ask itself
  arrived over Slack/Teams or is sitting on a Trello card. Search the mailbox (both directions, per the
  email guidance above) for an intro before assuming that step hasn't happened.
An item whose content describes an ask or a next step is only half-read until you've checked the channel
that ask actually points to — checking only the channel it arrived on and finding silence there is not
the same as confirming nothing happened.

**Also check Trello when the item could be outreach** — an introduction, or a reply from a company or
individual who might already be a tracked contact — regardless of which source it arrived on. Read
`<repo>/trello-boards.yaml` (the registry the `trello` source and `trello-outreach` skill use) for an
existing card naming that company or contact. A match means the item is already tracked: reference the
card in what you present (and consider updating it — bump the due date, add a comment) instead of acting
as if this were unstarted outreach. No match → treat it as genuinely new. This isn't source-specific, so
it applies the same way no matter which provider captured the item.

## 2b. Resolve a pointer — open the real content yourself
This is the shared **open-the-pointer mechanic** every stage uses — `triage.md` defines what a pointer is
and its kinds; a worker resolves needs-you ones here, the digest resolves fyi ones the same way. A pointer
is NOT the content, only a stub. **Open and read the underlying content yourself before doing anything
else**, with the right tool for that surface: a plain fetch when the page is static, and
**browser-chauffeur when the page renders client-side** (a client-rendered page returns only a wrapper
shell to a plain fetch). Summarize the real content as if it had arrived inline. Reading it is YOUR job;
never hand the lookup back to the user ("go read the message yourself").

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
  item's `source` field, and the helper sits at `scripts/seen-state.js` under this skill. Leave the
  source notification for the digest to clear, then **close this tab** (see §2c step 4).

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
4. **Close this tab** - via the Bash tool, run `python <skill>/scripts/close-session.py`
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

**Adopting a card from §2's check claims it the same way Trello's own CAPTURE does.**
When §2's lookup finds an existing Trello card for this item, push its `due` date out (tomorrow or
later, via `trello-outreach` - see `providers/trello-provider.md`'s CAPTURE section) before starting the
work above, not after, so the card can't spawn a second tab on another drain while you're mid-research.
This applies whether Trello is your own source or you found the card from another source entirely.

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

## 6. Advance the item (source-specific)
Only advance when step 3's work is complete — the task/action/deliverable is done. The item is your
task list; it stays in the queue until the work itself is finished, not just until you've drafted a reply.

Clear the item so it doesn't resurface by performing your source's clear/advance — DON'T assume what
that means, read the **CLEAR** op in `providers/<source>-provider.md`.

**The CLEAR is your completion signal - there is nothing else to write.** The keeper reads completion off
the source object itself: an item still sitting unhandled in its source, with no live worker session on
it, is one nobody finished, and the keeper re-queues it for a fresh tab. So an item you CLEAR is done,
and one you leave un-cleared comes back around - which is exactly what you want when the work isn't
finished. Your session stays open after the CLEAR, so when the user replies with new direction you keep
working in the same session and update the source/card again as needed.

If you drafted a reply in step 4 but step 3's underlying work isn't done yet, STOP - do NOT clear;
leave the item as-is so it stays live.

**Never clear while an un-handled open ask remains in the unread span.** For a conversation captured as one
item (§2's multi-ask case), clearing (advancing the read cursor / marking the conversation read) drops
**every** still-unread message under the one you're keyed to, including asks you haven't touched, and they
will not resurface. So before you CLEAR, confirm every ask you grouped out of the span in §2 is completed,
staged, or tracked on a follow-up card. If any remains open, do not clear: handle or track it first, or
leave the item un-cleared so it comes back around. Clearing is the last act after the whole span is
handled, never a per-message step.

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
what you did, and any draft you staged).

## 6a. If the completed work leaves nothing for Russell, self-close like auto-handle
An item can be genuinely `needs-you` at triage time — there really was something to do — and still end
with nothing for Russell to look at, once step 3's work is actually done: a recurring research/bookkeeping
sweep (visit some sources, create or update tracking cards on his own board), a lookup that answered
itself, a form that only needed data he'd already supplied. No pre-existing label or rule predicted this
in advance (that's what `auto-handle` is for, per the branch at the top of this file) — you're only
discovering it now, after doing the work, exactly because some things can't be known until you've done
the situational check or the work itself.

When that's the case, treat the close-out like `auto-handle`'s (steps 4–5 in the branch at the top) even
though this item was never labeled or triaged that way: log what happened somewhere Russell will find it
later — a dated comment on the source item (a Trello card, e.g.), or a digest queue-add. **When you queue
a digest entry, first re-tag the item's `triage` to `"auto-handle"` in `items/<id>.json` (Edit tool)
before the `queue-add` — the same re-tag §2c makes for an FYI downgrade.** This files the entry under the
digest's **"Auto-handled"** section (already done, dismiss-only), so a finished item is shown as handled
rather than resurfacing as a live needs-you. Queue it via
`node <skill>/scripts/seen-state.js queue-add <runtime_dir> <source> <id> <path to items/<id>.json>`,
then close the tab (`python <skill>/scripts/close-session.py`) instead of presenting-and-waiting.

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
completed work that left nothing for Russell (§6a) - likewise close the tab at once
(`python <skill>/scripts/close-session.py`). A silently-resolved tab is just noise in the taskbar;
close it.

**Close your browser tabs when you and the user are truly finished with the item.** If you opened tabs in
the browser (read a card, drove a web composer, clicked through a link), close them as your last act once
the item is genuinely done — the ideal that keeps the browser sweep a rare backstop rather than the norm.
"Done" here is later than the CLEAR: the CLEAR marks the item handled the moment the work is complete, but
your session stays live, and for most needs-you items the user still has a human step to do — send the
draft you staged, submit the form — and you often have follow-up (learning from the send per §5, a tracker
card) once they confirm. Keep any tab the user still needs open through all that. When they've told you
their part is done and you've finished any follow-up, close the tabs you opened: invoke browser-chauffeur
to run `chauffeur.py --close-owned`, which closes only this session's tabs (never the user's, never
another session's, never the browser's last page). If a tab you opened was never something the user needed
to see — its content is already mirrored where they work (a Slack draft that shows in their own Slack) —
close it as soon as that's clear rather than waiting.

**Close your own session tab too, once truly finished — don't wait to be asked.** Apply the same "truly
finished" bar to this tab, not just to browser tabs opened along the way — and the bar is about what's
still *live*, not about whether the eventual outcome has happened yet. The tab and the source item are two
different places to hold state, and the item is always the right one: a delay by itself (a send he's
holding until a stated time, a reply you're waiting on, a step that can't happen until something else
does) is not a reason to keep this tab open — make sure the item resurfaces on its own instead (a Trello
due date, a ⏳ nudge, a calendar reminder), then close now. Once the human step is done (Russell told you
he sent/submitted/confirmed it) and any follow-up you owed is finished (§5's learn-from-send, a tracker
card, advancing the source item) — or once what's left is a delay already tracked on the item rather than
something live — close this tab yourself as your very last act, by invoking the **`session-mgr:close`**
skill. Don't ask "anything else?" and don't wait for him to type `/close` — those two extra round-trips
are exactly what this rule removes. Stay open only when there's something to do right now, or you're
waiting on an answer from him in the next few minutes.

## 7. Improve the source (don't just hoard facts)
If the user had to tell you something you could have known, don't just note it — figure out *where it
should have come from* and improve THAT source so it's findable next time: a system, a skill, or the
internal knowledge source. Only when the shared brain is genuinely the right long-term home does it go
in the local `context.md`; voice feedback goes to the document-authoring skill. The goal is fewer
questions over time because sources got better, not a growing notes pile.
