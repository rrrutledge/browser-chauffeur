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


# ---------------------------------------------------------------------------- generic helpers

def run_node(args, **kw):
    return subprocess.run(["node", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def seen_state(*cli_args):
    return run_node([SEEN_STATE, *cli_args])


def slug(s, maxlen=18):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen].strip("-")


def load_seen(runtime_dir, source):
    """Return the {id: {triage, status}} map for a source; missing/corrupt -> {} (fail-safe)."""
    try:
        with open(os.path.join(runtime_dir, "seen.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get(source, {})
    except (OSError, ValueError):
        return {}


def open_count(seen):
    return sum(1 for r in seen.values() if r.get("triage") == "needs-you" and r.get("status") == "dispatched")


def read_config(repo):
    """Pull the scalar knobs + enabled provider names out of .claude/drainer.local.md frontmatter."""
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
        "providers": parse_provider_names(text),
        "runtime_dir": runtime_dir,
        "local_dir": scalar("local_dir", os.path.join(repo, "drainer-local")),
        "max_open_tabs": int(scalar("max_open_tabs", "3")),
        "max_messages_per_cycle": int(scalar("max_messages_per_cycle", "50")),
        "idle_threshold_seconds": int(scalar("idle_threshold_seconds", "600")),
    }


def parse_provider_names(text):
    """The immediate child keys under the `providers:` block (e.g. personal-outlook, trello)."""
    names, in_block = [], False
    for line in text.splitlines():
        if re.match(r"^\s*providers\s*:\s*$", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^\S", line) or line.strip() in ("---", ""):
                if line.strip() == "":
                    continue
                if re.match(r"^\S", line):
                    break
            m = re.match(r"^\s{2}([A-Za-z0-9_-]+)\s*:", line)
            if m:
                names.append(m.group(1))
    return names


# ---------------------------------------------------------------------------- provider adapters

class PersonalOutlookProvider:
    """personal-outlook mechanics — the only place mail.js / the Graph id scheme appears."""
    name = "personal-outlook"

    def __init__(self):
        self.mailjs = self._find_mail_js()

    @staticmethod
    def _find_mail_js():
        d = SCRIPT_DIR
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        if d:
            cand = os.path.join(d, "ms-graph", "skills", "ms-graph", "scripts", "mail.js")
            if os.path.exists(cand):
                return cand
        raise SystemExit("Could not locate ms-graph mail.js for personal-outlook.")

    def enumerate(self, limit):
        res = run_node([self.mailjs, "--list-inbox", "--json", f"--top={limit}"])
        if res.returncode != 0:
            raise SystemExit(f"personal-outlook enumerate failed (auth?): {res.stderr.strip()[:300]}")
        return json.loads(res.stdout or "[]")

    def stable_id(self, item):
        recv = (item.get("received") or "")[:16].replace("-", "").replace("T", "-").replace(":", "")[:13]
        sender = slug((item.get("fromAddress") or item.get("from") or "").split("@")[0])
        subj3 = slug("-".join((item.get("subject") or "").split()[:3]))
        return f"personal-outlook-{recv}-{sender}-{subj3}".strip("-")[:64]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        email_file = os.path.join(items_dir, f"{iid}.email.md")
        show = run_node([self.mailjs, f"--show={item['id']}"])
        body = show.stdout if show.returncode == 0 else "(could not load body)"
        with open(email_file, "w", encoding="utf-8") as f:
            f.write(f"# {item.get('subject')}\n\nFrom: {item.get('from')}\nReceived: {item.get('received')}\n"
                    f"Link: {item.get('webLink')}\nMessageId: {item['id']}\n\n---\n\n{body}\n")
        record = {
            "id": iid, "source": self.name, "triage": item["_bucket"], "kind": item.get("_kind"),
            "from": item.get("from"), "subject": item.get("subject"), "received": item.get("received"),
            "snippet": item.get("preview"), "url": item.get("webLink"), "messageId": item["id"],
            "emailFile": email_file, "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file


ADAPTERS = {PersonalOutlookProvider.name: PersonalOutlookProvider}


def load_providers(cfg):
    """Instantiate an adapter for each enabled provider we have code for; note the rest."""
    providers = []
    for name in cfg["providers"]:
        if name in ADAPTERS:
            providers.append(ADAPTERS[name]())
        else:
            print(f"(skipping provider '{name}': no poller adapter yet)")
    return providers


# ---------------------------------------------------------------------------- triage (the AI step)

TRIAGE_INSTRUCTIONS = (
    "You are the drainer poller's triage step. Classify each item per the rubric below, applied with "
    "the world-knowledge below. For EACH item decide its bucket; for needs-you also give "
    "kind = reply | work | work-then-reply (else null). Return ONLY a JSON array, one object per input "
    'id: [{"id": "...", "bucket": "needs-you|fyi|junk", "kind": "reply|work|work-then-reply|null", '
    '"reason": "<short>"}] — no prose, no code fence.'
)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def triage(items, repo, local_dir):
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
    return {v["id"]: v for v in json.loads(m.group(0))}


# ---------------------------------------------------------------------------- dispatch

def spawn_worker(iid, json_file, repo, runtime_dir):
    seeds = os.path.join(runtime_dir, "seeds")
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

    for provider in providers:
        new, total, seen = collect_new(provider, cfg)
        if not new:
            print(f"{provider.name}: {total} enumerated, 0 new. Nothing to dispatch.")
            continue

        verdicts = triage(new, repo, cfg["local_dir"])
        for it in new:
            v = verdicts.get(it["_id"], {"bucket": "needs-you", "kind": "reply"})  # unjudged -> act (fail-safe)
            it["_bucket"], it["_kind"] = v.get("bucket", "needs-you"), v.get("kind")
        counts = {b: sum(1 for it in new if it["_bucket"] == b) for b in ("needs-you", "fyi", "junk")}
        oc = open_count(seen)

        if args.dry_run:
            print(f"DRY-RUN - {provider.name}: {len(new)} new of {total} | "
                  f"{counts['needs-you']} needs-you, {counts['fyi']} fyi, {counts['junk']} junk")
            for it in new:
                held = it["_bucket"] == "needs-you" and oc >= cfg["max_open_tabs"]
                if it["_bucket"] == "needs-you" and not held:
                    oc += 1
                action = ("HOLD (at cap)" if held else "spawn worker") if it["_bucket"] == "needs-you" else "queue -> digest"
                print(f"  [{it['_bucket']:9}] {it['_id']}  ->  {action}\n"
                      f"      {it.get('from')} | {it.get('subject')}")
            continue

        dispatched, held, queued = 0, 0, 0
        for it in new:
            iid = it["_id"]
            if it["_bucket"] == "needs-you":
                if oc >= cfg["max_open_tabs"]:
                    held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
                    continue
                json_file = provider.capture(it, iid, cfg["runtime_dir"])
                spawn_worker(iid, json_file, repo, cfg["runtime_dir"])
                seen_state("record", cfg["runtime_dir"], provider.name, iid, "needs-you")
                oc += 1
                dispatched += 1
            else:
                json_file = provider.capture(it, iid, cfg["runtime_dir"])
                seen_state("queue-add", cfg["runtime_dir"], provider.name, iid, json_file)
                seen_state("record", cfg["runtime_dir"], provider.name, iid, it["_bucket"])
                queued += 1
        print(f"{provider.name}: dispatched {dispatched} worker tab(s), queued {queued} for digest, "
              f"held {held} at cap. Poller never clears.")


if __name__ == "__main__":
    main()
