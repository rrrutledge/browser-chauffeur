---
name: ms-graph
description: Read/write a personal Microsoft account's Outlook mail and calendar via the Microsoft Graph API (official @azure/msal-node + @microsoft/microsoft-graph-client). Use to list/create/update calendar events, search/read mail, draft replies, or send yourself a note — no browser needed after a one-time sign-in. For personal (consumer) Microsoft accounts.
---

# Microsoft Graph — Personal Outlook Mail & Calendar

**Personal vs work — pick the right skill.** This `ms-graph` skill is Russell's **personal**
Microsoft account (consumer Outlook.com) via MSAL + Graph SDK. For the **work** mailbox use the
**`ms-rest`** plugin (Outlook REST API, session-token sniff) — a corporate MSAL app registration is
ruled out there, so it rides the live Outlook-web token instead. Different auth path, different
mailbox.

Read and write a **personal** Outlook.com mailbox and calendar directly through the Microsoft Graph REST API, no browser automation. Built on Microsoft's own libraries:

- **`@azure/msal-node`** — handles auth, the token cache, and silent access-token refresh. It owns the refresh token internally; there is no manual refresh handling.
- **`@microsoft/microsoft-graph-client`** — the official Graph request builder.

**Why delegated, not app-only:** personal (consumer) Microsoft accounts don't support app-only tokens for mail/calendar — only delegated. So a one-time interactive sign-in seeds MSAL's cache, and every later call refreshes silently.

## Setup (per machine)

1. **Install deps** (idempotent, one-time): `node <skill>/scripts/setup.js` — installs the two libraries to `~/.claude/ms-graph/node_modules`.
2. **Set secrets as env vars** (never in a file): `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` from the Entra app registration.
3. **Sign in once** via browser-chauffeur: run `node <skill>/scripts/auth.js`, which prints `AUTH_URL: <url>` and serves `http://localhost:8080/callback`. Have browser-chauffeur navigate to the URL and approve consent. MSAL caches tokens to `~/.claude/ms-graph/token-cache.json` (machine-local, not synced). Re-run if the cache is lost or ~90 days elapse.

**Secrets & data stay machine-local.** This plugin (the code) is shared across machines via the marketplace; the account credentials (env vars) and token cache are per-machine, so the personal mailbox is only reachable where you've set them up.

## Entra app registration

A delegated app supporting "personal Microsoft accounts" with redirect URI (Web) `http://localhost:8080/callback` and delegated scopes `Mail.ReadWrite Mail.Send Calendars.ReadWrite MailboxSettings.ReadWrite User.Read offline_access`. `MailboxSettings.ReadWrite` is what unlocks the inbox-rule commands (`mail.js --list-rules/--create-rule/…`); consumer accounts grant it via dynamic consent at sign-in, so adding it to `SCOPES` and re-running `auth.js` is enough — no portal permission change needed. The `consumers` authority targets the personal mailbox. Recreate the client secret in the portal before it expires and update `GRAPH_CLIENT_SECRET`.

## Scripts

All under `scripts/`:

- **`graph-client.js`** — shared module: `getGraphClient()` (official client, silent-auth) and `getToken()`. Not run directly.
- **`auth.js`** — one-time / ~90-day interactive sign-in (authorization-code flow). Run via browser-chauffeur.
- **`calendar.js`**
  - List upcoming: `node calendar.js --days=14`
  - List calendars: `node calendar.js --list-calendars` (prints `name<TAB>id`)
  - List a named calendar over a date range: `node calendar.js --list --calendar="InnerSource Commons" --start=2026-05-01 --end=2026-05-31 [--tz=] [--json]` (`calendarView` expands recurrences and paginates; `--json` emits a structured array for scripts)
  - Create: `node calendar.js --create --subject="Dentist" --start="2026-06-20T15:00:00" --end="2026-06-20T16:00:00" [--location=] [--body=] [--attendees=a@x,b@y] [--reminder=N]`
  - Update reminder: `node calendar.js --update --subject="Dentist" --reminder=off`
  - Times are `--tz` (default `America/Chicago`). Events have **no** reminder unless `--reminder=N` (minutes before; 0 = at start).
  - Reusable from other scripts: `require('<…>/calendar.js')` exports `getCalendars()`, `getEvents({calendar,start,end,tz})`, `resolveCalendarId()` (CLI is `require.main`-guarded, so requiring it is side-effect-free).
- **`mail.js`**
  - List unread: `node mail.js --list-unread [--top=30]` (inbox unread, newest-first; one block per message with id + webLink)
  - List inbox (read+unread): `node mail.js --list-inbox [--top=50] [--json]` (inbox items regardless of read state, newest-first, count-capped by `--top`; `--json` emits a structured array for scripts)
  - Search: `node mail.js --search="Griffiths" [--top=10]`
  - Show one: `node mail.js --show=<messageId>`
  - Draft reply-all (never sends): `node mail.js --reply --message-id=<id> --body-file=reply.html`
  - Draft new to recipients (never sends): `node mail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.html [--cc=c@z] [--attach=file1.pdf,file2.png] [--replace] [--text]` (`--attach` adds file attachments; `--replace` deletes any existing drafts with the same subject first, so re-runs don't pile up duplicates; `--text` treats the body-file as plain text instead of HTML)
  - Send to self: `node mail.js --send-self --subject="..." --body-file=note.txt`
  - Delete one (reversible): `node mail.js --delete=<messageId>` (moves to Deleted Items, never a permanent purge)
  - Reusable from other scripts: `require('<…>/mail.js')` exports `createDraft(client, {to, subject, body, cc, attach, replace, contentType})` (CLI is `require.main`-guarded).
  - **Inbox rules** (server-side filters; needs the `MailboxSettings.ReadWrite` scope):
    - List: `node mail.js --list-rules [--json]` (full, untruncated conditions/exceptions/actions — the API returns every phrase, unlike the OWA UI which caps the visible list)
    - Create: `node mail.js --create-rule --name="Corporate Subjects" --subject-contains="A||B||C" [--body-contains=] [--from-contains=] [--subject-or-body=] [--except-from="gmail.com||outlook.com||icloud.com"] --move-to=archive [--mark-read] [--delete-msg] [--no-stop]` (multi-value flags split on `||`; `--move-to` takes a well-known folder id like `archive`; `--except-from` is the personal-domain fence; sequence is auto-assigned to the end)
    - Append phrases to a bucket: `node mail.js --append-rule="<id or name>" --subject-contains="D||E" [--body-contains=]`
    - Delete: `node mail.js --delete-rule="<id or name>"`

## Auth-error handling (do without being asked)

Access tokens auto-refresh via MSAL. If a call fails with "Not signed in" or an auth error, re-run the one-time `auth.js` sign-in via browser-chauffeur, then retry. Never surface a token error to the user — fix it and continue.

## Notes

- `$search` and `$orderby` can't be combined on `/me/messages` — search returns relevance order; don't add `orderby`.
- Draft replies (`--reply`) land in **Drafts** and are never sent — the user reviews and sends.
- `--send-self` is the reliable "transfer text to my phone" path (arrives in Outlook mobile) when a self-chat isn't available.
