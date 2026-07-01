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

# Windows Terminal's top-level window class. Used to tell "Russell is working in a terminal" (let the
# new worker tab surface and take focus, so he sees it and starts on it) from "Russell is in something
# else — a browser, slides" (keep the drainer window minimized so it never covers what he's doing).
WT_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
SW_MINIMIZE = 6


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
    and exits automatically. No WT tab is created, no hostpid kill is needed.
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
