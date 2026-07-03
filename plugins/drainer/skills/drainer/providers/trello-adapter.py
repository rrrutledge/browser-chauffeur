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

The **go-live date IS the queue** (startable-task model): the native Start date is a card's
"work-on-it-next / ping-back" date and the native Due date is a real deadline. enumerate returns cards
in active lists that are startable — Start now-or-earlier, OR Due now-or-earlier (a slipped deadline
forces the card up), OR no date at all — and NOT wearing a ⛔ Blocked (skip) label. Outreach cards set
no Start, so they still queue purely on Due — unchanged. Dated cards rank by their go-live date (the
earliest of start/due), most recent first; undated cards rank by their creation date, decoded from the
card's ObjectId. Blocked cards are suppressed until finishing their upstream runs
trello_utils.cascade_unblock (strips ⛔, sets Start=today). Credentials are TRELLO_API_KEY /
TRELLO_TOKEN in the environment (read by trello_utils.get_trello_session).
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
from provider_base import ProviderBase, ProviderError, slug  # noqa: E402


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
        # Same substring rule for labels: a card wearing a skip label is suppressed. "⛔ Blocked" cards
        # are hidden until their upstream clears (the push cascade strips the label). status_labels are
        # the superset held out of contact classification (a ⛔/⏳ label is never a contact name).
        self.skip_labels = {"blocked"}
        self.status_labels = {"blocked", "waiting"}
        # The ⏳ Waiting label token: cards wearing it are the reverse reply-matcher's watch list
        # (open_waiting_index), matched case-insensitively as a substring so "⏳ Waiting" hits.
        self.waiting_label_substr = "waiting"
        self.channels = []
        self.features = []
        # Board name → default initiative slug (from a board's `initiative:` field in the registry);
        # applies to every card on that board when no per-card initiative label is present.
        self.board_initiatives = {}
        # Resolved lazily on first enumerate; used to skip cards assigned to someone else.
        self._my_member_id = None

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
            raise ProviderError(
                "Could not locate trello-outreach's trello_utils.py for the trello provider.",
                kind="config")
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
            skip_labels = self._parse_inline_list(block, "skip_labels")
            if skip_labels:
                self.skip_labels = {s.lower() for s in skip_labels}
            status_labels = self._parse_inline_list(block, "status_labels")
            if status_labels:
                self.status_labels = {s.lower() for s in status_labels}
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
            self.board_initiatives = {
                b["name"]: b["initiative"] for b in boards if b.get("initiative")}

    @staticmethod
    def _parse_registry(text):
        """Parse `<repo>/trello-boards.yaml` — a `boards:` list of board items, each a `- name:` at
        two-space indent with an `id:` field at four-space indent. Anchoring on those exact indents
        keeps the parse robust against deeper nested fields (per-board `purpose`, `template_cards`, …)
        without needing a full YAML library (none ships with the poller's stdlib runtime). The
        optional four-space `initiative:` field is captured as a board's default initiative slug."""
        boards, cur = [], None
        for line in text.splitlines():
            m_name = re.match(r"^  -\s*name\s*:\s*(.+?)\s*$", line)
            m_id = re.match(r"^    id\s*:\s*(.+?)\s*$", line)
            m_init = re.match(r"^    initiative\s*:\s*(.+?)\s*$", line)
            if m_name:
                if cur:
                    boards.append(cur)
                cur = {"name": m_name.group(1).strip().strip('"\'')}
            elif m_id and cur is not None and "id" not in cur:
                cur["id"] = m_id.group(1).strip().strip('"\'')
            elif m_init and cur is not None and "initiative" not in cur:
                cur["initiative"] = m_init.group(1).strip().strip('"\'')
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
        """Split a card's labels into (channelLabel, features, contacts, initiativeLabel).

        A yellow label is the card's initiative (its name is returned as initiativeLabel and held out
        of contacts, so an initiative label is never mistaken for a contact name). Remaining labels
        classify by the label_vocab as before."""
        labels = card.get("labels", [])
        initiative = next((l.get("name") for l in labels
                           if (l.get("color") or "").lower() == "yellow" and l.get("name")),
                          None)
        # Hold status labels (⛔ Blocked / ⏳ Waiting) out of the name pool so they're never read as a
        # contact — they carry dependency state, not a person.
        names = [l.get("name") for l in labels
                 if l.get("name") and l.get("name") != initiative
                 and not any(tok in l.get("name").lower() for tok in self.status_labels)]
        channel = next((n for n in names if n in self.channels), None)
        feats = [n for n in names if n in self.features]
        contacts = [n for n in names if n not in self.channels and n not in self.features]
        return channel, feats, contacts, initiative

    def _has_skip_label(self, card):
        """True if the card wears a suppress label (default: ⛔ Blocked) — hidden until it's cleared."""
        for l in card.get("labels", []):
            nm = (l.get("name") or "").lower()
            if nm and any(tok in nm for tok in self.skip_labels):
                return True
        return False

    @staticmethod
    def _due_dt(due):
        if not due:
            return None
        try:
            return datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _created_dt(card_id):
        """Decode a card's creation time from its id: a Trello card id is a Mongo ObjectId whose first
        8 hex chars are the creation Unix timestamp. Used as the sort rank for undated cards, so a blank
        ranks by its age."""
        try:
            return datetime.fromtimestamp(int(card_id[:8], 16), timezone.utc)
        except (ValueError, TypeError):
            return None

    def _card_item(self, card, bname, bid, list_name, sort_dt):
        """Build the poller item dict for a card. Shared by enumerate (in-play cards) and
        open_waiting_index (⏳ cards regardless of date), so both produce the same shape and a
        reverse-matched Waiting card can be surfaced as an ordinary needs-you item."""
        channel, feats, contacts, initiative_label = self._classify_labels(card)
        # A per-card initiative label wins over the board's default initiative. The slug is the
        # initiative label's name slugified (→ initiatives/<slug>.md); board defaults are already
        # slugs in the registry.
        initiative = slug(initiative_label, 60) if initiative_label \
            else self.board_initiatives.get(bname)
        who = ", ".join(contacts) if contacts else bname
        return {
            "cardId": card["id"],
            "board": bname,
            "boardId": bid,  # so the reverse-match cascade knows which board to scan on resolve
            "list": list_name,
            "name": card.get("name", ""),
            "due": card.get("due"),
            "start": card.get("start"),
            "url": card.get("shortUrl") or card.get("url"),
            "desc": card.get("desc", ""),
            "channelLabel": channel,
            "features": feats,
            "contacts": contacts,
            "initiative": initiative,
            # Triage payload fields (mirror the inbox adapters):
            "from": who,
            "subject": card.get("name", ""),
            # `received` carries the card's date for the cross-source ordering; an undated card
            # uses its creation date, so it sorts by age alongside email/Slack and dated cards.
            "received": card.get("due") or (sort_dt.isoformat() if sort_dt else "(no due date)"),
            "preview": f"[{bname} / {list_name}] {(card.get('desc') or '').strip()[:200]}",
            "_due_sort": sort_dt,
        }

    def _is_waiting(self, card):
        """True if the card wears a ⏳ Waiting status label (blocked on a person's reply)."""
        for l in card.get("labels", []):
            if self.waiting_label_substr in (l.get("name") or "").lower():
                return True
        return False

    def open_waiting_index(self):
        """Every open ⏳ Waiting card across the drained boards, with the people it waits on parsed off
        its `Waiting-for:` line — the watch spec the reverse reply-matcher (Phase 2) consults.

        Unlike enumerate, this IGNORES the Start-date gate: a ⏳ card's Start is its ping-back date,
        usually in the FUTURE, so it would not enumerate until then — yet a reply can land earlier and
        should resolve it immediately. So we return every ⏳ card sitting in an active (non-skip) list,
        each as a full poller item (so a matched one can be surfaced verbatim) carrying an extra
        `_waitingFor` = [{name, channel}]. Cards with no parseable Waiting-for line are omitted (nothing
        to match on). Read-only; runs once per cycle only when inbound items are present to match."""
        if not self.boards:
            return []
        out = []
        for board in self.boards:
            bid, bname = board["id"], board.get("name", board["id"])
            lists = {l["id"]: l["name"] for l in self._utils.get_board_lists(bid, self.session)}
            for card in self._utils.get_board_cards(bid, self.session, fields="all"):
                list_name = lists.get(card.get("idList"))
                if not list_name:
                    continue
                if any(tok in list_name.lower() for tok in self.skip_lists):
                    continue
                if not self._is_waiting(card):
                    continue
                waiting_for = self._utils.parse_waiting_for(card.get("desc"))
                if not waiting_for:
                    continue
                sort_dt = self._due_dt(card.get("start")) or self._due_dt(card.get("due")) \
                    or self._created_dt(card["id"])
                item = self._card_item(card, bname, bid, list_name, sort_dt)
                item["_waitingFor"] = waiting_for
                out.append(item)
        return out

    # --------------------------------------------------------------- the ProviderBase contract
    def enumerate(self, limit):
        if not self.boards:
            return []
        try:
            return self._enumerate(limit)
        except ProviderError:
            raise  # already typed (kind preserved) — don't re-wrap as auth
        except Exception as e:
            # The board/list/card fetches hit the Trello REST API with TRELLO_API_KEY / TRELLO_TOKEN;
            # a bad/expired token or network error surfaces here. Raise the typed error so the poller
            # isolates trello and records it to provider-health instead of aborting the whole cycle.
            raise ProviderError(f"trello enumerate failed (auth/API?): {e}", kind="auth")

    def _my_id(self):
        """Return the authenticated member's Trello ID, fetched once and cached."""
        if self._my_member_id is None:
            me = self._utils.trello_request("GET", "/members/me", self.session,
                                            params={"fields": "id"})
            self._my_member_id = me.get("id") if isinstance(me, dict) else None
        return self._my_member_id

    def _enumerate(self, limit):
        now = datetime.now(timezone.utc)
        my_id = self._my_id()
        items = []
        for board in self.boards:
            bid, bname = board["id"], board.get("name", board["id"])
            lists = {l["id"]: l["name"] for l in self._utils.get_board_lists(bid, self.session)}
            # fields="all" so the newer `start` date comes back (the default card payload omits it).
            for card in self._utils.get_board_cards(bid, self.session, fields="all"):
                list_name = lists.get(card.get("idList"))
                # get_board_lists returns only OPEN lists; a card whose list isn't in that map sits on
                # an archived/closed list (still an open card, but off the board) — not active, skip it.
                if not list_name:
                    continue
                ln = list_name.lower()
                if any(tok in ln for tok in self.skip_lists):
                    continue
                # ⛔ Blocked cards are suppressed until their upstream clears (the push cascade removes
                # the label and sets Start = today, so they resurface on a later drain).
                if self._has_skip_label(card):
                    continue
                # Skip cards assigned to someone else; unassigned cards are always Russell's.
                assigned = card.get("idMembers") or []
                if assigned and my_id not in assigned:
                    continue
                # Startable-task model: Start = the "go-live / ping-back" date, Due = a real deadline.
                # A card is in play when its Start has arrived, OR its Due has arrived (a slipped
                # deadline forces it up as a safety net), OR it carries neither date (startable now).
                # Outreach cards set no Start, so they still queue purely on Due — unchanged behavior.
                start_dt = self._due_dt(card.get("start"))
                due_dt = self._due_dt(card.get("due"))
                gate_dts = [d for d in (start_dt, due_dt) if d is not None]
                if gate_dts and min(gate_dts) > now:
                    continue
                # Sort rank: a dated card ranks by its go-live date (the earliest of start/due); an
                # undated card ranks by its creation date (always in the past).
                sort_dt = min(gate_dts) if gate_dts else self._created_dt(card["id"])
                items.append(self._card_item(card, bname, bid, list_name, sort_dt))
        # Ranked by sort date, most recent first (an undated card sorts by its creation date, set above).
        # This is also the truncation order: when more than `limit` cards are in play the oldest ones are
        # dropped and resurface on a later cycle. A card whose sort date couldn't be derived falls back to
        # `now`, ranking it at the top.
        items.sort(key=lambda it: it["_due_sort"] or now, reverse=True)
        return items[:limit]

    def stable_id(self, item):
        # The go-live date is PART OF the identity, not just a field: a card recurs every cycle (a
        # nudge bumps its Start out, CLEAR bumps an outreach card's Due out), and seen-state's `clear`
        # leaves a drained id in seen.json forever (status=cleared, key persists) while dedup is pure
        # key-presence. So a stable per-card id would be marked seen on the first drain and never
        # resurface when the next date arrives. Folding the go-live date (Start when present, else Due,
        # YYYYMMDD) in makes each cycle a distinct item that surfaces anew; an undated card uses "nodue"
        # and so stays seen until it's given a date.
        stamp_src = item.get("start") or item.get("due") or ""
        stamp = "".join(c for c in stamp_src if c.isdigit())[:8] or "nodue"
        return f"{self.name}-{slug(item.get('name'), 40)}-{item['cardId'][-6:]}-{stamp}".strip("-")[:72]

    @staticmethod
    def _reverse_match_md(rm):
        """The reply-detected banner a reverse-matched card leads with, so the worker sees FIRST that
        this ⏳ card was surfaced early because its awaited reply landed — and what to do about it."""
        if not rm:
            return ""
        link = f"\nLink: {rm.get('url')}" if rm.get("url") else ""
        return (
            "## ⚡ Reply detected — this card was surfaced ahead of its ping-back date\n\n"
            f"An inbound message from **{rm.get('from')}** on **{rm.get('channel')}** looks like the "
            "reply this ⏳ Waiting card was waiting on.\n"
            f"Subject: {rm.get('subject') or '(none)'}{link}\n\n"
            f"> {(rm.get('preview') or '').strip()[:600]}\n\n"
            "**Do:** open the thread and confirm it resolves the ask. If it does — resolve this ⏳ card "
            "(advance/finish it, post a dated comment noting the reply + thread link) and it will "
            "unblock its downstream ⛔ cards. If it does NOT (unrelated message from the same person), "
            "leave the card on its ping-back date and just handle the message. See the trello provider "
            "doc's REVERSE-MATCH section.\n\n")

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        body_file = os.path.join(items_dir, f"{iid}.trello.md")
        comments = self._fetch_comments(item["cardId"])
        reverse_md = self._reverse_match_md(item.get("_reverseMatch"))
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(f"# {item.get('name')}\n\n"
                    f"{reverse_md}"
                    f"Board: {item.get('board')} / List: {item.get('list')}\n"
                    f"Next-action (start): {item.get('start') or '(none)'}\n"
                    f"Deadline (due): {item.get('due') or '(none)'}\n"
                    f"Channel: {item.get('channelLabel') or '(none)'}\n"
                    f"Contacts: {', '.join(item.get('contacts') or []) or '(none)'}\n"
                    f"Initiative: {item.get('initiative') or '(none)'}\n"
                    f"Link: {item.get('url')}\nCardId: {item['cardId']}\n\n"
                    f"## Description\n\n{item.get('desc') or '(empty)'}\n\n## Comments\n\n{comments}\n")
        record = {
            "id": iid, "source": self.name, "triage": item.get("_bucket", "needs-you"),
            "kind": item.get("_kind"), "cardId": item["cardId"], "board": item.get("board"),
            "boardId": item.get("boardId"),
            "list": item.get("list"), "name": item.get("name"), "due": item.get("due"),
            "start": item.get("start"),
            "url": item.get("url"), "contacts": item.get("contacts") or [],
            "channelLabel": item.get("channelLabel"), "initiative": item.get("initiative"),
            "reverseMatch": item.get("_reverseMatch"),  # the detected reply, when surfaced by Phase 2
            "bodyFile": body_file,
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
