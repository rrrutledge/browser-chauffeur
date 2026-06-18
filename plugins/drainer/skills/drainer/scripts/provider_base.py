"""Shared base for drainer poller provider adapters.

Each source the poller drives ships a `providers/<name>-adapter.py` next to its prose
`providers/<name>-provider.md`, defining a `Provider(ProviderBase)` with `name` + `enumerate` +
`stable_id` + `capture`. `run-poller.py` loads these dynamically — no provider mechanics live in the
poller itself. This module is the small shared surface (subprocess + slug helpers + the interface).
"""
import re
import subprocess


def run_node(args, **kw):
    return subprocess.run(["node", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def slug(s, maxlen=18):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen].strip("-")


class ProviderBase:
    """The interface the poller drives. Subclasses live in providers/<name>-adapter.py."""
    name = None

    def enumerate(self, limit):
        """Return a list of candidate item dicts (newest-first, up to `limit`)."""
        raise NotImplementedError

    def stable_id(self, item):
        """A deterministic id for an item (stable across cycles), used for seen-state."""
        raise NotImplementedError

    def capture(self, item, iid, runtime_dir):
        """Write the item's files under <runtime_dir>/items/ and return the path to <id>.json."""
        raise NotImplementedError
