# Extending the drainer — what each machine adds

The **engine and the shared providers** ship in this plugin and are generic and identity-free. A
machine adds only three things, all local: a settings file, a `context.md`, and (rarely) a custom
provider. Credentials always live in your OS store / env, never in any repo.

## 1. Settings — `.claude/drainer.local.md`
The single per-machine config (the plugin-settings pattern). Copy
`templates/drainer.local.example.md` to `.claude/drainer.local.md` and fill in: which `channels` are
active (referencing shared providers by name), per-provider config (e.g. Trello `boards`, label
vocab), `local_dir`, cadence, and presence. **You decide whether to version it** — keep it in a repo,
in this project, or uncommitted.

## 2. context.md (the local brain)
Copy `templates/context.example.md` to `<local_dir>/context.md` and fill in **your** world: who you
are, the systems you act in, your internal knowledge source (if any), your tracker board, and the
standing behavioral rules. The worker loads it at the start of every item.

## 3. Providers
Most machines need **none** — the shared providers in `providers/` cover Outlook (web), Teams (web),
and Trello outreach; you just enable them in `drainer.local.md`. They're generic (you sign in as
yourself; Trello takes a board id). Only a source not already shipped needs a new provider, written
into `<local_dir>/providers/` against `engine/channel-provider.md` — see `docs/writing-a-provider.md`.
Prefer API/MCP; use a browser only where no API exists.

## Credentials
OS credential store (Windows Credential Manager / Keychain) or environment variables (e.g.
`TRELLO_KEY`/`TRELLO_TOKEN`). **Never** in the plugin or the settings file. Providers fetch them at
runtime.

## Sibling skills it uses
`message-draft` + `document-authoring` (drafting & voice), `trello-outreach` (Trello reads/mutations &
tracker cards), and `browser-chauffeur` (the Outlook/Teams browser providers). All in this marketplace.

## A new machine, start to finish
1. `claude plugin install drainer@rrrutledge-claude-code-plugins`.
2. `cp templates/drainer.local.example.md .claude/drainer.local.md`; enable the providers you want and
   fill in their config (set `local_dir`).
3. Create `<local_dir>/context.md` from `templates/context.example.md`.
4. Wire credentials into your OS store; ensure the sibling skills are installed.
5. (Only if you have an unshipped source) add a custom provider — `docs/writing-a-provider.md`.
6. Add scheduling glue (presence-gate, overlap lock, cadence) for your OS.
7. Run a source by hand until trustworthy, then schedule it (continuous, or once a day for outreach).
