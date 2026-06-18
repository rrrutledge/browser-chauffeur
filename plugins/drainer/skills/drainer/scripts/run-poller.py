"""Drainer continuous-keeper poller — ONE fast-loop cycle, orchestrated in code.

The loop itself (enumerate -> drop seen -> cap -> dispatch -> record) is a deterministic algorithm,
so it lives here in Python — cheaper and more reliable than asking an AI to follow it each cycle.
AI is used for exactly two things: a single batched **triage** call per cycle (the needs-you / fyi /
junk judgment, per the drainer triage.md rubric) and the per-item **worker** session (the actual
reply/work, draft-only). See engine/poller-core.md for the contract.

Fail-safe: the poller never clears; a message-id is recorded as seen only AFTER its dispatch
succeeds; losing seen-state re-processes items (safe), never drops one.

Usage:
    python run-poller.py --repo C:/Users/russe/Dev/personal-ai-pod            # one live cycle
    python run-poller.py --repo C:/Users/russe/Dev/personal-ai-pod --dry-run  # triage report only
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import presence  # noqa: E402  (sibling module)

SEEN_STATE = os.path.join(SCRIPT_DIR, "seen-state.js")


# ---------------------------------------------------------------------------- helpers

def find_plugins_root():
    """Walk up from this script to the 'plugins' dir so we can locate sibling plugins (ms-graph)."""
    d = SCRIPT_DIR
    while d and os.path.basename(d) != "plugins":
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return d


def mail_js_path(override):
    if override:
        return override
    root = find_plugins_root()
    if root:
        cand = os.path.join(root, "ms-graph", "skills", "ms-graph", "scripts", "mail.js")
        if os.path.exists(cand):
            return cand
    raise SystemExit("Could not locate ms-graph mail.js; pass --mail-js <path>.")


def read_config(repo):
    """Pull the scalar knobs the orchestrator needs out of .claude/drainer.local.md frontmatter."""
    path = os.path.join(repo, ".claude", "drainer.local.md")
    text = ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        pass

    def scalar(key, default):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else default

    runtime_dir = scalar("runtime_dir", ".tmp/drainer")
    if not os.path.isabs(runtime_dir):
        runtime_dir = os.path.join(repo, runtime_dir)
    return {
        "runtime_dir": runtime_dir,
        "local_dir": scalar("local_dir", os.path.join(repo, "drainer-local")),
        "max_open_tabs": int(scalar("max_open_tabs", "3")),
        "max_messages_per_cycle": int(scalar("max_messages_per_cycle", "50")),
        "idle_threshold_seconds": int(scalar("idle_threshold_seconds", "600")),
        "has_personal_outlook": "personal-outlook:" in text,
    }


def slug(s, maxlen=24):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen].strip("-")


def stable_id(item):
    """personal-outlook-<YYYYMMDD-HHMM>-<sender>-<first-3-subject-words> (lowercase, dash-joined)."""
    recv = (item.get("received") or "")[:16].replace("-", "").replace("T", "-").replace(":", "")
    recv = recv[:13]  # YYYYMMDD-HHMM
    sender = slug((item.get("fromAddress") or item.get("from") or "").split("@")[0], 18)
    subj3 = slug("-".join((item.get("subject") or "").split()[:3]), 18)
    return f"personal-outlook-{recv}-{sender}-{subj3}".strip("-")[:64]


def load_seen(runtime_dir, source):
    """Return the {id: {triage, status}} map for a source; missing/corrupt -> {} (fail-safe)."""
    try:
        with open(os.path.join(runtime_dir, "seen.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get(source, {})
    except (OSError, ValueError):
        return {}


def open_count(seen):
    return sum(1 for r in seen.values() if r.get("triage") == "needs-you" and r.get("status") == "dispatched")


def run_node(args, **kw):
    return subprocess.run(["node", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def seen_state(*cli_args):
    return run_node([SEEN_STATE, *cli_args])


# ---------------------------------------------------------------------------- triage (the AI step)

TRIAGE_INSTRUCTIONS = (
    "You are the drainer poller's triage step. Use the installed `drainer` skill's "
    "`engine/triage.md` rubric (the three buckets needs-you / fyi / junk, the personal-message and "
    "container rules, and the tie-breakers) together with the world-knowledge below. For EACH item "
    "decide its bucket; for needs-you also give kind = reply | work | work-then-reply (else null). "
    "Return ONLY a JSON array, one object per input id: "
    '[{"id": "...", "bucket": "needs-you|fyi|junk", "kind": "reply|work|work-then-reply|null", '
    '"reason": "<short>"}] — no prose, no code fence.'
)


def triage(items, repo, local_dir):
    claude = shutil.which("claude") or "claude"
    context = ""
    try:
        with open(os.path.join(local_dir, "context.md"), encoding="utf-8") as f:
            context = f.read()
    except OSError:
        pass
    payload = [{"id": it["_id"], "from": it.get("from"), "subject": it.get("subject"),
                "received": it.get("received"), "isRead": it.get("isRead"),
                "preview": it.get("preview")} for it in items]
    prompt = (
        f"{TRIAGE_INSTRUCTIONS}\n\n## World-knowledge (drainer context.md)\n{context}\n\n"
        f"## New items to triage (JSON)\n{json.dumps(payload, indent=2)}\n"
    )
    res = subprocess.run(
        [claude, "-p", "--output-format", "json",
         "--permission-mode", "bypassPermissions", "--setting-sources", ""],
        input=prompt,  # prompt goes on stdin (too long for an argv on Windows)
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=repo, timeout=420,
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
    verdicts = {v["id"]: v for v in json.loads(m.group(0))}
    return verdicts


# ---------------------------------------------------------------------------- capture + dispatch

def capture(item, cfg, mailjs):
    items_dir = os.path.join(cfg["runtime_dir"], "items")
    os.makedirs(items_dir, exist_ok=True)
    iid = item["_id"]
    email_file = os.path.join(items_dir, f"{iid}.email.md")
    show = run_node([mailjs, f"--show={item['id']}"])
    body = show.stdout if show.returncode == 0 else "(could not load body)"
    with open(email_file, "w", encoding="utf-8") as f:
        f.write(f"# {item.get('subject')}\n\nFrom: {item.get('from')}\nReceived: {item.get('received')}\n"
                f"Link: {item.get('webLink')}\nMessageId: {item['id']}\n\n---\n\n{body}\n")
    record = {
        "id": iid, "source": "personal-outlook", "triage": item["_bucket"], "kind": item.get("_kind"),
        "from": item.get("from"), "subject": item.get("subject"), "received": item.get("received"),
        "snippet": item.get("preview"), "url": item.get("webLink"), "messageId": item["id"],
        "emailFile": email_file, "ts": datetime.now(timezone.utc).isoformat(),
    }
    json_file = os.path.join(items_dir, f"{iid}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return json_file


def spawn_worker(iid, json_file, repo, cfg):
    seeds = os.path.join(cfg["runtime_dir"], "seeds")
    os.makedirs(seeds, exist_ok=True)
    prompt_file = os.path.join(seeds, f"{iid}.prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(
            "You are a drainer worker handling ONE item. Read `~/.claude/CLAUDE.md`, then follow the "
            "installed `drainer` skill's `engine/worker-core.md` for the single captured item at\n"
            f"`{json_file}`.\nThe item's `source` names the provider — read that provider doc's CLEAR "
            "and DRAFT-MODE and use them. Draft-only: never send or post. When the work is complete "
            f"(draft staged and the source item cleared per CLEAR), write `{json_file[:-5]}.done` last, "
            "then stop.\n"
        )
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    subprocess.Popen(["cmd", "/c", spawn_cmd, f"drain:{iid}", repo, prompt_file], cwd=repo)


# ---------------------------------------------------------------------------- the cycle

def enumerate_personal_outlook(cfg, mailjs):
    res = run_node([mailjs, "--list-inbox", "--json", f"--top={cfg['max_messages_per_cycle']}"])
    if res.returncode != 0:
        raise SystemExit(f"enumerate failed (auth?): {res.stderr.strip()[:300]}")
    return json.loads(res.stdout or "[]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mail-js")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    cfg = read_config(repo)
    mailjs = mail_js_path(args.mail_js)

    if not args.dry_run:
        present, idle, locked = presence.is_present(cfg["idle_threshold_seconds"])
        if not present:
            return  # away/locked -> silent no-op

    if not cfg["has_personal_outlook"]:
        print("No personal-outlook provider enabled; nothing to do.")
        return

    raw = enumerate_personal_outlook(cfg, mailjs)
    seen = load_seen(cfg["runtime_dir"], "personal-outlook")
    new = []
    for it in raw:
        it["_id"] = stable_id(it)
        if it["_id"] not in seen:
            new.append(it)
    if not new:
        print(f"personal-outlook: {len(raw)} in inbox, 0 new. Nothing to dispatch.")
        return

    verdicts = triage(new, repo, cfg["local_dir"])
    for it in new:
        v = verdicts.get(it["_id"], {"bucket": "needs-you", "kind": "reply"})  # fail-safe: unjudged -> act
        it["_bucket"], it["_kind"] = v.get("bucket", "needs-you"), v.get("kind")

    counts = {"needs-you": 0, "fyi": 0, "junk": 0}
    for it in new:
        counts[it["_bucket"]] = counts.get(it["_bucket"], 0) + 1

    if args.dry_run:
        print(f"DRY-RUN — personal-outlook: {len(new)} new of {len(raw)} | "
              f"{counts['needs-you']} needs-you, {counts['fyi']} fyi, {counts['junk']} junk")
        oc = open_count(seen)
        for it in new:
            held = it["_bucket"] == "needs-you" and oc >= cfg["max_open_tabs"]
            if it["_bucket"] == "needs-you" and not held:
                oc += 1
            action = ("HOLD (at cap)" if held else "spawn worker") if it["_bucket"] == "needs-you" else "queue -> digest"
            print(f"  [{it['_bucket']:9}] {it['_id']}  ->  {action}\n"
                  f"      {it.get('from')} | {it.get('subject')}")
        return

    oc = open_count(seen)
    dispatched, held, queued = 0, 0, 0
    for it in new:
        iid = it["_id"]
        if it["_bucket"] == "needs-you":
            if oc >= cfg["max_open_tabs"]:
                held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
                continue
            json_file = capture(it, cfg, mailjs)
            spawn_worker(iid, json_file, repo, cfg)
            seen_state("record", cfg["runtime_dir"], "personal-outlook", iid, "needs-you")
            oc += 1
            dispatched += 1
        else:
            json_file = capture(it, cfg, mailjs)
            seen_state("queue-add", cfg["runtime_dir"], "personal-outlook", iid, json_file)
            seen_state("record", cfg["runtime_dir"], "personal-outlook", iid, it["_bucket"])
            queued += 1
    print(f"personal-outlook: dispatched {dispatched} worker tab(s), queued {queued} for digest, "
          f"held {held} at cap. Poller never clears.")


if __name__ == "__main__":
    main()
