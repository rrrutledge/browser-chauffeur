# drainer provider — the interface every provider implements

The engine (driver loop, harvester, digest) is source-agnostic: it operates on generic *items* and
delegates every source-specific step to that item's **provider**. A provider is one doc —
`providers/<source>-provider.md` — that implements the operations below. The providers a machine runs
are listed in `.claude/drainer.local.md` → `providers`. Classification is shared and lives in
`engine/triage.md` — providers never restate it.

This file is the **contract** (a checklist; markdown can't enforce it). Each `<source>-provider.md`
MUST define a section for each operation, named exactly so the engine can say "do the item's provider's
CAPTURE step," etc.

## Operations every provider implements

- **AUTH-GLANCE** — how to confirm the user is signed in / credentials are valid, and what to do if not.
- **ENUMERATE** — the surface to read, how to list items to consider (newest-first; due now-or-earlier
  for due-date sources), and how to build the stable `<id>` (using the provider's `idPrefix`).
- **CAPTURE** — for a needs-you item, write `<id>.json` (fields: `id`, `source`, `triage`, `kind`,
  `from`, `received`, `snippet`, `whatsAsked`, deep-link `url`, and the body-file pointer) plus the
  body file (`<id>.<bodyExt>`); and how to obtain the **deep link** used as `url`.
- **CLEAR** — clear/advance ONE item so it doesn't resurface (the source's "gone"). Used by BOTH the
  worker's ADVANCE step and the digest's dispose step. Must be reversible and narrated.
- **JUNK-LEARNING** — what to propose for a junk item, **if anything** (a filter/rule that stops it
  arriving). A provider may propose nothing — then junk is simply cleared.
- **DRAFT-MODE** — the `message-draft` skill mode used when composing a reply for this source.

All providers share the one generic `providers/worker-prompt.txt`; there's no per-provider worker
prompt to write.

## The buckets (shared)
Every provider classifies items per `triage.md` (the single rubric). Providers don't redefine the
buckets — they only implement how to ENUMERATE/CAPTURE/CLEAR for their surface.

## How to add a source
1. Write `providers/<source>-provider.md` defining every operation above.
2. A machine enables it in `.claude/drainer.local.md` → `providers` (the entry key is the source name;
   its value holds any config the provider needs).
The engine then picks it up automatically — no changes to the loop.
