---
name: slack
description: Read and mark-read a Slack workspace via the Slack Web API — no browser. Use to list unread DMs / group DMs / @-mentions / unread thread replies (muted conversations skipped), show a message with its permalink, or mark a conversation or thread read. Headless-safe. Reply drafting is a separate concern — the message-draft skill's `slack` mode (browser, draft-only) handles it.
---

# Slack — Read/Mark a Workspace via the Web API

Read and clear a Slack workspace directly over the **Slack Web API** with a token call — no browser. Zero
npm dependencies: `slack.js` uses Node's built-in `fetch` (Node 18+).

**Read-only here; drafting lives elsewhere.** This skill enumerates unread items and advances read
cursors. Composing a reply is a separate, general capability — the **`message-draft`** skill's `slack`
mode stages a reply in the Slack composer (browser) and leaves it unsent. Keep the two apart: reads go
through `slack.js`, drafts go through `message-draft`.

## Auth

`slack.js` auto-sniffs a fresh `xoxc-` token and companion `d` session cookie from the live CDP browser
session (Edge on port 9222) and caches them at `~/.claude/slack-token.json`. The cache is reused for
all subsequent calls; an `invalid_auth` response triggers a transparent re-sniff and single retry. No
manual token maintenance is needed as long as the CDP browser has an authenticated `app.slack.com/client/`
tab open.

**Bootstrap fallback:** `SLACK_BOT_TOKEN` and `SLACK_COOKIE_D` env vars are used if the sniff fails
(e.g. browser not running). `SLACK_TEAM_ID` is used to select the right team from `localStorage`; if
unset the first team found is used.

**Secrets stay machine-local.** The cached token lives in `~/.claude/` (never synced); the plugin
source is shared via the marketplace and contains no credentials.

## Scripts

Under `scripts/` (run with `node`):

- **`slack.js`**
  - Auth glance: `node slack.js --check` (calls `auth.test`; prints the signed-in user/team; non-zero
    exit on auth failure)
  - List unread: `node slack.js --list-unread [--top=50] [--json]` — unread **DMs**, **group DMs**,
    **@-mentions of you in channels**, and **unread replies in subscribed threads**, newest-first.
    **Muted conversations are skipped** (muting is the user's "stop"). `--json` emits a structured array;
    each item carries `id` (`<channel>:<ts>`), `channel`, `channelType` (`im`/`mpim`/`channel`/`thread`),
    `ts`, `threadTs` (set for thread items), `from`, `fromId`, `subject`, `channelName`, `received` (ISO),
    `preview`, `unreadCount`.
  - Show one: `node slack.js --show --channel=<C> --ts=<ts> [--thread-ts=<tts>] [--json]` — the message
    text plus a `chat.getPermalink` url. Pass `--thread-ts` to read a threaded reply. `--json` emits
    `{channel,ts,threadTs,from,fromId,received,text,permalink}`.
  - Mark read: `node slack.js --mark --channel=<C> --ts=<ts> [--thread-ts=<tts>]` — `conversations.mark`
    up to `<ts>`, or `subscriptions.thread.mark` when `--thread-ts` is given (the conversation/thread's
    "gone"; reversible — re-reading re-surfaces it, never deletes).

## How it works (Web API endpoints)

- `auth.test` — identity (`--check`, and to learn your own `user_id` for mention detection).
- `users.prefs.get` — the muted-conversation set (`all_notifications_prefs.channels[id].muted`), so muted
  conversations are excluded from `--list-unread`.
- `client.counts` — the unread/mention badge counts across all DMs, group DMs, and channels in one call
  (a Slack **client** endpoint; it needs the `d` cookie).
- `conversations.history` — the unread top-level messages in a conversation since its `last_read`.
- `subscriptions.thread.getView` — subscribed threads with unread replies (each thread keeps its own
  `last_read`, separate from the channel's, so thread replies aren't in `conversations.history`).
- `conversations.replies` — the messages of one thread (for `--show`/`--mark` on a threaded reply).
- `conversations.info` / `users.info` — resolve channel names and sender real-names (cached per run).
- `chat.getPermalink` — a stable web link to one message (the captured item's `url`).
- `conversations.mark` / `subscriptions.thread.mark` — advance the conversation / thread read cursor (CLEAR).

## Notes

- The load-bearing identifier is **`<channel>:<ts>`** (the `id` in `--json`): a Slack `ts` is unique per
  message. Pass the `channel`/`ts` (and `threadTs` for a thread item) to `--show` and `--mark`.
- An **item** is one **conversation** for a DM/group-DM (keyed to its latest unread message), one
  **message** for each channel @-mention, and one **thread** for each subscribed thread with unread
  replies (keyed to its latest unread reply).
- **No reply drafting here.** Slack has no draft API — the **`message-draft`** skill's `slack` mode types
  a reply into the Slack composer (browser) and leaves it as an unsent draft for review.
