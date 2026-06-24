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
- **Initiatives** — an optional `initiatives:` block in the same `trello-boards.yaml` maps an
  initiative slug → `{label, confluence_url, page_id, summary}`. A card belongs to an initiative two
  ways (a card tag wins over the board default): a board-level `initiative: <slug>` field (every card
  on that board inherits it — best when the whole board is one program), or a per-card Trello label
  whose name matches an initiative `label` (best for mixed boards). See INITIATIVE-LOOKUP. This block
  is read by the worker, not the poller adapter — keep its shape free of a four-space `id:` line so the
  board parser ignores it.
- Drainer knobs in `.claude/drainer.local.md` → `providers.trello`:
  - `skip_lists` — terminal/parking lists to ignore (e.g. Abandoned, Finished, Adopted, Templates).
  - `label_vocab` — `{channels: [...], features: [...]}`; any label not in those is a contact name.
Credentials: `TRELLO_API_KEY` / `TRELLO_TOKEN` in the environment (used by `trello-outreach`).

## AUTH-GLANCE
Confirm `TRELLO_API_KEY`/`TRELLO_TOKEN` are set. If not, tell the user to set them and stop.

## ENUMERATE
Via `trello-outreach`, list cards across the configured boards that sit in an **active** list (not in
`skip_lists`) and are either **due now-or-earlier** (overdue counts) **or have no due date at all** —
undated cards are still in play and shouldn't be missed. Sort oldest-due first (undated last). Build a
stable id: `trello-<card-name-slug>-<last6 of cardId>-<dueYYYYMMDD|nodue>`. The due date is part of the
id on purpose: a card recurs every follow-up cycle (CLEAR bumps its due date out), and seen-state keeps
a drained id forever, so without the due stamp a card would be marked seen on its first drain and never
resurface when its next due date arrives. Parse each card's labels with `label_vocab` into channel /
features / contacts so the worker knows where the conversation lives.

## CAPTURE (needs-you)
The card itself is the item, and **we own it** — unlike inbound mail/Teams, the same card recurs every
follow-up, so the card is a durable cache for everything needed to act. Read its description +
structured comments FIRST; then run INITIATIVE-LOOKUP for program context; act on that before
re-discovering anything. Write `items/<id>.json`:
`{ "id","source":"trello","triage":"needs-you","kind":"reply|work","cardId","board","list","name",`
`"due","url","contacts":[...],"channelLabel":"<Email|Teams|Slack|...>","ts":"<ISO now>" }`
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
Many outreach cards share one program — Russell is following up with many people to onboard them to
the same initiative — so a card like "Okta / Brett Wessling" carries no per-card context of its own.
Resolve the card's initiative and load the program once, before drafting:
1. **Find the initiative slug.** First a card label whose name matches an `initiatives[].label` in
   `trello-boards.yaml`; if none, the `initiative:` field on the card's board entry. No match → no
   initiative (proceed as a plain card — draft from the card/thread alone, ask Russell if blank).
2. **Load the program context.** Look up that slug in the `initiatives:` block. Read its `summary` for a
   fast orientation, then fetch the `confluence_url` / `page_id` (Atlassian MCP or the
   `confluence-investigator` skill) for the full picture: what the program is, the outreach goal (what
   we're asking the contact to do), the lifecycle stage the card's list maps to, and any role
   (Producer/Consumer) the card's labels imply.
3. **Draft from that context.** Use the program + the card's stage/contact to ground a meaningful
   message — no need to ask Russell what the outreach is about. The Confluence page is the source of
   truth; if it lacks the specific ask for this stage, that's a gap to flag (improve the page), not a
   question to bounce to Russell every cycle.

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
