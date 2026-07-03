"""Launch or reuse a persistent Edge/Chrome instance with CDP enabled.

Default (persistent) mode:
    python launch-browser.py
    python launch-browser.py --url https://example.com

  Checks ~/.claude/browser-chauffeur/state.json for an already-running browser.
  If alive (CDP port responds), prints the existing info and exits. Otherwise
  launches a fresh browser with a persistent profile at
  ~/.claude/browser-chauffeur/profile/ so logins survive across tasks.

  The persistent browser stays running across Claude instances. DO NOT kill it
  manually - this preserves your logged-in sessions for future tasks.

Fresh mode (one-off, temporary browser):
    python launch-browser.py --fresh --port 9222 --url https://example.com

  Always launches a new browser with a unique timestamped profile.
  For --fresh mode only: caller is responsible for killing the PID and
  cleaning the profile when done.

Notes baked in (so callers don't have to remember them):
- Windows --user-data-dir requires backslash paths. Forward-slash Unix paths
  from Git Bash silently fail and the CDP port never binds — handled here by
  building the path with pathlib + str().
- Edge sidebar hijack: Edge with Microsoft 365 accounts has a built-in
  Teams/Chat sidebar that intercepts Teams URLs into a popup widget instead
  of a full-page tab. We disable it via --disable-features and pass the
  target URL as a positional argument so it opens as a real tab.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

EDGE_DISABLE_FEATURES = (
    "msEdgeSidebarV2,msEdgeSidebar,msEdgeChatAndNotification,"
    "msTeamsLeftChrome,EdgeSidebar,msEdgeSidebarPwaIntegration,"
    "msEdgeSyncPromoRollout,msEdgeWelcomePageEnabled"
)

# Global state directory shared across all Claude instances
CHAUFFEUR_DIR = Path.home() / ".claude" / "browser-chauffeur"
STATE_FILE = str(CHAUFFEUR_DIR / "state.json")
PERSISTENT_PROFILE = str(CHAUFFEUR_DIR / "profile")
TAB_REGISTRY = CHAUFFEUR_DIR / "created-tabs.json"

# Backstop tab hygiene. The primary cleanup is the owner reap — a tab is closed
# promptly when its owning session ends (see sweep_tabs). These two are the
# safety nets under that: TAB_TTL_SECONDS ages out a tab that's been idle a long
# time (default 12h — comfortably past a browser login and any lunch/afk gap, so
# it only catches genuinely abandoned tabs); MAX_TABS is a hard ceiling that
# closes the least-recently-active until back under it, so the browser can never
# accumulate enough tabs to crash (default 15 — well under the ~20 where the
# browser starts to struggle). Both are env-overridable without a code change.
TAB_TTL_SECONDS = int(os.environ.get("BROWSER_CHAUFFEUR_TAB_TTL", 12 * 60 * 60))
MAX_TABS = int(os.environ.get("BROWSER_CHAUFFEUR_MAX_TABS", 15))


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return False
        except (ConnectionRefusedError, socket.timeout, OSError):
            return True


def find_free_port(start: int = 9222, count: int = 5) -> int | None:
    for port in range(start, start + count):
        if is_port_available(port):
            return port
    return None


def is_pid_running(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True,
    )
    return str(pid) in result.stdout


def is_cdp_alive(port: int) -> bool:
    try:
        resp = urlopen(f"http://localhost:{port}/json/version", timeout=2)
        data = json.loads(resp.read())
        return "Browser" in data
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return False


def sweep_tabs(port: int) -> None:
    """Keep the persistent browser's tab count low and healthy.

    Reclaiming is driven by idleness; ownership only lets us clean up promptly
    instead of waiting. Three layers, applied in order:
      1. Owner reap (the courtesy) — a tab whose owning session has ended is
         closed right away, rather than waiting for it to age out or become the
         idlest under the cap. The owner is the Claude session that opened the
         tab (its long-lived host process; see the launcher's OWNER_PID env), so
         a tab lives as long as that session's window is open and is cleaned up
         when it closes. A tab opened without the openTab helper has no owner —
         it's cleaned up by layers 2–3 instead.
      2. Age-out (TTL) — any tab idle (no activity) longer than TAB_TTL_SECONDS
         is closed, regardless of owner, catching genuinely abandoned tabs.
         Activity = a tab created/reused via the openTab/findTab helpers, or a
         URL/title change the sweep notices between runs. Tabs opened without
         openTab are adopted on first sight so their idleness can be tracked.
      3. Count cap — if more than MAX_TABS remain, close the least-recently-
         active until back under the ceiling. Pure idleness, ownership-agnostic:
         an actively-used tab has recent activity so it's never the one closed.

    Never touched: the browser's last remaining page (closing it would exit the
    browser and lose all logins). This is a dedicated automation browser
    separate from the user's personal browser, so idle tabs carry no user
    browsing to protect. Uses the raw CDP HTTP endpoints (/json, /json/close),
    which never auto-attach to targets and so never hang the way
    connectOverCDP can.

    Best-effort: any error here is swallowed so it can't block a launch.
    """
    now_ms = int(time.time() * 1000)

    try:
        resp = urlopen(f"http://localhost:{port}/json", timeout=5)
        targets = json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError):
        return

    live = {t["id"]: t for t in targets if t.get("type") == "page" and "id" in t}
    if not live:
        return

    try:
        with open(TAB_REGISTRY) as f:
            entries = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        entries = []

    # Index the registry by targetId, dropping entries whose tab is already
    # gone. Preserve the recorded owner/ts so a live session's tab isn't lost.
    reg: dict[str, dict] = {}
    for e in entries:
        tid = e.get("targetId")
        if tid not in live:
            continue
        cur = live[tid]
        # Passive activity signal: if the tab's URL or title changed since we
        # last saw it, it was navigated/worked in between sweeps — refresh its
        # activity time so eviction favors genuinely idle tabs. This needs no
        # cooperation from the scripts that touched the tab.
        if e.get("url") != cur.get("url", "") or e.get("title") != cur.get("title", ""):
            e["lastActive"] = now_ms
        e["url"] = cur.get("url", "")
        e["title"] = cur.get("title", "")
        e.setdefault("ts", now_ms)
        e.setdefault("lastActive", e["ts"])
        reg[tid] = e
    # Adopt any live tab we don't already track (opened without openTab, or by
    # the user). Record first-seen time so TTL/cap can age it out later.
    for tid, t in live.items():
        if tid not in reg:
            reg[tid] = {"targetId": tid, "ownerPid": None, "ownerSession": None,
                        "url": t.get("url", ""), "title": t.get("title", ""),
                        "ts": now_ms, "lastActive": now_ms}

    open_ids = set(live)

    def recency(e: dict) -> int:
        # Least-recently-active first. Falls back to creation time for entries
        # predating lastActive tracking.
        return e.get("lastActive") or e.get("ts") or 0

    def close(tid: str) -> bool:
        # Never close the browser's last page — that would exit the browser.
        if len(open_ids) <= 1:
            return False
        try:
            urlopen(f"http://localhost:{port}/json/close/{tid}", timeout=5).read()
        except (URLError, OSError):
            return False
        open_ids.discard(tid)
        reg.pop(tid, None)
        return True

    def owner_pid(e: dict):
        # ownerPid is the current field; nodePid is the pre-1.9 name.
        return e.get("ownerPid") or e.get("nodePid")

    closed = 0
    # Layers 1 & 2 — owner reap (session ended) + age-out (idle past TTL),
    # least-recently-active first. Both apply regardless of whether some other
    # session is alive: a tab is reclaimed on its owner ending OR on its own
    # idleness, never held open just because unrelated sessions are running.
    for e in sorted(reg.values(), key=recency):
        tid = e["targetId"]
        if tid not in open_ids:
            continue
        pid = owner_pid(e)
        owner_ended = pid is not None and not is_pid_running(pid)
        is_idle = (now_ms - recency(e)) >= TAB_TTL_SECONDS * 1000
        if owner_ended or is_idle:
            if close(tid):
                closed += 1

    # Layer 3 — hard ceiling. Close the least-recently-active until back under
    # the cap, ownership-agnostic: an actively-used tab has recent activity so
    # it's never the one chosen; whatever's been idle longest goes first.
    for e in sorted(reg.values(), key=recency):
        if len(open_ids) <= MAX_TABS:
            break
        tid = e["targetId"]
        if tid not in open_ids:
            continue
        if close(tid):
            closed += 1

    try:
        TAB_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        tmp = TAB_REGISTRY.with_name(TAB_REGISTRY.name + f".{os.getpid()}.tmp")
        with open(tmp, "w") as f:
            json.dump(list(reg.values()), f)
        os.replace(tmp, TAB_REGISTRY)
    except OSError:
        pass

    if closed:
        print(f"Swept {closed} tab(s) to keep the browser healthy.")


def load_state() -> dict | None:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(pid: int, port: int, profile_dir: str) -> None:
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"pid": pid, "port": port, "profile_dir": profile_dir}, f)


def launch_browser(port: int, url: str, profile_dir: str) -> tuple[str, int]:
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    common_args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--suppress-message-center-popups",
        "--start-maximized",
        url,
    ]

    if os.path.isfile(EDGE_PATH):
        cmd = [EDGE_PATH, f"--disable-features={EDGE_DISABLE_FEATURES}", *common_args]
        browser_name = "Edge"
    elif os.path.isfile(CHROME_PATH):
        cmd = [CHROME_PATH, *common_args]
        browser_name = "Chrome"
    else:
        print("No supported browser found (Edge or Chrome)", file=sys.stderr)
        sys.exit(1)

    proc = subprocess.Popen(cmd)
    return browser_name, proc.pid


def run_persistent(url: str) -> int:
    state = load_state()
    if state:
        pid, port, profile_dir = state["pid"], state["port"], state["profile_dir"]
        # Edge process sharing can change PIDs - if CDP responds, browser is alive
        if is_cdp_alive(port):
            # Reap orphaned, aged-out, and over-the-cap tabs before handing the
            # browser back — keeps the target count low so connectOverCDP stays
            # healthy and the browser can't accumulate enough tabs to crash.
            sweep_tabs(port)
            print(f"Reusing existing browser on port {port} (original PID {pid})")
            print(f"PID={pid}")
            print(f"PORT={port}")
            print(f"PROFILE_DIR={profile_dir}")
            return 0
        elif is_pid_running(pid):
            print(f"Warning: PID {pid} running but CDP port {port} not responding. Launching new browser.")
            # PID exists but CDP dead - likely a different process reused the PID

    port = find_free_port()
    if port is None:
        print("No available port in range 9222-9226", file=sys.stderr)
        return 1

    browser_name, pid = launch_browser(port, url, PERSISTENT_PROFILE)

    # Verify CDP port actually bound (Edge process sharing can prevent it)
    print(f"Launched {browser_name} (PID {pid}), waiting for CDP on port {port}...")
    time.sleep(3)  # Give browser time to start

    if not is_cdp_alive(port):
        print(f"\n[!] ERROR: CDP port {port} did not bind!", file=sys.stderr)
        print("This usually happens when Edge process sharing prevents --remote-debugging-port.", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("1. Close ALL Edge windows (personal browser too)", file=sys.stderr)
        print("2. Run: taskkill /F /IM msedge.exe", file=sys.stderr)
        print("3. Try launching again", file=sys.stderr)
        print(f"\nIf that doesn't work, try --fresh mode with a different port:", file=sys.stderr)
        print(f"  python launch-browser.py --fresh --port 9226 --url {url}", file=sys.stderr)
        return 1

    save_state(pid, port, PERSISTENT_PROFILE)

    print(f"[OK] {browser_name} on port {port} (PID {pid})")
    print(f"PID={pid}")
    print(f"PORT={port}")
    print(f"PROFILE_DIR={PERSISTENT_PROFILE}")
    return 0


def run_fresh(port: int, url: str, profile_dir: str | None) -> int:
    if profile_dir is None:
        profile_dir = str(Path.cwd() / ".tmp" / f"cdp-profile-{int(time.time())}")

    browser_name, pid = launch_browser(port, url, profile_dir)

    print(f"Launched {browser_name} on port {port} (PID {pid})")
    print(f"PID={pid}")
    print(f"PORT={port}")
    print(f"PROFILE_DIR={profile_dir}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fresh", action="store_true",
                   help="Launch a one-off browser with a unique profile (old behavior)")
    p.add_argument("--port", type=int, default=None,
                   help="CDP port (required for --fresh, ignored in persistent mode)")
    p.add_argument("--url", default="about:blank",
                   help="Initial URL (default: about:blank)")
    p.add_argument("--profile-dir", default=None,
                   help="Profile directory (--fresh only; auto-generated if omitted)")
    args = p.parse_args()

    if args.fresh:
        if args.port is None:
            print("--port is required with --fresh", file=sys.stderr)
            return 1
        return run_fresh(args.port, args.url, args.profile_dir)

    return run_persistent(args.url)


if __name__ == "__main__":
    sys.exit(main())
