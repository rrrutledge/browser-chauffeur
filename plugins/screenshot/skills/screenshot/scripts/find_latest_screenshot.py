import argparse
import glob
import os
import time


def candidate_folders():
    home = os.path.expanduser("~")
    folders = [
        os.path.join(home, "OneDrive", "Pictures", "Screenshots 1"),
        os.path.join(home, "Pictures", "Screenshots"),
        os.path.join(home, "OneDrive", "Pictures", "Screenshots"),
    ]
    folders.extend(glob.glob(os.path.join(home, "OneDrive*", "Pictures", "Screenshots")))
    seen = set()
    existing = []
    for folder in folders:
        key = os.path.normcase(os.path.normpath(folder))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isdir(folder):
            existing.append(folder)
    return existing


def screenshots_by_recency():
    candidates = []
    for folder in candidate_folders():
        for name in os.listdir(folder):
            if name == "desktop.ini" or not name.lower().endswith(".png"):
                continue
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                candidates.append(path)
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--index", type=int, default=1, help="1-based rank by recency; 1 is the latest, 2 the one before that, etc.")
    group.add_argument("--count", type=int, help="print this many of the most recent screenshots, newest first, one per line")
    group.add_argument("--since", type=float, help="print every screenshot modified within this many minutes of now, newest first, one per line")
    args = parser.parse_args()

    ranked = screenshots_by_recency()
    if not ranked:
        raise SystemExit("No screenshots found in any candidate folder")

    if args.count is not None:
        for path in ranked[: args.count]:
            print(path)
    elif args.since is not None:
        cutoff = time.time() - args.since * 60
        for path in ranked:
            if os.path.getmtime(path) >= cutoff:
                print(path)
    else:
        if args.index < 1 or args.index > len(ranked):
            raise SystemExit(f"Only {len(ranked)} screenshot(s) found; --index {args.index} is out of range")
        print(ranked[args.index - 1])
