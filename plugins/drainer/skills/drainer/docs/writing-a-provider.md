# Writing a provider — step by step

A **provider** teaches the engine how to read and clear ONE source. The engine's loop is
provider-agnostic; it calls your provider's operations and never knows whether you used an API, an
MCP, or a browser. This is the doc you follow to add a source. The contract is
`engine/channel-provider.md`; the shipped providers in `../providers/` are complete worked examples to
copy from.

## Where it lives
Providers live in your **local folder** (`<local_dir>/providers/`, where `local_dir` is set in
`.claude/drainer.local.md`), never in the plugin. Each provider is two files plus one registry entry:
- `providers/<channel>-channel.md` — the operations (this doc).
- `providers/<channel>-worker-prompt.txt` — the thin worker prompt for a spawned item.
- one entry in `.claude/drainer.local.md` → `channels`.

## The 7 operations
Implement each as a named section in `<channel>-channel.md` so the engine prompts can say "do the
item's provider's CAPTURE step":

1. **AUTH-GLANCE** — confirm access cheaply; say what to do if not signed in.
2. **ENUMERATE** — list NEW/unread items newest-first; build the stable `<id>` from the channel's
   `idPrefix`.
3. **CAPTURE** — for a needs-you item, write `<id>.json` (`id`, `channel`, `triage`, `kind`, `from`,
   `received`, `snippet`, `whatsAsked`, deep-link `url`, body-file pointer) + the body file.
4. **CLEAR** — make ONE item "gone" (reversible, narrated).
5. **JUNK-LEARNING** — what to propose for junk, if anything.
6. **DRAFT-MODE** — the `message-draft` mode for replies on this channel.
7. **WORKER-PROMPT** — point at `<channel>-worker-prompt.txt`.

Classification is NOT a provider concern — every channel uses `engine/triage.md`.

## Worked examples — the shipped providers
The best examples are the real providers in `../providers/`, each a complete implementation of the
seven ops:
- **`outlook-channel.md`** — a browser provider (Outlook web via browser-chauffeur): list-view
  enumerate, open-on-needs-you capture, delete-to-clear, Outlook-rule junk-learning.
- **`teams-channel.md`** — a browser provider with the Teams footguns, deep-link capture, mark-read
  clear, and the meeting-recording container case.
- **`trello-channel.md`** — a once-a-day, config-driven provider that delegates all reads/mutations to
  the `trello-outreach` skill.

Copy whichever is closest, change the mechanics for your source, and enable it in
`.claude/drainer.local.md` → `channels`:

```yaml
mychannel:
  provider: mychannel        # a shipped provider name, or providers/mychannel-channel.md in local_dir
  cadence: continuous        # or daily for a due-date source
```

## Tips by source type
- **Browser providers** drive everything via **browser-chauffeur** and draft via `message-draft`;
  the engine loop is identical, only the provider body differs (see outlook/teams).
- **API/MCP providers** are preferred where an API exists — same seven ops, just cheaper/faster reads.
- **Delegating providers** (like Trello) can hand reads/mutations to a sibling skill instead of
  re-implementing an API.

## Checklist
- [ ] `providers/<channel>-channel.md` defines all 7 ops by name.
- [ ] `providers/<channel>-worker-prompt.txt` exists and points at `worker-core.md`.
- [ ] `.claude/drainer.local.md` has the `channels.<channel>` entry.
- [ ] CLEAR is reversible and narrated.
- [ ] No classification logic in the provider (uses `engine/triage.md`).
