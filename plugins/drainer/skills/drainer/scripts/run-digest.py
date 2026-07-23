"""Drainer EOD digest launcher — opens ONE interactive digest tab, once a day.

The fast-loop poller (`run-poller.py`) is headless and silent; the digest is the OPPOSITE — it must
be a visible, interactive session, because it empties the fyi/junk queue only AFTER Russell reviews and
approves. So this launcher is deliberately thin: it opens a single Windows Terminal tab running a fresh
Claude session seeded to follow `engine/digest-core.md`. All the judgment (summarize fyi, group junk
with source-stop proposals, and clearing on Russell's OK) happens inside that interactive session.

The daily Scheduled Task (see `install-digest-schedule.ps1`) runs this once a day.

Usage:
    python run-digest.py --repo C:/Users/russe/Dev/personal-ai-pod              # open the digest tab
    python run-digest.py --repo C:/Users/russe/Dev/personal-ai-pod --dry-run    # print the brief only
"""
import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROVIDERS_DIR = os.path.join(SKILL_DIR, "providers")
sys.path.insert(0, SCRIPT_DIR)
from drainer_config import read_config  # noqa: E402  (shared .claude/drainer.local.md reader)
from provider_base import run_node, spawn_tab  # noqa: E402  (shared subprocess + tab-spawn helpers)

SEEN_STATE = os.path.join(SCRIPT_DIR, "seen-state.js")


def write_seed(runtime_dir, repo, cfg):
    """Write the digest session's prompt file: a pointer to digest-core.md plus the few runtime
    facts it can't infer (where the queue/state live, the providers dir)."""
    seeds = os.path.join(runtime_dir, "seeds")
    os.makedirs(seeds, exist_ok=True)
    prompt_file = os.path.join(seeds, "digest.prompt.txt")
    digest_core = os.path.join(SKILL_DIR, "engine", "digest-core.md")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(
            "You are the drainer EOD digest session. Read `~/.claude/CLAUDE.md`, then follow the "
            f"drainer digest procedure at\n`{digest_core}`.\n\n"
            "Runtime facts for this run:\n"
            f"- runtime_dir: `{runtime_dir}` (holds digest-queue.json, seen.json, and items/).\n"
            f"- repo: `{repo}`.\n"
            f"- seen-state helper: `{SEEN_STATE}` (run with node).\n"
            f"- providers dirs: `{PROVIDERS_DIR}` and `{os.path.join(cfg['local_dir'], 'providers')}` "
            "(machine-local providers) — each item's `source` names its `<source>-provider.md` in one of "
            "these (read it for CLEAR and JUNK-LEARNING).\n"
            f"- provider-health file: `{os.path.join(runtime_dir, 'provider-health.json')}` — read it FIRST "
            "(digest-core step 0) and surface any stuck provider; missing/empty means all healthy.\n\n"
            "Present the digest to Russell and clear NOTHING until he approves. Draft-only: never send "
            "or post. When the queue is emptied (or Russell defers) and you are done, stop.\n"
        )
    return prompt_file


def print_brief(runtime_dir, cfg):
    """Deterministic preview (no AI, no tab): provider health + queue counts. For the dry-run ramp."""
    queue = run_node([SEEN_STATE, "queue-list", runtime_dir]).stdout
    try:
        q = json.loads(queue or "[]")
    except ValueError:
        q = []
    counts = {"fyi": 0, "junk": 0, "other": 0}
    for e in q:
        t = (e.get("item") or {}).get("triage")
        counts[t if t in ("fyi", "junk") else "other"] += 1
    print(f"DRY-RUN digest brief for {runtime_dir}")
    try:
        with open(os.path.join(runtime_dir, "provider-health.json"), encoding="utf-8") as f:
            health = json.load(f) or {}
    except (OSError, ValueError):
        health = {}
    stuck = {n: h for n, h in health.items() if (h or {}).get("consecutive_failures", 0) >= 2}
    if stuck:
        print(f"  Provider health: {len(stuck)} stuck (>=2 consecutive failures):")
        for n, h in stuck.items():
            print(f"    [{h.get('last_error_kind', '?'):6}] {n}: {h.get('consecutive_failures')} cycles "
                  f"failing since last OK {h.get('last_ok_ts')}\n        {h.get('last_error')}")
    else:
        print("  Provider health: all healthy (no provider with >=2 consecutive failures).")
    print(f"  Digest queue: {len(q)} item(s) -> {counts['fyi']} fyi, {counts['junk']} junk, "
          f"{counts['other']} other")
    for e in q:
        it = e.get("item") or {}
        print(f"    [{(it.get('triage') or '?'):4}] {e.get('id')}\n"
              f"        {it.get('from')} | {it.get('subject')}")
    print("Nothing cleared (dry-run).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    cfg = read_config(repo)
    runtime_dir = cfg["runtime_dir"]

    if args.dry_run:
        print_brief(runtime_dir, cfg)
        return

    prompt_file = write_seed(runtime_dir, repo, cfg)
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    spawn_tab([spawn_cmd, "drain:digest", repo, prompt_file, cfg["digest_model"]], cwd=repo)
    print(f"Opened digest tab (model {cfg['digest_model']}) for {runtime_dir}.")


if __name__ == "__main__":
    main()
