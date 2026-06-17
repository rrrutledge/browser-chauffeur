# Extending the drainer — where each machine plugs in

The drainer **engine** ships in this plugin and is generic and identity-free. Every machine that runs
it injects its own world through four extension points, all kept **local to the machine** — never in
the plugin. The rule: *engine = generic logic + contracts + example templates; everything that
identifies you, your org, your contacts, or your systems lives in your local settings + folder.*

## The settings file (`.claude/drainer.local.md`)
Per-machine config lives in **`.claude/drainer.local.md`** in your project (the plugin-settings
pattern). Copy `templates/drainer.local.example.md` to `.claude/drainer.local.md` and fill in: the
`local_dir` (a folder you control, holding `context.md` + `providers/`), the source registry
(`channels`), outreach board config, cadence, and presence. **You decide whether `local_dir` is
versioned** — keep it in a repo, in this project, or uncommitted. The plugin only needs the settings
file; `local_dir` tells it where your content lives.

## The four extension points

### 1. Providers (the only substantive per-machine difference)
A **provider** implements the `engine/channel-provider.md` contract for one source — AUTH-GLANCE,
ENUMERATE, CAPTURE, CLEAR, JUNK-LEARNING, DRAFT-MODE, WORKER-PROMPT. The engine discovers providers
from `local_dir/providers/` (listed in `.claude/drainer.local.md` → `channels`) and never knows how a
source is actually read. Prefer API/MCP; use a browser only where no API exists. Full guide:
`docs/writing-a-provider.md`.

### 2. context.md (the local brain)
Copy `templates/context.example.md` to `<local_dir>/context.md` and fill in **your** world: who you
are, the systems you act in, your internal knowledge source (if any), your tracker board, and the
standing behavioral rules. The engine loads "the local context" at the start of every worker.

### 3. Settings (`.claude/drainer.local.md`)
The single per-machine config file: the source registry (active channels, provider path, id prefix,
body ext, cadence), board IDs, list/stage names, contact/label vocabularies, runtime path, cadence,
and presence. The bundled `scripts/` read identifiers from here — they hold no hardcoded IDs.

### 4. Credentials
Always local — OS credential store (Windows Credential Manager / Keychain) or environment variables.
**Never** in the plugin or the settings file. Providers fetch tokens at runtime.

## Dependencies
The worker procedure relies on a few sibling plugins (document-authoring, message-draft,
trello-outreach, and browser-chauffeur on browser machines). See `DEPENDENCIES.md`.

## What the engine guarantees
Given conforming providers + a `context.md` + `.claude/drainer.local.md` + credentials, the engine
gives you the driver loop, the triage rubric, the worker procedure, serialization, the digest model,
the voice loop, and the behavioral rules — identically on every machine. Improve any of those once,
in the plugin, and every machine benefits on its next update.

## A new machine, start to finish
1. `claude plugin install drainer@rrrutledge-claude-code-plugins`.
2. `cp templates/drainer.local.example.md .claude/drainer.local.md` and fill it in (set `local_dir`).
3. Create `<local_dir>/context.md` from `templates/context.example.md`.
4. Write providers into `<local_dir>/providers/` (see `docs/writing-a-provider.md`). Prefer API/MCP;
   browser only where no API exists.
5. Install the dependency plugins (`DEPENDENCIES.md`); wire credentials into your OS store.
6. Add scheduling glue (presence-gate, overlap lock, cadence) for your OS.
7. Run a source by hand until trustworthy, then schedule it (continuous full-drain or once-a-day).
