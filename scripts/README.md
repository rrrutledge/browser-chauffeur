# Repo-level scripts

Utilities shared across this repo's plugins and the session tooling, referenced by stable clone
path (e.g. `~/Dev/rrrutledge/rrrutledge-claude-code-plugins/scripts/<name>`). They live here — not
inside any one plugin — so several callers can reuse them without depending on a plugin version.

| Script | What it does |
| ------ | ------------ |
| `launch-session.ps1` | Launch a fresh Claude session in a Windows Terminal tab (handoff or drainer-worker mode). |
| `wait-done.py` | Block until a completion marker file appears. |
| `peek.py` | Render a spawned session's transcript as a compact timeline. |
| `check_version_bump.py` | CI helper: verify a plugin's version was bumped when its files changed. |

## The launch → wait → peek toolkit

`launch-session.ps1`, `wait-done.py`, and `peek.py` compose into one pattern: **spawn a Claude session
in its own tab, wait for it to finish, and watch its progress while you wait.** An orchestrator (the
handoff launcher, a drainer worker delegating to another repo, or any agent) uses all three together.

### 1. Launch — `launch-session.ps1`

Opens a new Windows Terminal tab running a fresh `claude` session. Two modes:

- **Prompt-file mode** (`-PromptFile <path>`): the full instructions live on disk; the session is
  seeded with a one-line pointer to them. Writes a sidecar file next to the prompt file:
  - `<prompt>.session` — the session id (so `peek.py` can find the transcript).
- **Seed mode** (`-SeedFile <path>`): the seed text itself lives in the file and is passed verbatim
  (used by the handoff launcher). Add `-Model "<id>"` to pin a model; omit to inherit the session default.

Both modes invoke `powershell` without `-NoProfile`, so the tab loads the user's `$PROFILE` — that's
where `$env:CLAUDE_HOST_PID` (the PID hosting the tab, for a self-resolving session to close its own
tab) and `$env:BROWSER_CHAUFFEUR_OWNER_PID` come from, not from this script.

All prose is passed via a FILE, never on the command line — an embedded quote or `;` would break `wt`
tokenization. Only paths, titles, model ids, and guids cross the command line.

### 2. Wait — `wait-done.py`

```
python wait-done.py <path>.done
```

Blocks (polling every 20s) until either `<path>.done` or `<path>.skip` exists, then exits 0. Run it in
the **foreground** in short cycles so the orchestrator's tab stays in the "working" state; between
cycles, `peek` the spawned session to show live progress.

### 3. Peek — `peek.py`

```
python peek.py <prompt>.session --tail 8
```

Resolves the session id (from a `.session` file, a raw id, or a `.jsonl` path) to the session's
`~/.claude/projects/**.jsonl` transcript and prints a compact timeline — assistant text, tool calls,
and short tool results, skipping base64 image blobs — so you can see what the spawned tab is doing.

## The `.done` / `.skip` marker protocol

Spawned sessions and their orchestrator coordinate through two zero-content marker files, not a live
channel:

- **`.done`** — the spawned session writes this (with a one-line summary as its content) when it has
  finished its work. `wait-done.py` returns as soon as it appears. Re-writing it later is harmless.
- **`.skip`** — the orchestrator (or a human) writes this to unblock a `wait-done.py` that is stuck on
  a session that will never finish. Same base path as the `.done`, with a `.skip` extension.

The marker base path is chosen by the orchestrator and handed to the spawned session in its prompt
(e.g. a drainer worker points the session at `<item>.work.done` / `<item>.work-result.md`). This keeps
the handoff to a single file the orchestrator polls — no extra monitoring machinery.

## Primary consumers

These are generic, but the **drainer** is the main user: a drainer worker handling a SkyStage/IDP item
launches a full session in the internal-developer-portal repo, waits on its `.done`, and peeks its
progress meanwhile (see `drainer-local/skystage-idp-session.md` in the russ-ai-pod repo). The
**handoff launcher** (documented in `~/.claude/CLAUDE.md`) uses `launch-session.ps1` in seed mode.
