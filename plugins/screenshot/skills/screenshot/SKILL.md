---
skill: screenshot
description: Auto-invoke when the user mentions taking a screenshot, sharing a screenshot, or references "this screenshot" without providing a file path. Loads the most recent screenshot from the Windows Screenshots folder.
instructions: |-
  Read and display the most recent screenshot, checked across every candidate Screenshots folder —
  not just the first one found.

  **On this machine, OneDrive has split screenshots across two folders that both still receive new
  files at different times** (`Screenshots 1` and `Screenshots`, depending on which one OneDrive's
  sync conflict resolution currently treats as the write target — this has flipped before and can
  flip again). Checking only the first candidate that exists is what causes a stale result: the
  right screenshot can be sitting in a folder never reached because an earlier candidate already
  matched. Always check every candidate folder that exists and compare file timestamps across all
  of them — never stop at the first hit.

  Steps:
  1. Enumerate every candidate location that exists (don't stop at the first match):
     - ~/OneDrive/Pictures/Screenshots 1
     - ~/Pictures/Screenshots (standard Windows location, no OneDrive)
     - ~/OneDrive/Pictures/Screenshots (no " 1" suffix)
     - ~/OneDrive*/Pictures/Screenshots (OneDrive for Business — use glob to find)
  2. Across *all* folders found in step 1, list their .png files (excluding desktop.ini) and pick
     the single most recently modified one overall — not the newest within just the first folder.
  3. Use the Read tool to load and display that screenshot.
  4. If the user says the screenshot you showed isn't the one they meant (wrong content, too old,
     "that's not it"), re-check every candidate folder rather than assuming the file doesn't exist —
     the true latest file is very likely sitting in a folder that didn't win step 2's comparison
     because it was mistakenly skipped, or a new file landed after your first check. Re-list and
     re-compare timestamps across all folders before telling the user nothing was found.
  5. If the user provided additional text in the args, treat it as a question or context about the
     screenshot.

  Env-var paths (`$USERPROFILE`, etc.) can't be used directly in Bash per this user's shell rules —
  write a small Python script to `.tmp/` that reads `os.environ["USERPROFILE"]`, globs every
  candidate folder, and sorts every `.png` found (across all folders) by `mtime` descending.
  
  Example invocations:
  - /screenshot → just show the latest screenshot
  - /screenshot what's this error? → show screenshot and answer the question
  - /screenshot help me fix this bug → show screenshot and help with the bug
---
