# gmail provider — personal/Workspace Gmail (IMAP + app password)

A provider for a **Gmail or Google Workspace** mailbox read and cleared entirely through **IMAP** with
a 16-character **App Password** — no OAuth client, no Cloud project, no browser. All IMAP calls go
through the **`gmail`** skill's `gmail.js` (don't reimplement IMAP here); it owns the connection and the
`[Gmail]/Drafts` + `[Gmail]/All Mail` folder mechanics. Implements `../engine/provider.md`; classify by
`../engine/triage.md`.
id prefix: `gmail-`; body file: `<id>.email.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the
> sibling **`gmail-adapter.py`** that the poller drives. This doc is the **worker-facing** prose —
> AUTH-GLANCE, the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> This is the IMAP counterpart to the Graph-based `outlook-graph-provider.md`. Use it for a Google
> account where you can mint an app password (2-Step Verification on, IMAP enabled).

## Config (in `.claude/drainer.local.md` → `providers.gmail`)
No config — auth is by environment variables. Credentials: `GMAIL_ADDRESS` (the full address) and
`GMAIL_APP_PASSWORD` (the 16-character Google App Password) in the environment. The mailbox must have
2-Step Verification on and IMAP enabled (Workspace: the admin must also allow IMAP).

The `gmail` `gmail.js` lives at `<gmail-skill>/scripts/gmail.js` — run it with `node`.

## AUTH-GLANCE
Run `node gmail.js --check`. If it prints "Signed in as … Inbox has N message(s)." you're connected. If
it errors with `AUTHENTICATIONFAILED` / "Invalid credentials", the app password is wrong/revoked or
IMAP is disabled — re-mint the app password, re-set `GMAIL_APP_PASSWORD`, confirm IMAP is enabled, then
retry. There is no token to refresh; never surface a raw auth error to the user.

## SITUATIONAL-CHECK (do this BEFORE drafting any reply)
The captured item is the original inbound message; the conversation may have moved on. Check the
sent thread first — search Gmail for the subject with `in:sent` to see whether the user has already
replied since this item was captured. Use `mcp__claude_ai_Gmail__search_threads` with a query like
`subject:"<subject>" from:<user_address> in:sent` and read the thread to find the latest sent
message. If the user's most recent message on the thread is already a reply to this sender, close
the item without a new draft. Also check Drafts — `node gmail.js --list-drafts` — to avoid
creating a duplicate if a prior session already staged one.

## CAPTURE (the item shape the worker reads)
The adapter writes these two files for each dispatched item (`gmail-adapter.py` → `capture`); this is
the shape the worker can rely on:
- `items/<id>.email.md` — header block (From, Received, Link, MessageId) + the full body text (from
  `gmail.js --show=<messageId>`).
- `items/<id>.json` — `{ "id","source":"gmail","triage","kind","from","subject","received","snippet",`
  `"url":"<gmail web link>","messageId":"<RFC822 Message-ID>","emailFile":"<abs path>","ts" }`.

`messageId` is the load-bearing field — the worker needs it for the reply draft and for CLEAR. It is the
RFC822 Message-ID header (with angle brackets). The `url` opens the message in Gmail by that id.

## CLEAR
`node gmail.js --archive=<messageId>` — removes the message from the inbox and keeps it in **[Gmail]/All
Mail** (reversible; narrate it). This is the email "handled and out of the inbox" — it stays fully
searchable in All Mail with no Trash purge timer. Archiving, not trashing, is the drainer's clear: a
drained item has been dealt with, not discarded.

**Order matters when you're also drafting a reply:** stage the threaded reply draft (DRAFT-MODE below)
*before* you archive the original. `--reply` reads the original out of the inbox to thread on and quote it,
so once the message has left the inbox a reply can no longer thread. If the original was already cleared (a
prior session archived it, or you cleared it first), move it from All Mail back to the inbox before replying,
then archive it again after the draft is staged:
```js
// .tmp restore helper — search [Gmail]/All Mail by Message-ID, messageMove(uid, 'INBOX')
```

## JUNK-LEARNING
Stop this junk arriving again, in **priority order** (best outcome = never received) — propose, never
apply without the user's OK:
1. **Unsubscribe** — if the message carries an unsubscribe link (a `List-Unsubscribe` header or a footer
   link), propose using it. This is the cleanest stop.
2. **Turn it off at the source app** — if there's no unsubscribe but the sender is an app whose
   notifications the user controls (GitHub notification settings, LinkedIn email preferences, …),
   propose adjusting that app's settings so the email is never sent.
3. **Gmail filter** — only when neither above applies, fall back to a filter (Gmail → Settings →
   Filters → a sender/subject match that archives or deletes the sender going forward). IMAP can't
   create Gmail filters, so describe the filter for the user to add.

## DRAFT-MODE
**First, before writing a single word of the body: invoke the `document-authoring` skill (call the Skill
tool to load it) and read its Conversational writing + "Never do these" sections. Compose the draft
against what you just read — do not write from memory.** The skill is the single source of truth for
Russell's voice and its hard rules; a draft composed from memory reliably leaks the very tokens those
rules ban. This read is a gate: it happens before drafting, not as an after-the-fact check.

Then write the message text in that voice. The voice loop in the document-authoring skill still applies —
diff sent-vs-draft after each send and append a lesson. Write the body as HTML to a file, then create the
draft with `gmail.js` — **never sent** from inside the worker. Show the draft text in the terminal. The
user reviews it and either edits + sends in Gmail himself, or — back in the top-level interactive session
— tells Claude to send it, which promotes that exact draft via `gmail.js --send-draft` (see the `gmail`
skill's **Sending** section). A worker never sends; it only stages. Pick the mode by who the message goes to:
- **Reply on the thread** (responding to inbound mail): always use `node gmail.js --reply
  --message-id=<messageId> --body-file=<file>` — it sets In-Reply-To/References and appends the quoted
  original, so the draft lands *inside* the conversation in [Gmail]/Drafts. This is what makes the draft
  openable and editable in Gmail's compose box at the bottom of the thread. A draft made with `--draft-new`
  carries no threading headers — Gmail shows it as a floating duplicate that's awkward to open — so never
  fall back to `--draft-new` for a reply. The original must be in the inbox for `--reply` to work; if it's
  already in All Mail, restore it first (see CLEAR), reply, then re-archive.
- **Fresh 1:1 (or small-group) note** (e.g. an outreach nudge to one contact — do NOT reply-all a group
  thread to single someone out): `node gmail.js --draft-new --to="<addr>" --subject="<subj>"
  --body-file=<file> [--cc="<addrs>"]`.
