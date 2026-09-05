"""Shared base for drainer poller provider adapters.

Each source the poller drives ships a `providers/<name>-adapter.py` next to its prose
`providers/<name>-provider.md`, defining a `Provider(ProviderBase)` with `name` + `enumerate` +
`stable_id` + `capture`. `run-poller.py` loads these dynamically — no provider mechanics live in the
poller itself. This module is the small shared surface (subprocess + slug helpers + the interface).
"""
import ctypes
import glob
import os
import re
import subprocess
import threading
import time

# Suppress the brief console window each child process would otherwise flash when the poller runs
# under pythonw (no parent console). 0 on non-Windows. The visible worker tabs are spawned via wt.exe
# separately and are unaffected.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Windows Terminal's top-level window class. Used to tell "Russell is working in a terminal" (let the
# new worker tab surface and take focus, so he sees it and starts on it) from "Russell is in something
# else — a browser, slides" (keep the drainer window minimized so it never covers what he's doing).
WT_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
SW_MINIMIZE = 6

# The neutral priority band — the rank of any drained item carrying no priority label (all email/Slack,
# and every Trello card the job-board poller didn't tag). The trello adapter assigns it to unlabeled
# cards and run-poller falls back to it in the cross-source sort, so both agree on where "no priority"
# sits. Which fit tiers rank above or below neutral is defined in one place: the trello adapter's
# _PRIORITY_BAND.
NEUTRAL_PRIORITY_BAND = 1


def band_rank(it):
    """The cross-source queue order, defined in ONE place: priority band, then level, then referral.
    Every drained item (email/Slack, ordinary Trello cards, and job-search cards) is ranked by this
    tuple; only job-search cards carry a non-neutral value in any band (the trello adapter stamps
    `_priority_band`/`_level_band`/`_referral_band` — see its _PRIORITY_BAND, _level_band, _referral_band
    for what each value means). To reorder the whole queue — e.g. put referral back ahead of level —
    change the tuple HERE; both sort sites (trello-adapter._enumerate and run-poller's cross-source
    needs-you sort) and the band-ranking test read it, so the policy lives at one spot. Each caller
    appends its own trailing date key (the adapter's `_sort_dt`, the poller's `received`), which breaks
    the final tie most-recent-first."""
    return (it.get("_priority_band", NEUTRAL_PRIORITY_BAND),
            it.get("_level_band", 0),
            it.get("_referral_band", 0))


def _window_class(hwnd):
    """Win32 class name of a window handle, or '' if it can't be read."""
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def spawn_silent(prompt_file, model, cwd):
    """Run a Claude worker silently with no visible window or terminal tab.

    Uses `claude --print` (single-turn non-interactive mode): Claude runs tools, completes the task,
    and exits automatically. No WT tab is created, no self-close needed.
    For background maintenance tasks (e.g. Teams mark-read) that need no human review.
    """
    seed = (
        f"Your task instructions are in '{prompt_file}' - "
        "open it and begin immediately without waiting for further input."
    )
    args = ["claude", "--print"]
    if model:
        args += ["--model", model]
    args.append(seed)
    subprocess.Popen(
        args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW | subprocess.DETACHED_PROCESS,
    )


def spawn_tab(args, cwd):
    """Open a Windows Terminal worker tab (via spawn-tab.cmd) with focus-aware placement.

    Adding a tab to the existing 'drainer' window always activates that window — wt.exe's --no-focus
    governs only NEW-window creation, not a tab added to a window that already exists (verified on
    WT 1.24). So we read the foreground window BEFORE the Popen and branch on it:

      - foreground IS a terminal  -> Russell is working in the terminal; let the new tab surface and
        take focus normally so he sees it and starts on it. Do nothing.
      - foreground is anything else (browser, PowerPoint, ...) -> don't interrupt him: once WT grabs
        focus, minimize the drainer window. Minimizing the grabber returns activation to whatever he
        was using, and (unlike SetForegroundWindow from a headless process) is not blocked by the
        Windows foreground lock.
    """
    try:
        prev = ctypes.windll.user32.GetForegroundWindow()
        prev_is_terminal = _window_class(prev) == WT_WINDOW_CLASS if prev else False
    except AttributeError:
        prev, prev_is_terminal = None, False
    subprocess.Popen(["cmd", "/c", *args], cwd=cwd, creationflags=NO_WINDOW)
    if prev and not prev_is_terminal:
        threading.Thread(target=_minimize_terminal_on_grab, args=(prev,), daemon=True).start()


