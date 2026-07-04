# outlook-graph provider — personal Outlook.com mail (Microsoft Graph API)

A provider for a **personal** Outlook.com mailbox (`outlook.live.com`) read and cleared entirely
through the **Microsoft Graph API** — no browser. All Graph calls go through the **`ms-graph`** skill's
`mail.js` (don't reimplement Graph here); it owns auth, the token cache, and silent refresh. Implements
`../engine/provider.md`; classify by `../engine/triage.md`.
id prefix: `outlook-graph-`; body file: `<id>.email.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the
> sibling **`outlook-graph-adapter.py`** that the poller drives. This doc is the **worker-facing**
> prose — AUTH-GLANCE, the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> This is the API counterpart to the browser `outlook-provider.md` (which is for **enterprise** Outlook
> on the web). Use this one for a personal Microsoft account: it's cheaper, faster, and browser-free.

**Shared email rules:** See `email-provider.md` for CAPTURE shape, SITUATIONAL-CHECK decision logic,
DRAFT-MODE voice rules, and JUNK-LEARNING priority order. This file covers only the Graph-specific
mechanisms.

## Config (in `.claude/drainer.local.md` → `providers.outlook-graph`)
No config — you sign in once via `ms-graph`. Credentials: `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` in
the environment (used by `ms-graph`); the MSAL token cache is machine-local at
`~/.claude/ms-graph/token-cache.json`.

The `ms-graph` `mail.js` lives at `<ms-graph-skill>/scripts/mail.js` — run it with `node`.

## AUTH-GLANCE
Run `node mail.js --list-unread --top=1`. If it prints messages (or "No unread messages."), you're
signed in. If it errors with "Not signed in" or an auth error, do the `ms-graph` one-time sign-in
(`node scripts/auth.js` via browser-chauffeur), then retry — never surface the token error to the user.

## SITUATIONAL-CHECK mechanism
The inbox is drained and emptied by the poller, so recent replies live in **Deleted Items** (where CLEAR
moves handled messages), not the inbox or Archive. Search all three folders — inbox, Archive, Deleted
Items — covering both directions and **paginating each fully**. Use `node mail.js --search="<subject>"`
— verify it covers Deleted Items and do not stop at the first page.

## CAPTURE
See `email-provider.md` for the shared two-file shape. Graph-specific: `messageId` is the opaque Graph
message id.

## CLEAR
`node mail.js --delete=<messageId>` — moves the message to **Deleted Items** (reversible; narrate it).
Never a permanent purge.

## JUNK-LEARNING (step 3 — Outlook.com-specific)
After exhausting unsubscribe and source-app options (see `email-provider.md`): propose an **Outlook.com
inbox rule**, using the **`mail-filters`** skill to choose the phrase and shape (append the type phrase
to the right consolidated bucket, keep the sender-domain exclusion whitelist that fences every broad
bucket, and pin any body match to its sender). Create it via `ms-graph`'s
`mail.js --append-rule`/`--create-rule` (the `MailboxSettings.ReadWrite` scope is wired in) once Russell
OKs the phrase.

## DRAFT-MODE CLI commands
Follow all voice and reply-vs-fresh rules in `email-provider.md`, then use these Graph commands:

- **Reply-all on the thread:** `node mail.js --reply --message-id=<messageId> --body-file=<file>`
  — Graph's reply-all keeps the thread quote below your text automatically and preserves all To+CC
  recipients. Thread off the most recent message (see `email-provider.md`).
- **Fresh note:** `node mail.js --draft-new --to="<addr>" --subject="<subj>" --body-file=<file>
  [--cc="<addrs>"]`
