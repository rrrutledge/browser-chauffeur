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

**Shared email rules:** See `email-base.md` for CAPTURE shape, SITUATIONAL-CHECK decision logic,
DRAFT-MODE voice rules, and JUNK-LEARNING priority order. This file covers only the Gmail-specific
mechanisms.

## Config (in `.claude/drainer.local.md` → `providers.gmail`)
No config — auth is by environment variables. Credentials: `GMAIL_ADDRESS` (the full address) and
`GMAIL_APP_PASSWORD` (the 16-character Google App Password) in the environment. The mailbox must have
2-Step Verification on and IMAP enabled (Workspace: the admin must also allow IMAP). Optionally
`GMAIL_SIGNATURE_HTML` (an HTML snippet) — when set, `gmail.js` appends it to every staged draft
automatically, since IMAP has no way to read the account's actual Gmail-configured signature.

The `gmail` `gmail.js` lives at `<gmail-skill>/scripts/gmail.js` — run it with `node`.

## AUTH-GLANCE
Run `node gmail.js --check`. If it prints "Signed in as … Inbox has N message(s)." you're connected. If
it errors with `AUTHENTICATIONFAILED` / "Invalid credentials", the app password is wrong/revoked or
IMAP is disabled — re-mint the app password, re-set `GMAIL_APP_PASSWORD`, confirm IMAP is enabled, then
retry. There is no token to refresh; never surface a raw auth error to the user.

## SITUATIONAL-CHECK mechanism
Use `mcp__claude_ai_Gmail__search_threads` with `subject:"<subject>"` (no `in:` filter) — this covers
All Mail in both directions. Read newest-first. CLEAR archives to All Mail (not Trash), so any reply
the contact sent after capture is always findable here. Also run `node gmail.js --list-drafts` to check
for an existing draft before staging a new one.

## CAPTURE
See `email-base.md` for the shared two-file shape. Gmail-specific: `messageId` is the RFC822
Message-ID header (with angle brackets). The `url` opens the message in Gmail by that id.

## CLEAR
`node gmail.js --archive=<messageId>` — removes the message from the inbox and keeps it in **[Gmail]/All
Mail** (reversible; narrate it). Archiving, not trashing, is the drainer's clear: a drained item has
been dealt with, not discarded.

`--reply` looks the original up in both the inbox and All Mail, so it can thread and quote whether the
message is still in the inbox or has already been archived — archive order relative to drafting no longer
matters.

## JUNK-LEARNING (the first-reach rule — Gmail-specific)
The first-reach stop (per `email-base.md`'s rule-first order): a **Gmail filter**, using the
**`mail-filters`** skill to choose the phrase and shape. Gmail scopes on `subject:(…)` so a *generic
footer* phrase (one that also appears in wanted mail) can't trigger the filter — but a **distinctive**
body phrase that only shows up in this junk type is fair game via `--add-body` — reach for it when the
subject doesn't hand you a clean phrase. Use `from:X subject:Y` for company-specific noise. Once Russell OKs the phrase, append it to the right mechanism bucket with the
**`gmail`** skill's `filters.js` (the OAuth settings path):
`node filters.js --append-filter=<id> --add-subject='"<phrase>"'` for a subject phrase, or `--add-body`
for a body phrase — `--list-filters` first to find the bucket's id. Create a new bucket with
`--create-filter --query='…' --archive --mark-read` only for a genuinely new mechanism.

## DRAFT-MODE CLI commands
Follow all voice and reply-vs-fresh rules in `email-base.md`, then use these Gmail commands:

- **Reply-all on the thread:** `node gmail.js --reply --message-id=<messageId> --body-file=<file>`
  — sets In-Reply-To/References, appends the quoted original, and CCs all original To+CC recipients.
  Thread off the **most recent message** (see `email-base.md`). Pass the latest message-id even
  when that message is one the user sent; `--reply` searches All Mail so no inbox restore is needed.
- **Fresh note:** `node gmail.js --draft-new --to="<addr>" --subject="<subj>" --body-file=<file>
  [--cc="<addrs>"]`
