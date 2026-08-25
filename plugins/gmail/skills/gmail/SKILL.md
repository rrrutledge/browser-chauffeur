---
name: gmail
description: Read/draft/clear a personal Gmail or Google Workspace mailbox via IMAP using a Google App Password — no OAuth app, no Cloud project, no browser. Use to list the inbox, show a message, archive mail, or stage reply/new drafts in the Drafts folder. Staging is draft-only; a reviewed draft is sent only on Russ's explicit per-message say-so via --send-draft. For a Google account where you can mint an app password (2-Step Verification on, IMAP enabled). Also manages Gmail filters programmatically (list/create/append/delete) through a separate, additive OAuth settings-only path — filters.js.
---

# Gmail — Personal/Workspace Mail via IMAP + App Password

**A native `mcp__claude_ai_Gmail__*` connector (Claude's built-in Gmail integration) may also be
connected to this same mailbox** — for the ISC account (`russ@innersourcecommons.org`), it is. That
connector has no signature handling and no way to delete a draft it created. **Always draft and reply
through this skill's `gmail.js`, never the native connector** — `GMAIL_SIGNATURE_HTML` places the
signature correctly (after the body, before the quoted original) on every `--reply`/`--draft-new`, and
`--delete-draft` cleans up a stray or superseded draft. Reach for the native connector only for
read-only lookups this skill doesn't cover (e.g. `search_threads` across accounts this skill isn't
configured for) — never for staging a draft on an account this skill already serves.

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
5. **Optional signature** — set `GMAIL_SIGNATURE_HTML` to an HTML snippet (e.g.
   `Name<br>Title<br><a href="...">...</a>`) and `--draft-new`/`--reply` append it to every staged
   draft automatically. IMAP has no way to read the account's Gmail-configured signature (that's a
   webmail-only setting with no IMAP equivalent), so this env var is the closest available substitute —
   set it once from whatever your Gmail signature actually says, and update it by hand if that changes.
   **When `GMAIL_SIGNATURE_HTML` is set, the `--body-file` content must end on its last substantive
   sentence — never add a name/sign-off line of your own (`Russ`, `Thanks, Russ`, etc.).** The
   auto-appended block already names the sender, so a sign-off line above it duplicates the name and
   is the single most common mistake when staging a draft here — check the last line of every
   `--body-file` against this before running `--reply`/`--draft-new`.