def _minimize_terminal_on_grab(prev):
    """Minimize the drainer window once it steals focus from `prev`. Runs in a daemon thread.

    WT claims focus in stages, so we wait briefly, then watch the foreground: if it never leaves
    `prev`, there is nothing to do; if a terminal window grabs it, minimize that window — which slides
    it off-screen and hands activation back to `prev` without fighting the foreground lock.
    """
    user32 = ctypes.windll.user32
    time.sleep(0.4)  # let WT finish its (staged) activation
    for _ in range(15):
        fg = user32.GetForegroundWindow()
        if fg == prev:
            return  # focus never left Russell's window
        if _window_class(fg) == WT_WINDOW_CLASS:
            try:
                user32.ShowWindow(fg, SW_MINIMIZE)
            except Exception:
                pass
            return
        time.sleep(0.05)


class ProviderError(Exception):
    """A provider's enumerate (or adapter load) failed for THIS provider only.

    The poller catches this per-provider so one source's failure never aborts the cycle for the
    others; it records the failure to provider-health.json so the daily digest can surface a stuck
    provider for Russell to fix. `kind` distinguishes the two failure modes the digest reports
    differently:
      - "auth"   — a transient credential / network failure (expired token, IMAP blip). Expected
                   occasionally; self-heals once the credential is refreshed.
      - "config" — a deploy/config error (a helper .js or utility couldn't be located). Rare and
                   loud; it won't self-heal, so the digest flags it distinctly.
    """

    def __init__(self, message, kind="auth"):
        super().__init__(message)
        self.kind = kind


def run_node(args, **kw):
    return subprocess.run(["node", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=NO_WINDOW, **kw)


def slug(s, maxlen=18):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen].strip("-")


def find_skill_script(start_file, skill, rel_path):
    """Locate a sibling skill's script/module across the two layouts a plugin actually runs from.

    Dev repo:   <plugins>/<skill>/skills/<skill>/<rel_path>                    (sibling of drainer)
    Installed:  <plugins>/cache/<marketplace>/<skill>/<ver>/skills/<skill>/<rel_path>
    Walks up from `start_file` to the first ancestor directory literally named `plugins`, tries the
    dev-repo sibling path, and otherwise globs the installed-cache layout specifically, returning the
    highest real version (parsed as a digit tuple, so `1.10.1` correctly beats `1.9.0`) among the
    matches.

    Deliberately never falls back to a bare recursive glob under `<plugins>/`: that would also match
    `<plugins>/marketplaces/<marketplace>/plugins/<skill>/...` — a raw git checkout of the plugin
    source kept in sync for `claude plugin update` to read, never `npm install`-ed, so a script found
    there can't actually run (e.g. a missing `node_modules` dependency). Only the two layouts a plugin
    is actually installed/run from are searched.

    Returns None if nothing resolves; the caller raises its own ProviderError with a source-specific
    message.
    """
    d = os.path.dirname(os.path.abspath(start_file))
    while d and os.path.basename(d) != "plugins":
        parent = os.path.dirname(d)
        if parent == d:
            d = None
            break
        d = parent
    if not d:
        return None
    sibling = os.path.join(d, skill, "skills", skill, rel_path)
    if os.path.exists(sibling):
        return sibling
    suffix = os.path.join("skills", skill, rel_path)
    matches = glob.glob(os.path.join(d, "cache", "*", skill, "*", suffix))
    if not matches:
        return None

    def version_tuple(path):
        ver = path[:-(len(suffix) + 1)].rsplit(os.sep, 1)[-1]
        return tuple(int(n) for n in re.findall(r"\d+", ver))

    return max(matches, key=version_tuple)


