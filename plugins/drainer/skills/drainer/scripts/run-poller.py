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
import time
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROVIDERS_DIR = os.path.join(SKILL_DIR, "providers")
sys.path.insert(0, SCRIPT_DIR)
import presence  # noqa: E402  (sibling module)
from provider_base import run_node, NO_WINDOW, ProviderError, spawn_tab, spawn_silent  # noqa: E402  (subprocess helper + typed provider failure)
from drainer_config import read_config, find_provider_file  # noqa: E402  (shared .claude/drainer.local.md reader + provider resolution)

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
        path = find_provider_file(PROVIDERS_DIR, cfg["local_dir"], name, "-adapter.py")
        if not path:
            print(f"(skipping provider '{name}': no poller adapter at providers/{name}-adapter.py "
                  f"or {cfg['local_dir']}/providers/{name}-adapter.py)")
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
    "the world-knowledge below. For EACH item decide its bucket; for needs-you (and auto-handle) also "
    "give kind = reply | work | work-then-reply (else null) and complexity = simple | complex (simple = "
    "a quick reply or a trivial action; complex = multi-step work, research, code, or a delicate / "
    "high-stakes message — these get a stronger model). Use bucket = auto-handle ONLY when a provider "
    "AUTO-HANDLE rule (in the world-knowledge / provider docs) plainly matches — a standing decision with "
    "no judgment left; when in doubt use needs-you. Return ONLY a JSON array, one object per input "
    'id: [{"id": "...", "bucket": "needs-you|auto-handle|fyi|junk", '
    '"kind": "reply|work|work-then-reply|null", '
    '"complexity": "simple|complex", "reason": "<short>"}] — no prose, no code fence.'
)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _auto_handle_rules(providers_by_name, local_dir):
    """Concatenate each enabled provider's AUTO-HANDLE section so the triage model can recognize an
    auto-handle item. The rules live in providers/<name>-provider.md (worker-facing), but classification
    happens here at triage time, so the relevant sections are surfaced to the model. A provider with no
    AUTO-HANDLE section contributes nothing. New providers add rules just by writing the section."""
    out = []
    for name in sorted(providers_by_name):
        doc = _read(find_provider_file(PROVIDERS_DIR, local_dir, name, "-provider.md") or "")
        m = re.search(r"^##\s+AUTO-HANDLE\b.*?(?=^##\s|\Z)", doc, re.DOTALL | re.MULTILINE)
        if m:
            out.append(f"### {name}\n{m.group(0).strip()}")
    return "\n\n".join(out)


