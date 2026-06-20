"""trello poller adapter — outreach boards via the trello-outreach skill's trello_utils.py (Trello REST).

All Trello mechanics live HERE, alongside the prose contract in `trello-provider.md`: locating
trello_utils.py, reading the `providers.trello` board config out of `.claude/drainer.local.md`, the
due-date-as-queue enumerate, the `trello-<slug>-<last6>` id scheme, and the captured item shape. The
poller (`scripts/run-poller.py`) loads this adapter dynamically and drives it through the
`ProviderBase` interface — it contains no Trello specifics.

Unlike the gmail/slack/outlook adapters (which enumerate a single inbox), Trello drains several boards,
so this adapter takes a `configure(cfg)` pass from the poller to learn the repo. The board list is the
single source of truth shared with the `trello-outreach` skill: `<repo>/trello-boards.yaml` (name + id
per board). The drainer drains EVERY board in that registry. Per-drainer knobs (`skip_lists` /
`label_vocab`) stay in that repo's drainer.local.md. If no registry file is present, it falls back to a
legacy `providers.trello.boards` block in drainer.local.md.

The card's **due date IS the queue**: enumerate returns cards in active lists that are due now-or-earlier
or have no due date, oldest-due first (undated last). Credentials are TRELLO_API_KEY / TRELLO_TOKEN in
the environment (read by trello_utils.get_trello_session).
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

# scripts/ is on sys.path (the poller inserts it); fall back to a relative add when run standalone.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, slug  # noqa: E402


class Provider(ProviderBase):
    name = "trello"

    def __init__(self):
        self._utils = self._import_trello_utils()
        self._session = None
        # Defaults; overridden by configure(cfg) once the poller hands us the repo + parsed config.
        self.boards = []
        # Stored lowercased; a list is skipped if any token is a substring of its name (case-insensitive),
        # so emoji-prefixed lists like "📋 Templates" still match the plain "Templates" token.
        self.skip_lists = {"abandoned", "finished", "adopted", "templates"}
        self.channels = []
        self.features = []

    # --------------------------------------------------------------- locate the trello-outreach helper
    @staticmethod
    def _import_trello_utils():
        """Locate the trello-outreach skill's trello_utils.py across dev-repo and installed-cache layouts.

        Dev repo:   <plugins>/trello-outreach/skills/trello-outreach/scripts/trello_utils.py
        Installed:  <plugins>/cache/<marketplace>/trello-outreach/<ver>/skills/.../trello_utils.py
        Walk up to the first `plugins` dir, then try the sibling path, else glob for any trello_utils.py
        beneath it and take the highest-versioned (lexically greatest) path. Mirrors how gmail-adapter
        finds gmail.js.
        """
        d = os.path.dirname(os.path.abspath(__file__))
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        path = None
        if d:
            sibling = os.path.join(d, "trello-outreach", "skills", "trello-outreach", "scripts",
                                   "trello_utils.py")
            if os.path.exists(sibling):
                path = sibling
            else:
                matches = glob.glob(
                    os.path.join(d, "**", "trello-outreach", "**", "scripts", "trello_utils.py"),
                    recursive=True)
                if matches:
                    path = sorted(matches)[-1]
        if not path:
            raise SystemExit("Could not locate trello-outreach's trello_utils.py for the trello provider.")
        import importlib.util
        spec = importlib.util.spec_from_file_location("trello_utils", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @property
    def session(self):
        if self._session is None:
            self._session = self._utils.get_trello_session()
        return self._session

    # --------------------------------------------------------------- config (boards/skip/label vocab)
    def configure(self, cfg):
        """Learn the boards to drain + the drainer knobs from the repo.

        Boards come from the shared registry `<repo>/trello-boards.yaml` (the same file the
        trello-outreach skill reads) — the drainer drains every board in it. `skip_lists` / `label_vocab`
        are drainer-specific and stay in `.claude/drainer.local.md`'s `providers.trello` block. If the
        registry file is absent, boards fall back to a legacy `boards:` list in that same block.

        Called by the poller after construction; a no-op contract on ProviderBase means gmail/slack
        ignore it.
        """
        repo = cfg.get("repo")
        if not repo:
            return
        # Drainer knobs (skip_lists / label_vocab) — and legacy boards fallback — from drainer.local.md.
        block = ""
        try:
            with open(os.path.join(repo, ".claude", "drainer.local.md"), encoding="utf-8") as f:
                block = self._slice_trello_block(f.read())
        except OSError:
            pass
        if block:
            skip = self._parse_inline_list(block, "skip_lists")
            if skip:
                self.skip_lists = {s.lower() for s in skip}
            self.channels = self._parse_inline_list(block, "channels")
            self.features = self._parse_inline_list(block, "features")
        # Boards: the shared registry is authoritative; drainer.local.md's boards block is the fallback.
        boards = []
        try:
            with open(os.path.join(repo, "trello-boards.yaml"), encoding="utf-8") as f:
                boards = self._parse_registry(f.read())
        except OSError:
            pass
        if not boards and block:
            boards = self._parse_boards(block)
        if boards:
            self.boards = boards

    @staticmethod
    def _parse_registry(text):
        """Parse `<repo>/trello-boards.yaml` — a `boards:` list of board items, each a `- name:` at
        two-space indent with an `id:` field at four-space indent. Anchoring on those exact indents
        keeps the parse robust against deeper nested fields (per-board `purpose`, `template_cards`, …)
        without needing a full YAML library (none ships with the poller's stdlib runtime)."""
        boards, cur = [], None
        for line in text.splitlines():
            m_name = re.match(r"^  -\s*name\s*:\s*(.+?)\s*$", line)
            m_id = re.match(r"^    id\s*:\s*(.+?)\s*$", line)
            if m_name:
                if cur:
                    boards.append(cur)
                cur = {"name": m_name.group(1).strip().strip('"\'')}
            elif m_id and cur is not None and "id" not in cur:
                cur["id"] = m_id.group(1).strip().strip('"\'')
        if cur:
            boards.append(cur)
        return [b for b in boards if b.get("id")]

    @staticmethod
    def _slice_trello_block(text):
        """Return the lines under `  trello:` up to the next 2-space-indented provider key (or EOF)."""
        lines = text.splitlines()
        out, in_block = [], False
        for line in lines:
            if re.match(r"^  trello\s*:\s*$", line):
                in_block = True
                continue
            if in_block:
                # A new 2-space top-level key (sibling provider) or a non-indented line ends the block.
                if re.match(r"^  \S", line) or re.match(r"^\S", line):
                    break
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _parse_boards(block):
        """Parse the `boards:` list of `{name, id}` from the trello block."""
        boards, cur = [], None
        in_boards = False
        for line in block.splitlines():
            if re.match(r"^\s*boards\s*:\s*$", line):
                in_boards = True
                continue
            if in_boards:
                # End of the boards list: a less-indented key at the trello level (4 spaces).
                if re.match(r"^    \S", line) and not line.lstrip().startswith("- ") \
                        and not re.match(r"^\s*(name|id)\s*:", line):
                    in_boards = False
                m_name = re.match(r"^\s*-\s*name\s*:\s*(.+?)\s*$", line)
                m_id = re.match(r"^\s*id\s*:\s*(.+?)\s*$", line)
                if m_name:
                    if cur:
                        boards.append(cur)
                    cur = {"name": m_name.group(1).strip().strip('"\'')}
                elif m_id and cur is not None:
                    cur["id"] = m_id.group(1).strip().strip('"\'')
        if cur:
            boards.append(cur)
        return [b for b in boards if b.get("id")]

    @staticmethod
    def _parse_inline_list(block, key):
        """Parse an inline YAML list `key: [a, b, c]` from the block (returns [] if absent/empty)."""
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*\[(.*?)\]\s*$", block, re.MULTILINE)
        if not m:
            return []
        inner = m.group(1).strip()
        if not inner:
            return []
        return [x.strip().strip('"\'') for x in inner.split(",") if x.strip()]

    # --------------------------------------------------------------- label classification
    def _classify_labels(self, card):
        """Split a card's labels into (channelLabel, features, contacts) using the label_vocab."""
        names = [l.get("name") for l in card.get("labels", []) if l.get("name")]
        channel = next((n for n in names if n in self.channels), None)
        feats = [n for n in names if n in self.features]
        contacts = [n for n in names if n not in self.channels and n not in self.features]
        return channel, feats, contacts

    @staticmethod
    def _due_dt(due):
        if not due:
            return None
        try:
            return datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError:
            return None

    # --------------------------------------------------------------- the ProviderBase contract
    def enumerate(self, limit):
        if not self.boards:
            return []
        now = datetime.now(timezone.utc)
        items = []
        for board in self.boards:
            bid, bname = board["id"], board.get("name", board["id"])
            lists = {l["id"]: l["name"] for l in self._utils.get_board_lists(bid, self.session)}
            for card in self._utils.get_board_cards(bid, self.session):
                list_name = lists.get(card.get("idList"))
                # get_board_lists returns only OPEN lists; a card whose list isn't in that map sits on
                # an archived/closed list (still an open card, but off the board) — not active, skip it.
                if not list_name:
                    continue
                ln = list_name.lower()
                if any(tok in ln for tok in self.skip_lists):
                    continue
                due_dt = self._due_dt(card.get("due"))
                # In play: due now-or-earlier (overdue counts) OR no due date at all.
                if due_dt is not None and due_dt > now:
                    continue
                channel, feats, contacts = self._classify_labels(card)
                who = ", ".join(contacts) if contacts else bname
                items.append({
                    "cardId": card["id"],
                    "board": bname,
                    "list": list_name,
                    "name": card.get("name", ""),
                    "due": card.get("due"),
                    "url": card.get("shortUrl") or card.get("url"),
                    "desc": card.get("desc", ""),
                    "channelLabel": channel,
                    "features": feats,
                    "contacts": contacts,
                    # Triage payload fields (mirror the inbox adapters):
                    "from": who,
                    "subject": card.get("name", ""),
                    "received": card.get("due") or "(no due date)",
                    "preview": f"[{bname} / {list_name}] {(card.get('desc') or '').strip()[:200]}",
                    "_due_sort": due_dt,
                })
        # Oldest-due first; undated last (None sorts after any real datetime).
        items.sort(key=lambda it: (it["_due_sort"] is None, it["_due_sort"] or now))
        return items[:limit]

    def stable_id(self, item):
        # The due date is PART OF the identity, not just a field: a card recurs every follow-up cycle
        # (CLEAR bumps its due date out), and seen-state's `clear` leaves a drained id in seen.json
        # forever (status=cleared, key persists) while dedup is pure key-presence. So a stable
        # per-card id would be marked seen on the first drain and never resurface when the next due
        # date arrives. Folding the due date (YYYYMMDD) in makes each due-cycle a distinct item that
        # surfaces anew; an undated card uses "nodue" and so stays seen until it's given a due date.
        due = (item.get("due") or "")
        stamp = "".join(c for c in due if c.isdigit())[:8] or "nodue"
        return f"{self.name}-{slug(item.get('name'), 40)}-{item['cardId'][-6:]}-{stamp}".strip("-")[:72]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        body_file = os.path.join(items_dir, f"{iid}.trello.md")
        comments = self._fetch_comments(item["cardId"])
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(f"# {item.get('name')}\n\n"
                    f"Board: {item.get('board')} / List: {item.get('list')}\n"
                    f"Due: {item.get('due') or '(none)'}\n"
                    f"Channel: {item.get('channelLabel') or '(none)'}\n"
                    f"Contacts: {', '.join(item.get('contacts') or []) or '(none)'}\n"
                    f"Link: {item.get('url')}\nCardId: {item['cardId']}\n\n"
                    f"## Description\n\n{item.get('desc') or '(empty)'}\n\n## Comments\n\n{comments}\n")
        record = {
            "id": iid, "source": self.name, "triage": item.get("_bucket", "needs-you"),
            "kind": item.get("_kind"), "cardId": item["cardId"], "board": item.get("board"),
            "list": item.get("list"), "name": item.get("name"), "due": item.get("due"),
            "url": item.get("url"), "contacts": item.get("contacts") or [],
            "channelLabel": item.get("channelLabel"), "bodyFile": body_file,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file

    def _fetch_comments(self, card_id):
        try:
            actions = self._utils.trello_request(
                "GET", f"/cards/{card_id}/actions", self.session,
                params={"filter": "commentCard", "limit": "50"})
        except Exception:
            return "(could not load comments)"
        if not actions:
            return "(none)"
        out = []
        for a in actions:
            who = (a.get("memberCreator") or {}).get("fullName", "?")
            when = a.get("date", "")
            text = (a.get("data") or {}).get("text", "")
            out.append(f"- {when} {who}: {text}")
        return "\n".join(out)
