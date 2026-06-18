# personal-outlook provider — personal Outlook.com mail (Microsoft Graph API)

A provider for a **personal** Outlook.com mailbox (`outlook.live.com`) read and cleared entirely
through the **Microsoft Graph API** — no browser. All Graph calls go through the **`ms-graph`** skill's
`mail.js` (don't reimplement Graph here); it owns auth, the token cache, and silent refresh. Implements
`../engine/provider.md`; classify by `../engine/triage.md`.
id prefix: `personal-outlook-`; body file: `<id>.email.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the
> sibling **`personal-outlook-adapter.py`** that the poller drives. This doc is the **worker-facing**
> prose — AUTH-GLANCE, the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

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

## CAPTURE (the item shape the worker reads)
The adapter writes these two files for each dispatched item (`personal-outlook-adapter.py` → `capture`);
this is the shape the worker can rely on:
- `items/<id>.email.md` — header block (From, Received, Link, MessageId) + the full body text (from
  `mail.js --show=<messageId>`).
- `items/<id>.json` — `{ "id","source":"personal-outlook","triage","kind","from","subject","received",`
  `"snippet","url":"<webLink>","messageId":"<Graph id>","emailFile":"<abs path>","ts" }`.

`messageId` is the load-bearing field — the worker needs it for the reply draft and for CLEAR.

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
