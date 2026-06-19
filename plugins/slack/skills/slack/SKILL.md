---
name: slack
description: Read and mark-read a personal Slack workspace (InnerSource Commons) via the Slack Web API using a sniffed xoxc user token + xoxd cookie — no bot app, no OAuth scopes, no browser. Use to list unread DMs / group DMs / @-mentions, show a message with its permalink, or mark a conversation read. Headless-safe; reply drafts go through the slack-message skill (browser, draft-only).
---

# Slack — Read/Mark a Personal Workspace via the Web API (xoxc token + xoxd cookie)

Read and clear a Slack workspace directly over the **Slack Web API** with a personal **`xoxc-` user
token** and its matching **`xoxd-` session cookie** — no bot app, no OAuth scopes, no browser. Zero npm
dependencies: `slack.js` uses Node's built-in `fetch` (Node 18+).

**Why a sniffed token, not a bot:** the drainer's headless poller needs to read unread DMs and mentions
the way Russell sees them — a bot token can't see a person's unreads. The browser-sniffed `xoxc` user
token plus the `xoxd` `d` cookie act as Russell's own client. (The cookie is required: the `xoxc` token
returns `invalid_auth` without it.) Reply **drafting** is a separate concern — Slack has no draft API, so
worker reply drafts go through the **`slack-message`** skill (browser, draft-only), never an API send.

## Setup (per machine)

Set three secrets as environment variables (never in a file):

- **`SLACK_BOT_TOKEN`** — despite the name, a personal `xoxc-` **user** token, sniffed from the browser's
  `localStorage.localConfig_v2.teams[<teamId>].token`.
- **`SLACK_COOKIE_D`** — the `xoxd-...` value of the `d` cookie for `.slack.com` (DevTools → Application →
  Cookies). Needed alongside the token.
- **`SLACK_TEAM_ID`** — `T04PXKRM0` (InnerSource Commons).

Both the token and the cookie expire periodically. When `--check` reports `invalid_auth`, re-sniff them
per `personal-ai-pod/docs/slack-token-refresh.md` (the browser-localStorage trick) and re-set the env vars.

**Secrets stay machine-local.** The plugin code is shared via the marketplace; the token/cookie are
per-machine, so the workspace is only reachable where you've set them.

## Scripts

Under `scripts/` (run with `node`):

- **`slack.js`**
  - Auth glance: `node slack.js --check` (calls `auth.test`; prints the signed-in user/team; non-zero
    exit on auth failure)
  - List unread: `node slack.js --list-unread [--top=50] [--json]` — unread **DMs**, **group DMs**, and
    **@-mentions of you in channels**, newest-first. `--json` emits a structured array; each item carries
    `id` (`<channel>:<ts>`), `channel`, `channelType` (`im`/`mpim`/`channel`), `ts`, `from`, `fromId`,
    `subject`, `channelName`, `received` (ISO), `preview`, `unreadCount`.
  - Show one: `node slack.js --show --channel=<C> --ts=<ts> [--json]` — the message text plus a
    `chat.getPermalink` url. `--json` emits `{channel,ts,from,fromId,received,text,permalink}`.
  - Mark read: `node slack.js --mark --channel=<C> --ts=<ts>` — `conversations.mark` up to `<ts>`
    (the conversation's "gone"; reversible — re-reading re-surfaces it, never deletes).

## Auth-error handling

`--check` is the cheap glance. An `invalid_auth` / `not_authed` error means the `xoxc` token or the `d`
cookie expired or was revoked — re-sniff both from the browser and re-set `SLACK_BOT_TOKEN` /
`SLACK_COOKIE_D` (see the token-refresh doc). There is no refresh-token flow.

## How it works (Web API endpoints)

- `auth.test` — identity (`--check`, and to learn your own `user_id` for mention detection).
- `client.counts` — the unread/mention badge counts across all DMs, group DMs, and channels in one call
  (this is a Slack **client** endpoint; it needs the `d` cookie).
- `conversations.history` — the unread messages in a conversation since its `last_read`.
- `conversations.info` / `users.info` — resolve channel names and sender real-names (cached per run).
- `chat.getPermalink` — a stable web link to one message (the captured item's `url`).
- `conversations.mark` — advance the read cursor (CLEAR).

## Notes

- The load-bearing identifier is **`<channel>:<ts>`** (the `id` in `--json`): a Slack `ts` is unique per
  message. Pass the `channel`/`ts` to `--show` and `--mark`.
- An **item** is one **conversation** for a DM/group-DM (keyed to its latest unread message) and one
  **message** for each channel @-mention.
- **No reply drafting here.** Slack has no draft API — use the **`slack-message`** skill (browser) to type
  a reply into the composer and leave it as an unsent draft.
