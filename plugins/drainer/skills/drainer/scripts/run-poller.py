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
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROVIDERS_DIR = os.path.join(SKILL_DIR, "providers")
sys.path.insert(0, SCRIPT_DIR)
import presence  # noqa: E402  (sibling module)
from provider_base import run_node, NO_WINDOW, ProviderError  # noqa: E402  (subprocess helper + typed provider failure)
from drainer_config import read_config  # noqa: E402  (shared .claude/drainer.local.md reader)

SEEN_STATE = os.path.join(SCRIPT_DIR, "seen-state.js")
HEALTH_FILE = "provider-health.json"


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


# ---------------------------------------------------------------------------- provider health (observability)
#
# The poller runs headless under pythonw (stdout/stderr discarded), so a provider whose credential
# expired would fail silently every cycle and Russell would never know to refresh it. We record each
# provider's outcome to <runtime_dir>/provider-health.json so the once-a-day digest (the visible,
# interactive channel) can surface a stuck provider. Stdlib-only and fail-safe, like seen-state.js:
# a missing/corrupt file reads as empty, and writes are atomic (temp + replace).

def load_health(runtime_dir):
    try:
        with open(os.path.join(runtime_dir, HEALTH_FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_health(runtime_dir, health):
    os.makedirs(runtime_dir, exist_ok=True)
    path = os.path.join(runtime_dir, HEALTH_FILE)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(health, f, indent=2)
    os.replace(tmp, path)


def record_health_ok(health, name):
    """A successful enumerate resets the failure streak and stamps last_ok_ts; keeps prior error fields
    for reference (so the digest can say 'recovered at <last_ok_ts> after failing since <last_error_ts>')."""
    h = health.setdefault(name, {})
    h["consecutive_failures"] = 0
    h["last_ok_ts"] = datetime.now(timezone.utc).isoformat()
    health[name] = h


def record_health_failure(health, name, error, kind):
    """A failed enumerate (or adapter load) increments the streak and records a short error + its kind
    (auth = transient/self-heals once creds refreshed; config = deploy error, won't self-heal)."""
    h = health.setdefault(name, {})
    h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
    h["last_error"] = (error or "")[:300]
    h["last_error_kind"] = kind
    h["last_error_ts"] = datetime.now(timezone.utc).isoformat()
    h.setdefault("last_ok_ts", None)
    health[name] = h


# read_config / parse_provider_names live in drainer_config.py — shared with the digest launcher so
# the two entry points never drift on knob names or defaults (imported at the top of the file).


# ---------------------------------------------------------------------------- provider adapters

def load_providers(cfg, health):
    """Dynamically load each enabled provider's adapter from providers/<name>-adapter.py.

    The poller holds no provider mechanics; an adapter lives beside its prose provider doc and
    implements provider_base.ProviderBase. A provider enabled in config without an adapter is skipped.

    Adapter construction (`__init__` locates its helper .js/util) can raise ProviderError(kind=config)
    when a deploy is broken. That failure is isolated here — recorded to health and skipped — so one
    mislocated helper never aborts the cycle for the other providers.
    """
    providers = []
    for name in cfg["providers"]:
        path = os.path.join(PROVIDERS_DIR, f"{name}-adapter.py")
        if not os.path.exists(path):
            print(f"(skipping provider '{name}': no poller adapter at providers/{name}-adapter.py)")
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"{name.replace('-', '_')}_adapter", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            prov = mod.Provider()
            prov.configure(cfg)  # hand the adapter the parsed config (repo + knobs); no-op for inbox adapters
            providers.append(prov)
        except ProviderError as e:
            record_health_failure(health, name, str(e), e.kind)
            print(f"(provider '{name}' failed to load [{e.kind}]: {e})")
        except Exception as e:  # a broken adapter import shouldn't take the whole cycle down
            record_health_failure(health, name, f"adapter load error: {e}", "config")
            print(f"(provider '{name}' failed to load: {e})")
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


def triage(items, repo, local_dir, model, providers_by_name):
    claude = shutil.which("claude") or "claude"
    rubric = _read(os.path.join(SCRIPT_DIR, "..", "engine", "triage.md"))  # embed -> self-contained
    context = _read(os.path.join(local_dir, "context.md"))

    def preview(it):
        # The owning adapter supplies the text triage sees: its `triage_text` returns the new message
        # body (quote-stripped) rather than just the subject. Adapters whose enumerate carries no preview
        # (gmail) override it to fetch the body for these new items; the default just returns `preview`.
        p = providers_by_name.get(it["_source"])
        return p.triage_text(it) if p else (it.get("preview") or "")

    payload = [{"id": it["_id"], "source": it["_source"], "from": it.get("from"),
                "subject": it.get("subject"), "received": it.get("received"),
                "isRead": it.get("isRead"), "preview": preview(it)} for it in items]
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

def _item_bits(json_file):
    """(display-label, subject/name, who) parsed from a captured item json; ('', '', '') on error."""
    labels = {"personal-outlook": "Outlook", "gmail": "Gmail", "slack": "Slack", "trello": "Trello"}
    try:
        with open(json_file, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return "", "", ""
    src = rec.get("source") or ""
    label = labels.get(src, (src.split("-")[0] or "item").capitalize())
    subject = (rec.get("subject") or rec.get("name") or "").strip()
    who = (rec.get("from") or "").strip()
    if not who:
        contacts = rec.get("contacts") or []
        who = (contacts[0] if contacts else "") or ""
    if "<" in who:  # "Name <addr>" -> the name (or the address if unnamed)
        head, _, tail = who.partition("<")
        who = head.strip().strip('"') or tail.rstrip(">").strip()
    return label, subject, who


def _worker_title(iid, json_file):
    """The INITIAL tab title (shown for the ~1s before the worker's Claude session renames the tab
    itself). Short and human-readable; falls back to the id on any error."""
    label, subject, who = _item_bits(json_file)
    if not label:
        return f"drain:{iid}"
    title = f"{label}: {subject}" if subject else label
    if who:
        title += f" - {who}"
    title = re.sub(r'[&<>|%"^]', " ", title)  # neutralize cmd-breaking chars
    title = re.sub(r"\s+", " ", title).strip()  # collapse whitespace
    return title[:50].strip() or f"drain:{iid}"


def _worker_summary(json_file):
    """A one-line item summary that LEADS the worker's seed prompt. Claude names the tab off its first
    message, so leading with this makes the tab self-title descriptively while keeping its attention star
    (no --suppressApplicationTitle needed). Lead with the CONTENT — the subject/card and who it's from —
    since that's what matters at a glance; the source (Gmail/Slack/Trello/…) is incidental and is NOT
    forced into the title. '' when there's nothing to say."""
    _label, subject, who = _item_bits(json_file)
    if not subject and not who:
        return ""
    s = "You are handling this for Russell"
    if subject:
        s += f': "{subject}"'
    if who:
        s += f", from {who}"
    return s + "."


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
    # A one-line summary leads the seed so the worker's Claude session self-titles the tab descriptively
    # while keeping its attention star (the launcher prepends this; see launch-session.ps1 -SummaryFile).
    summary_file = os.path.join(seeds, f"{iid}.summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(_worker_summary(json_file))
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    # CREATE_NO_WINDOW hides the brief cmd shim console; wt.exe opens its own (visible) worker tab.
    subprocess.Popen(["cmd", "/c", spawn_cmd, _worker_title(iid, json_file), repo, prompt_file,
                      worker_model, summary_file], cwd=repo, creationflags=NO_WINDOW)


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

    health = load_health(cfg["runtime_dir"])
    providers = load_providers(cfg, health)
    if not providers:
        print("No providers with a poller adapter are enabled; nothing to do.")
        if not args.dry_run:
            save_health(cfg["runtime_dir"], health)  # persist any config-load failures recorded above
        return

    reconcile_done(cfg["runtime_dir"])  # free cap slots for items whose workers finished last cycle

    # --- enumerate ALL providers first, accumulate into one global list ---
    # Each provider's enumerate is isolated: a failure (expired creds, IMAP/API blip) is caught,
    # recorded to provider-health.json, and the loop continues so the OTHER providers still drain this
    # cycle. The daily digest reads that health file and surfaces a stuck provider for Russell to fix.
    all_new, seen_by_source, totals = [], {}, {}
    for provider in providers:
        try:
            new, total, seen = collect_new(provider, cfg)
        except ProviderError as e:
            record_health_failure(health, provider.name, str(e), e.kind)
            print(f"{provider.name}: enumerate FAILED [{e.kind}] — {e}. Skipping; other providers continue.")
            continue
        except Exception as e:  # unexpected adapter fault — still isolate it, never abort the cycle
            record_health_failure(health, provider.name, str(e), "unknown")
            print(f"{provider.name}: enumerate FAILED [unknown] — {e}. Skipping; other providers continue.")
            continue
        record_health_ok(health, provider.name)
        seen_by_source[provider.name] = seen
        totals[provider.name] = total
        all_new.extend(new)
        if not new:
            print(f"{provider.name}: {total} enumerated, 0 new.")
    # Dry-run is a manual diagnostic often run from a shell without the User-scope creds; persisting
    # health then would log false failures, so only a live cycle records the outcome.
    if not args.dry_run:
        save_health(cfg["runtime_dir"], health)  # persist this cycle's per-provider outcomes

    if not all_new:
        print("0 new items across all sources. Nothing to dispatch.")
        return

    # --- one combined triage call over all sources ---
    prov = {p.name: p for p in providers}  # name -> adapter (also used below for cross-source dispatch)
    verdicts = triage(all_new, repo, cfg["local_dir"], cfg["triage_model"], prov)
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
