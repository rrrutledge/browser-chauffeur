"""Launch a fresh Edge or Chrome instance with CDP enabled.

Usage:
    python launch-browser.py --port 9222 --url https://example.com
    python launch-browser.py --port 9222 --url https://example.com --profile-dir "C:\\custom\\path"

Prints the launched browser name and PID. Exits 1 if no supported browser is
found.

Notes baked in (so callers don't have to remember them):
- Always launches a FRESH instance with a unique profile directory so the
  user's personal browser state isn't disturbed.
- Windows --user-data-dir requires backslash paths. Forward-slash Unix paths
  from Git Bash silently fail and the CDP port never binds — handled here by
  building the path with pathlib + str().
- Edge sidebar hijack: Edge with Microsoft 365 accounts has a built-in
  Teams/Chat sidebar that intercepts Teams URLs into a popup widget instead
  of a full-page tab. We disable it via --disable-features and pass the
  target URL as a positional argument so it opens as a real tab.
- The launched process is detached: this script returns the PID and exits;
  the browser keeps running. Save the PID and use Stop-Process -Id <PID>
  -Force in Phase 3 to close only what you launched.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

EDGE_DISABLE_FEATURES = (
    "msEdgeSidebarV2,msEdgeSidebar,msEdgeChatAndNotification,"
    "msTeamsLeftChrome,EdgeSidebar,msEdgeSidebarPwaIntegration,"
    "msEdgeSyncPromoRollout,msEdgeWelcomePageEnabled"
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--url", required=True)
    p.add_argument(
        "--profile-dir",
        default=None,
        help="Profile directory. Auto-generated under <cwd>/.tmp/cdp-profile-<ts> if omitted.",
    )
    args = p.parse_args()

    if args.profile_dir:
        profile_dir = args.profile_dir
    else:
        profile_dir = str(Path.cwd() / ".tmp" / f"cdp-profile-{int(time.time())}")

    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    common_args = [
        f"--remote-debugging-port={args.port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--suppress-message-center-popups",
        "--start-maximized",
        args.url,
    ]

    if os.path.isfile(EDGE_PATH):
        cmd = [EDGE_PATH, f"--disable-features={EDGE_DISABLE_FEATURES}", *common_args]
        browser_name = "Edge"
    elif os.path.isfile(CHROME_PATH):
        cmd = [CHROME_PATH, *common_args]
        browser_name = "Chrome"
    else:
        print("No supported browser found (Edge or Chrome)", file=sys.stderr)
        return 1

    proc = subprocess.Popen(cmd)
    print(f"Launched {browser_name} on port {args.port} (PID {proc.pid})")
    print(f"PID={proc.pid}")
    print(f"PROFILE_DIR={profile_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
