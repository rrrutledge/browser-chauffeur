# trello provider — outreach boards (Trello API)

A provider for the **outreach** source. The card's **due date IS the queue**: harvested on
every run like any other source, it simply returns cards due now-or-earlier (usually none), so it
rides the single schedule with no special cadence. All Trello reads and mutations go through the
**`trello-outreach`** skill (don't reimplement the Trello API here). Implements
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
  - `label_vocab` — `{channels: [...], features: [...]}`; any label not in those is a contact name.
Credentials: `TRELLO_API_KEY` / `TRELLO_TOKEN` in the environment (used by `trello-outreach`).

## AUTH-GLANCE
Confirm `TRELLO_API_KEY`/`TRELLO_TOKEN` are set. If not, tell the user to set them and stop.

## ENUMERATE
Via `trello-outreach`, list cards across the configured boards that sit in an **active** list (not in
`skip_lists`) and are either **due now-or-earlier** (overdue counts) **or have no due date at all** —
undated cards are still in play and shouldn't be missed. Rank most-recently-due first; an undated card
has no deadline, so it ranks by its **creation date** (decoded from the card's ObjectId) instead of
being pinned to the top of the queue. Build a
stable id: `trello-<card-name-slug>-<last6 of cardId>-<dueYYYYMMDD|nodue>`. The due date is part of the
id on purpose: a card recurs every follow-up cycle (CLEAR bumps its due date out), and seen-state keeps
a drained id forever, so without the due stamp a card would be marked seen on its first drain and never
resurface when its next due date arrives. Parse each card's labels with `label_vocab` into channel /
features / contacts so the worker knows where the conversation lives, and resolve the card's
`initiative` (the initiative-colored label's slug, else the board default).

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
- **stop** — move to Abandoned + clear the due date (not pursuing).
Each advance also posts a dated comment recording what happened, so the board reflects reality.

### Nudge cadence

Pick the tier based on how closely the user works with the contact:

**Frequent collaborator** — someone the user works with regularly who would treat this as a normal part of their day:
- After sending → bump **3 business days**
- After 1st follow-up (no reply) → bump **1 week**

**Infrequent contact** — someone outside the user's regular workflow, or where this ask isn't part of their day job:
- After sending → bump **1 week**
- After 1st follow-up (no reply) → bump **2 weeks**

When unsure, default to infrequent.

If the situational check finds **nothing to do right now** (it's not yet time to follow up, or they
replied and the user already answered), silently bump the due date and finish — surface no tab.

## JUNK-LEARNING
N/A — outreach cards are curated, not inbound noise.

## DRAFT-MODE
`message-draft` skill, in the mode matching the card's channel (`outlook` / `teams` / `slack`).
