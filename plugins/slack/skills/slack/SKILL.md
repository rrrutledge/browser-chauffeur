---
name: slack
description: Read, mark-read, and send in a Slack workspace via the Slack Web API — no browser. Use to list unread DMs / group DMs / @-mentions / unread thread replies (muted conversations skipped), show a message with its permalink, mark a conversation or thread read, find a user's DM (flagging duplicate accounts), send an explicit pre-approved message (dry-run by default), or delete one you sent. Headless-safe. For staging a reply for review in the Slack composer itself (browser, draft-only, the default when a reply hasn't already been explicitly approved), use the message-draft skill's `slack` mode instead.
---

# Slack — Read, Mark, and Send via the Web API

Read, clear, and send in a Slack workspace directly over the **Slack Web API** with a token call — no
browser. Zero npm dependencies: `slack.js` uses Node's built-in `fetch` (Node 18+).

**Two ways to get a message out — pick based on how approved it already is.** `slack.js --send` here
does an **explicit, direct API send**: it's for a message whose exact text Russell has already reviewed
and given specific go-ahead to send (a one-off, or each item in an approved batch) — it dry-runs by
default and only posts with `--commit`. The **`message-draft`** skill's `slack` mode instead **stages a
reply in the Slack composer itself** (browser) and leaves it unsent for Russell to review and press Send
— that's the default path for a reply that hasn't already been explicitly approved. Reads/marks always go
through `slack.js`.

## Auth

`slack.js` calls the Web API with a token, sent as a Bearer header plus a companion `d` session cookie.
The cookie is required for a browser-issued `xoxc` user token (which is `invalid_auth` without it) and for
the `client.*` endpoints; a bot/app token that doesn't need a cookie can set it to any non-empty value. A
user token is what lets the poller read unread DMs and mentions the way the account-holder sees them.

Set three environment variables (never in a file):

- **`SLACK_BOT_TOKEN`** — the Slack API token (for a personal user token, the `xoxc-` value).
- **`SLACK_COOKIE_D`** — the `d` session cookie value (the `xoxd-…` companion to an `xoxc` token).
- **`SLACK_TEAM_ID`** — the workspace's team id.

**Secrets stay machine-local.** The plugin code is shared via the marketplace; the token/cookie are
per-machine, so the workspace is only reachable where you've set them. For a browser-sniffed user token,
the token and cookie expire periodically — when `--check` reports `invalid_auth`, re-sniff both from the
browser (the token from `localStorage.localConfig_v2.teams[<teamId>].token`, the cookie from
DevTools → Application → Cookies → `d`) and re-set the env vars. There is no refresh-token flow.

## Scripts

Under `scripts/` (run with `node`):