**Secrets stay machine-local.** The plugin code is shared via the marketplace; `GMAIL_ADDRESS` /
`GMAIL_APP_PASSWORD` / `GMAIL_SIGNATURE_HTML` are per-machine, so the mailbox is only reachable (and
signed the same way) where you've set them.

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
    **Skip a Gmail emoji-reaction email as the threading target** — a bare 👍/❤️ sent via Gmail's
    in-app reaction feature is a real message with a real Message-ID, but Gmail renders it specially and
    shows blank when opened, so a reply threaded off it looks empty to the recipient in the Gmail UI even
    though the draft itself is fine. When the most recent message in the thread is a reaction, thread off
    the nearest message before it that carries real content instead.
  - **`--body-file` is Markdown** — write the body in Markdown (`**bold**`, `[text](url)`, paragraphs,
    lists) and the script converts it to HTML via `marked`. HTML tags in the source pass through
    unchanged. **If `GMAIL_SIGNATURE_HTML` is set (see Setup step 5), stop at the last content
    sentence — no sign-off line.**
  - **`--no-quote` (with `--reply`)** — suppress the auto-appended quoted original while keeping the
    thread's In-Reply-To/References headers. Use it for an **interleaved reply**: the `--body-file`
    supplies its own quote (the sender's text in styled `<blockquote>`s) with responses spliced between
    their points, instead of a single clean quote at the bottom. Without it, `--reply` always appends
    the full quoted original.
  - **`--inline=<img[,img]>` (with `--reply` / `--draft-new`)** — embed image files in the message body via `cid:` references, placed after the body text, so they render inline rather than as a bottom-of-message attachment.
    It combines with `--attach` for regular files.
    **Default to `--inline` for illustrative screenshots** - a screenshot that illustrates or proves a point the body text is making belongs next to that point.
  - **`--to=<addr>` (with `--reply`)** — override the computed recipient, for threading a reply off a no-reply relay whose real correspondent is in `Reply-To` (e.g. a Google "shared a file" notification) so the reply reaches the person, not the no-reply box.
  - Draft new (never sends): `node gmail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.md [--cc=c@z]`
    (`--reply` and `--draft-new` each print a `draft-id:` line — the staged draft's Message-ID. That id
    is what `--send-draft` takes. `--reply` also replaces any prior draft on the same thread, so a thread
    never carries more than one draft.)
  - Send a staged draft (REAL SEND): `node gmail.js --send-draft --draft-id=<draft-message-id>`
    (transmits that one draft's exact bytes via SMTP, removes it from Drafts; Gmail files the copy in
    `[Gmail]/Sent`). See **Sending** below — this runs only on Russ's explicit per-message say-so.
  - Archive one (reversible): `node gmail.js --archive=<message-id>` (removes from the inbox, keeps it in
    `[Gmail]/All Mail` — the way mail is cleared: handled and out of the inbox, never discarded)
  - Delete a draft: `node gmail.js --delete-draft=<draft-message-id>` (discards a staged draft that's no
    longer wanted — e.g. the outreach it belonged to was abandoned. Takes the same `draft-id` that
    `--reply`/`--draft-new` printed when it was staged. Drafts have no other home, so this isn't
    recoverable the way `--archive` is — only delete a draft once its underlying card/thread is truly
    closed out, not as a routine cleanup step.)

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

## Filter management (OAuth settings path)

Managing Gmail **filters** lives in the Gmail settings REST API, which IMAP can't reach — so filters use
a **second, additive path** alongside the app-password path above. It is **settings-only**: its single
scope is `https://www.googleapis.com/auth/gmail.settings.basic`, which lists/creates/deletes filters and
grants **no** mail read or send. The IMAP + app-password path still owns all message access; this path
only adds filters. Together they make Gmail a peer of Outlook, whose rules are managed programmatically
through `ms-graph`'s `mail.js`.

Use the **`mail-filters`** skill to choose *what* a filter should match (the phrase-selection craft and
the master `-from:` fence); use these commands to *create* it.

### Setup (per machine, one-time)

1. **Deps** — `node <skill>/scripts/setup.js` also installs `google-auth-library` (the OAuth client)
   into `~/.claude/gmail/node_modules`.
2. **Google Cloud OAuth client** — in a Google Cloud project with the **Gmail API** enabled, create an
   OAuth client of type **Desktop app** (a desktop client allows the loopback redirect this flow uses
   without pre-registering a URI). Capture its id/secret into env vars (never a file):
   `GMAIL_OAUTH_CLIENT_ID`, `GMAIL_OAUTH_CLIENT_SECRET`.
3. **One-time sign-in** — `node <skill>/scripts/gmail-auth.js`, driven via **browser-chauffeur**: it
   prints an `AUTH_URL:` line, serves `http://localhost:8710/callback`, and on consent exchanges the code
   and caches the token to `~/.claude/gmail/oauth-token.json` (machine-local). Approve consent as the
   intended account — for ISC that's the Workspace account `russ@innersourcecommons.org`. After this,
   `filters.js` runs silently (the client auto-refreshes the access token).

**Secrets stay machine-local**, like the app password — the mailbox's filters are reachable only where
`GMAIL_OAUTH_CLIENT_ID` / `GMAIL_OAUTH_CLIENT_SECRET` are set and the token is cached.

### Commands — `filters.js`

- **List filters:** `node filters.js --list-filters [--json]` — every filter with its `criteria.query`
  and action; `--json` emits the raw array (each item carries its `id`).
- **Create a filter:**
  `node filters.js --create-filter --query='subject:("A" OR "B") -from:(gmail.com OR outlook.com)' --archive [--mark-read]`
  — `--query` is the raw Gmail search, so OR-lists and the `-from:` fence work verbatim. `--archive`
  removes the `INBOX` label (Skip the Inbox); `--mark-read` also removes `UNREAD`; `--trash` routes to
  Trash instead. `--name` is an optional human label for output only.
- **Append a phrase to a bucket:**
  `node filters.js --append-filter=<id> --add-subject='"C" OR "D"'` (splices inside the `subject:(…)`
  group), `--add-body='"E"'` (splices inside the leading `(…)` group), or `--add='"F"'` (appends
  ` OR "F"` at top level). This is the everyday "add to the right bucket" op.
- **Delete a filter:** `node filters.js --delete-filter=<id>` — reversible: re-create it with
  `--create-filter`. It does not touch mail the filter already archived.

**Gmail filters are anonymous** — identified server-side by `id` + criteria, never a name; read the id
from `--list-filters`. And they **can't be edited in place**, so `--append-filter` reads the query,
splices the addition, **deletes** the old filter, and **creates** a new one — meaning the **id changes**.
The command reports the new id.

## Auth-error handling

`--check` is the cheap glance. An auth failure (`AUTHENTICATIONFAILED` / "Invalid credentials") means
the app password is wrong/revoked or IMAP is disabled — re-mint the app password and re-set
`GMAIL_APP_PASSWORD`, and confirm IMAP is enabled. There is no token to refresh.

For the **OAuth filter path**, a `filters.js` "Not signed in" or an `invalid_grant` (the refresh token was
revoked or expired) means the one-time sign-in must be re-run: `node scripts/gmail-auth.js` via
browser-chauffeur. If Google declines to return a refresh token, revoke prior access at
`https://myaccount.google.com/permissions` first, then re-run so a fresh one is issued.

## Notes

- The load-bearing identifier is the **Message-ID header** (`id` in `--json`): pass it to `--show`,
  `--reply`, and `--archive`. `--show` and `--archive` look the header up in the **INBOX** (valid while
  the message is in the inbox); `--reply` looks it up in the **inbox and All Mail**, so it can thread off
  any message in the thread — inbox, archived, or sent.
- Drafts (`--reply` / `--draft-new`) land in **[Gmail]/Drafts**. They go out only via `--send-draft` on
  Russ's explicit say-so (see **Sending**); otherwise he reviews and sends in Gmail himself.
- Gmail's special folders are addressed as `[Gmail]/Drafts` and `[Gmail]/All Mail`.
