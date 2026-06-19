# slack provider — InnerSource Commons Slack (Web API, xoxc token + xoxd cookie)

A provider for a **personal Slack workspace** (InnerSource Commons, team `T04PXKRM0`) read and cleared
through the **Slack Web API** with a sniffed **`xoxc-` user token** + its **`xoxd-` `d` cookie** — no bot
app, no OAuth scopes, no browser. All reads go through the **`slack`** skill's `slack.js` (don't
reimplement the API here); it owns the `client.counts` unread badges, `conversations.history`, and the
`conversations.mark` read-cursor mechanics. Implements `../engine/provider.md`; classify by
`../engine/triage.md`.
id prefix: `slack-`; body file: `<id>.slack.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the sibling
> **`slack-adapter.py`** that the poller drives. This doc is the **worker-facing** prose — AUTH-GLANCE,
> the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> This is the Web-API counterpart to the IMAP `gmail-provider.md` / Graph `personal-outlook-provider.md`.
> Use it for a Slack workspace where you can sniff a personal user token from the browser.

## Config (in `.claude/drainer.local.md` → `providers.slack`)
No config — auth is by environment variables. Credentials: `SLACK_BOT_TOKEN` (despite the name, a
personal `xoxc-` **user** token), `SLACK_COOKIE_D` (the `xoxd-` `d` session cookie — the token is
`invalid_auth` without it), and `SLACK_TEAM_ID` (`T04PXKRM0`) in the environment.

The `slack` `slack.js` lives at `<slack-skill>/scripts/slack.js` — run it with `node`.

## What is an item
- one **unread DM** (im) — keyed to its latest unread message,
- one **unread group DM** (mpim) — keyed to its latest unread message,
- one **@-mention of Russell in a channel** — one item per mentioning message.

A new reply in an already-seen DM produces a new `ts`, so it re-surfaces as a fresh item next cycle.

## AUTH-GLANCE
Run `node slack.js --check`. If it prints "Signed in as … (InnerSource Commons …)" you're connected. If
it errors with `invalid_auth` / `not_authed`, the `xoxc` token or the `d` cookie expired or was revoked —
re-sniff **both** from the browser per `personal-ai-pod/docs/slack-token-refresh.md`
(`localStorage.localConfig_v2.teams['T04PXKRM0'].token` for the token; DevTools → Cookies → `d` for the
cookie) and re-set `SLACK_BOT_TOKEN` / `SLACK_COOKIE_D`. There is no refresh-token flow; never surface a
raw auth error to the user.

## SITUATIONAL-CHECK (do this BEFORE drafting any reply)
The captured item is the message as it arrived; the conversation may have moved on. Re-read the
conversation with `node slack.js --show --channel=<C> --ts=<ts>` (and open the permalink if you need full
thread context) to confirm Russell hasn't already replied and the ask is still open. Check Slack's own
**Drafts** (the slack-message skill stages drafts in the composer) so you don't stack a second draft on a
conversation that already has one. Reply only to what is still open.

## CAPTURE (the item shape the worker reads)
The adapter writes these two files for each dispatched item (`slack-adapter.py` → `capture`); this is the
shape the worker can rely on:
- `items/<id>.slack.md` — header block (From, Channel, Received, Link, MessageRef) + the message text
  (from `slack.js --show --json`).
- `items/<id>.json` — `{ "id","source":"slack","triage","kind","from","subject","received","snippet",`
  `"url":"<permalink>","messageId":"<channel>:<ts>","channel","ts","channelType","channelName",`
  `"bodyFile","ts_captured" }`.

`channel` + `ts` (also joined as `messageId`) are the load-bearing fields — the worker needs them for
SITUATIONAL-CHECK (`--show`) and CLEAR (`--mark`). `url` is the message permalink, openable in Slack.

## CLEAR
`node slack.js --mark --channel=<channel> --ts=<ts>` — advances the conversation's read cursor to `<ts>`
via `conversations.mark` (the Slack "gone"). Reversible and non-destructive: nothing is deleted, and
re-reading the conversation (or a newer message arriving) re-surfaces it. Narrate it. For a channel
mention, marking up to the mention's `ts` clears that mention's unread badge. Never delete messages.

## JUNK-LEARNING
Stop this noise arriving again, in **priority order** (best outcome = it never pings) — propose, never
apply without the user's OK:
1. **Mute the channel** — for a noisy channel whose @-here/@-channel or keyword pings aren't for Russell,
   propose muting it (Slack: channel → Mute), so it stops generating unreads/badges.
2. **Adjust notification keywords / preferences** — if a bot or integration keeps mentioning Russell,
   propose tuning Slack notification preferences (or the integration's settings) so the ping stops.
3. **Leave the channel** — only when Russell has no reason to be in it at all, propose leaving it.

Marking read (CLEAR) silences the current item but does not stop the next one — the steps above are what
actually stop recurrence. There is no inbound-mail-style unsubscribe for Slack.

## DRAFT-MODE
**First, before writing a single word of the body: invoke the `document-authoring` skill (call the Skill
tool to load it) and read its Conversational writing + "Never do these" sections. Compose the draft
against what you just read — do not write from memory.** The skill is the single source of truth for
Russell's voice and its hard rules; a draft composed from memory reliably leaks the very tokens those
rules ban. This read is a gate: it happens before drafting, not as an after-the-fact check.

Then write the message text in that voice. Slack has **no draft API**, so the reply is staged through the
**`slack-message`** skill (browser, via browser-chauffeur): it jumps to the person/conversation, confirms
the channel header matches, and **types the reply into the composer without sending** — Slack auto-saves
it as a per-conversation draft for Russell to review and send. **Never press Enter / never send.** Show
the draft text in the terminal and tell Russell to edit + send it himself in Slack. The voice loop in the
document-authoring skill still applies — diff sent-vs-draft after he sends and append a lesson.

- **Reply in the same conversation** (a DM, group DM, or the channel where he was mentioned): drive
  `slack-message` to that conversation and stage the draft there. For a channel mention, reply in-channel
  (or in-thread if the mention was a threaded message) rather than starting a DM, unless the content is
  clearly better handled privately.
- A reply is warranted only after any underlying **work** (step 3 of worker-core) is done — draft about
  the outcome, not a promise.
