"""Block until <done_path> exists (or a corresponding .skip file). Exit 0 either way.

Usage: python wait-done.py <done_path>

Polls every 20 seconds. Accepts a .skip file (same base, .skip extension) as an
alternate signal so the driver can unblock a stuck worker without a .done.
"""
import os
import sys
import time

POLL_SECONDS = 20
STATUS_EVERY = 60


def main():
    if len(sys.argv) < 2:
        print("Usage: wait-done.py <done_path>", file=sys.stderr)
        sys.exit(1)

    done_path = sys.argv[1]
    skip_path = os.path.splitext(done_path)[0] + ".skip"

    waited = 0
    while True:
        if os.path.exists(done_path) or os.path.exists(skip_path):
            return
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        if waited % STATUS_EVERY == 0:
            print(f"   ...still waiting ({waited // 60} min). "
                  f"Worker writes {os.path.basename(done_path)} when done, "
                  f"or create {os.path.basename(skip_path)} to skip.")


if __name__ == "__main__":
    main()
