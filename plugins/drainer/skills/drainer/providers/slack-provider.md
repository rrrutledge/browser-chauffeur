# slack provider — a Slack workspace (Web API)

A provider for a **Slack workspace** read and cleared through the **Slack Web API** — no browser. All
reads go through the **`slack`** skill's `slack.js` (don't reimplement the API here); it owns the
`client.counts` unread badges, the mute filter, `conversations.history` / `subscriptions.thread.getView`,
and the `conversations.mark` / `subscriptions.thread.mark` read-cursor mechanics. Implements
`../engine/provider.md`; classify by `../engine/triage.md`.
id prefix: `slack-`; body file: `<id>.slack.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the sibling
> **`slack-adapter.py`** that the poller drives. This doc is the **worker-facing** prose — AUTH-GLANCE,
> the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> This is the Web-API counterpart to the IMAP `gmail-provider.md` / Graph `personal-outlook-provider.md`.

## Config (in `.claude/drainer.local.md` → `providers.slack`)
No config — auth is by environment variables. Credentials: `SLACK_BOT_TOKEN` (the Slack API token — for a
personal user token, the `xoxc-` value), `SLACK_COOKIE_D` (the `d` session cookie — required for a browser
`xoxc` token, which is `invalid_auth` without it, and for the `client.*` endpoints), and `SLACK_TEAM_ID`
(the workspace's team id) in the environment.

The `slack` `slack.js` lives at `<slack-skill>/scripts/slack.js` — run it with `node`.

## What is an item
- one **unread DM** (im) — keyed to its latest unread message,
- one **unread group DM** (mpim) — keyed to its latest unread message,
- one **@-mention in a channel** — one item per mentioning message,
- one **subscribed thread with unread replies** — keyed to its latest unread reply (the `subject` notes
  whether it also @-mentions you).

**Muted conversations are skipped** by enumerate — muting a channel/DM is the user's "stop," so the
drainer honors it. A new message/reply produces a new `ts`, so the conversation re-surfaces next cycle.

## AUTH-GLANCE
Run `node slack.js --check`. If it prints "Signed in as …" you're connected. If it errors with
`invalid_auth` / `not_authed`, the token or the `d` cookie expired or was revoked. For a browser-sniffed
user token, re-sniff **both** from the browser (the token from
`localStorage.localConfig_v2.teams[<teamId>].token`; the `d` cookie from DevTools → Application → Cookies)
and re-set `SLACK_BOT_TOKEN` / `SLACK_COOKIE_D`. There is no refresh-token flow; never surface a raw auth
error to the user.

## SITUATIONAL-CHECK (do this BEFORE drafting any reply)
The captured item is the message as it arrived; the conversation may have moved on. Re-read it with
`node slack.js --show --channel=<C> --ts=<ts>` (add `--thread-ts=<threadTs>` for a thread item; open the
permalink for full thread context) to confirm there's not already a reply and the ask is still open. The
`message-draft` slack mode stages drafts in the Slack composer — check the conversation in Slack so you
don't stack a second draft. Reply only to what is still open.

## CAPTURE (the item shape the worker reads)
The adapter writes these two files for each dispatched item (`slack-adapter.py` → `capture`); this is the
shape the worker can rely on:
- `items/<id>.slack.md` — header block (From, Channel, Received, Link, MessageRef) + the message text
  (from `slack.js --show --json`).
- `items/<id>.json` — `{ "id","source":"slack","triage","kind","from","subject","received","snippet",`
  `"url":"<permalink>","messageId":"<channel>:<ts>","channel","ts","threadTs","channelType",`
  `"channelName","bodyFile","ts_captured" }`.

`channel` + `ts` (also joined as `messageId`) are the load-bearing fields — the worker needs them for
SITUATIONAL-CHECK (`--show`) and CLEAR (`--mark`). For a **thread** item, `threadTs` is also set and is
required for both `--show` and `--mark`. `channelType` is `im` / `mpim` / `channel` / `thread`. `url` is
the message permalink, openable in Slack.

## CLEAR
Advance the read cursor (the Slack "gone") — reversible and non-destructive (nothing is deleted; re-reading
or a newer message re-surfaces it). Narrate it. Never delete messages.
- **DM / group DM / channel mention** — `node slack.js --mark --channel=<channel> --ts=<ts>`
  (`conversations.mark`). For a channel mention, marking up to the mention's `ts` clears its unread badge.
- **Thread item** — `node slack.js --mark --channel=<channel> --ts=<ts> --thread-ts=<threadTs>`
  (`subscriptions.thread.mark`) — advances the thread's own read cursor.

## AUTO-HANDLE
Standing rules where Russell has decided the answer in advance, so the poller triages the item
**`auto-handle`** (per `../engine/triage.md`) and the worker executes it autonomously — no tab, no wait —
then records it in the digest's "Auto-handled" section. Each rule below names its exact condition and
action; act only when an item plainly matches one. Anything that doesn't match a rule here is NOT
auto-handle — it falls back to the normal needs-you/fyi/junk triage.

1. **Workspace invite request → approve** — when the **`@Slack`** bot DMs Russell with a request to
   invite a *new person to the workspace*, carrying a **"Send Invitation"** button. Russell always
   approves these.
   - **Action:** drive **browser-chauffeur** to the message permalink (`url` in the captured item) and
     click **"Send Invitation"**.
   - **Digest note:** "Auto-approved workspace invite: *[invitee email]* (requested by *[requester]*)."
   - **Then** CLEAR the item (mark read) and write `.done` immediately.
   - This rule is for *adding a person to the workspace* only — distinguished from a Slack Connect join
     by the wording: "invite [person] to [workspace]" = this rule (approve); "join a Slack Connect
     channel" = rule 2 below (reject).

2. **Slack Connect channel/workspace connect request → reject** — a message that says **"Request to join
   a Slack Connect channel"** or otherwise asks to *connect an external workspace/channel* (linking a
   different org, not adding a person to this workspace). Russell always declines these.
   - **Action:** drive **browser-chauffeur** to the message permalink (`url` in the captured item) and
     click **"Decline"** (the reject/ignore action on the request — not "Accept").
   - **Digest note:** "Auto-rejected Slack Connect request: *[channel/org]* (requested by *[requester]*)."
   - **Then** CLEAR the item (mark read) and write `.done` immediately.

## JUNK-LEARNING
Stop this noise arriving again, in **priority order** (best outcome = it never pings) — propose, never
apply without the user's OK:
1. **Mute the conversation** — for a noisy channel/DM whose pings aren't for the user, propose muting it
   (Slack: channel → Mute). Enumerate skips muted conversations, so this genuinely stops it surfacing.
2. **Adjust notification keywords / preferences** — if a bot or integration keeps mentioning the user,
   propose tuning Slack notification preferences (or the integration's settings) so the ping stops.
3. **Leave the channel** — only when the user has no reason to be in it at all, propose leaving it.

Marking read (CLEAR) silences the current item but does not stop the next one — the steps above are what
actually stop recurrence. There is no inbound-mail-style unsubscribe for Slack.

## DRAFT-MODE
Stage the reply through the **`message-draft`** skill's **`slack`** mode (browser, draft-only) — that skill
owns the composer mechanics and the voice gate. It jumps to the conversation, confirms the header matches,
and **types the reply into the Slack composer without sending** (Slack auto-saves it as a per-conversation
draft). **Never press Enter / never send.** Show the draft text in the terminal and tell the user to edit +
send it themselves in Slack. (message-draft loads `document-authoring` for the voice and runs its stage-time
voice gate; the voice loop still applies — diff sent-vs-draft after the user sends and append a lesson.)

- **Reply in the same conversation** (a DM, group DM, the channel where the user was mentioned, or the
  thread): point `message-draft` slack mode at that conversation. For a channel/thread mention, reply
  in-channel / in-thread rather than starting a DM, unless the content is clearly better handled privately.
- A reply is warranted only after any underlying **work** (step 3 of worker-core) is done — draft about the
  outcome, not a promise.
