# personal-outlook provider — personal Outlook.com mail (Microsoft Graph API)

A provider for a **personal** Outlook.com mailbox (`outlook.live.com`) read and cleared entirely
through the **Microsoft Graph API** — no browser. All Graph calls go through the **`ms-graph`** skill's
`mail.js` (don't reimplement Graph here); it owns auth, the token cache, and silent refresh. Implements
`../engine/provider.md`; classify by `../engine/triage.md` (this file is only the mechanics).
id prefix: `poutlook-`; body file: `<id>.email.md`.

> This is the API counterpart to the browser `outlook-provider.md` (which is for **enterprise** Outlook
> on the web). Use this one for a personal Microsoft account: it's cheaper, faster, and browser-free.

## Config (in `.claude/drainer.local.md` → `providers.personal-outlook`)
No config — you sign in once via `ms-graph`. Credentials: `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` in
the environment (used by `ms-graph`); the MSAL token cache is machine-local at
`~/.claude/ms-graph/token-cache.json`.

The `ms-graph` `mail.js` lives at
`<ms-graph-skill>/scripts/mail.js` — run it with `node`.

## AUTH-GLANCE
Run `node mail.js --list-unread --top=1`. If it prints messages (or "No unread messages."), you're
signed in. If it errors with "Not signed in" or an auth error, do the `ms-graph` one-time sign-in
(`node scripts/auth.js` via browser-chauffeur), then retry — never surface the token error to the user.

## ENUMERATE
`node mail.js --list-inbox --since-days=<inbox_window_days, default 7>` — inbox **read + unread** within
the window, newest-first. Each block gives the received time, a `read`/`UNREAD` marker, subject, sender,
the Graph **message id**, the **deep link** (`webLink`), and a preview line — enough to triage from the
block alone. Triage every returned message regardless of read state (the goal is an empty inbox, not just
zero-unread); de-duplication against already-processed items is the **poller's** job via seen-state, not
this provider's. Build a stable id:
`poutlook-<YYYYMMDD-HHMM of received>-<sender-slug>-<first-3-subject-words-slug>` (lowercase,
non-alphanumerics → single dashes; ≤48 chars). Triage from the block; if a block is genuinely
undecidable, `node mail.js --show=<messageId>` that ONE message to disambiguate.

## CAPTURE (needs-you)
`node mail.js --show=<messageId>` to read the full body, then capture:
- **Deep link** = the message's `webLink` from ENUMERATE (an `outlook.live.com` deep link).
- Write `items/<id>.email.md` — header block (From, To, Cc, Date, Subject, Link, MessageId) + the full
  body text from `--show`.
- Write `items/<id>.json`:
  `{ "id","source":"personal-outlook","triage":"needs-you","kind":"reply|work|work-then-reply","from",`
  `"subject","received","snippet","whatsAsked":"<1-2 lines>","url":"<webLink>","messageId":"<Graph id>",`
  `"emailFile":"<abs path to .email.md>","ts":"<ISO now>" }`
Keep `messageId` — the worker needs it for the reply draft and for CLEAR.

## CLEAR
`node mail.js --delete=<messageId>` — moves the message to **Deleted Items** (reversible; narrate it).
This is the email "gone." Never a permanent purge.

## JUNK-LEARNING
Stop this junk arriving again, in **priority order** (best outcome = never received) — propose, never
apply without the user's OK:
1. **Unsubscribe** — if the message carries an unsubscribe link (a `List-Unsubscribe` header or a footer
   link), propose using it. This is the cleanest stop.
2. **Turn it off at the source app** — if there's no unsubscribe but the sender is an app whose
   notifications the user controls (GitHub notification settings, LinkedIn email preferences, …),
   propose adjusting that app's settings so the email is never sent.
3. **Outlook.com inbox rule** — only when neither above applies, fall back to a rule (Settings → Rules:
   a sender/subject match that deletes or files the sender going forward). Graph can create rules via
   `/me/mailFolders/inbox/messageRules`; until that's wired into `mail.js`, describe the rule for the
   user to add.

## DRAFT-MODE
Apply the **`document-authoring`** voice to the message text (this is what `message-draft` would do; the
voice loop in the document-authoring skill still applies — diff sent-vs-draft after each send and append
a lesson). Write the body as HTML to a file, then create the draft with `mail.js` — **never sent**. Show
the draft text in the terminal and tell the user to edit + send it themselves. Pick the mode by who the
message goes to:
- **Reply on the thread** (responding to inbound mail): `node mail.js --reply --message-id=<messageId>
  --body-file=<file>` — a reply-all draft in the thread. Include the quoted original per
  `~/.claude/CLAUDE.md` (Graph's reply-all keeps the thread quote below your text automatically).
- **Fresh 1:1 (or small-group) note** (e.g. an outreach nudge to one contact — do NOT reply-all a group
  thread to single someone out): `node mail.js --draft-new --to="<addr>" --subject="<subj>"
  --body-file=<file> [--cc="<addrs>"]`.
