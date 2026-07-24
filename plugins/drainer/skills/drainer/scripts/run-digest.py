"""Drainer EOD digest launcher — opens ONE interactive digest tab, once a day.

The fast-loop poller (`run-poller.py`) is headless and silent; the digest is the OPPOSITE — it must
be a visible, interactive session, because it empties the fyi/junk queue and re-surfaces stale
needs-you items only AFTER Russell reviews and approves. So this launcher is deliberately thin: it
opens a single Windows Terminal tab running a fresh Claude session seeded to follow
`engine/digest-core.md`. All the judgment (summarize fyi, group junk with source-stop proposals, the
reconciliation scan, and clearing on Russell's OK) happens inside that interactive session.

The daily Scheduled Task (see `install-digest-schedule.ps1`) runs this once a day.

Usage:
    python run-digest.py --repo C:/Users/russe/Dev/personal-ai-pod              # open the digest tab
    python run-digest.py --repo C:/Users/russe/Dev/personal-ai-pod --dry-run    # print the brief only
"""
import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROVIDERS_DIR = os.path.join(SKILL_DIR, "providers")
sys.path.insert(0, SCRIPT_DIR)
from drainer_config import read_config, find_provider_file  # noqa: E402  (shared .claude/drainer.local.md reader + provider resolution)
from provider_base import run_node, NO_WINDOW, spawn_tab  # noqa: E402  (shared subprocess helper + console-hide flag)

SEEN_STATE = os.path.join(SCRIPT_DIR, "seen-state.js")


def seen_state(*cli_args):
    return run_node([SEEN_STATE, *cli_args])


def reconcile_cleared(runtime_dir, cfg):
    """Silent, deterministic CLEAR-verification sweep — no AI, nothing shown to Russell.

    A worker marks a needs-you item 'cleared' by writing .done, and the poller trusts that at face
    value. But the worker's own CLEAR call (archiving the source message) can silently fail while
    .done still gets written, leaving the item stuck in the live Inbox forever — seen-state has no way
    to notice, since it never rechecks anything once an id is marked cleared.

    For each 'cleared' needs-you item, ask its provider (if it offers still_in_inbox_ids — email
    providers do, chat/card providers don't) whether the source message is still physically present.
    If so, requeue() it — the same reset orphan recovery uses — so the next poller cycle re-enumerates
    it as brand new. From there the existing machinery handles it with zero special-casing: worker-core's
    situational-check recognizes an already-answered thread and self-closes quietly (archive + .done,
    no tab shown), or — if it's genuinely still open — it surfaces as an ordinary fresh needs-you item.
    Either way Russell sees nothing extra; this just closes the blind spot.
    """
    cleared = json.loads(seen_state("cleared-list", runtime_dir).stdout or "[]")
    if not cleared:
        return 0

    by_source = {}
    for r in cleared:
        by_source.setdefault(r["source"], []).append(r["id"])

    inbox_ids_by_source = {}
    for name in by_source:
        path = find_provider_file(PROVIDERS_DIR, cfg["local_dir"], name, "-adapter.py")
        if not path:
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"{name.replace('-', '_')}_adapter", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            prov = mod.Provider()
            prov.configure(cfg)
            ids = prov.still_in_inbox_ids()
        except Exception:
            ids = None  # a broken/uncheckable adapter this run just means: skip reconciliation for it
        if ids is not None:
            inbox_ids_by_source[name] = ids

    reset = 0
    for source, ids in inbox_ids_by_source.items():
        for iid in by_source[source]:
            try:
                with open(os.path.join(runtime_dir, "items", f"{iid}.json"), encoding="utf-8") as f:
                    message_id = json.load(f).get("messageId")
            except (OSError, ValueError):
                continue
            if message_id and message_id in ids:
                seen_state("requeue", runtime_dir, source, iid)
                print(f"reconcile: {iid} ({source}) still in inbox despite 'cleared' status -> reset for a fresh pass.")
                reset += 1
    return reset


