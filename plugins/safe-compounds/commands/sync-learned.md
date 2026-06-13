---
description: Open a PR promoting any locally-learned safe commands into the plugin source
---

Promote this machine's safe-compounds "learned" commands into the plugin source
and open a pull request, so the learnings are shared instead of staying local.

Do it directly with your normal tools — there is no script:

1. Read the machine-local learned store: `~/.claude/safe-compounds-learned.json`.
   It is the source of truth (learnings accumulate across sessions). If the file
   doesn't exist or all its lists are empty, tell the user there's nothing to
   promote and stop.

2. For each entry, add it to the matching allowlist in the source and remove it
   from any "to do" mental list:
   - `commands` (top-level tools)  → the `SAFE_COMMANDS` set in
     `safe_compounds/trust.py`
   - `NPM_SAFE_SUBCOMMANDS`, `YARN_SAFE_SUBCOMMANDS`, `PIP_SAFE_SUBCOMMANDS`,
     `PNPM_SAFE_SUBCOMMANDS`, `BUN_SAFE_SUBCOMMANDS` → the same-named set in
     `safe_compounds/commands.py`
   - `GH_AI_APPROVED_PAIRS` → the `GH_AI_APPROVED_PAIRS_BASE` set in
     `safe_compounds/commands.py`
   Skip anything already present. Keep each set sorted and its formatting tidy.

3. Run the test suite (`python -m pytest plugins/safe-compounds`) to confirm the
   edits are valid.

4. Create a branch, commit the source edits, push, and open a PR with `gh`
   summarizing what was promoted.

5. Clear the promoted entries from `~/.claude/safe-compounds-learned.json` (set
   the synced lists to empty) so they aren't promoted again.

This never happens automatically — the per-command hook only writes to the local
store; promotion happens only when the user runs this command.
