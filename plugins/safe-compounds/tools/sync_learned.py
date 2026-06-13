"""Promote machine-local learned approvals into the plugin source and open a PR.

The hook records AI-approved commands/subcommands in a machine-local JSON store
(~/.claude/safe-compounds-learned.json) for fast local reuse. Run this when you
want those learnings shared with everyone: it folds each entry into the matching
allowlist in the source, commits on a new branch, pushes, opens a PR via `gh`,
and clears the synced entries from the local store.

    python plugins/safe-compounds/tools/sync_learned.py

Requires `gh` authenticated and a clean-ish working tree. Run it from the repo
checkout (not the installed plugin cache).
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TOOLS_DIR)
PKG_DIR = os.path.join(PLUGIN_DIR, "safe_compounds")
REPO_ROOT = os.path.dirname(os.path.dirname(PLUGIN_DIR))

TRUST_FILE = os.path.join(PKG_DIR, "trust.py")
COMMANDS_FILE = os.path.join(PKG_DIR, "commands.py")

# learned-store key -> (source file, set name in that file)
TARGETS = {
    "commands": (TRUST_FILE, "SAFE_COMMANDS"),
    "NPM_SAFE_SUBCOMMANDS": (COMMANDS_FILE, "NPM_SAFE_SUBCOMMANDS"),
    "YARN_SAFE_SUBCOMMANDS": (COMMANDS_FILE, "YARN_SAFE_SUBCOMMANDS"),
    "PIP_SAFE_SUBCOMMANDS": (COMMANDS_FILE, "PIP_SAFE_SUBCOMMANDS"),
    "PNPM_SAFE_SUBCOMMANDS": (COMMANDS_FILE, "PNPM_SAFE_SUBCOMMANDS"),
    "BUN_SAFE_SUBCOMMANDS": (COMMANDS_FILE, "BUN_SAFE_SUBCOMMANDS"),
    "GH_AI_APPROVED_PAIRS": (COMMANDS_FILE, "GH_AI_APPROVED_PAIRS_BASE"),
}


def learned_path():
    return os.environ.get(
        "SAFE_COMPOUNDS_LEARNED_JSON",
        os.path.expanduser("~/.claude/safe-compounds-learned.json"),
    )


def load_learned():
    try:
        with open(learned_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _existing_items(body):
    return set(re.findall(r"'([^']+)'", body))


def _format_grouped(items):
    """Group by first letter (used for the large SAFE_COMMANDS set)."""
    groups = {}
    for c in sorted(items):
        groups.setdefault(c[0].lower(), []).append(c)
    lines = ["    " + ", ".join(f"'{c}'" for c in groups[k]) + "," for k in sorted(groups)]
    return "\n" + "\n".join(lines) + "\n"


def _format_wrapped(items, width=92):
    lines, cur, length = [], [], 4
    for item in (f"'{c}'" for c in sorted(items)):
        if length + len(item) + 2 > width and cur:
            lines.append("    " + ", ".join(cur) + ",")
            cur, length = [item], 4 + len(item)
        else:
            cur.append(item)
            length += len(item) + 2
    if cur:
        lines.append("    " + ", ".join(cur) + ",")
    return "\n" + "\n".join(lines) + "\n"


def add_items(file_path, set_name, items):
    """Insert items into a `set_name = {...}` literal. Returns the items that
    were actually new (already-present ones are ignored)."""
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(rf"({re.escape(set_name)}\s*=\s*\{{)(.*?)(\}})", content, re.DOTALL)
    if not m:
        raise SystemExit(f"Could not find set {set_name} in {file_path}")
    existing = _existing_items(m.group(2))
    new = [i for i in items if i not in existing]
    if not new:
        return []
    combined = existing | set(new)
    formatter = _format_grouped if set_name == "SAFE_COMMANDS" else _format_wrapped
    block = m.group(1) + formatter(combined) + m.group(3)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content[:m.start()] + block + content[m.end():])
    return new


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], capture_output=True, text=True)


def main():
    learned = load_learned()
    commands = learned.get("commands", [])
    subs = learned.get("subcommands", {})

    plan = {}
    if commands:
        plan["commands"] = commands
    for category, values in subs.items():
        if values and category in TARGETS:
            plan[category] = values

    if not plan:
        print("Nothing learned to sync.")
        return

    added = {}
    for key, values in plan.items():
        file_path, set_name = TARGETS[key]
        new = add_items(file_path, set_name, values)
        if new:
            added[set_name] = new

    if not added:
        print("All learned entries are already in the source; clearing local store.")
        _clear_synced(learned, plan)
        return

    summary = "; ".join(f"{name}: {', '.join(vals)}" for name, vals in added.items())
    print(f"Adding -> {summary}")

    branch = "safe-compounds-learned-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    git("checkout", "-b", branch)
    git("add", os.path.relpath(TRUST_FILE, REPO_ROOT), os.path.relpath(COMMANDS_FILE, REPO_ROOT))

    msg_lines = ["safe-compounds: promote learned commands\n"]
    for name, vals in added.items():
        msg_lines.append(f"- {name}: {', '.join(vals)}")
    msg = "\n".join(msg_lines)
    commit = git("commit", "-m", msg)
    if commit.returncode != 0:
        raise SystemExit("commit failed:\n" + commit.stderr)
    push = git("push", "-u", "origin", branch)
    if push.returncode != 0:
        raise SystemExit("push failed:\n" + push.stderr)

    pr = subprocess.run(
        ["gh", "pr", "create", "--repo", "rrrutledge/rrrutledge-claude-code-plugins",
         "--title", "safe-compounds: promote learned commands",
         "--body", "Auto-generated from the machine-local learned store.\n\n" + msg,
         "--base", "main", "--head", branch],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    print(pr.stdout.strip() or pr.stderr.strip())
    if pr.returncode != 0:
        raise SystemExit("gh pr create failed")

    _clear_synced(learned, plan)
    print("Cleared synced entries from the local store.")


def _clear_synced(learned, plan):
    """Remove the entries we just promoted from the local learned store."""
    if "commands" in plan:
        learned["commands"] = []
    subs = learned.get("subcommands", {})
    for category in plan:
        if category in subs:
            subs[category] = []
    with open(learned_path(), "w", encoding="utf-8") as f:
        json.dump(learned, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
