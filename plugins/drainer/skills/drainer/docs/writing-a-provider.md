# Writing a provider — step by step

A **provider** teaches the engine how to read and clear ONE source. The engine's loop is
provider-agnostic; it calls your provider's operations and never knows whether you used an API, an
MCP, or a browser. This is the doc you follow to add a source. The contract is
`engine/channel-provider.md`; the skeleton is `templates/provider.example.md`; this walks the whole
flow with a worked example.

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

## Worked example — Outlook via Microsoft Graph (API, no browser)

`providers/outlook-channel.md`:

```markdown
# outlook provider (Microsoft Graph)

## AUTH-GLANCE
Token from the ms-graph skill's cache. Validate with `GET /me`. If 401, run the ms-graph sign-in.

## ENUMERATE
GET /me/mailFolders/inbox/messages?$filter=isRead eq false&$orderby=receivedDateTime desc&$top=50
id = idPrefix + message.id (last 12 chars).

## CAPTURE
For a needs-you item write <id>.json with from=sender, received=receivedDateTime,
snippet=bodyPreview, url=webLink, whatsAsked=<one line>. Body file <id>.email.md = message.body
(html→markdown).

## CLEAR
POST /me/messages/{id}/move {destinationId:"deleteditems"}  — reversible (Deleted Items). Narrate it.

## JUNK-LEARNING
Propose an Outlook rule (from-address or subject pattern) for recurring junk.

## DRAFT-MODE
message-draft mode: outlook

## WORKER-PROMPT
providers/outlook-worker-prompt.txt
```

`providers/outlook-worker-prompt.txt`:

```
Follow engine/worker-core.md. SOURCE=outlook. Your data is items/<id>.json + items/<id>.email.md
(read both off disk). Your ADVANCE = the outlook provider's CLEAR step (move to Deleted Items).
Write items/<id>.done as your final step.
```

`.claude/drainer.local.md` → `channels`:

```yaml
outlook:
  provider: providers/outlook-channel.md
  worker: providers/outlook-worker-prompt.txt
  idPrefix: outlook-
  bodyExt: email.md
  cadence: continuous
```

That's it — the continuous full-drain and once-a-day loops both pick the channel up automatically.

## Browser provider (work machine)
Same seven operations, but ENUMERATE/CAPTURE/CLEAR drive the browser via **browser-chauffeur** and
DRAFT-MODE still routes through `message-draft`. Declare browser-chauffeur in that machine's
`DEPENDENCIES`. The engine loop is identical — only the provider body differs.

## Checklist
- [ ] `providers/<channel>-channel.md` defines all 7 ops by name.
- [ ] `providers/<channel>-worker-prompt.txt` exists and points at `worker-core.md`.
- [ ] `.claude/drainer.local.md` has the `channels.<channel>` entry.
- [ ] CLEAR is reversible and narrated.
- [ ] No classification logic in the provider (uses `engine/triage.md`).
