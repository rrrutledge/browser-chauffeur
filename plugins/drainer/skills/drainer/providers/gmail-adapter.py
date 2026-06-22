"""gmail poller adapter — Gmail/Workspace mail via the gmail skill's gmail.js (IMAP + app password).

All gmail mechanics live HERE, alongside the prose contract in `gmail-provider.md`: locating gmail.js,
the `--list-inbox --json` enumerate, the Message-ID id scheme, and the captured item shape. The poller
(`scripts/run-poller.py`) loads this adapter dynamically and drives it through the `ProviderBase`
interface — it contains no Gmail specifics.

This is the IMAP sibling of `outlook-graph-adapter.py` (Graph). Same operations, different transport:
gmail.js talks IMAP to imap.gmail.com with GMAIL_ADDRESS / GMAIL_APP_PASSWORD from the environment.
"""
import glob
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone

# scripts/ is on sys.path (the poller inserts it); fall back to a relative add when run standalone.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, run_node, slug  # noqa: E402


class Provider(ProviderBase):
    name = "gmail"

    def __init__(self):
        self.gmailjs = self._find_gmail_js()

    @staticmethod
    def _find_gmail_js():
        """Locate the gmail skill's gmail.js across both the dev-repo and installed-plugin-cache layouts.

        Dev repo:   <plugins>/gmail/skills/gmail/scripts/gmail.js          (sibling of drainer)
        Installed:  <plugins>/cache/<marketplace>/gmail/<ver>/skills/gmail/scripts/gmail.js
        Walk up to the first `plugins` dir, then try the sibling path, else glob for any gmail
        gmail.js beneath it and take the highest-versioned (lexically greatest) path.
        """
        d = os.path.dirname(os.path.abspath(__file__))
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        if d:
            sibling = os.path.join(d, "gmail", "skills", "gmail", "scripts", "gmail.js")
            if os.path.exists(sibling):
                return sibling
            matches = glob.glob(os.path.join(d, "**", "gmail", "**", "scripts", "gmail.js"),
                                recursive=True)
            if matches:
                return sorted(matches)[-1]  # highest version / latest path
        raise ProviderError("Could not locate the gmail skill's gmail.js for the gmail provider.",
                            kind="config")

    @staticmethod
    def _web_link(message_id):
        """A Gmail web link that opens the message by its RFC822 Message-ID (account-index agnostic)."""
        mid = (message_id or "").strip("<>")
        return "https://mail.google.com/mail/u/0/#search/" + urllib.parse.quote(f"rfc822msgid:{mid}")

    def enumerate(self, limit):
        res = run_node([self.gmailjs, "--list-inbox", "--json", f"--top={limit}"])
        if res.returncode != 0:
            raise ProviderError(f"gmail enumerate failed (auth/IMAP?): {res.stderr.strip()[:300]}",
                                kind="auth")
        return json.loads(res.stdout or "[]")

    def triage_text(self, item):
        """Fetch the message body and return just the NEW content (quoted reply chain stripped), so the
        triage step sees what the message actually says instead of only its subject line. The IMAP
        envelope listing carries no preview, so without this triage would classify a Gmail thread purely
        on sender + subject. Falls back to the (usually empty) preview if the body can't be fetched."""
        message_id = item.get("id")
        if not message_id:
            return item.get("preview") or ""
        show = run_node([self.gmailjs, f"--show={message_id}"])
        if show.returncode != 0:
            return item.get("preview") or ""
        return self._new_message_excerpt(show.stdout)

    @staticmethod
    def _new_message_excerpt(raw, limit=1500):
        """From a `gmail.js --show` dump (Subject/From/To/Cc/Date header lines, then the body), keep the
        header lines and the new message text, dropping the quoted reply chain. The To/Cc lines are kept
        on purpose — they're how triage tells a message aimed at Russell from one where he's only a CC.
        The quote chain begins at the first `On <date> … wrote:` attribution or the first `>`-quoted line."""
        kept = []
        for line in (raw or "").splitlines():
            s = line.strip()
            if s.startswith(">") or re.match(r"^On .*wrote:\s*$", s):
                break
            kept.append(line)
        return "\n".join(kept).strip()[:limit]

    def stable_id(self, item):
        # Timestamp to the second so two messages from the same sender with the same opening subject in
        # the same minute don't collide and silently drop one. Mirrors the outlook-graph scheme.
        digits = "".join(c for c in (item.get("received") or "") if c.isdigit())
        recv = f"{digits[:8]}-{digits[8:14]}"  # YYYYMMDD-HHMMSS
        sender = slug((item.get("fromAddress") or item.get("from") or "").split("@")[0])
        subj3 = slug("-".join((item.get("subject") or "").split()[:3]))
        return f"{self.name}-{recv}-{sender}-{subj3}".strip("-")[:72]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        email_file = os.path.join(items_dir, f"{iid}.email.md")
        message_id = item["id"]
        show = run_node([self.gmailjs, f"--show={message_id}"])
        body = show.stdout if show.returncode == 0 else "(could not load body)"
        web_link = self._web_link(message_id)
        with open(email_file, "w", encoding="utf-8") as f:
            f.write(f"# {item.get('subject')}\n\nFrom: {item.get('from')}\nReceived: {item.get('received')}\n"
                    f"Link: {web_link}\nMessageId: {message_id}\n\n---\n\n{body}\n")
        record = {
            "id": iid, "source": self.name, "triage": item["_bucket"], "kind": item.get("_kind"),
            "from": item.get("from"), "subject": item.get("subject"), "received": item.get("received"),
            "snippet": item.get("preview"), "url": web_link, "messageId": message_id,
            "emailFile": email_file, "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
