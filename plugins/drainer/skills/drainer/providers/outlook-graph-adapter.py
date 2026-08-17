"""outlook-graph poller adapter — Microsoft Graph mail via the ms-graph skill's mail.js.

All outlook-graph mechanics live HERE, alongside the prose contract in
`outlook-graph-provider.md`: locating mail.js, the `--list-inbox --json` enumerate, the Graph id
scheme, and the captured item shape. The poller (`scripts/run-poller.py`) loads this adapter
dynamically and drives it through the `ProviderBase` interface — it contains no Outlook specifics.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

# scripts/ is on sys.path (the poller inserts it); fall back to a relative add when run standalone.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, run_node, slug  # noqa: E402


class Provider(ProviderBase):
    name = "outlook-graph"

    def __init__(self):
        self.mailjs = self._find_mail_js()

    @staticmethod
    def _find_mail_js():
        """Locate ms-graph's mail.js across both the dev-repo and installed-plugin-cache layouts.

        Dev repo:   <plugins>/ms-graph/skills/ms-graph/scripts/mail.js          (sibling of drainer)
        Installed:  <plugins>/cache/<marketplace>/ms-graph/<ver>/skills/ms-graph/scripts/mail.js
        Walk up to the first `plugins` dir, then try the sibling path, else glob for any ms-graph
        mail.js beneath it and take the highest-versioned (lexically greatest) path.
        """
        d = os.path.dirname(os.path.abspath(__file__))
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        if d:
            sibling = os.path.join(d, "ms-graph", "skills", "ms-graph", "scripts", "mail.js")
            if os.path.exists(sibling):
                return sibling
            matches = glob.glob(os.path.join(d, "**", "ms-graph", "**", "scripts", "mail.js"),
                                recursive=True)
            if matches:
                return sorted(matches)[-1]  # highest version / latest path
        raise ProviderError("Could not locate ms-graph mail.js for outlook-graph.", kind="config")

    def enumerate(self, limit):
        res = run_node([self.mailjs, "--list-inbox", "--json", f"--top={limit}"])
        if res.returncode != 0:
            raise ProviderError(f"outlook-graph enumerate failed (auth?): {res.stderr.strip()[:300]}",
                                kind="auth")
        msgs = json.loads(res.stdout or "[]")
        return [m for m in msgs if not self._own_outbound_reply(m)]

    @staticmethod
    def _own_outbound_reply(m):
        """True for a message Russell sent to other people that surfaced back in his inbox (a reply
        threaded into the conversation, e.g. his "RE: Baggage Fee" to his dad). That is his own outbound
        side, not inbound mail to triage — dropping it here keeps his replies out of the queue. A genuine
        self-note (he is a recipient, so `toMe` is set) is preserved: it's a task he captured for himself.
        `fromMe`/`toMe` come from mail.js, which resolves the mailbox owner's own address."""
        return bool(m.get("fromMe")) and not bool(m.get("toMe"))

    def still_in_inbox_ids(self):
        res = run_node([self.mailjs, "--list-inbox", "--json", "--top=500"])
        if res.returncode != 0:
            return None
        try:
            msgs = json.loads(res.stdout or "[]")
        except ValueError:
            return None
        return {m["id"] for m in msgs if m.get("id")}

    def _fetch_body(self, item):
        """The message body, for relay-correspondent extraction when a relay's name isn't already in the
        subject/preview. Only reached for a recognized relay sender whose cheap fields missed, so this
        per-item Graph fetch stays rare."""
        show = run_node([self.mailjs, f"--show={item['id']}"])
        return show.stdout if show.returncode == 0 else ""

    def clear(self, item):
        """Archive an fyi/junk message at triage time (the provider CLEAR: `mail.js --delete` moves it to
        Archive, reversible and still searchable). Returns True on success, False on failure — see
        ProviderBase.clear for why the poller can call this without risk of losing the item."""
        res = run_node([self.mailjs, f"--delete={item['id']}"])
        return res.returncode == 0

    def stable_id(self, item):
        # Timestamp to the second (plus ms when Graph supplies them) so two messages from the same
        # sender with the same opening subject in the same minute don't collide and silently drop one.
        digits = "".join(c for c in (item.get("received") or "") if c.isdigit())
        recv = f"{digits[:8]}-{digits[8:14]}{digits[14:17]}"  # YYYYMMDD-HHMMSS(ms)
        sender = slug((item.get("fromAddress") or item.get("from") or "").split("@")[0])
        subj3 = slug("-".join((item.get("subject") or "").split()[:3]))
        return f"{self.name}-{recv}-{sender}-{subj3}".strip("-")[:72]

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
            "correspondent": item.get("_correspondent"), "emailFile": email_file,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
