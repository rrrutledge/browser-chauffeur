"""zoom poller adapter — Zoom AI Companion meeting summaries via this project's zoom-meeting-notes-rest.js.

All Zoom mechanics + auth live in the personal-ai-pod project's `scripts/zoom-meeting-notes-rest.js`
(REST calls, the OAuth token read/refresh, the template/instance walk, the next_steps filter). This
adapter is thin, exactly like `gmail-adapter.py` around `gmail.js`: it shells to that script's
`--drainer-list --json` mode (via `run_node`, cwd = the project repo so the script's relative
`.tmp/zoom-tokens.json` resolves), then computes stable ids and writes the captured item files.

**Fan-out without a ProviderBase change.** A Zoom meeting summary is naturally *1 meeting → N action
items assigned to Russell + 1 recap*. The poller loop is one-candidate → one-stable_id → one worker tab,
so the fan-out happens in `enumerate`: the node script emits **one candidate per Russell action item**
(recap folded into each for context) **plus one recap candidate** for the meeting as a whole. This is the
same shape as the trello adapter turning one board into many card-items — `capture()` still writes exactly
one `<iid>.json`, so no `ProviderBase` extension is needed.

Implements `../engine/provider.md`; classify by `../engine/triage.md`. Prose contract:
`zoom-provider.md`. id prefix: `zoom-`; body file: `<id>.zoom.md`.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

# scripts/ is on sys.path (the poller inserts it); fall back to a relative add when run standalone.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, run_node, slug  # noqa: E402


def _hash(text, n=6):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:n]


class Provider(ProviderBase):
    name = "zoom"

    def __init__(self):
        self.repo = None
        self.script = None
        self.runtime_dir = None
        # Defaults; overridden by configure() from the providers.zoom block in drainer.local.md.
        self.lookback_hours = 48
        self.cooldown_minutes = 30      # a summary is "final" only once it's been unmodified this long
        self.poll_interval_minutes = 20  # self-throttle: skip the (heavy) template walk between cycles

    # --------------------------------------------------------------- config
    def configure(self, cfg):
        """Learn the project repo (where zoom-meeting-notes-rest.js + .tmp/zoom-tokens.json live), the
        runtime dir (for the self-throttle marker), and the optional zoom knobs. Called by the poller
        after construction."""
        self.repo = cfg.get("repo")
        self.runtime_dir = cfg.get("runtime_dir")
        if self.repo:
            self.script = os.path.join(self.repo, "scripts", "zoom-meeting-notes-rest.js")
            block = self._zoom_block(self.repo)
            self.lookback_hours = self._int_knob(block, "lookback_hours", self.lookback_hours)
            self.cooldown_minutes = self._int_knob(block, "cooldown_minutes", self.cooldown_minutes)
            self.poll_interval_minutes = self._int_knob(
                block, "poll_interval_minutes", self.poll_interval_minutes)

    @staticmethod
    def _zoom_block(repo):
        """Return the lines under `  zoom:` in drainer.local.md (up to the next 2-space provider key)."""
        try:
            with open(os.path.join(repo, ".claude", "drainer.local.md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        out, in_block = [], False
        for line in text.splitlines():
            if re.match(r"^  zoom\s*:\s*$", line):
                in_block = True
                continue
            if in_block:
                if re.match(r"^  \S", line) or re.match(r"^\S", line):
                    break
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _int_knob(block, key, default):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(\d+)\s*$", block, re.MULTILINE)
        return int(m.group(1)) if m else default

    # --------------------------------------------------------------- self-throttle
    def _throttle_path(self):
        return os.path.join(self.runtime_dir, "zoom-poll-state.json") if self.runtime_dir else None

    def _throttled(self):
        """True if the last run was within poll_interval_minutes — the template/instance walk is heavy
        (dozens of API calls), so between throttle windows we skip it and return no candidates. Nothing is
        lost: seen-state dedups and the cooldown gate means a just-finished meeting isn't ready yet anyway.
        Fail-safe: an unreadable/missing marker never throttles."""
        p = self._throttle_path()
        if not p:
            return False
        try:
            with open(p, encoding="utf-8") as f:
                last = datetime.fromisoformat(json.load(f)["last_run"])
        except (OSError, ValueError, KeyError):
            return False
        age_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
        return age_min < self.poll_interval_minutes

    def _mark_run(self):
        p = self._throttle_path()
        if not p:
            return
        os.makedirs(self.runtime_dir, exist_ok=True)
        tmp = f"{p}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)
        os.replace(tmp, p)

    # --------------------------------------------------------------- the ProviderBase contract
    def enumerate(self, limit):
        if not self.script or not os.path.exists(self.script):
            raise ProviderError(
                f"zoom: could not find zoom-meeting-notes-rest.js at {self.script!r} "
                f"(repo={self.repo!r}).", kind="config")
        if self._throttled():
            return []
        res = run_node(
            [self.script, "--drainer-list", f"--lookback-hours={self.lookback_hours}",
             f"--cooldown-minutes={self.cooldown_minutes}"],
            cwd=self.repo)
        if res.returncode != 0:
            # The node script surfaces token/OAuth failures on stderr; treat as transient/self-heals.
            raise ProviderError(f"zoom enumerate failed (auth/API?): {res.stderr.strip()[:300]}",
                                kind="auth")
        try:
            data = json.loads(res.stdout or "{}")
        except ValueError:
            raise ProviderError(f"zoom enumerate returned non-JSON: {res.stdout[:200]!r}", kind="config")
        items = [self._to_item(c) for c in data.get("candidates", [])]
        # Newest meeting first (matches the poller's global newest-first ordering).
        items.sort(key=lambda it: it.get("received") or "", reverse=True)
        self._mark_run()
        return items[:limit]

    @staticmethod
    def _to_item(c):
        """Map a node candidate into the poller item shape (triage payload fields + the raw fields
        capture needs). Carries the full candidate so capture writes a rich body with the recap folded in."""
        topic = c.get("topic") or "Zoom meeting"
        recap = c.get("recap") or ""
        if c.get("kind") == "action-item":
            step = c.get("stepText") or ""
            preview = (f"Zoom action item assigned to Russell, from the meeting \"{topic}\".\n"
                       f"Action: {step}\n\nMeeting recap (context): {recap[:600]}")
            subject = step[:120]
        else:  # recap wrapper — the "meeting happened" fact; nothing is asked of Russell by the recap
            n = len(c.get("allNextSteps") or [])
            preview = (f"Recap of the Zoom meeting \"{topic}\" (informational — nothing is asked of "
                       f"Russell by the recap itself; his action items from this meeting are tracked as "
                       f"their own separate drainer items). Recap: {recap[:800]}\n\nMeeting had {n} next "
                       f"step(s) total.")
            subject = f"Meeting recap: {topic}"
        item = dict(c)
        item.update({"from": topic, "subject": subject, "received": c.get("meetingStart"),
                     "preview": preview})
        return item

    def stable_id(self, item):
        # meeting_uuid is unique per occurrence (a recurring meeting's occurrences each get their own),
        # so it anchors identity; the action-item text is hashed on top (stepId lives only in the summary
        # HTML and can change as the AI refines the summary, so it's a convenience link, never the id).
        topic = slug(item.get("topic"), 20)
        mh = _hash(item.get("meetingId"))
        if item.get("kind") == "action-item":
            return f"{self.name}-{topic}-{mh}-{_hash(item.get('stepText'))}".strip("-")[:72]
        return f"{self.name}-{topic}-{mh}-recap".strip("-")[:72]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        body_file = os.path.join(items_dir, f"{iid}.zoom.md")
        is_action = item.get("kind") == "action-item"
        url = (item.get("taskUrl") or item.get("docUrl")) if is_action else item.get("docUrl")

        steps = "\n".join(f"- {s}" for s in (item.get("allNextSteps") or [])) or "(none)"
        details = "\n\n".join(
            f"### {d.get('label', '')}\n{d.get('summary', '')}" for d in (item.get("summaryDetails") or [])
        ) or "(none)"
        action_block = f"## This action item (assigned to Russell)\n\n{item.get('stepText')}\n\n" if is_action else ""
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(
                f"# {item.get('subject')}\n\n"
                f"Meeting: {item.get('topic')}\n"
                f"When: {item.get('meetingStart')} to {item.get('meetingEnd') or '?'}\n"
                f"Summary doc: {item.get('docUrl') or '(none)'}\n"
                f"Task link: {url or '(none)'}\n"
                f"MeetingId: {item.get('meetingId')}\n"
                f"StepId: {item.get('stepId') or '(none)'}\n\n"
                f"{action_block}"
                f"## Meeting recap\n\n{item.get('recap') or '(none)'}\n\n"
                f"## All next steps (whole meeting)\n\n{steps}\n\n"
                f"## Details\n\n{details}\n")

        record = {
            "id": iid, "source": self.name, "triage": item.get("_bucket", "needs-you"),
            "kind": item.get("_kind"), "zoomKind": item.get("kind"),
            "from": item.get("from"), "subject": item.get("subject"), "received": item.get("received"),
            "snippet": item.get("preview"), "url": url,
            "meetingId": item.get("meetingId"), "meetingTopic": item.get("topic"),
            "stepId": item.get("stepId"), "stepText": item.get("stepText"),
            "bodyFile": body_file, "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
