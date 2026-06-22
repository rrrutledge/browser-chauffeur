"""teams poller adapter — Microsoft Teams chats/channels via the teams skill's teams-chat.js.

All teams mechanics live HERE, alongside the prose contract in `teams-provider.md`: locating the teams
skill's teams-chat.js, the `enumerate --unread` read, the conversation-id scheme, and the captured item
shape. The poller (`scripts/run-poller.py`) loads this adapter dynamically and drives it through the
`ProviderBase` interface — it contains no Teams specifics.

This is the Teams sibling of `slack-adapter.py`: it wraps a sibling skill's read CLI. teams-chat.js talks
the Teams internal REST services with tokens sniffed from the live Teams web session; the one-time sniff
needs `playwright` (resolved from the home repo's node_modules via NODE_PATH). CLEAR (mark-read) and
DRAFT-MODE stay browser-driven in the worker — see `teams-provider.md`.
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
from provider_base import ProviderBase, ProviderError, run_node, slug  # noqa: E402

# Stable per-machine home (teams-chat.js caches its sniffed tokens here, absolutely). We also run node
# from here for a consistent cwd.
TOKEN_HOME = os.path.join(os.path.expanduser("~"), ".claude", "drainer")


class Provider(ProviderBase):
    name = "teams"

    def __init__(self):
        self.teamsjs = self._find_teams_js()
        self.repo = None  # set by configure(cfg); the home repo's node_modules carries playwright
        os.makedirs(TOKEN_HOME, exist_ok=True)

    def configure(self, cfg):
        """Learn the home repo from the poller so the token sniff can resolve `playwright` from its
        node_modules (see _node_kw). No-op contract on ProviderBase, so this is purely additive."""
        self.repo = cfg.get("repo")

    @staticmethod
    def _find_teams_js():
        """Locate the teams skill's teams-chat.js across dev-repo and installed-plugin-cache layouts.

        Dev repo:   <plugins>/teams/skills/teams/scripts/teams-chat.js          (sibling of drainer)
        Installed:  <plugins>/cache/<marketplace>/teams/<ver>/skills/teams/scripts/teams-chat.js
        Walk up to the first `plugins` dir, then try the sibling path, else glob and take the
        highest-versioned (lexically greatest) path.
        """
        d = os.path.dirname(os.path.abspath(__file__))
        while d and os.path.basename(d) != "plugins":
            parent = os.path.dirname(d)
            if parent == d:
                d = None
                break
            d = parent
        if d:
            sibling = os.path.join(d, "teams", "skills", "teams", "scripts", "teams-chat.js")
            if os.path.exists(sibling):
                return sibling
            matches = glob.glob(os.path.join(d, "**", "teams", "**", "scripts", "teams-chat.js"),
                                recursive=True)
            if matches:
                return sorted(matches)[-1]  # highest version / latest path
        raise ProviderError("Could not locate the teams skill's teams-chat.js for the teams provider.", kind="config")

    def _node_kw(self):
        """run_node kwargs: NODE_PATH so the token sniff resolves `playwright` from the home repo.

        configure(cfg) supplies the home repo, whose node_modules carries playwright. When tokens are
        already cached, node never loads playwright.
        """
        env = dict(os.environ)
        repo = self.repo
        if repo:
            node_modules = os.path.join(repo, "node_modules")
            existing = env.get("NODE_PATH")
            env["NODE_PATH"] = node_modules + (os.pathsep + existing if existing else "")
        return {"cwd": TOKEN_HOME, "env": env}

    def enumerate(self, limit):
        res = run_node([self.teamsjs, "enumerate", "--unread", "--top", str(limit)], **self._node_kw())
        if res.returncode != 0:
            raise ProviderError(f"teams enumerate failed (signed in to Teams web?): {res.stderr.strip()[:300]}", kind="auth")
        items = json.loads(res.stdout or "[]")
        # The engine's triage payload reads top-level from/subject/received/preview (the slack
        # convention). Teams' native shape is label + nested lastMessage, so surface those fields at
        # the top level for triage; capture/stable_id still read the native label/lastMessage below.
        for it in items:
            lm = it.get("lastMessage") or {}
            it.setdefault("subject", it.get("label"))
            it.setdefault("from", lm.get("from") or it.get("label"))
            it.setdefault("received", lm.get("time"))
            it.setdefault("preview", lm.get("preview"))
        return items

    def stable_id(self, item):
        lm = item.get("lastMessage") or {}
        digits = "".join(c for c in (lm.get("time") or "") if c.isdigit())
        when = f"{digits[:8]}-{digits[8:12]}"  # YYYYMMDD-HHMM
        who = slug(item.get("label") or lm.get("from") or "")
        words3 = slug("-".join((lm.get("preview") or "").split()[:3]))
        return f"{self.name}-{when}-{who}-{words3}".strip("-")[:72]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        msg_file = os.path.join(items_dir, f"{iid}.msg.md")
        conv_id = item["id"]  # IC3 conversation id (messages/CLEAR handle)
        lm = item.get("lastMessage") or {}
        # Pull recent messages for context (covers multi-message unread threads); fall back to preview.
        show = run_node([self.teamsjs, "messages", conv_id, "--top", "20"], **self._node_kw())
        msgs = []
        if show.returncode == 0:
            try:
                msgs = json.loads(show.stdout or "[]")
            except ValueError:
                msgs = []
        header = (f"# {item.get('label')}\n\nChat/From: {item.get('label')}\n"
                  f"Type: {item.get('type')}\nLatest: {lm.get('time')}\nLink: {item.get('deepLink')}\n\n---\n\n")
        if msgs:
            body = "\n\n".join(f"**{m.get('from')}** ({m.get('time')}):\n{m.get('text')}" for m in reversed(msgs))
        else:
            body = lm.get("preview") or "(could not load messages)"
        with open(msg_file, "w", encoding="utf-8") as f:
            f.write(header + body + "\n")
        record = {
            "id": iid, "source": self.name, "triage": item["_bucket"], "kind": item.get("_kind"),
            "from": lm.get("from") or item.get("label"), "subject": item.get("label"),
            "chatType": item.get("type"), "received": lm.get("time"),
            "snippet": lm.get("preview"), "url": item.get("deepLink"),
            "messageId": conv_id, "convId": conv_id,
            "msgFile": msg_file, "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
