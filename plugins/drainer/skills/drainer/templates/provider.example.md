# <channel> provider — example skeleton

> Copy to your local `providers/<channel>-channel.md` and implement each operation for this source.
> Implements the contract in `engine/channel-provider.md`. Prefer API/MCP; use a browser only where no
> API exists. Classification is NOT here — every channel uses `engine/triage.md`.

## AUTH-GLANCE
How to confirm the user is signed in / the API token is valid (one cheap check), and what to do if not.
*(API source: a token-validity ping. Browser source: one screenshot + the sign-in spawn command.)*

## ENUMERATE
The surface to read and how to list NEW/unread items, newest-first. How to build the stable `<id>`
using this channel's `idPrefix` from `.claude/drainer.local.md`.
*(e.g. Graph: `GET /me/mailFolders/inbox/messages?$filter=isRead eq false&$orderby=receivedDateTime desc`)*

## CAPTURE
For a needs-you item, write `<id>.json` with: `id`, `channel`, `triage`, `kind`, `from`, `received`,
`snippet`, `whatsAsked`, deep-link `url`, and the body-file pointer; plus the body file
(`<id>.<bodyExt>`). How to obtain the **deep link** used as `url`.

## CLEAR
Clear/advance ONE item so it doesn't resurface (this channel's "gone"). Used by both the worker's
ADVANCE and the digest dispose. Must be reversible and narrated.
*(e.g. Graph: move the message to Deleted Items / Archive — reversible.)*

## JUNK-LEARNING
What to propose for a junk item, if anything (this channel's analog of a filter rule). May propose
nothing — then junk is simply cleared.

## DRAFT-MODE
The `message-draft` skill mode used when composing a reply on this channel (e.g. `outlook`, `gmail`,
`teams`, `slack`).

## WORKER-PROMPT
Point to `providers/<channel>-worker-prompt.txt` — a thin prompt that tells a worker to read
`<id>.json` + the body file off disk and follow `engine/worker-core.md`, with SOURCE and ADVANCE
filled in.
