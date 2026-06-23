# outlook-rest provider — Outlook mail via the Outlook REST API

A provider for an Outlook mailbox read and cleared through the **Outlook REST API** — no browser for
reads. All mail mechanics go through the **`ms-rest`** skill's `outlook-mail.js` (don't reimplement the
API here); it owns the bearer token sniffed from the live Outlook web session, the paged `enumerate`,
`get`, `delete`, and the `create-reply` / `create-draft` compose calls. Implements
`../engine/provider.md`; classify by `../engine/triage.md`.
id prefix: `outlook-rest-`; body file: `<id>.email.md`.

> Two-file provider: the **reading** mechanics (enumerate, stable id, capture-writing) live in the
> sibling **`outlook-rest-adapter.py`** that the poller drives. This doc is the **worker-facing** prose —
> AUTH-GLANCE, the captured item shape, CLEAR, JUNK-LEARNING, DRAFT-MODE.

> This is the **REST-transport** counterpart to the Graph-transport `outlook-graph-provider.md`:
> same operations, the Outlook REST v2.0 transport with a session-sniffed token instead of
> ms-graph/MSAL. It reads whatever account is signed into Outlook web (so it suits a work mailbox that
> has no personal Graph app).

## Config (in `.claude/drainer.local.md` → `providers.outlook-rest`)
No config — `outlook-rest: {}`. Auth is a bearer token the `ms-rest` skill sniffs from the live Outlook
web session (signed in as yourself; no tenant baked in) and caches at `~/.claude/drainer/.tmp/outlook-token.json`.
The one-time sniff needs `playwright` (resolved from the home repo's `node_modules`); once cached,
reads run with no browser at all.

The `ms-rest` `outlook-mail.js` lives at `<ms-rest-skill>/outlook-mail.js` — run it with `node`.

## AUTH-GLANCE
Run `node <ms-rest>/outlook-mail.js token`. `Token OK ✅` means a valid token is available (cached or
freshly sniffed) and the channel is ready. If it reports "No Mail.ReadWrite token sniffed", Outlook web
needs a signed-in tab to sniff from: open `https://outlook.office.com/mail/` (or
`https://outlook.cloud.microsoft/mail/`) in the browser-chauffeur browser, confirm signed in, and
stop reading mail until the token sniffs clean. Never surface a raw auth error to the user.

## CAPTURE (needs-you)
The adapter writes these; documented here so the worker can rely on the shape:
- `items/<id>.email.md` — header block (From, Received, Link=`webLink`, MessageId) + the full body.
- `items/<id>.json`:
  `{ "id","source":"outlook-rest","triage":"needs-you","kind":"reply|work|work-then-reply","from",`
  `"subject","received","snippet","url":"<webLink>","messageId":"<Outlook REST id>",`
  `"emailFile":"<abs path to .email.md>","ts":"<ISO now>" }`

  `messageId` is the Outlook REST id — CLEAR and `get` need it. (`id` is the stable slug; `messageId`
  is the API handle. Both are persisted.)

## SITUATIONAL-CHECK
Before drafting anything, read the full thread to see if the conversation has already moved. The
inbox is drained and emptied by the poller, so recent replies live in **Deleted Items** (where CLEAR
moves handled messages), not the inbox or Archive. Search all three folders — inbox, Archive, Deleted
Items — and **paginate each one** (follow `@odata.nextLink`); a reply swept since the last drain cycle
will only exist in Deleted Items. Use the `ms-rest` skill's `outlook-core.js` `apiCall` helper to
query `/me/mailfolders/<folder>/messages` filtered by `receivedDateTime ge <cutoff>`, ordered newest-
first, and match against the contact's name/address and the thread subject. If the most recent message
in the thread is already a reply from the user, the item is done — close it without a new draft.

## CLEAR
Run `node <ms-rest>/outlook-mail.js delete <messageId>` (the Outlook REST id from `<id>.json`). Moves
the message to Deleted Items (reversible). Narrate each deletion with a one-line reason. Used by the
worker's ADVANCE step and the digest's dispose step.

## JUNK-LEARNING
Propose an **Outlook rule** (a sender/subject/body match that files or deletes the class going forward)
so this junk stops arriving. Prefer extending an existing rule bucket over a new standalone rule.
Propose, never apply without the user's OK. (The live rule list is the Outlook Rules UI, not this file.)

## DRAFT-MODE
`message-draft` skill, `outlook` mode — which composes via `ms-rest`'s `create-reply` / `create-draft`
(same REST token as read/delete). The draft lands un-sent in **Drafts** with clickable links and the
quoted original below the new text; the user reviews and sends. Apply the `document-authoring` voice to
the body before creating the draft. Never auto-send (`send-draft` is gated behind an explicit OK).
