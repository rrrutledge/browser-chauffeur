"""Shared base for drainer poller provider adapters.

Each source the poller drives ships a `providers/<name>-adapter.py` next to its prose
`providers/<name>-provider.md`, defining a `Provider(ProviderBase)` with `name` + `enumerate` +
`stable_id` + `capture`. `run-poller.py` loads these dynamically — no provider mechanics live in the
poller itself. This module is the small shared surface (subprocess + slug helpers + the interface).
"""
import ctypes
import re
import subprocess
import threading
import time

# Suppress the brief console window each child process would otherwise flash when the poller runs
# under pythonw (no parent console). 0 on non-Windows. The visible worker tabs are spawned via wt.exe
# separately and are unaffected.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def spawn_tab(args, cwd):
    """Open a Windows Terminal tab (via spawn-tab.cmd) without leaving focus on it.

    Adding a tab to the existing 'drainer' window always activates that window — wt.exe's --no-focus
    governs only NEW-window creation, not a tab added to a window that already exists (verified on
    WT 1.24). So we save the foreground window before the Popen and restore it once WT has activated.
    """
    try:
        user32 = ctypes.windll.user32
        prev = user32.GetForegroundWindow()
    except AttributeError:
        prev = None
    subprocess.Popen(["cmd", "/c", *args], cwd=cwd, creationflags=NO_WINDOW)
    if prev:
        threading.Thread(target=_restore_foreground, args=(prev,), daemon=True).start()


def _restore_foreground(hwnd):
    """Return the OS foreground to `hwnd` after Windows Terminal grabs it. Runs in a daemon thread.

    A bare SetForegroundWindow from this headless (pythonw, scheduled-task) process is silently
    ignored by Windows' foreground lock — the call returns but focus does not move. To defeat the
    lock we tap ALT (which clears it for the calling thread) and AttachThreadInput to the current
    foreground thread before setting focus, retrying until it sticks. WT claims focus in stages, so
    we wait briefly first and then reclaim in a short retry loop.
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    time.sleep(0.4)  # let WT finish its (staged) activation before we reclaim
    for _ in range(15):
        if user32.GetForegroundWindow() == hwnd:
            return
        try:
            user32.keybd_event(0x12, 0, 0, 0)   # ALT down — clears the foreground lock
            user32.keybd_event(0x12, 0, 2, 0)   # ALT up
            fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            cur_thread = kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(fg_thread, cur_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fg_thread, cur_thread, False)
        except Exception:
            pass
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

    def stable_id(self, item):
        """A deterministic id for an item (stable across cycles), used for seen-state."""
        raise NotImplementedError

    def capture(self, item, iid, runtime_dir):
        """Write the item's files under <runtime_dir>/items/ and return the path to <id>.json."""
        raise NotImplementedError