- **`slack.js`**
  - Auth glance: `node slack.js --check` (calls `auth.test`; prints the signed-in user/team; non-zero
    exit on auth failure)
  - List unread: `node slack.js --list-unread [--top=50] [--json]` — unread **DMs**, **group DMs**,
    **@-mentions of you in channels**, **unread channel messages (no @-mention, one item per channel)**,
    and **unread replies in subscribed threads**, newest-first. **Muted conversations are skipped**
    (muting is the user's "stop"). `--json` emits a structured array; each item carries `id`
    (`<channel>:<ts>`), `channel`, `channelType` (`im`/`mpim`/`channel`/`thread`), `ts`, `threadTs`
    (set for thread items), `from`, `fromId`, `subject`, `channelName`, `received` (ISO), `preview`,
    `unreadCount`. Channel items: `subject` is `"@mention in #name"` for @-mention items or
    `"Unread in #name"` for non-mention unread items.
  - Show one: `node slack.js --show --channel=<C> --ts=<ts> [--thread-ts=<tts>] [--json]` — the message
    text plus a `chat.getPermalink` url. Pass `--thread-ts` to read a threaded reply. `--json` emits
    `{channel,ts,threadTs,from,fromId,received,text,permalink}`.
  - History: `node slack.js --history --channel=<C> [--thread-ts=<tts>] [--limit=50] [--json]` — recent
    messages, oldest first: a whole thread (`conversations.replies`) when `--thread-ts` is given, else
    the channel/DM/group-DM timeline (`conversations.history`). Use this for a situational check — a
    captured item's `url`/`ts` points at one message, not the whole conversation, so pull the history
    around it to see anything posted after capture, in either direction (the contact's reply, or your
    own follow-up). `--json` emits an array of `{ts,threadTs,replyCount,from,fromId,received,text}`.
  - Mark read: `node slack.js --mark --channel=<C> --ts=<ts> [--thread-ts=<tts>]` — `conversations.mark`
    up to `<ts>`, or `subscriptions.thread.mark` when `--thread-ts` is given (the conversation/thread's
    "gone"; reversible — re-reading re-surfaces it, never deletes).
  - Find a DM: `node slack.js --find-dm=<name substring> [--json]` — `users.list` matched against real
    name, then `conversations.open` per match to resolve the 1:1 DM channel id (`conversations.open` only
    opens/returns the existing DM, it never sends). **Duplicate-account aware**: long-lived workspaces
    accumulate an old inactive account plus a person's current one under the same name — results are
    sorted newest-`updated`-first and flagged with `[DUPLICATE NAME: N accounts...]` when more than one
    account matches, so the stale one is never silently picked. This isn't rare: one real workspace had
    156 duplicate names out of ~4,300 members.
  - Send: `node slack.js --send --user=<userId> --text="..." [--unfurl=false] [--commit]` —
    `conversations.open` + `chat.postMessage`. **Dry-run by default** (prints the resolved channel and
    exact text, does not send); only sends with `--commit`. Use `--channel=<C>` instead of `--user` to
    send to a channel or an already-known conversation id directly. A real `<@USERID>` in `--text` renders
    as a proper mention chip. To make a message read like a forward of an existing Slack message without
    hand-reconstructing the quote, just include that message's own permalink in `--text` — with unfurl
    left on (the default), Slack auto-unfurls its own permalink into a rich quote card (avatar, author,
    text, "Posted in #channel", "View message"), which reads like a native forward for a fraction of the
    code. **Never `--commit` without the specific message having been reviewed and explicitly approved**
    — the dry-run output is what to show for that approval, every time, even inside an already-approved
    batch (dry-run each item, don't skip straight to committing the whole batch blind).
  - Delete: `node slack.js --delete --channel=<C> --ts=<ts> [--commit]` — `chat.delete`. Dry-run by
    default; only deletes with `--commit`. Verify afterward with `--history` on the same channel and
    confirm the message is actually gone — `chat.delete` can silently no-op on a message it doesn't own.

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
- `users.list` — full member directory, paginated (`--find-dm`); each member carries an `updated`
  timestamp, which is what the duplicate-account sort/flag is built on.
- `conversations.open` — resolve or create the 1:1 DM channel for a user id (`--find-dm`, `--send --user`).
  Never sends anything by itself.
- `chat.postMessage` — the actual send (`--send --commit`).
- `chat.delete` — retract a message you sent (`--delete --commit`).

## Notes

- The load-bearing identifier is **`<channel>:<ts>`** (the `id` in `--json`): a Slack `ts` is unique per
  message. Pass the `channel`/`ts` (and `threadTs` for a thread item) to `--show`, `--mark`, and `--delete`.
- An **item** is one **conversation** for a DM/group-DM (keyed to its latest unread message), one
  **message** for each channel @-mention, and one **thread** for each subscribed thread with unread
  replies (keyed to its latest unread reply).
- **`--send` is for an already-approved, explicit outbound message** — a one-off Russell just reviewed,
  or one item in a batch he's given a specific go-ahead to run. It is not a substitute for
  `message-draft`'s browser-composer staging when a reply hasn't been explicitly approved yet — default
  to `message-draft` unless the exact text has already been reviewed and greenlit.
