---
description: Open a PR promoting any locally-learned safe commands into the plugin source
---

Promote the machine-local safe-compounds "learned" commands into the plugin
source and open a pull request, so the learnings are shared instead of staying
on this one machine.

Steps:

1. Show the user what's currently in the local learned store so they know what
   will be promoted:
   `cat ~/.claude/safe-compounds-learned.json` (it may not exist — that just
   means nothing has been learned yet; report that and stop).

2. Run the sync script from the repo checkout:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/sync_learned.py"`

   It folds each learned entry into the matching allowlist in the source
   (`SAFE_COMMANDS` in `trust.py`, the `*_SAFE_SUBCOMMANDS` sets in
   `commands.py`), commits on a new branch, pushes, opens a PR via `gh`, and
   clears the synced entries from the local store.

3. Report the resulting PR URL (printed by the script). If the script says
   "Nothing learned to sync," tell the user there was nothing to promote.

Notes:
- Requires `gh` authenticated and the repo checkout available. The script must
  run against the dev checkout, not the installed plugin cache.
- This never runs automatically — the per-command hook only writes to the local
  store; promotion happens only when you invoke this command.
