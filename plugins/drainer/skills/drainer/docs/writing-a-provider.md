# Writing a provider

A **provider** teaches the engine how to read and clear ONE source. The engine's loop is
provider-agnostic; it calls your provider's operations and never knows whether you used an API, an MCP,
or a browser. The contract is `engine/provider.md`; the providers in `../providers/` are complete
worked examples to copy from.

## Where it lives
A provider is one file: `providers/<source>-provider.md`. A machine enables it by name (with any config
it needs) in `.claude/drainer.local.md` → `providers`. All providers share the one generic
`providers/worker-prompt.txt` — there's no per-provider worker prompt to write.

## The operations
Implement each as a named section in `<source>-provider.md` so the engine can say "do the item's
provider's CAPTURE step":

1. **AUTH-GLANCE** — confirm access cheaply; say what to do if not signed in.
2. **ENUMERATE** — list items to consider (newest-first; due-now-or-earlier for due-date sources);
   build the stable `<id>` from the provider's `idPrefix`.
3. **CAPTURE** — for a needs-you item, write `<id>.json` (`id`, `source`, `triage`, `kind`, `from`,
   `received`, `snippet`, `whatsAsked`, deep-link `url`, body-file pointer) + the body file.
4. **CLEAR** — make ONE item "gone" (reversible, narrated).
5. **JUNK-LEARNING** — what to propose for junk, if anything (a filter that stops it arriving).
6. **DRAFT-MODE** — the `message-draft` mode for replies for this source.

Classification is NOT a provider concern — every provider uses `engine/triage.md`.

## Worked examples — the shipped providers
Each is a complete implementation to copy from:
- **`outlook-provider.md`** — a browser provider (Outlook web via browser-chauffeur): list-view
  enumerate, open-on-needs-you capture, delete-to-clear, Outlook-rule junk-learning.
- **`personal-outlook-provider.md`** — an API provider (personal Outlook.com via the Microsoft Graph
  API through the `ms-graph` skill): `mail.js --list-unread` enumerate, `--show` capture, `--delete`
  (move to Deleted Items) clear, `--reply` draft. The API counterpart to `outlook-provider.md`, no
  browser — copy this when wrapping any API/MCP source through a sibling skill.
- **`teams-provider.md`** — a browser provider with the Teams footguns, deep-link capture, mark-read
  clear, and the meeting-recording container case.
- **`trello-provider.md`** — a config-driven provider that delegates all reads/mutations to the
  `trello-outreach` skill (due-date source: returns due-now-or-earlier cards, plus cards with no due
  date; usually little).

Copy whichever is closest, change the mechanics for your source, and a machine enables it in
`.claude/drainer.local.md` → `providers` (the entry key is the source name; its value holds any config
the provider needs).

## Tips by source type
- **Browser providers** drive everything via **browser-chauffeur** and draft via `message-draft`; the
  engine loop is identical, only the provider body differs (see outlook/teams).
- **API/MCP providers** are preferred where an API exists — same operations, cheaper/faster reads.
- **Delegating providers** (like Trello) hand reads/mutations to a sibling skill instead of
  re-implementing an API.

## Checklist
- [ ] `providers/<source>-provider.md` defines all six ops by name.
- [ ] `.claude/drainer.local.md` has the `providers.<source>` entry.
- [ ] CLEAR is reversible and narrated.
- [ ] No classification logic in the provider (uses `engine/triage.md`).