# ---------------------------------------------------------------------------- correspondent identity
#
# The poller holds a second item from the same correspondent out of dispatch while an earlier one of
# theirs is still being worked, so one tab reads both with full context instead of two racing. That
# needs a stable answer to "who is this from" per item. For a DIRECT sender the envelope From address
# is that answer. For a RELAY sender it is NOT: a shared no-reply address (Securus/JPay's
# donotreply@jpay.com serves every incarcerated contact; LinkedIn notification mail comes from
# LinkedIn, not the person who wrote) fronts many real people, so the real identity has to be parsed
# out of the notification body. `RELAY_CORRESPONDENTS` is that per-relay parse; extend it by adding an
# entry.

RELAY_CORRESPONDENTS = (
    # Securus / JPay inmate-messaging notifications: "...new Message from: TYLER COSSEY Please login...".
    {
        "tag": "securus",
        "from_rx": re.compile(r"@(?:jpay|securustech)\.(?:com|net)", re.I),
        "name_rxs": (re.compile(r"Message from:\s*(.+?)(?:\s+Please\b|[.\n]|$)", re.I),),
    },
    # LinkedIn message notifications: the person's name is in the subject, never the sender address.
    {
        "tag": "linkedin",
        "from_rx": re.compile(r"@linkedin\.com", re.I),
        "name_rxs": (
            re.compile(r"(?:new )?messages? from\s+(.+?)(?:\s+on LinkedIn|[.\n]|$)", re.I),
            re.compile(r"^(.+?)\s+sent you a message", re.I),
        ),
    },
)


def from_identity(item):
    """The default correspondent identity for a DIRECT sender: their email address, lowercased. When a
    person emails from their own address the From address IS the correspondent, so two messages from them
    share this key. Returns None when there is no address at all (a source with no sender notion), so
    such items are never held."""
    addr = (item.get("fromAddress") or "").strip().lower()
    if not addr:
        m = re.search(r"<([^>]+)>", item.get("from") or "")
        addr = (m.group(1) if m else (item.get("from") or "")).strip().lower()
    return addr or None


def relay_correspondent(item, get_body):
    """Correspondent identity for a sender whose envelope From address should NOT be used as-is. Covers
    two distinct cases, both resolved here so `correspondent()` stays a plain two-way dispatch:
      - a RELAY: a shared no-reply that fronts many real people and so does not identify who wrote
        (e.g. Securus/JPay). Its identity has to be extracted from the subject/preview/body instead.
      - a SELF-NOTE (`fromMe` and `toMe` both set): every self-note shares the account owner's own
        address, so using that address as-is would collapse them all into one correspondent — one open
        self-note tab would then silently hold every other self-note out of dispatch, indefinitely and
        without a trace, until it closed. Content extraction is the wrong tool here too (recurring or
        near-duplicate subjects, e.g. two "Research plane ticket prices" notes sent seconds apart, would
        collide and reintroduce the same bug) — a self-note is always exempt, full stop.

    Returns one of three things:
      - a namespaced identity string when the item is from a known relay and the correspondent's name is
        extractable from its subject / preview / body (e.g. Securus's "Message from: TYLER COSSEY"),
      - None when there is no identity to hold on — a relay whose name can't be extracted, or a
        self-note — so the caller holds nothing rather than falling back to the shared From address,
        which would wrongly collapse two different real people (or every self-note) onto one key,
      - False when the sender is a plain direct sender, so the caller uses the ordinary from-address
        identity.

    The tag namespaces the extracted name so it can never collide with a real from-address, and the body
    (`get_body()`, an expensive per-item fetch) is consulted only after the cheap in-memory subject and
    preview both miss."""
    if item.get("fromMe") and item.get("toMe"):
        return None
    sender = item.get("fromAddress") or item.get("from") or ""
    for relay in RELAY_CORRESPONDENTS:
        if not relay["from_rx"].search(sender):
            continue

        def extract(text):
            for rx in relay["name_rxs"]:
                m = rx.search(text or "")
                if m:
                    name = re.sub(r"\s+", " ", m.group(1)).strip().lower()
                    if name:
                        return f"relay|{relay['tag']}|{name}"
            return None

        for text in (item.get("subject"), item.get("preview")):
            hit = extract(text)
            if hit:
                return hit
        return extract(get_body())  # body fetched only after the cheap fields miss; None -> never hold
    return False