def write_seed(runtime_dir, repo, cfg):
    """Write the digest session's prompt file: a pointer to digest-core.md plus the few runtime
    facts it can't infer (where the queue/state live, the stale threshold, the providers dir)."""
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
            "(digest-core step 0) and surface any stuck provider; missing/empty means all healthy.\n"
            f"- stale_hours (reconciliation threshold): {cfg['stale_hours']}.\n\n"
            "Present the digest to Russell and clear NOTHING until he approves. Draft-only: never send "
            "or post. When the queue is emptied (or Russell defers) and you are done, stop.\n"
        )
    return prompt_file


def _fmt_local(ts):
    """An ISO-8601 UTC timestamp rendered in the machine's local zone, or the raw string on any error."""
    if not ts:
        return "never"
    try:
        return datetime.datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %I:%M %p %Z")
    except ValueError:
        return ts


def _print_heartbeat(hb):
    """Show the poller's own liveness (`_poller` heartbeat) so a run of empty cycles is legible: the
    poller stamps this every live cycle — including a presence-gated no-op — so a stale `last_drained`
    reads as 'correctly idle' or 'not running' instead of a silent death."""
    if not hb:
        print("  Poller heartbeat: none recorded yet (no live cycle has run since this was added).")
        return
    print(f"  Poller heartbeat: last ran {_fmt_local(hb.get('last_run_ts'))} "
          f"(decided: {hb.get('last_decision', '?')}); last drained {_fmt_local(hb.get('last_drained_ts'))}.")


def print_brief(runtime_dir, cfg):
    """Deterministic preview (no AI, no tab): queue counts + the stale-item list. For the dry-run ramp."""
    queue = run_node([SEEN_STATE, "queue-list", runtime_dir]).stdout
    stale = run_node([SEEN_STATE, "stale-list", runtime_dir, str(cfg["stale_hours"])]).stdout
    try:
        q = json.loads(queue or "[]")
    except ValueError:
        q = []
    counts = {"fyi": 0, "junk": 0, "other": 0}
    for e in q:
        t = (e.get("item") or {}).get("triage")
        counts[t if t in ("fyi", "junk") else "other"] += 1
    try:
        s = json.loads(stale or "[]")
    except ValueError:
        s = []
    print(f"DRY-RUN digest brief for {runtime_dir}")
    try:
        with open(os.path.join(runtime_dir, "provider-health.json"), encoding="utf-8") as f:
            health = json.load(f) or {}
    except (OSError, ValueError):
        health = {}
    stuck = {n: h for n, h in health.items()
             if not n.startswith("_") and (h or {}).get("consecutive_failures", 0) >= 2}
    if stuck:
        print(f"  Provider health: {len(stuck)} stuck (>=2 consecutive failures):")
        for n, h in stuck.items():
            print(f"    [{h.get('last_error_kind', '?'):6}] {n}: {h.get('consecutive_failures')} cycles "
                  f"failing since last OK {h.get('last_ok_ts')}\n        {h.get('last_error')}")
    else:
        print("  Provider health: all healthy (no provider with >=2 consecutive failures).")
    _print_heartbeat(health.get("_poller") or {})
    print(f"  Digest queue: {len(q)} item(s) -> {counts['fyi']} fyi, {counts['junk']} junk, "
          f"{counts['other']} other")
    for e in q:
        it = e.get("item") or {}
        print(f"    [{(it.get('triage') or '?'):4}] {e.get('id')}\n"
              f"        {it.get('from')} | {it.get('subject')}")
    print(f"  Reconciliation (needs-you dispatched-but-uncleared > {cfg['stale_hours']}h): {len(s)} stale")
    for r in s:
        it = r.get("item") or {}
        age = r.get("ageHours")
        print(f"    [{'?' if age is None else str(age) + 'h':>5}] {r.get('id')}\n"
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

    reset = reconcile_cleared(runtime_dir, cfg)
    if reset:
        print(f"reconciliation: reset {reset} cleared-but-still-present item(s) for a fresh pass.")

    prompt_file = write_seed(runtime_dir, repo, cfg)
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    spawn_tab([spawn_cmd, "drain:digest", repo, prompt_file, cfg["digest_model"]], cwd=repo)
    print(f"Opened digest tab (model {cfg['digest_model']}) for {runtime_dir}.")


if __name__ == "__main__":
    main()
