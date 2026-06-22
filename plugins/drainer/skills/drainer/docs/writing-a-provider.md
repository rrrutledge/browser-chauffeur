# Writing a provider

A **provider** teaches the engine how to read and clear ONE source. The engine's loop is
provider-agnostic; it calls your provider's operations and never knows whether you used an API, an MCP,
or a browser. The contract is `engine/provider.md`; the providers in `../providers/` are complete
worked examples to copy from.

## Where it lives — two files that sit together
A provider is **two files** in `providers/`, because two consumers drive it:

- **`providers/<source>-adapter.py`** — **code** the deterministic poller loads and drives (how to
  *read* the source).
- **`providers/<source>-provider.md`** — **prose** the AI worker reads to act on one item (how to
  *act* and *clear*).

A machine enables the provider by name (with any config it needs) in `.claude/drainer.local.md` →
`providers`. All providers share the one generic worker flow (`engine/worker-core.md`).

## The adapter (code) — `<source>-adapter.py`
Define `class Provider(ProviderBase)` (from `scripts/provider_base.py`) exposing three methods the
poller calls. The poller loads it by name; no source mechanics live in the poller.

```python
import os, sys
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, run_node, slug

class Provider(ProviderBase):
    name = "<source>"                       # matches the drainer.local.md providers key

    def enumerate(self, limit):             # newest-first candidate item dicts, up to `limit`
        ...                                 # surface auth failures here; poller skips on error
        return items

    def stable_id(self, item):              # deterministic, stable across cycles (seen-state dedups on it)
        return f"{self.name}-..."

    def capture(self, item, iid, runtime_dir):  # write items/<iid>.json (+ body file); return the json path
        ...
        return json_file
```

## The prose (`<source>-provider.md`) — what the worker reads
Implement each as a named section so the worker can "do the item's provider's CLEAR step":

1. **AUTH-GLANCE** — confirm access cheaply; say what to do if not signed in.
2. **CAPTURE** — the `<id>.json` shape the worker can rely on (the adapter writes it; this documents it).
3. **CLEAR** — make ONE item "gone" (reversible, narrated).
4. **JUNK-LEARNING** — what to propose for junk, if anything, in priority order (unsubscribe →
   source-app notification settings → inbox rule).
5. **DRAFT-MODE** — the `message-draft` mode for replies for this source.

Classification is NOT a provider concern — every item is judged by `engine/triage.md`.

## Worked examples — the shipped providers
Each is a complete implementation to copy from:
- **`outlook-rest-provider.md`** + **`outlook-rest-adapter.py`** — a **REST two-file example** for an
  Outlook mailbox via the `ms-rest` skill's `outlook-mail.js` (token sniffed from the live Outlook web
  session; reads whatever account is signed in). Adapter: `enumerate` / `get` reads; prose: `delete`
  clear, Outlook-rule junk-learning, `message-draft` `outlook` mode. Copy this when the sibling skill
  needs a one-time browser sniff but reads run REST.
- **`personal-outlook-provider.md`** + **`personal-outlook-adapter.py`** — the **API two-file example**
  (personal Outlook.com via the Microsoft Graph API through the `ms-graph` skill). Adapter:
  `mail.js --list-inbox --json` enumerate, the Graph id scheme, `--show` capture. Prose: `--delete` clear,
  `--reply` draft, unsubscribe/rule junk-learning. Copy this when wrapping any pure-API/MCP source.
- **`teams-provider.md`** + **`teams-adapter.py`** — a **REST-read / browser-clear two-file example** via
  the `teams` skill's `teams-chat.js`: REST `enumerate`/`messages` reads, but mark-read CLEAR and reply
  DRAFT stay browser-driven (Teams' `isRead` flips only on a real open; no draft API). Includes the Teams
  footguns and the meeting-recording container case.
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
- [ ] `providers/<source>-adapter.py` defines `Provider(ProviderBase)` with `name`/`enumerate`/
      `stable_id`/`capture`.
- [ ] `providers/<source>-provider.md` defines the prose ops (AUTH-GLANCE, CAPTURE shape, CLEAR,
      JUNK-LEARNING, DRAFT-MODE) by name.
- [ ] `.claude/drainer.local.md` has the `providers.<source>` entry.
- [ ] CLEAR is reversible and narrated.
- [ ] No classification logic in the provider (uses `engine/triage.md`).
