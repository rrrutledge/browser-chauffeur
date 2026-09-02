"""physical-task poller adapter — a dedicated Outlook calendar of physical-world to-dos, drained
through the Microsoft Graph API via the ms-graph skill's calendar.js.

All physical-task mechanics live HERE, alongside the prose contract in
`physical-task-provider.md`: locating calendar.js, the due/gap ENUMERATE, the id scheme (the raw
Graph event/occurrence id — stable until CLEAR deletes it), and the captured item shape. The poller
(`scripts/run-poller.py`) loads this adapter dynamically and drives it through the `ProviderBase`
interface.

The model: a task's placement on the dedicated calendar IS its due date (mirrors Trello's Start —
"now-or-earlier is startable"), and nothing here ever moves it, so an undone task just keeps coming
back until CLEAR deletes it (done) or moves it to a later day (deferred). What's unique to this
source is a SECOND gate on top of "due": a physical task also needs a live free gap — computed fresh
every cycle — of at least its own duration before Russell's next real (non-solo) calendar commitment,
because unlike every other source, nobody but Russell can do the actual work.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, run_node, slug  # noqa: E402


class Provider(ProviderBase):
    name = "physical-task"

    def __init__(self):
        self.calendarjs = self._find_calendar_js()
        self.calendar = "Physical Tasks"
        self.lookahead_hours = 2
        self.buffer_minutes = 20
        self.exclude = []

    @staticmethod
    def _find_calendar_js():
        """Locate ms-graph's calendar.js across both the dev-repo and installed-plugin-cache layouts
        — same search shape as outlook-graph-adapter's `_find_mail_js`."""
        d = os.path.dirname(os.path.abspath(__file__))
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        if d:
            sibling = os.path.join(d, "ms-graph", "skills", "ms-graph", "scripts", "calendar.js")
            if os.path.exists(sibling):
                return sibling
            matches = glob.glob(os.path.join(d, "**", "ms-graph", "**", "scripts", "calendar.js"),
                                recursive=True)
            if matches:
                return sorted(matches)[-1]
        raise ProviderError("Could not locate ms-graph calendar.js for physical-task.", kind="config")

    # --------------------------------------------------------------- config
    def configure(self, cfg):
        """`providers.physical-task` in drainer.local.md: `calendar` (default "Physical Tasks"),
        `lookahead_hours` (default 2 — how far ahead the gap check looks for the next real
        commitment; short on purpose, since no task should ever be sized past an hour — see
        CAPTURE's duration note), `buffer_minutes` (default 20 — added on top of a task's own
        duration before it counts as eligible, covering the lag between a gap being detected and
        Russell actually opening the worker tab), `exclude` (calendar names to leave out of the gap
        check, e.g. a read-only subscription). Called by the poller after construction; harmless
        with no block at all."""
        block = self._block(cfg.get("repo"))
        self.calendar = self._str_knob(block, "calendar") or self.calendar
        self.lookahead_hours = self._int_knob(block, "lookahead_hours", self.lookahead_hours)
        self.buffer_minutes = self._int_knob(block, "buffer_minutes", self.buffer_minutes)
        self.exclude = self._list_knob(block, "exclude")

    @staticmethod
    def _block(repo):
        if not repo:
            return ""
        try:
            with open(os.path.join(repo, ".claude", "drainer.local.md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        out, in_block = [], False
        for line in text.splitlines():
            if re.match(r"^  physical-task\s*:\s*$", line):
                in_block = True
                continue
            if in_block:
                if re.match(r"^  \S", line) or re.match(r"^\S", line):
                    break
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _int_knob(block, key, default):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(\d+)\s*(?:#.*)?$", block, re.MULTILINE)
        return int(m.group(1)) if m else default

    @staticmethod
    def _str_knob(block, key):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", block, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else None

    @staticmethod
    def _list_knob(block, key):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*\[(.*?)\]\s*$", block, re.MULTILINE)
        if not m or not m.group(1).strip():
            return []
        return [x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()]

    # --------------------------------------------------------------- reads
    def _due_tasks(self):
        """Every due (start date today-or-earlier) task on the configured calendar, regardless of
        current gap — the full candidate set. Raises ProviderError on an auth/API failure."""
        res = run_node([self.calendarjs, "--list-due-tasks", f"--calendar={self.calendar}", "--json"])
        if res.returncode != 0:
            raise ProviderError(f"physical-task enumerate failed (auth?): {res.stderr.strip()[:300]}",
                                kind="auth")
        return json.loads(res.stdout or "[]")

    def _gap_minutes(self):
        args = [self.calendarjs, "--gap-minutes", "--json", f"--lookahead-hours={self.lookahead_hours}"]
        if self.exclude:
            args.append(f"--exclude={','.join(self.exclude)}")
        res = run_node(args)
        if res.returncode != 0:
            raise ProviderError(f"physical-task gap check failed: {res.stderr.strip()[:300]}", kind="auth")
        return json.loads(res.stdout or "{}").get("minutes", 0)

    def enumerate(self, limit):
        due = self._due_tasks()
        if not due:
            return []
        gap = self._gap_minutes()
        # `buffer_minutes` covers the lag between a gap being detected here and Russell actually
        # opening the worker tab (a tab budget it has to wait for, or just not being the tab he's
        # on right now) — a task only counts as fitting once its own duration PLUS that buffer is
        # covered, not just its bare duration.
        eligible = [t for t in due if t["minutes"] + self.buffer_minutes <= gap]
        # Longest-fitting-task first: a big gap is wasted on a short task when a longer one also
        # fits, so sort descending by duration before the poller's cross-source dispatch order
        # (which otherwise ties same-priority-band items and falls back to insertion order) picks
        # one. See `still_in_inbox_ids` — nothing here depends on this order beyond that tie-break.
        eligible.sort(key=lambda t: -t["minutes"])
        return eligible[:limit]

    def still_in_inbox_ids(self):
        """Reconcile's analog of "still in the inbox": every currently-due task, gap or no gap. A
        task the poller dispatched whose tab later closed without a CLEAR is still due (its event
        wasn't deleted) — dropping its seen key here lets it dispatch again next time a real gap
        opens, instead of being silently forgotten for good."""
        try:
            return {t["id"] for t in self._due_tasks()}
        except ProviderError:
            return None

    def stable_id(self, item):
        # Keyed on the underlying Graph event/occurrence id, which stays constant for this task's
        # whole undone lifetime (it is never recreated or re-stamped) — unlike email or Trello, no
        # date needs to be baked into the id: CLEAR deletes the id itself, which is what stops it
        # from ever being enumerated again.
        return f"{self.name}-{slug(item['subject'])}-{item['id'][-10:]}"

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        record = {
            "id": iid, "source": self.name, "triage": item["_bucket"], "kind": item.get("_kind"),
            "subject": item["subject"], "date": item["date"], "minutes": item["minutes"],
            "isRecurring": item["isRecurring"], "calendar": self.calendar,
            "eventId": item["id"], "url": item.get("webLink"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
