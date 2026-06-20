---
name: gmail
description: Read/draft/clear a personal Gmail or Google Workspace mailbox via IMAP using a Google App Password — no OAuth app, no Cloud project, no browser. Use to list the inbox, show a message, archive mail or move it to Trash, or stage reply/new drafts in the Drafts folder (never sent). For a Google account where you can mint an app password (2-Step Verification on, IMAP enabled).
---

# Gmail — Personal/Workspace Mail via IMAP + App Password

Read and write a Gmail or Google Workspace mailbox directly over **IMAP** with a **16-character
App Password** — no OAuth client, no Google Cloud project, no browser automation. Built on:

- **`imapflow`** — the IMAP client (connect, list, search, fetch, move, append).
- **`mailparser`** — parses fetched RFC822 source into headers + text/html.
- **`nodemailer`** (MailComposer) — builds RFC822 drafts (reply and new) that are appended to Drafts.

**Why an app password, not OAuth:** the Gmail REST API requires registering an OAuth client inside a
Google Cloud project. IMAP needs only an app password, which everything the drainer does (list, trash,
stage drafts) flows through. Simpler to set up and headless-safe (no token to refresh).

## Setup (per machine)

1. **Install deps** (idempotent, one-time): `node <skill>/scripts/setup.js` — installs imapflow /
   mailparser / nodemailer to `~/.claude/gmail/node_modules` so any copy of the script resolves them.
2. **Enable the prerequisites on the Google account** (once):
   - Turn on **2-Step Verification**.
   - In Gmail → Settings → **Forwarding and POP/IMAP** → **Enable IMAP**. For Workspace, the admin
     must also allow IMAP access.
3. **Mint an App Password** at `https://myaccount.google.com/apppasswords` (name it e.g. "drainer").
   Google shows the 16-character code **once** — as four space-separated groups of four lowercase
   letters. Capture all 16 letters (no spaces).
4. **Set secrets as env vars** (never in a file): `GMAIL_ADDRESS` (the full address) and
   `GMAIL_APP_PASSWORD` (the 16 letters, no spaces).

**Secrets stay machine-local.** The plugin code is shared via the marketplace; `GMAIL_ADDRESS` /
`GMAIL_APP_PASSWORD` are per-machine, so the mailbox is only reachable where you've set them.

## Scripts

Under `scripts/` (run with `node`):

- **`gmail.js`**
  - Auth glance: `node gmail.js --check` (connects, reports inbox count; non-zero exit on auth failure)
  - List inbox: `node gmail.js --list-inbox [--top=50] [--json]` (newest-first; `--json` emits a
    structured array for scripts — each item has the RFC822 Message-ID as `id`, plus `uid`, `subject`,
    `from`, `fromAddress`, `received`, `isRead`)
  - Show one: `node gmail.js --show=<message-id>` (`<message-id>` is the Message-ID header, with the
    angle brackets, e.g. `<abc@mail.gmail.com>`)
  - List drafts: `node gmail.js --list-drafts [--top=30]`
  - Draft reply (never sends): `node gmail.js --reply --message-id=<id> --body-file=reply.html`
    (appends a threaded draft to `[Gmail]/Drafts` with In-Reply-To/References set + the quoted original)
  - Draft new (never sends): `node gmail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.html [--cc=c@z]`
  - Archive one (reversible): `node gmail.js --archive=<message-id>` (removes from the inbox, keeps it in
    `[Gmail]/All Mail` — no Trash purge timer; this is the "handled, out of the inbox" clear)
  - Trash one (reversible): `node gmail.js --trash=<message-id>` (moves to `[Gmail]/Trash`, never a
    permanent purge)

## Auth-error handling

`--check` is the cheap glance. An auth failure (`AUTHENTICATIONFAILED` / "Invalid credentials") means
the app password is wrong/revoked or IMAP is disabled — re-mint the app password and re-set
`GMAIL_APP_PASSWORD`, and confirm IMAP is enabled. There is no token to refresh.

## Notes

- The load-bearing identifier is the **Message-ID header** (`id` in `--json`): pass it to `--show`,
  `--reply`, `--archive`, and `--trash`. Lookups search the INBOX for that header, so it stays valid as
  long as the message is in the inbox.
- Drafts (`--reply` / `--draft-new`) land in **[Gmail]/Drafts** and are never sent — the user reviews
  and sends in Gmail.
- Gmail's special folders are addressed as `[Gmail]/Drafts`, `[Gmail]/Trash`, and `[Gmail]/All Mail`.
