# trello provider — outreach boards (Trello API)

A provider for the **outreach** source. The card's **due date IS the queue**: harvested on
every run like any other source, it simply returns cards due now-or-earlier (usually none), so it
rides the single schedule with no special cadence. All Trello reads and mutations go through the
**`trello-outreach`** skill (don't reimplement the Trello API here). Implements
`../engine/provider.md`; classify by `../engine/triage.md`. id prefix: `trello-`.

## Config (in `.claude/drainer.local.md` → `providers.trello`)
- `boards` — `[{name, id}]` to drain.
- `skip_lists` — terminal/parking lists to ignore (e.g. Abandoned, Finished, Adopted, Templates).
- `label_vocab` — `{channels: [...], features: [...]}`; any label not in those is a contact name.
Credentials: `TRELLO_API_KEY` / `TRELLO_TOKEN` in the environment (used by `trello-outreach`).

## AUTH-GLANCE
Confirm `TRELLO_API_KEY`/`TRELLO_TOKEN` are set. If not, tell the user to set them and stop.

## ENUMERATE
Via `trello-outreach`, list cards across the configured boards that sit in an **active** list (not in
`skip_lists`) and are either **due now-or-earlier** (overdue counts) **or have no due date at all** —
undated cards are still in play and shouldn't be missed. Sort oldest-due first (undated last). Build a
stable id: `trello-<card-name-slug>-<last6 of cardId>`. Parse each card's labels with `label_vocab`
into channel / features / contacts so the worker knows where the conversation lives.

## CAPTURE (needs-you)
The card itself is the item, and **we own it** — unlike inbound mail/Teams, the same card recurs every
follow-up, so the card is a durable cache for everything needed to act. Read its description +
structured comments FIRST; act on that before re-discovering anything. Write `items/<id>.json`:
`{ "id","source":"trello","triage":"needs-you","kind":"reply|work","cardId","board","list","name",`
`"due","url","contacts":[...],"channelLabel":"<Email|Teams|Slack|...>","ts":"<ISO now>" }`
Then find the relevant **thread** (email / Teams / Slack) for the contact + channel and read it to
decide the move.

**Cache back to the card.** Anything you learn that the next pass would otherwise re-derive — the
thread deep link, the contact's role/handle, where they are in the outreach, the last message
gist/date, the agreed next step — write into the card's description/comments via `trello-outreach`, in
a stable structured shape. CLEAR (advance) then updates that cache. Over time a card should carry
enough that a follow-up needs almost no re-discovery. (A dedicated card schema for this is worth
designing — see the project's Trello-caching follow-up.)

## CLEAR (advance the card)
Only **after** the user confirms they sent/handled the message, advance the card via `trello-outreach`:
- **nudge** — bump the due date out N days (they haven't replied; follow up later).
- **advance** — move to a later stage + set the next due date (it progressed).
- **stop** — move to Abandoned + clear the due date (not pursuing).
Each advance also posts a dated comment recording what happened, so the board reflects reality.

If the situational check finds **nothing to do right now** (it's not yet time to follow up, or they
replied and the user already answered), silently bump the due date and finish — surface no tab.

## JUNK-LEARNING
N/A — outreach cards are curated, not inbound noise.

## DRAFT-MODE
`message-draft` skill, in the mode matching the card's channel (`outlook` / `teams` / `slack`).
