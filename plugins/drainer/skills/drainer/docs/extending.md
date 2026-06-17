# Extending the drainer — what each machine adds

The **engine and the providers** ship in this plugin and are generic and identity-free. A machine adds
only two local things: a settings file and a `context.md`. Credentials always live in your OS store /
env, never in any repo.

## 1. Settings — `.claude/drainer.local.md`
The single per-machine config (the plugin-settings pattern). Copy
`templates/drainer.local.example.md` to `.claude/drainer.local.md` and fill in: which `providers` are
active (by name), per-provider config (e.g. Trello `boards`, label vocab), `local_dir`, the harvest
interval, and presence. **You decide whether to version it** — keep it in a repo, in this project, or
uncommitted.

## 2. context.md (the local brain)
Copy `templates/context.example.md` to `<local_dir>/context.md` and fill in **your** world: who you
are, the systems you act in, your internal knowledge source (if any), your tracker board, and the
standing behavioral rules. The worker loads it at the start of every item.

## Providers
The providers in `providers/` cover Outlook (web), Teams (web), and Trello outreach; enable the ones
you want in `drainer.local.md` and give any config they need (Trello board id; a Slack workspace
subdomain). They're generic: you sign in as yourself. To add a source that isn't there yet, write a
new provider — see `docs/writing-a-provider.md`.

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
5. Add scheduling glue (presence-gate, overlap lock, one interval) for your OS.
6. Run a source by hand until trustworthy, then schedule a single harvest of all sources.
