"""personal-outlook poller adapter — Microsoft Graph mail via the ms-graph skill's mail.js.

All personal-outlook mechanics live HERE, alongside the prose contract in
`personal-outlook-provider.md`: locating mail.js, the `--list-inbox --json` enumerate, the Graph id
scheme, and the captured item shape. The poller (`scripts/run-poller.py`) loads this adapter
dynamically and drives it through the `ProviderBase` interface — it contains no Outlook specifics.
"""
import json
import os
import sys
from datetime import datetime, timezone

# scripts/ is on sys.path (the poller inserts it); fall back to a relative add when run standalone.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, run_node, slug  # noqa: E402


class Provider(ProviderBase):
    name = "personal-outlook"

    def __init__(self):
        self.mailjs = self._find_mail_js()

    @staticmethod
    def _find_mail_js():
        """Locate ms-graph's mail.js by walking up to the shared plugins/ dir."""
        d = os.path.dirname(os.path.abspath(__file__))
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
        return f"{self.name}-{recv}-{sender}-{subj3}".strip("-")[:64]

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
