# trello provider — outreach boards (Trello API)

A provider for the **outreach** source. The card's **go-live date IS the queue**: harvested on
every run like any other source, it returns cards that are startable now — Start now-or-earlier, OR
Due now-or-earlier, OR undated — and not wearing a ⛔ Blocked label. Outreach cards set no Start, so
they queue purely on their **due date** (the follow-up date) exactly as before. Task cards use the
**startable model** (see STARTABLE-TASK MODEL): Start = the "work-on-it-next / ping-back" date, Due =
a real deadline. It rides the single schedule with no special cadence. All Trello reads and mutations
go through the **`trello-outreach`** skill (don't reimplement the Trello API here). Implements
`../engine/provider.md`; classify by `../engine/triage.md`. id prefix: `trello-`.

## Config
- **Boards** — the single source of truth is `<repo>/trello-boards.yaml` (a `boards:` list of
  `{name, id}`), the same registry the `trello-outreach` skill reads. The drainer drains **every** board
  in it, so adding a board is a one-file edit. (Legacy fallback: a `providers.trello.boards` list in
  `.claude/drainer.local.md` if no registry file exists.)
  - **Format the adapter parses:** the poller runs on bare stdlib Python (no PyYAML), so the adapter
    extracts boards by a fixed indent convention rather than full YAML — each board is `  - name:` at
    **two-space** indent with its `    id:` at **four-space** indent. Keep that shape. Any deeper
    per-board fields (`purpose`, `template_cards`, …) are free-form and ignored by the drainer.
- **Initiatives** — shared outreach programs many cards belong to. The **registry is the
  `initiatives/` folder** in the repo: one `initiatives/<slug>.md` per program (a file existing ⇒ the
  initiative exists — no central list to maintain). The file either holds the content inline or, via a
  `source:` frontmatter pointer, redirects to where the content lives (a Confluence/other URL). See
  `initiative-doc-template.md` (in this skill) for the two shapes — source-stub vs inline-content. A
  card is tagged with an initiative two ways (a per-card
  tag wins over the board default):
  - **Per-card** — a Trello **yellow label** (yellow is the initiative color). The adapter resolves it:
    label name → slug → `initiatives/<slug>.md`. The yellow label is held out of contact
    classification, so it's never mistaken for a contact name.
  - **Board default** — an `initiative: <slug>` field on a board entry in `trello-boards.yaml` (every
    card on that board inherits it — best when the whole board is one program). The four-space
    `initiative:` field is parsed by the adapter alongside `id`.
  The adapter writes the resolved slug as `initiative` on the item. See INITIATIVE-LOOKUP for loading
  the content and STAGE-PLAYBOOK for the generic per-stage activity.
- Drainer knobs in `.claude/drainer.local.md` → `providers.trello`:
  - `skip_lists` — terminal/parking lists to ignore (e.g. Abandoned, Finished, Adopted, Templates).
  - `skip_labels` — labels whose cards are suppressed (default `[Blocked]` → hides ⛔ Blocked cards).
    Matched as a case-insensitive substring, so `blocked` catches `⛔ Blocked`.
  - `status_labels` — dependency-state labels held out of contact classification (default
    `[Blocked, Waiting]`), so a ⛔/⏳ label is never read as a person's name.
  - `label_vocab` — `{channels: [...], features: [...]}`; any label not in those is a contact name.
Credentials: `TRELLO_API_KEY` / `TRELLO_TOKEN` in the environment (used by `trello-outreach`).

## AUTH-GLANCE
Confirm `TRELLO_API_KEY`/`TRELLO_TOKEN` are set. If not, tell the user to set them and stop.

## STARTABLE-TASK MODEL
The default posture is **hungry to start**: everything is startable now unless it's genuinely blocked.
Two facts live in native Trello fields, two in labels + a description convention:
- **Start date = "work-on-it-next / ping-back"** — the day the card should resurface. This is the queue
  driver. A startable-now task carries **no** Start; a ⏳ Waiting card's Start is when to re-nudge.
- **Due date = a real deadline** — tracked and shown, but not what surfaces the card (a slipped Due
  does force it up as a safety net). Reserved for genuine deadlines.
- **⏳ Waiting** (label) = blocked on a **person's** reply. Still surfaces on its ping-back Start so the
  worker can re-nudge. Record `Waiting-for: <name> · <channel>` in the description (Phase 2's reply
  matcher reads it).
- **⛔ Blocked** (label) = blocked on **another card** finishing. Suppressed entirely (`skip_labels`)
  until unblocked. Record `Blocked-by: <upstream-shortlink>[, …]` in the description; optionally attach
  the upstream card for a human-visible link. (`trello-outreach`'s SKILL.md owns applying this at
  creation time — it's the mechanics layer every Trello write goes through.)

**Unblock is a push.** When an upstream card is finished (moved to a terminal/skip list or archived),
call `trello_utils.cascade_unblock(board_id, finished_card_id, session)`: it scans the board once,
finds cards whose `Blocked-by:` names the finished card, and for each whose **last** blocker just
cleared, strips its ⛔ label and sets **Start = today** so it surfaces on the next drain. Nothing polls
the blocked card. (Phase 2 will add a second trigger — an inbound reply resolving a ⏳ card — to this
same cascade.)

## ENUMERATE
Via `trello-outreach`, list cards across the configured boards that sit in an **active** list (not in
`skip_lists`), are **not** wearing a `skip_labels` label (⛔ Blocked), and are **startable** — Start
now-or-earlier, OR Due now-or-earlier (overdue counts), OR carrying neither date. Rank dated cards by
their **go-live date** (the earliest of Start/Due, most recent first) and undated cards by their
**creation date** (decoded from the card's ObjectId). Build a stable id:
`trello-<card-name-slug>-<last6 of cardId>-<goLiveYYYYMMDD|nodue>` where the go-live date is Start when
present, else Due. That date is part of the id on purpose: a card recurs every cycle (a nudge bumps its
Start out; an outreach CLEAR bumps its Due out), and seen-state keeps a drained id forever, so without
the stamp a card would be marked seen on its first drain and never resurface. Parse each card's labels
with `label_vocab` into channel / features / contacts (⛔/⏳ status labels are held out) so the worker
knows where the conversation lives, and resolve the card's `initiative` (the initiative-colored label's
slug, else the board default).

## CAPTURE (needs-you)
The card itself is the item, and **we own it** — unlike inbound mail/Teams, the same card recurs every
follow-up, so the card is a durable cache for everything needed to act. Read its description +
structured comments FIRST; then run INITIATIVE-LOOKUP for program context; act on that before
re-discovering anything. Write `items/<id>.json`:
`{ "id","source":"trello","triage":"needs-you","kind":"reply|work","cardId","board","list","name",`
`"due","url","contacts":[...],"channelLabel":"<Email|Teams|Slack|...>","initiative":"<slug|null>","ts":"<ISO now>" }`
Then find the relevant **thread** (email / Teams / Slack) for the contact + channel and read it to
decide the move. For **email** threads, follow the SITUATIONAL-CHECK guidance in the matching
provider doc and search the whole mailbox in both directions (incoming from the contact AND your sent
replies) — recent messages may have been swept out of the inbox by a prior drain cycle:
- **outlook-rest / outlook-graph**: search inbox + Archive + **Deleted Items** (paginated) — CLEAR
  moves handled messages to Deleted Items.
- **gmail**: search All Mail with no `in:` filter — CLEAR archives (not trashes), so everything is
  in All Mail.

**Cache back to the card.** Anything you learn that the next pass would otherwise re-derive — the
thread deep link, the contact's role/handle, where they are in the outreach, the last message
gist/date, the agreed next step — write into the card's description/comments via `trello-outreach`, in
a stable structured shape. CLEAR (advance) then updates that cache. Over time a card should carry
enough that a follow-up needs almost no re-discovery. (A dedicated card schema for this is worth
designing — see the project's Trello-caching follow-up.)

## INITIATIVE-LOOKUP
Many outreach cards share one program — the user is following up with many people to onboard them to
the same initiative — so a card like "Acme Corp / Jane Doe" carries no per-card context of its own.
The initiative supplies the **content** (what the program is, why it matters, the ask); the generic
STAGE-PLAYBOOK below supplies the **activity** for the card's current column. Load once, before
drafting:
1. **Take the resolved slug.** The item's `initiative` field (set by the adapter from the
   initiative-colored label, else the board default). Empty → no initiative; proceed as a plain card
   (draft from the card/thread alone, ask the user if blank).
2. **Open `initiatives/<slug>.md`** from the repo and read its content. If it carries a `source:`
   frontmatter pointer, the content lives there instead — fetch it by shape:
   - an **http(s) URL** → a Confluence page (`*.atlassian.net/wiki`) via Atlassian MCP or the
     `confluence-investigator` skill (extract the numeric page id from the URL when one is needed); any
     other URL via plain web fetch.
   - otherwise the file body itself is the content.
   You want: what the program is, why it matters to the contact, the ask, and any role the contact
   plays if the initiative defines roles. (If the file is missing, the slug is still a useful hint —
   note the gap and draft from the card/thread.)
3. **Draft from content + playbook.** Combine the initiative content with the STAGE-PLAYBOOK intent for
   the card's column to ground a meaningful message — no need to ask the user what the outreach is
   about. If the content genuinely lacks something the message needs, that's a gap to fix in the
   initiative doc, not a question to bounce to the user every cycle.

## STAGE-PLAYBOOK (how to advance a card to the next phase)
A card's column is a starting point, not something to describe back. For each phase the goal is to move
the contact to the **next** phase: situation-check first (did they reply? did the planned step happen?),
then take or draft the action that drives progression. Every outreach board is some version of the same
awareness→commitment→done funnel, so this advance logic lives here once and stays **generic**; the
initiative content (INITIATIVE-LOOKUP) supplies what any given step actually involves for that program.

Map the card's column onto the nearest phase by intent — boards name and sub-divide these differently:

- **Not yet aware → aware.** They don't know about it. Action: send the first-contact intro — what it
  is, why it matters to them, an invite to talk. (Sending it advances the card.)
- **Aware → interested.** They've heard of it. Action: follow up to land a yes — answer questions,
  surface the benefit, ask what they need to move forward.
- **Interested → committed.** They want in. Action: nail down the concrete next step, and if the work
  needs scheduling, get it on a calendar.
- **Committed / scheduled → in progress.** A plan or date exists. Action: confirm it still holds and
  that they've started; nudge to re-confirm if it has slipped.
- **In progress → done.** They're working on it. Action: check for blockers, offer help, push toward
  completion.
- **Done.** Terminal — close the loop and thank them. (Usually a `skip_lists` list.)
- **Abandoned.** Terminal — not pursuing; no action.

Some boards insert their own steps between these (e.g. a reconciliation or review stage); treat such a
column as the nearest generic phase and let the initiative doc say what that step requires.

Always situation-check before acting: if they've already replied or the step already happened, the move
is usually to **advance** the card (CLEAR) rather than send again; if it's simply not yet time to follow
up, silently bump the due date (CLEAR) and surface no tab.

## CLEAR (advance the card)
Only **after** the user confirms they sent/handled the message, advance the card via `trello-outreach`:
- **nudge** — bump the due date out N days (they haven't replied; follow up later). Use the cadence below.
- **advance** — move to a later stage + set the next due date (it progressed).
- **stop** — move to Abandoned + clear the due date (not pursuing). If a message draft was staged for
  this card and never sent, discard it too (e.g. `node gmail.js --delete-draft=<draft-id>` for a Gmail
  draft) — an abandoned card means the draft is dead weight, not a reminder to revisit.
Each advance also posts a dated comment recording what happened, so the board reflects reality.

For **task cards** (startable model), a ⏳ Waiting card also nudges by bumping its **Start** (ping-back
date), never its Due; and whenever a card is **finished** (moved to a terminal/skip list), fire
`trello_utils.cascade_unblock(board_id, finished_card_id, session)` so any ⛔ Blocked cards waiting on
it are freed (⛔ stripped, Start set to today) on the spot.

### Nudge cadence

**A stated timeframe beats the fixed tiers below.** When the counterparty already gave a concrete
expected response time, follow up relative to that time instead of picking a tier:
- **Personal contact named their own timeline** ("I'll get back to you by Friday") — bump to a little
  *after* that time, giving them some grace past their own estimate.
- **Business or process gave an upper-bound estimate** ("may take up to 10 business days") — bump to a
  little *before* that bound, so the check-in lands inside their stated window instead of waiting for
  it to expire.

Otherwise, when no such timeframe was given, pick the tier based on how closely the user works with the contact:

**Frequent collaborator** — someone the user works with regularly who would treat this as a normal part of their day:
- After sending → bump **3 business days**
- After 1st follow-up (no reply) → bump **1 week**

**Infrequent contact** — someone outside the user's regular workflow, or where this ask isn't part of their day job:
- After sending → bump **1 week**
- After 1st follow-up (no reply) → bump **2 weeks**

When unsure, default to infrequent. When the ask requires real commitment or internal approval from the contact (e.g. sponsorship money, a formal agreement), start at **2 weeks** instead of 1 — regardless of how closely the user works with them.

If the situational check finds **nothing to do right now** (it's not yet time to follow up, or they
replied and the user already answered), silently bump the due date and finish — surface no tab.

## JUNK-LEARNING
N/A — outreach cards are curated, not inbound noise.

## DRAFT-MODE
`message-draft` skill, in the mode matching the card's channel (`outlook` / `teams` / `slack`).