def triage(items, repo, local_dir, model, providers_by_name):
    claude = shutil.which("claude") or "claude"
    rubric = _read(os.path.join(SCRIPT_DIR, "..", "engine", "triage.md"))  # embed -> self-contained
    context = _read(os.path.join(local_dir, "context.md"))
    auto_rules = _auto_handle_rules(providers_by_name, local_dir)

    def preview(it):
        # The owning adapter supplies the text triage sees: its `triage_text` returns the new message
        # body (quote-stripped) rather than just the subject. Adapters whose enumerate carries no preview
        # (gmail) override it to fetch the body for these new items; the default just returns `preview`.
        p = providers_by_name.get(it["_source"])
        return p.triage_text(it) if p else (it.get("preview") or "")

    payload = [{"id": it["_id"], "source": it["_source"], "from": it.get("from"),
                "subject": it.get("subject"), "received": it.get("received"),
                "isRead": it.get("isRead"), "preview": preview(it)} for it in items]
    auto_block = (
        f"## Auto-handle rules (per provider — use bucket=auto-handle only when one plainly matches)\n"
        f"{auto_rules}\n\n" if auto_rules else ""
    )
    prompt = (
        f"{TRIAGE_INSTRUCTIONS}\n\n## Rubric (engine/triage.md)\n{rubric}\n\n"
        f"{auto_block}"
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
    labels = {"outlook-graph": "Outlook", "gmail": "Gmail", "slack": "Slack", "trello": "Trello",
              "zoom": "Zoom"}
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
    since that's what matters at a glance; the source is incidental and is NOT forced into the title.

    MUST stay free of characters that break PowerShell 5.1 native-arg passing when launch-session.ps1
    hands the seed to `claude`: an embedded double quote (or `;`) truncates the ENTIRE seed mid-word,
    silently dropping the 'Read the file …' pointer so the worker never learns what item it's on. So the
    subject is NOT wrapped in quotes and any quotes/semicolons/newlines in it are stripped. '' when there's
    nothing to say."""
    _label, subject, who = _item_bits(json_file)

    def safe(x):  # strip seed-breaking chars (quotes, semicolons) and collapse whitespace to one line
        return re.sub(r"\s+", " ", re.sub(r'["“”;]', "", x or "")).strip()

    subject, who = safe(subject), safe(who)
    if not subject and not who:
        return ""
    # Produce a terse title-like string: Claude names the tab off its first message, so the
    # shorter and more content-forward this is, the better the tab name. Skip `who` when it's
    # already in the subject (e.g. "DM from John" doesn't need "from John" appended again).
    if who and subject and who.lower() not in subject.lower():
        return f"{subject} from {who}"
    return subject or f"from {who}"


def _precheck_newer_id(teamsjs, conv_id, first_unread_id, node_kw):
    """Return the earliest message id numerically greater than first_unread_id, or None.

    Called before spawning the mark-read worker so boundary-guard data is pre-computed
    without requiring the LLM to do REST discovery. Returns None if first_unread_id is
    absent, the REST call fails, or no newer messages exist.
    """
    if not first_unread_id:
        return None
    res = run_node([teamsjs, "messages", conv_id, "--top", "20"], **node_kw)
    if res.returncode != 0:
        return None
    try:
        msgs = json.loads(res.stdout or "[]")
    except ValueError:
        return None
    newer = []
    for m in msgs:
        try:
            if int(m.get("id", "0")) > int(first_unread_id):
                newer.append(m["id"])
        except (ValueError, TypeError):
            pass
    return min(newer, key=lambda x: int(x)) if newer else None


def _spawn_teams_mark_read(items, teams_provider, repo, runtime_dir, worker_model):
    """Spawn a single silent batch worker tab that marks all Teams fyi/junk items read.

    The boundary-check (REST fetch + compare against firstUnreadMessageId) is done here
    in Python before spawning, so the worker only has to open each conversation in Teams
    web via browser-chauffeur and then run a pre-computed mark-unread call if needed.
    Items are already recorded in seen-state before this is called.
    """
    seeds = os.path.join(runtime_dir, "seeds")
    os.makedirs(seeds, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prompt_file = os.path.join(seeds, f"teams-mark-read-{ts}.prompt.txt")
    teamsjs = teams_provider.teamsjs
    node_kw = teams_provider._node_kw()
    convs = []
    for it in items:
        conv_id = it.get("convId") or it.get("messageId") or it["_id"]
        mark_unread_id = _precheck_newer_id(
            teamsjs, conv_id, it.get("firstUnreadMessageId"), node_kw
        )
        convs.append({
            "convId": conv_id,
            "label": it.get("label") or it.get("subject") or it["_id"],
            "markUnreadId": mark_unread_id,
        })
    convs_json = json.dumps(convs, indent=2)
    n = len(items)
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(
            f"You are a drainer batch worker marking {n} Teams conversation(s) read. "
            "Read `~/.claude/CLAUDE.md` first.\n\n"
            "For EACH conversation below: use browser-chauffeur to open Teams web "
            "(`https://teams.cloud.microsoft/v2/?ctx=chat`) and click the conversation "
            "row matching `label` — this flips isRead. Then, if `markUnreadId` is not null, "
            f"run: `node \"{teamsjs}\" mark-unread --conversation-id <convId> "
            "--message-id <markUnreadId>` — this re-flags any message that arrived after "
            "the poller started so the next cycle picks it up. No REST discovery needed; "
            "the ids are already computed.\n\n"
            f"Conversations:\n{convs_json}\n\n"
            f"When done, write `{prompt_file[:-10]}done` to signal completion. "
            "No draft, no digest entry, no user interaction — this is a silent background task."
        )
    spawn_silent(prompt_file, worker_model, repo)


def spawn_worker(iid, json_file, repo, runtime_dir, worker_model, local_dir):
    seeds = os.path.join(runtime_dir, "seeds")
    os.makedirs(seeds, exist_ok=True)
    prompt_file = os.path.join(seeds, f"{iid}.prompt.txt")
    worker_core = os.path.join(SKILL_DIR, "engine", "worker-core.md")
    local_providers = os.path.join(local_dir, "providers")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(
            "You are a drainer worker handling ONE item. Read `~/.claude/CLAUDE.md`, then follow the "
            f"drainer worker procedure at `{worker_core}` for the single captured item at\n"
            f"`{json_file}`.\nThe item's `source` field names the provider — read its "
            f"`<source>-provider.md` (in `{PROVIDERS_DIR}`, or `{local_providers}` for a machine-local "
            "provider) for its CLEAR and DRAFT-MODE and use them. "
            "Draft-only: never send or post. When you judge the item's work complete, present your "
            "result to the user and write "
            f"`{json_file[:-5]}.done` proactively in that same turn — write it as soon as you think "
            "you're done, without waiting for the user to acknowledge. Freeing the concurrency slot "
            "early costs nothing: this session stays open after .done, so if the user replies with new "
            "direction (a changed decision, a draft rewrite, more work) you just keep going and update "
            "the source again as needed — re-writing .done later is harmless. (Items you resolve "
            "WITHOUT surfacing to the user — junk routed to the digest, or a situational no-op close — "
            "get .done immediately too.)\n"
            "If you opened any browser tabs, close them once you and the user are truly finished with the "
            "item — later than .done: after the user has done their human step (sent the draft, submitted "
            "the form) and you've done any follow-up. Then invoke browser-chauffeur to run "
            "`chauffeur.py --close-owned`, which closes only this session's browser tabs (never the "
            "user's, never another session's). Keep the session's own PowerShell tab open for the user.\n"
            "If the item's `triage` field is `auto-handle`, follow worker-core's auto-handle BRANCH "
            "instead: execute the standing rule autonomously, CLEAR the source, queue a digest entry, "
            "and write .done IMMEDIATELY — no presentation, no wait. Then CLOSE UP as your very last step: "
            "first close any browser tabs you opened with browser-chauffeur's `chauffeur.py "
            "--close-owned`, then via the Bash tool run "
            f"`python \"{os.path.join(SCRIPT_DIR, 'close-session.py')}\"` — it fires the SessionEnd hook "
            "event (so the live-session registry drops this session instead of listing it as "
            "crash-interrupted) and then terminates this session and closes its tab, so a self-resolved "
            "item never lingers as a finished tab you must check. Never raw-`taskkill` the host PID — a "
            "force-killed session dies before SessionEnd can fire. "
            "Do this ONLY for auto-handle — needs-you items always stay open and wait for the user.\n"
        )
    # A one-line summary leads the seed so the worker's Claude session self-titles the tab descriptively
    # while keeping its attention star (the launcher prepends this; see launch-session.ps1 -SummaryFile).
    summary_file = os.path.join(seeds, f"{iid}.summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(_worker_summary(json_file))
    spawn_cmd = os.path.join(SCRIPT_DIR, "spawn-tab.cmd")
    spawn_tab([spawn_cmd, _worker_title(iid, json_file), repo, prompt_file, worker_model, summary_file],
              cwd=repo)


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


def live_session_ids():
    """The set of session guids that currently have a running `claude --session-id <guid>` process.
    Worker tabs launch claude with --session-id on the command line (launch-session.ps1), so a tab that
    was closed (or whose claude exited) drops out of this set. That distinguishes 'tab closed' (process
    gone — never going to finish) from 'parked, waiting for Russell' (process alive, just idle), which a
    transcript-activity check cannot. One CIM query per cycle.

    Returns None if the scan can't be run/parsed — the caller then SKIPS the liveness fast-path this cycle
    (the time-based backstop still applies), so an inability to see processes never reaps a live tab."""
    ps = (r"Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'session-id' } | "
          r"ForEach-Object { $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30,
                             creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return set(re.findall(r"session-id\s+([0-9a-fA-F-]{36})", out))


def total_claude_tabs():
    """Count of every running claude.exe process system-wide — drainer worker tabs, the drainer
    itself, and any tab Russell opened by hand. The real constraint on dispatch speed is total open
    Claude Code tabs competing for his attention, not how many the drainer itself has dispatched, so
    target_open_tabs is checked against this instead of the drainer's own seen-state bookkeeping.

    Returns None if the scan can't be run/parsed — the caller then SKIPS the tab-count throttle this
    cycle (fail-safe: an inability to see processes never blocks dispatch, mirroring live_session_ids)."""
    ps = "(Get-Process -Name claude -ErrorAction SilentlyContinue | Measure-Object).Count"
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30,
                             creationflags=NO_WINDOW).stdout
        return int(out.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _session_guid(runtime_dir, iid):
    """(guid, mtime) from the worker's seeds/<id>.prompt.txt.session, or (None, None). mtime ~ launch
    time, used to give a freshly-launched tab a grace period before liveness can reap it."""
    p = os.path.join(runtime_dir, "seeds", f"{iid}.prompt.txt.session")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip(), os.path.getmtime(p)
    except OSError:
        return None, None


def reconcile_orphans(runtime_dir, cfg):
    """Self-heal orphaned worker tabs that would hold a global cap slot forever. A worker launches
    `claude --session-id <guid>` (guid recorded in seeds/<id>.prompt.txt.session); if that process is gone
    the tab was CLOSED and can never write <id>.done. Re-queue such an item — drop its seen key so the
    next enumerate re-dispatches a fresh tab, freeing the slot.

    Recovery is purely LIVENESS-based: a tab whose process is still running is left alone no matter how
    long it's been open — it's either being worked or parked waiting for the user, both of which resolve
    on their own. So there is no time-based timeout; closed-tab detection is the whole signal. A grace
    window (orphan_grace_minutes) keeps a just-launched tab — whose process / .session file may not be up
    yet — from being misread as dead. No retry cap: a finished item resolves by the worker writing .done.
    Sibling of reconcile_done — same place in the cycle, the other half of slot bookkeeping."""
    live = live_session_ids()
    if live is None:
        return 0  # can't see processes this cycle -> reap nothing (fail-safe); recover next cycle instead
    try:  # stale-list with 0 hours returns EVERY dispatched needs-you item (with ages), the full slate
        dispatched = json.loads(seen_state("stale-list", runtime_dir, "0").stdout or "[]")
    except ValueError:
        dispatched = []
    grace_s = cfg["orphan_grace_minutes"] * 60
    now = time.time()
    requeued = 0
    for r in dispatched:
        iid, source = r.get("id"), r.get("source")
        if not iid or not source:
            continue
        guid, smtime = _session_guid(runtime_dir, iid)
        if guid and guid in live:
            continue  # process alive -> being worked or parked for the user; never reap an open tab
        # Not alive (process exited, or the launch left no trackable session). Only reap once it's clearly
        # past the launch grace, so a tab still spinning up isn't killed. Grace is measured from the
        # .session file's mtime (launch time) when present, else from the item's dispatch age.
        age_h = r.get("ageHours")
        launched_ago = (now - smtime) if smtime is not None else (age_h * 3600 if age_h is not None else None)
        if launched_ago is None or launched_ago >= grace_s:
            seen_state("requeue", runtime_dir, source, iid)
            print(f"orphan {iid} ({source}): worker tab closed -> re-queued for a fresh tab.")
            requeued += 1
    if requeued:
        print(f"orphan recovery: {requeued} re-queued.")
    return requeued


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
    if not args.dry_run:
        reconcile_orphans(cfg["runtime_dir"], cfg)  # self-heal closed worker tabs (mutates -> live cycles only)

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

    # --- deterministic pre-triage rules ---
    # (1) every active Trello card is always needs-you — see comments below for why
    # (2) junk-bucket items from outlook-graph-junk silently record as seen (already correctly filed)
    pre_triaged = []
    correctly_junked = []
    ai_triage = []
    for it in all_new:
        if it["_source"] == "trello":
            # The adapter only enumerates cards in play — due now-or-earlier, or with no due date at all.
            # A due card's moment has arrived ("the due date IS the queue"); an undated card is on the
            # board precisely because it needs a look — at minimum to give it a date — so it must not be
            # sidelined to the digest. Either way the answer is needs-you, so skip the AI call: it's a
            # tautology the model sometimes gets wrong (it mis-filed undated cards to fyi).
            it["_bucket"], it["_kind"] = "needs-you", "work"
            it["_complexity"] = "simple"
            pre_triaged.append(it)
        else:
            ai_triage.append(it)

    # --- one combined triage call over all sources (remaining items) ---
    prov = {p.name: p for p in providers}  # name -> adapter (also used below for cross-source dispatch)
    if ai_triage:
        verdicts = triage(ai_triage, repo, cfg["local_dir"], cfg["triage_model"], prov)
    else:
        verdicts = {}
    for it in ai_triage:
        v = verdicts.get(it["_id"], {"bucket": "needs-you", "kind": "reply"})  # unjudged -> act (fail-safe)
        it["_bucket"], it["_kind"] = v.get("bucket", "needs-you"), v.get("kind")
        it["_complexity"] = v.get("complexity", "simple")
    if pre_triaged:
        print(f"  {len(pre_triaged)} trello card(s) -> needs-you (deterministic, skipped AI)")

    # Split off correctly-junked items AFTER triage: outlook-graph-junk items triaged as junk are
    # already in the right place, so record them as seen with zero noise (no capture, no queue-add).
    correctly_junked = [it for it in all_new if it["_source"] == "outlook-graph-junk" and it["_bucket"] == "junk"]
    needs_and_others = [it for it in all_new if not (it["_source"] == "outlook-graph-junk" and it["_bucket"] == "junk")]

    # --- live tab count, checked against target_open_tabs (None -> scan failed, throttle skipped) ---
    live_tabs = total_claude_tabs()

    # --- split: needs-you (globally ordered), auto-handle (own worker, no cap), others (digest) ---
    # Ordering across ALL sources is by date, most-recent first: the newest email / Slack message or
    # most-recently-due card leads. Each item carries its date in `received` — an inbox message's arrival
    # time, a dated card's due date, or an undated card's creation date (the trello adapter stamps that),
    # so undated cards sort by age alongside everything else.
    needs = sorted(
        (it for it in needs_and_others if it["_bucket"] == "needs-you"),
        key=lambda it: it.get("received") or "",
        reverse=True,
    )
    # auto-handle items get a worker tab too (they need a browser to act), but the worker executes
    # autonomously and writes .done immediately — so they self-clear fast and are dispatched unconditionally,
    # never held behind the target_open_tabs throttle that gates needs-you below, letting a standing-rule
    # action run without waiting behind tabs parked for Russell's attention.
    auto = [it for it in needs_and_others if it["_bucket"] == "auto-handle"]
    others = [it for it in needs_and_others if it["_bucket"] not in ("needs-you", "auto-handle")]

    if args.dry_run:
        counts = {b: sum(1 for it in all_new if it["_bucket"] == b)
                  for b in ("needs-you", "auto-handle", "fyi", "junk")}
        total_all = sum(totals.values())
        print(f"DRY-RUN — {len(all_new)} new of {total_all} across {len(providers)} source(s) | "
              f"{counts['needs-you']} needs-you, {counts['auto-handle']} auto-handle, "
              f"{counts['fyi']} fyi, {counts['junk']} junk ({len(correctly_junked)} correctly-filed junk) | "
              f"target open tabs {cfg['target_open_tabs']}, currently open "
              f"{live_tabs if live_tabs is not None else 'unknown'}")
        if auto:
            print("  auto-handle (autonomous worker, not capped):")
            for it in auto:
                model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
                print(f"    [{it['_source']:20}] {it['_id']}  ->  spawn auto-worker [{it['_complexity']} -> {model}]\n"
                      f"        {it.get('received')} | {it.get('from')} | {it.get('subject')}")
        print("  needs-you (newest-first globally):")
        tabs = live_tabs
        for it in needs:
            held = tabs is not None and tabs >= cfg["target_open_tabs"]
            if not held and tabs is not None:
                tabs += 1
            model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
            action = "HOLD (at cap)" if held else f"spawn worker [{it['_complexity']} -> {model}]"
            print(f"    [{it['_source']:20}] {it['_id']}  ->  {action}\n"
                  f"        {it.get('received')} | {it.get('from')} | {it.get('subject')}")
        if others:
            print("  others -> digest:")
            for it in others:
                print(f"    [{it['_bucket']:9}] [{it['_source']:20}] {it['_id']}\n"
                      f"        {it.get('from')} | {it.get('subject')}")
        teams_others = [it for it in others if it["_source"] == "teams"]
        if teams_others:
            print(f"  teams mark-read batch (dry-run): {len(teams_others)} conv(s): "
                  + ", ".join(it.get("convId") or it["_id"] for it in teams_others))
        return

    dispatched, auto_dispatched, held, queued = 0, 0, 0, 0
    # auto-handle first: a worker that executes a standing rule and self-clears immediately. Not throttled
    # by target_open_tabs, recorded with its own triage so capture stamps the json and the worker takes
    # worker-core's auto-handle branch (act -> CLEAR -> queue digest -> .done now).
    for it in auto:
        provider = prov[it["_source"]]
        iid = it["_id"]
        model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        spawn_worker(iid, json_file, repo, cfg["runtime_dir"], model, cfg["local_dir"])
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "auto-handle")
        auto_dispatched += 1
    for it in needs:
        provider = prov[it["_source"]]
        iid = it["_id"]
        if live_tabs is not None and live_tabs >= cfg["target_open_tabs"]:
            held += 1  # leave UNRECORDED -> retried next cycle (fail-safe throttle)
            continue
        model = cfg["worker_model_complex"] if it["_complexity"] == "complex" else cfg["worker_model"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        spawn_worker(iid, json_file, repo, cfg["runtime_dir"], model, cfg["local_dir"])
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "needs-you")
        if live_tabs is not None:
            live_tabs += 1
        dispatched += 1
    for it in others:
        provider = prov[it["_source"]]
        iid = it["_id"]
        json_file = provider.capture(it, iid, cfg["runtime_dir"])
        seen_state("queue-add", cfg["runtime_dir"], it["_source"], iid, json_file)
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, it["_bucket"])
        queued += 1

    # Correctly-junked items from outlook-graph-junk (already in the right place) are recorded as
    # seen with NO capture and NO queue-add — they generate zero noise and never surface to the user.
    correctly_junked_count = 0
    for it in correctly_junked:
        iid = it["_id"]
        seen_state("record", cfg["runtime_dir"], it["_source"], iid, "junk")
        correctly_junked_count += 1

    teams_others = [it for it in others if it["_source"] == "teams"]
    if teams_others and prov.get("teams"):
        _spawn_teams_mark_read(teams_others, prov["teams"], repo, cfg["runtime_dir"], cfg["worker_model"])

    print(f"dispatched {dispatched} worker tab(s), {auto_dispatched} auto-handle worker(s), "
          f"queued {queued} for digest, {correctly_junked_count} correctly-filed junk (no action), "
          f"held {held} at target open tabs of {cfg['target_open_tabs']}. "
          f"Poller never clears.")


if __name__ == "__main__":
    main()
