import glob
import os


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


def latest_screenshot():
    candidates = []
    for folder in candidate_folders():
        for name in os.listdir(folder):
            if name == "desktop.ini" or not name.lower().endswith(".png"):
                continue
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


if __name__ == "__main__":
    result = latest_screenshot()
    if result is None:
        raise SystemExit("No screenshots found in any candidate folder")
    print(result)
