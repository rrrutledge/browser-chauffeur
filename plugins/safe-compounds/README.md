# safe-compounds

A `PreToolUse` hook that lets long Claude Code sessions run without a stream of
permission prompts — **without** `--dangerously-skip-permissions`. It approves
only things that are genuinely safe, and blocks (with a corrective message) the
patterns your `CLAUDE.md` says to avoid.

This plugin is the repo-managed, tested successor to the hand-maintained
`~/.claude/allow-safe-compounds.py` script.

## What it does

For each tool call, the hook decides **ALLOW** (auto-approve), **BLOCK** (deny
with a message telling Claude how to redo it), or **PROMPT** (stay silent and
let the normal permission flow ask you).

- **Bash** — splits a compound command (`a && b | c`) into segments and approves
  it only if *every* segment is a trusted command or a recognized-safe form
  (read-only `git`/`gh`/`curl`, package-manager installs, CWD-scoped
  `cp`/`mv`, `start` on viewable file types, `wt` launching a trusted program,
  …). Destructive forms (`git push --force`, `rm`-ish patterns outside CWD,
  POST to public URLs) fall through to a prompt.
- **Enforcement** — blocks heredocs, output/input redirection, inline
  `python -c` / `node -e`, PowerShell cmdlets in bash, `cmd /c`, `sed -i`,
  `$VAR` expansion / `VAR=...` assignment, and complex bash (loops, `$()`,
  conditionals, brace groups) — each with a message pointing at the
  `CLAUDE.md`-preferred alternative.
- **Write/Edit** — approves `.tmp/` files, `.claude/{skills,commands,screenshots}`,
  and files inside a git repo's working tree; redirects stray temp-named files
  into `.tmp/`.
- **MCP** — approves read-only and reversible-write operations; prompts on
  destructive verbs (`delete`, `purge`, …).

## Architecture

```
hook.py                  entrypoint / orchestrator (decision order)
safe_compounds/
  shell.py               tokenizing, segment splitting, command-name extraction
  paths.py               cross-platform "is this path inside an allowed area?"
  trust.py               the trusted command set (base + settings + learned)
  ai.py                  single Claude Haiku request impl (fallback classifier)
  learned.py             machine-local store of AI-approved commands
  scripts.py             node/python script safety analysis
  commands.py            git/gh/curl/sed/start/wt/cmd + package managers + file ops
  enforce.py             the BLOCK rules (CLAUDE.md style enforcement)
  approve.py             per-segment trust decision
  mcp.py                 MCP tool classification
  writes.py              Write/Edit handling
```

One orchestrator (not two separate hook processes) preserves the original
block-then-approve ordering, which the Write/Edit path depends on (a temp-named
file *inside* `.tmp/` must be allowed, not redirected).

## Configuration (environment variables)

- `SAFE_COMPOUNDS_DISABLE_AI=1` — disable all Haiku fallbacks (kill-switch; used
  by the test suite).
- `SAFE_COMPOUNDS_TRUSTED_JSON=<path>` — use a JSON list as the trusted set
  verbatim instead of the live sources (used by tests to pin behavior).
- `SAFE_COMPOUNDS_LEARNED_JSON=<path>` — override the learned-store location
  (default `~/.claude/safe-compounds-learned.json`).

The AI fallback uses the same credentials as before
(`ANTHROPIC_HOOK_API_KEY` / `ANTHROPIC_API_KEY`, or Vertex via
`ANTHROPIC_VERTEX_PROJECT_ID`). With no credentials, AI calls return "undecided"
and the command simply falls through to a prompt.

## Learned commands

When Haiku approves a previously-unknown command or subcommand, it is recorded
in `~/.claude/safe-compounds-learned.json` (machine-local, never synced). This
replaces the old design where the hook rewrote its own source file — which
produced OneDrive sync-conflict copies and could not survive a plugin update.

## Tests

```
python -m pip install pytest
python -m pytest plugins/safe-compounds
```

The characterization suite runs the hook as a subprocess over a corpus of
representative inputs and asserts each decision matches `tests/fixtures/golden.json`
— the decisions produced by the original hook (frozen in `tests/oracle/`). Unit
tests cover the parsing/classification helpers. Everything is hermetic (AI
disabled, trusted set pinned, temp working dirs), so CI is deterministic.

## Requirements

- Python 3 on `PATH` (the harness runs `python "${CLAUDE_PLUGIN_ROOT}/hook.py"`).
