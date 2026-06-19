"""Drainer continuous-keeper poller — ONE fast-loop cycle, orchestrated in code.

The loop itself (enumerate -> drop seen -> cap -> dispatch -> record) is a deterministic algorithm, so
it lives here in Python — cheaper and more reliable than asking an AI to follow it each cycle. AI is used
for exactly two things: a single batched **triage** call per cycle (the needs-you / fyi / junk judgment,
per engine/triage.md) and the per-item **worker** session (the actual reply/work, draft-only).

The orchestration below is **provider-agnostic**: it reads which providers are enabled from
`.claude/drainer.local.md` and drives each through a small adapter (enumerate / stable_id / capture).
All source-specific mechanics — mail.js, the Outlook id scheme, the Graph message body — live inside an
adapter class, never in the loop. New sources (Gmail, Trello, …) plug in by adding an adapter.

Fail-safe: the poller never clears; a message-id is recorded as seen only AFTER its dispatch succeeds;
losing seen-state re-processes items (safe), never drops one. See engine/poller-core.md for the contract.

Usage:
    python run-poller.py --repo C:/Users/russe/Dev/personal-ai-pod            # one live cycle
    python run-poller.py --repo C:/Users/russe/Dev/personal-ai-pod --dry-run  # triage report only
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROVIDERS_DIR = os.path.join(SKILL_DIR, "providers")
sys.path.insert(0, SCRIPT_DIR)
import presence  # noqa: E402  (sibling module)
from provider_base import run_node, NO_WINDOW  # noqa: E402  (shared subprocess helper + console-hide flag)
from drainer_config import read_config  # noqa: E402  (shared .claude/drainer.local.md reader)

SEEN_STATE = os.path.join(SCRIPT_DIR, "seen-state.js")


# ---------------------------------------------------------------------------- generic helpers

def seen_state(*cli_args):
    return run_node([SEEN_STATE, *cli_args])


def load_seen(runtime_dir, source):
    """Return the {id: {triage, status}} map for a source; missing/corrupt -> {} (fail-safe)."""
    try:
        with open(os.path.join(runtime_dir, "seen.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get(source, {})
    except (OSError, ValueError):
        return {}


def open_count(seen):
    return sum(1 for r in seen.values() if r.get("triage") == "needs-you" and r.get("status") == "dispatched")


# read_config / parse_provider_names live in drainer_config.py — shared with the digest launcher so
# the two entry points never drift on knob names or defaults (imported at the top of the file).


# ---------------------------------------------------------------------------- provider adapters

def load_providers(cfg):
    """Dynamically load each enabled provider's adapter from providers/<name>-adapter.py.

    The poller holds no provider mechanics; an adapter lives beside its prose provider doc and
    implements provider_base.ProviderBase. A provider enabled in config without an adapter is skipped.
    """
    providers = []
    for name in cfg["providers"]:
        path = os.path.join(PROVIDERS_DIR, f"{name}-adapter.py")
        if not os.path.exists(path):
            print(f"(skipping provider '{name}': no poller adapter at providers/{name}-adapter.py)")
            continue
        spec = importlib.util.spec_from_file_location(f"{name.replace('-', '_')}_adapter", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        providers.append(mod.Provider())
    return providers


# ---------------------------------------------------------------------------- triage (the AI step)

TRIAGE_INSTRUCTIONS = (
    "You are the drainer poller's triage step. Classify each item per the rubric below, applied with "
    "the world-knowledge below. For EACH item decide its bucket; for needs-you also give "
    "kind = reply | work | work-then-reply (else null) and complexity = simple | complex (simple = a "
    "quick reply or a trivial action; complex = multi-step work, research, code, or a delicate / "
    "high-stakes message — these get a stronger model). Return ONLY a JSON array, one object per input "
    'id: [{"id": "...", "bucket": "needs-you|fyi|junk", "kind": "reply|work|work-then-reply|null", '
    '"complexity": "simple|complex", "reason": "<short>"}] — no prose, no code fence.'
)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def triage(items, repo, local_dir, model):
    claude = shutil.which("claude") or "claude"
    rubric = _read(os.path.join(SCRIPT_DIR, "..", "engine", "triage.md"))  # embed -> self-contained
    context = _read(os.path.join(local_dir, "context.md"))
    payload = [{"id": it["_id"], "source": it["_source"], "from": it.get("from"),
                "subject": it.get("subject"), "received": it.get("received"),
                "isRead": it.get("isRead"), "preview": it.get("preview")} for it in items]
    prompt = (
        f"{TRIAGE_INSTRUCTIONS}\n\n## Rubric (engine/triage.md)\n{rubric}\n\n"
        f"## World-knowledge (drainer context.md)\n{context}\n\n"
        f"## New items to triage (JSON)\n{json.dumps(payload, indent=2)}\n"
    )
    res = subprocess.run(
        # Triage is pure text-in / JSON-out (rubric + context are embedded below), so it needs no
        # tools and no elevated permissions; --setting-sources "" keeps the call lightweight.
        [claude, "-p", "--model", model, "--output-format", "json", "--setting-sources", ""],
        input=prompt,  # prompt goes on stdin (too long for an argv on Windows)
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=repo, timeout=420,
        creationflags=NO_WINDOW,  # no console flash under pythonw
    )
    if res.returncode != 0:
        raise SystemExit(f"triage call failed: {res.stderr.strip()[:400]}")
    result = res.stdout
    try:  # claude --output-format json wraps the text in {"result": "..."}
        result = json.loads(res.stdout).get("result", res.stdout)
    except ValueError:
        pass
    m = re.search(r"\[.*\]", result, re.DOTALL)
    if not m:
        raise SystemExit(f"triage returned no JSON array:\n{result[:400]}")
    return {v["id"]: v for v in json.loads(m.group(0))}


# ---------------------------------------------------------------------------- dispatch

def spawn_worker(iid, json_file, repo, runtime_dir, worker_model):
    seeds = os.path.join(runtime_dir, "seeds")
    os.makedirs(seeds, exist_ok=True)
    prompt_file = os.path.join(seeds, f"{iid}.prompt.txt")
    worker_core = os.path.join(SKILL_DIR, "engine", "worker-core.md")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(
            "You are a drainer worker handling ONE item. Read `~/.claude/CLAUDE.md`, then follow the "
            f"drainer worker procedure at `{worker_core}` for the single captured item at\n"
            f"`{json_file}`.\nThe item's `source` field names the provider — read "
            f"`{PROVIDERS_DIR}/<source>-provider.md` for its CLEAR and DRAFT-MODE and use them. "
            "Draft-only: never send or post. When the work is complete, present your result to the "
            "user and WAIT for their acknowledgment (they've seen it and replied) before you write "
            f"`{json_file[:-5]}.done` last and stop — do NOT write it in the same turn you present. "
            "Writing .done frees a concurrency slot, so deferring it until the user engages keeps new "
            "tabs from piling up faster than they can be handled. (Items you resolve WITHOUT surfacing "
            "to the user — junk routed to the digest, or a situational no-op close — get .done "
            "immediately, since they never opened for the user's attention.)\n"
        )
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    # CREATE_NO_WINDOW hides the brief cmd shim console; wt.exe opens its own (visible) worker tab.
    subprocess.Popen(["cmd", "/c", spawn_cmd, f"drain:{iid}", repo, prompt_file, worker_model],
                     cwd=repo, creationflags=NO_WINDOW)


# ---------------------------------------------------------------------------- the cycle

def reconcile_done(runtime_dir):
    """Mark any item with a worker-written <id>.done marker as cleared in seen-state, freeing a cap
    slot. The worker writes .done on completion; the poller is the authority on seen-state status."""
    items_dir = os.path.join(runtime_dir, "items")
    if not os.path.isdir(items_dir):
        return 0
    freed = 0
    for fn in os.listdir(items_dir):
        if not fn.endswith(".done"):
            continue
        iid = fn[:-5]
        try:
            with open(os.path.join(items_dir, f"{iid}.json"), encoding="utf-8") as f:
                source = json.load(f).get("source")
        except (OSError, ValueError):
            source = None
        if source:
            seen_state("clear", runtime_dir, source, iid)
            freed += 1
    return freed


def collect_new(provider, cfg):
    """Enumerate a provider, stamp ids/source, drop already-seen; return (new_items, total, seen)."""
    raw = provider.enumerate(cfg["max_messages_per_cycle"])
    seen = load_seen(cfg["runtime_dir"], provider.name)
    new = []
    for it in raw:
        it["_id"] = provider.stable_id(it)
        it["_source"] = provider.name
        if it["_id"] not in seen:
            new.append(it)
    return new, len(raw), seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    cfg = read_config(repo)

    if not args.dry_run:
        present, _, _ = presence.is_present(cfg["idle_threshold_seconds"])
        if not present:
            return  # away/locked -> silent no-op

    providers = load_providers(cfg)
    if not providers:
        print("No providers with a poller adapter are enabled; nothing to do.")
        return

    reconcile_done(cfg["runtime_dir"])  # free cap slots for items whose workers finished last cycle

    # --- enumerate ALL providers first, accumulate into one global list ---
    all_new, seen_by_source, totals = [], {}, {}
    for provider in providers:
        new, total, seen = collect_new(provider, cfg)
        seen_by_source[provider.name] = seen
        totals[provider.name] = total
        all_new.extend(new)
        if not new:
            print(f"{provider.name}: {total} enumerated, 0 new.")

    if not all_new:
        print("0 new items across all sources. Nothing to dispatch.")
        return

    # --- one combined triage call over all sources ---
    verdicts = triage(all_new, repo, cfg["local_dir"], cfg["triage_model"])
    for it in all_new:
        v = verdicts.get(it["_id"], {"bucket": "needs-you", "kind": "reply"})  # unjudged -> act (fail-safe)
        it["_bucket"], it["_kind"] = v.get("bucket", "needs-you"), v.get("kind")
        it["_complexity"] = v.get("complexity", "simple")

    # --- global open count across ALL sources ---
    global_oc = sum(open_count(s) for s in seen_by_source.values())

    # --- split: needs-you (newest-first globally) vs others ---
    needs = sorted(
        (it for it in all_new if it["_bucket"] == "needs-you"),
        key=lambda it: it.get("received") or "",
        reverse=True,  # newest first; items missing received sort last via ""
    )
    others = [it for it in all_new if it["_bucket"] != "needs-you"]

    prov = {p.name: p for p in providers}  # name -> adapter for cross-source dispatch

    if args.dry_run:
        counts = {b: sum(1 for it in all_new if it["_bucket"] == b) for b in ("needs-you", "fyi", "junk")}
        total_all = sum(totals.values())
        print(f"DRY-RUN — {len(all_new)} new of {total_all} across {len(providers)} source(s) | "
              f"{counts['needs-you']} needs-you, {counts['fyi']} fyi, {counts['junk']} junk | "
              f"global cap {cfg['max_open_tabs']}, currently open {global_oc}")
        print("  needs-you (newest-first globally):")
        oc = global_oc
        for it in needs:
            held = oc >= cfg["max_open_tabs"]
            if not held:
                oc += 1
            model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
            action = "HOLD (at cap)" if held else f"spawn worker [{it['_complexity']} -> {model}]"
            print(f"    [{it['_source']:20}] {it['_id']}  ->  {action}\n"
                  f"        {it.get('received')} | {it.get('from')} | {it.get('subject')}")
        if others:
            print("  others -> digest:")
            for it in others:
                print(f"    [{it['_bucket']:9}] [{it['_source']:20}] {it['_id']}\n"
                      f"        {it.get('from')} | {it.get('subject')}")
        return

    dispatched, held, queued = 0, 0, 0
    for it in needs:
        provider = prov[it["_source"]]
        iid = it["_id"]
        if global_oc >= cfg["max_open_tabs"]:
            held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
            continue
        model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        spawn_worker(iid, json_file, repo, cfg["runtime_dir"], model)
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "needs-you")
        global_oc += 1
        dispatched += 1
    for it in others:
        provider = prov[it["_source"]]
        iid = it["_id"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        seen_state("queue-add", cfg["runtime_dir"], it["_source"], iid, json_file)
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, it["_bucket"])
        queued += 1

    print(f"dispatched {dispatched} worker tab(s), queued {queued} for digest, "
          f"held {held} at global cap of {cfg['max_open_tabs']}. Poller never clears.")


if __name__ == "__main__":
    main()
