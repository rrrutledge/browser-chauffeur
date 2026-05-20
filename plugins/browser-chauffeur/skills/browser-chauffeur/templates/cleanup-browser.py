"""Browser Chauffeur cleanup utilities.

Usage:
    python cleanup-browser.py --reset         # Kill persistent browser and delete profile
    python cleanup-browser.py --clean-old     # Remove old fresh-mode profiles from .tmp/
    python cleanup-browser.py --size          # Report persistent profile size
    python cleanup-browser.py --all           # All of the above

The --reset operation is useful when you need to clear all logins and start fresh,
or when the persistent browser is in a bad state. The --clean-old operation removes
accumulated temporary profiles from before persistent mode or from explicit --fresh
launches.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

CHAUFFEUR_DIR = Path.home() / ".claude" / "browser-chauffeur"
STATE_FILE = CHAUFFEUR_DIR / "state.json"
PERSISTENT_PROFILE = CHAUFFEUR_DIR / "profile"


def get_dir_size(path: Path) -> int:
    """Return size of directory in bytes."""
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob('*'):
        if item.is_file():
            try:
                total += item.stat().st_size
            except (OSError, PermissionError):
                pass
    return total


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def is_pid_running(pid: int) -> bool:
    """Check if a process is running on Windows."""
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True,
    )
    return str(pid) in result.stdout


def reset_persistent_browser() -> None:
    """Kill the persistent browser and delete its profile and state."""
    print("Resetting persistent browser...")

    # Kill the browser if running
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
                pid = state.get("pid")
                if pid and is_pid_running(pid):
                    print(f"  Killing browser process (PID {pid})...")
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
        except (json.JSONDecodeError, KeyError, OSError):
            pass

        STATE_FILE.unlink()
        print(f"  Deleted state file: {STATE_FILE}")

    # Delete the profile
    if PERSISTENT_PROFILE.exists():
        size = get_dir_size(PERSISTENT_PROFILE)
        print(f"  Deleting profile ({format_size(size)}): {PERSISTENT_PROFILE}")
        shutil.rmtree(PERSISTENT_PROFILE, ignore_errors=True)

    print("✓ Reset complete. Next launch will create a fresh browser.")


def clean_old_profiles() -> None:
    """Remove old fresh-mode profiles from .tmp/ directories."""
    print("Cleaning old fresh-mode profiles...")

    # Search for .tmp directories in current working directory and parent directories
    search_paths = [Path.cwd(), Path.cwd().parent]
    found_any = False

    for search_path in search_paths:
        tmp_dir = search_path / ".tmp"
        if not tmp_dir.exists():
            continue

        # Find all cdp-profile-* directories except the persistent one
        for profile_dir in tmp_dir.glob("cdp-profile-*"):
            if profile_dir.is_dir() and profile_dir.name != "cdp-profile-chauffeur":
                size = get_dir_size(profile_dir)
                print(f"  Deleting {profile_dir.name} ({format_size(size)})...")
                shutil.rmtree(profile_dir, ignore_errors=True)
                found_any = True

    if found_any:
        print("✓ Old profiles cleaned.")
    else:
        print("  No old profiles found.")


def report_profile_size() -> None:
    """Report the size of the persistent profile."""
    if not PERSISTENT_PROFILE.exists():
        print("Persistent profile does not exist yet.")
        return

    size = get_dir_size(PERSISTENT_PROFILE)
    print(f"Persistent profile size: {format_size(size)}")
    print(f"Location: {PERSISTENT_PROFILE}")

    # Warn if over 1GB
    if size > 1024 * 1024 * 1024:
        print("\n⚠️  Profile is over 1GB. Consider resetting if it's grown too large.")
        print("   Large profiles slow down browser startup and consume disk space.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset", action="store_true",
                   help="Kill persistent browser and delete profile")
    p.add_argument("--clean-old", action="store_true",
                   help="Remove old fresh-mode profiles from .tmp/")
    p.add_argument("--size", action="store_true",
                   help="Report persistent profile size")
    p.add_argument("--all", action="store_true",
                   help="Perform all cleanup operations")

    args = p.parse_args()

    if not any([args.reset, args.clean_old, args.size, args.all]):
        p.print_help()
        return 1

    if args.all or args.size:
        report_profile_size()
        print()

    if args.all or args.clean_old:
        clean_old_profiles()
        print()

    if args.all or args.reset:
        reset_persistent_browser()

    return 0


if __name__ == "__main__":
    sys.exit(main())
