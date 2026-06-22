# teams provider — Microsoft Teams via the internal REST services

A provider for Microsoft Teams read through the **Teams internal REST services** (the same services
Teams web uses) — fast, no DOM hydration. All reads go through the **`teams`** skill's `teams-chat.js`
(don't reimplement the API here); it owns the sniffed ic3 + aggregator tokens, the authoritative
`isRead` unread detection, the watched-team channel scoping, and the `messages` read. Implements
`../engine/provider.md`; classify by `../engine/triage.md`.
id prefix: `teams-`; body file: `<id>.msg.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the
> sibling **`teams-adapter.py`** that the poller drives. This doc is the **worker-facing** prose —
> AUTH-GLANCE, the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> Reads are REST (fast, browser-free once the token is cached); **CLEAR and DRAFT stay browser-driven**
> because Teams' authoritative `isRead` flips only on a real conversation open, and Teams has no draft API.

## Config (in `.claude/drainer.local.md` → `providers.teams`)
No config block — `teams: {}`. Behavior is tuned by environment variables read by the `teams` skill:
`DRAINER_TEAMS_WATCHED_TEAM_ID` / `DRAINER_TEAMS_WATCHED_TEAM_NAME` (only this team's channels surface)
and `DRAINER_SELF_NAME` (labels 1:1/group chats by the other member[s]). Tokens are sniffed from the
live Teams web session and cached at `~/.claude/drainer/teams-ic3-token.json`; the one-time sniff needs
`playwright` (resolved from the home repo's `node_modules`).

The `teams` `teams-chat.js` lives at `<teams-skill>/scripts/teams-chat.js` — run it with `node`.

## Teams footguns (IRREVERSIBLE — never violate)
- **Enter SENDS** in a Teams composer. Reads are REST and never type into a composer. All composing
  happens later in the worker via the `message-draft` skill (`teams` mode), which owns the footguns
  (identity-gate the chat, target the visible composer, Shift+Enter for newlines, never a bare Enter).
- **Heavy iframes (browser path only):** for CLEAR/DRAFT keep to ONE browser-driving context.

## AUTH-GLANCE
Run `node <teams>/teams-chat.js token`. `Tokens OK ✅` means both tokens are valid (cached or freshly
sniffed) and the channel is ready. If it errors with "Missing token(s)", Teams web isn't open/signed in
in the CDP browser: open `https://teams.microsoft.com/`, confirm signed in, and stop reading Teams until
the token sniffs clean. Never surface a raw auth error to the user.

## MEETING RECORDING MESSAGES
A meeting-recording notification (recording/transcript link or "Meeting ended" summary) is a container —
see `../engine/triage.md § Containers that hold action items`. Open the meeting's AI notes (via
browser-chauffeur) and look for action items assigned to **you**; each becomes its own needs-you item
(`whatsAsked` = the action-item text). If AI notes exist but none are yours, it's fyi. If no AI notes
exist, fyi.

## CAPTURE (needs-you)
The adapter writes these; documented here so the worker can rely on the shape:
- `items/<id>.msg.md` — header block (Chat/From, Type [dm|group|channel|meeting], Latest, Link=`deepLink`)
  + the recent messages.
- `items/<id>.json`:
  `{ "id","source":"teams","triage":"needs-you","kind":"reply|work|work-then-reply","from":"<person`
  `or chat label>","subject":"<chat label>","chatType":"dm|group|channel|meeting","received","snippet",`
  `"url":"<conversation deep link>","messageId":"<IC3 conv id>","convId":"<IC3 conv id>",`
  `"msgFile":"<abs path to .msg.md>","ts":"<ISO now>" }`

  `convId` (= `messageId`) is the IC3 conversation id — CLEAR needs it to identify the conversation.

## CLEAR
**Browser-driven (via `browser-chauffeur`), not REST.** Teams' authoritative `isRead` is not driven by
any replayable HTTP call (the consumptionhorizon PUTs return 200 but don't flip `isRead`); opening the
conversation in Teams web flips it within ~5 s via a trouter/websocket signal. So mark-read = **open the
conversation in Teams web**: navigate the CDP browser to `https://teams.cloud.microsoft/v2/?ctx=chat`,
wait for the rail, and click the conversation's row (match its visible `label`; `getByText`, first
match). Verify by re-running `node teams-chat.js enumerate --unread` — the item drops out of unread.
Teams has no delete/trash; mark-read is the "gone," and it is reversible. Narrate each clear with a
one-line reason.

If the underlying WORK isn't finished (you only drafted a reply), do NOT clear — leave the conversation
unread and write a "paused" note instead.

## JUNK-LEARNING
None. Teams junk is just cleared (marked read) — the user manages their own Teams mutes; don't propose
mutes or rules.

## DRAFT-MODE
`message-draft` skill, `teams` mode (browser composer — owns the voice + composer mechanics + the
footgun rules). Only the read mechanics use the REST script; drafting stays in the browser.