class ProviderBase:
    """The interface the poller drives. Subclasses live in providers/<name>-adapter.py."""
    name = None

    def configure(self, cfg):
        """Optional hook: receive the parsed drainer config (incl. `repo`) after construction. Adapters
        that drain user-configured targets (e.g. trello boards) override this; inbox adapters ignore it."""
        return None

    def enumerate(self, limit):
        """Return a list of candidate item dicts (newest-first, up to `limit`)."""
        raise NotImplementedError

    def triage_text(self, item):
        """The body text the triage step shows the model for this item. Default: the light `preview`
        that `enumerate` already attached. Adapters whose `enumerate` returns no usable body (e.g. the
        gmail adapter, where the IMAP envelope listing carries no preview) override this to fetch a
        quote-stripped excerpt of the new message — so triage classifies on real content, not just the
        subject line. Called only for the NEW items being triaged, so a per-item fetch here stays cheap."""
        return item.get("preview") or ""

    def _fetch_body(self, item):
        """The message body used only for relay-correspondent extraction, and only when the subject and
        preview don't already carry the name. Empty by default; email adapters that can fetch a body
        override it so a relay whose name lives only in the body still resolves."""
        return ""

    def correspondent(self, item):
        """A stable identity for WHO an item is from, used to hold a second item from the same
        correspondent out of dispatch while an earlier one of theirs is still being worked. A direct
        sender keys on their from-address; a sender whose address shouldn't be used as-is (a relay
        fronting many real people, or a self-note) is resolved by `relay_correspondent` instead — see
        its docstring. None means there is no identity to hold on, so the item always dispatches."""
        relay = relay_correspondent(item, lambda: self._fetch_body(item))
        return relay if relay is not False else from_identity(item)

    def stable_id(self, item):
        """A deterministic id for an item (stable across cycles), used for seen-state."""
        raise NotImplementedError

    def capture(self, item, iid, runtime_dir):
        """Write the item's files under <runtime_dir>/items/ and return the path to <id>.json."""
        raise NotImplementedError

    def clear(self, item):
        """Archive this item's source object at triage time, for an fyi/junk item being queued for the
        daily digest. An inbox provider whose CLEAR is a reversible archive overrides this so a message
        Russell has effectively already dispositioned leaves his inbox the moment it's triaged, rather
        than sitting there as noise until he approves clearing it at the digest. Return True on a
        successful archive, False on a failure. The default returns None: the provider has no safe
        poll-time archive (its CLEAR isn't a plain archive, or the source has no inbox), so its fyi/junk
        items stay put and the digest clears them on Russell's approval.

        Called by the poller only AFTER the item is safely captured, queued for the digest, and recorded
        seen, so a failed or absent clear never loses the item: an item whose clear fails just stays in
        the inbox until the digest, which still clears it on Russell's review."""
        return None

    def still_in_inbox_ids(self):
        """Optional: the set of this provider's message ids currently sitting in the live Inbox. This
        is what the poller's reconcile reads completion off - an item whose message is gone from the
        inbox was handled; one still sitting there, with no live worker session on it, was not.
        Return None if this provider has no such check available this run (a transient failure) or no
        meaningful notion of "still in inbox" at all (Slack, Teams) -- the reconcile skips it. The trello
        adapter overrides this: its analog is the set of currently-startable card ids (see its override).
        """
        return None
