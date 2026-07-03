---
name: gmail
description: Read/draft/clear a personal Gmail or Google Workspace mailbox via IMAP using a Google App Password — no OAuth app, no Cloud project, no browser. Use to list the inbox, show a message, archive mail, or stage reply/new drafts in the Drafts folder. Staging is draft-only; a reviewed draft is sent only on Russ's explicit per-message say-so via --send-draft. For a Google account where you can mint an app password (2-Step Verification on, IMAP enabled).
---

# Gmail — Personal/Workspace Mail via IMAP + App Password

Read and write a Gmail or Google Workspace mailbox directly over **IMAP** with a **16-character
App Password** — no OAuth client, no Google Cloud project, no browser automation. Built on:

- **`imapflow`** — the IMAP client (connect, list, search, fetch, move, append).
- **`mailparser`** — parses fetched RFC822 source into headers + text/html.
- **`nodemailer`** (MailComposer) — builds RFC822 drafts (reply and new) that are appended to Drafts.

**Why an app password, not OAuth:** the Gmail REST API requires registering an OAuth client inside a
Google Cloud project. IMAP needs only an app password, which everything the drainer does (list, archive,
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
  - List sent: `node gmail.js --list-sent [--top=50] [--json]` (sent mail, newest-first; same output
    format as `--list-inbox`)
  - Search: `node gmail.js --search=<query> [--folder=all|inbox|sent] [--top=50] [--json]` (IMAP TEXT
    search — matches headers + body; `--folder` defaults to `all` (`[Gmail]/All Mail`), covering both
    inbox and sent; results newest-first. Use this to check whether a reply was sent to a contact before
    concluding a thread is unresponded.)
  - Show one: `node gmail.js --show=<message-id>` (`<message-id>` is the Message-ID header, with the
    angle brackets, e.g. `<abc@mail.gmail.com>`)
  - List drafts: `node gmail.js --list-drafts [--top=30]`
  - Draft reply (never sends): `node gmail.js --reply --message-id=<id> --body-file=reply.md`
    (appends a threaded draft to `[Gmail]/Drafts` with In-Reply-To/References set + the quoted original).
    `<id>` is looked up in both the **inbox and All Mail**, so pass the **most recent** message in the
    thread to thread off — even one the user sent. When that message is the user's own, the reply keeps its recipients (To/CC)
    instead of addressing back to the user; otherwise it's a reply-all to the sender + other recipients.
  - **`--body-file` is Markdown** — write the body in Markdown (`**bold**`, `[text](url)`, paragraphs,
    lists) and the script converts it to HTML via `marked`. HTML tags in the source pass through
    unchanged.
  - Draft new (never sends): `node gmail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.md [--cc=c@z]`
    (`--reply` and `--draft-new` each print a `draft-id:` line — the staged draft's Message-ID. That id
    is what `--send-draft` takes. `--reply` also replaces any prior draft on the same thread, so a thread
    never carries more than one draft.)
  - Send a staged draft (REAL SEND): `node gmail.js --send-draft --draft-id=<draft-message-id>`
    (transmits that one draft's exact bytes via SMTP, removes it from Drafts; Gmail files the copy in
    `[Gmail]/Sent`). See **Sending** below — this runs only on Russ's explicit per-message say-so.
  - Archive one (reversible): `node gmail.js --archive=<message-id>` (removes from the inbox, keeps it in
    `[Gmail]/All Mail` — the way mail is cleared: handled and out of the inbox, never discarded)

## Sending

Staging is the default and stays draft-only. A staged draft becomes a real send **only** when Russ
gives an explicit per-message instruction to send (e.g. "send it") **after** he has reviewed that exact
draft in this turn. When that happens:

1. Re-show (or confirm he just saw) the exact draft text that will go out.
2. Run `node gmail.js --send-draft --draft-id=<the draft-id printed when it was staged>`.

Hold the line on these — they are what keep send safe:

- Default, silence, or ambiguous phrasing mean draft-only. Never infer a send from anything but a
  clear, explicit instruction to send this message.
- Send only the draft Russ reviewed this turn. Because `--reply` replaces prior drafts on the thread,
  the `draft-id` you just staged is the one he saw — send that id, never an older one.
- An autonomous or `auto-handle` drain never sends. `--send-draft` is human-in-the-loop only; in any
  non-interactive run, stop at the staged draft.

## Auth-error handling

`--check` is the cheap glance. An auth failure (`AUTHENTICATIONFAILED` / "Invalid credentials") means
the app password is wrong/revoked or IMAP is disabled — re-mint the app password and re-set
`GMAIL_APP_PASSWORD`, and confirm IMAP is enabled. There is no token to refresh.

## Notes

- The load-bearing identifier is the **Message-ID header** (`id` in `--json`): pass it to `--show`,
  `--reply`, and `--archive`. `--show` and `--archive` look the header up in the **INBOX** (valid while
  the message is in the inbox); `--reply` looks it up in the **inbox and All Mail**, so it can thread off
  any message in the thread — inbox, archived, or sent.
- Drafts (`--reply` / `--draft-new`) land in **[Gmail]/Drafts**. They go out only via `--send-draft` on
  Russ's explicit say-so (see **Sending**); otherwise he reviews and sends in Gmail himself.
- Gmail's special folders are addressed as `[Gmail]/Drafts` and `[Gmail]/All Mail`.
