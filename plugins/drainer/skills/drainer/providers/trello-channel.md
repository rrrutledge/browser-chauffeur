# trello provider — outreach boards (Trello API, once a day)

A **shared** provider with one config value: which board(s) to drain. Trello is the **outreach**
source — the card's **due date IS the queue**, so it's drained once a day. All Trello reads and
mutations go through the **`trello-outreach`** skill (don't reimplement the Trello API here).
Implements `../engine/channel-provider.md`; classify by `../engine/triage.md`. id prefix: `trello-`.

## Config (in `.claude/drainer.local.md` → `outreach`)
- `boards` — `[{name, id}]` to drain.
- `skip_lists` — terminal/parking lists to ignore (e.g. Abandoned, Finished, Adopted, Templates).
- `label_vocab` — `{channels: [...], features: [...]}`; any label not in those is a contact name.
Credentials: `TRELLO_KEY` / `TRELLO_TOKEN` in the environment (used by `trello-outreach`).

## AUTH-GLANCE
Confirm `TRELLO_KEY`/`TRELLO_TOKEN` are set. If not, tell the user to set them and stop.

## ENUMERATE
Via `trello-outreach`, list cards across the configured boards with a **due date ≤ end of today**
(overdue counts) that sit in an **active** list (not in `skip_lists`). Sort oldest-due first. Build a
stable id: `trello-<card-name-slug>-<last6 of cardId>`. Parse each card's labels with `label_vocab`
into channel / features / contacts so the worker knows where the conversation lives.

## CAPTURE (needs-you)
The card itself is the item (we own these cards, so the context should already be ON the card — read
its description + comments first). Write `items/<id>.json`:
`{ "id","channel":"trello","triage":"needs-you","kind":"reply|work","cardId","board","list","name",`
`"due","url","contacts":[...],"channelLabel":"<Email|Teams|Slack|...>","ts":"<ISO now>" }`
Then find the relevant **thread** (email / Teams / Slack) for the contact + channel and read it to
decide the move. When you learn something the card was missing, **enrich the card** (via
`trello-outreach`) so the next pass needs no re-discovery.

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

## WORKER-PROMPT
`trello-worker-prompt.txt`.
