# drainer channel provider — the interface every source implements

The drainer's core algorithms (the **sweep**, the **harvester**, the **digest**, and `drain.py`) are
channel-agnostic: they operate on generic *items* and delegate every channel-specific step to that
item's **channel provider**. A provider is one doc — `channel-watch/<channel>-channel.md` — that
implements the operations below, plus one `<channel>-worker-prompt.txt`. The active providers are
listed in **`drainer/channels.json`** (the registry). Classification is shared and lives in
`drainer/triage.md` — providers never restate it.

This file is the **contract** (a checklist; markdown can't enforce it). Each `<channel>-channel.md`
MUST define a section for each operation, named exactly so the core prompts can say "do the item's
provider's CAPTURE step," etc.

## Operations every provider implements

- **AUTH-GLANCE** — how to confirm Russell is signed in to this channel (one screenshot), and the
  exact sign-in spawn command to run if not.
- **ENUMERATE** — the surface to read, how to list NEW/unread items (newest-first), and how to build
  the stable `<id>` (using the channel's `idPrefix` from the registry).
- **CAPTURE** — for a needs-you item, write `<id>.json` (fields: `id`, `channel`, `triage`, `kind`,
  `from`, `received`, `snippet`, `whatsAsked`, deep-link `url`, and the body-file pointer) plus the
  body file (`<id>.<bodyExt>`); and how to obtain the **deep link** used as `url`.
- **CLEAR** — clear/advance ONE item so it doesn't resurface (the channel's "gone"). Used by BOTH the
  worker's ADVANCE step and the digest's dispose step. Must be reversible and narrated.
- **JUNK-LEARNING** — what to propose for a junk item, **if anything** (a channel's analog of a
  filter rule). A channel may propose nothing — then junk is simply cleared, no suggestion.
- **DRAFT-MODE** — the `message-draft` skill mode used when composing a reply on this channel.
- **WORKER-PROMPT** — the `<channel>-worker-prompt.txt` rendered for a spawned worker tab (it reads
  `<id>.json` + the body file off disk and follows `worker-core.md`).

## The buckets (shared)
Every channel classifies items per `triage.md` (the single rubric). Providers don't redefine the
buckets — they only implement how to ENUMERATE/CAPTURE/CLEAR for their surface.

## How to add a channel (e.g. Slack, personal mail)
1. Write `channel-watch/<channel>-channel.md` defining every operation above.
2. Write `channel-watch/<channel>-worker-prompt.txt` (mirror an existing one;
   `{{REPO}}` + `<id>` placeholders).
3. Add ONE entry to `drainer/channels.json`:
   `"<channel>": {"provider":"channel-watch/<channel>-channel.md","worker":"channel-watch/<channel>-worker-prompt.txt","idPrefix":"<channel>-","bodyExt":"<ext>"}`
The sweep, harvester, digest, and `drain.py` then pick it up automatically — no edits to their logic.
(All channels spawn their worker tab via the one generic `spawn-item.cmd`.)
