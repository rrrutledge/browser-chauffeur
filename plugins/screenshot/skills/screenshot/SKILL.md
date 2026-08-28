---
skill: screenshot
description: Auto-invoke when the user mentions taking a screenshot, sharing a screenshot, or references "this screenshot" without providing a file path. Loads the most recent screenshot from the Windows Screenshots folder.
instructions: |-
  Read and display the most recent screenshot from the Windows Screenshots folder.
  
  Steps:
  1. Check ALL of these candidate Screenshots folders — more than one can exist and hold live
     screenshots at once on this machine (e.g. OneDrive renamed the original "Screenshots" folder to
     "Screenshots 1" after a sync conflict, but some apps still write new files into a plain
     "Screenshots" folder alongside it):
     - ~/OneDrive/Pictures/Screenshots 1
     - ~/Pictures/Screenshots (standard Windows location, no OneDrive)
     - ~/OneDrive/Pictures/Screenshots
     - ~/OneDrive*/Pictures/Screenshots (OneDrive for Business - use glob to find)
     - ~/OneDrive*/Pictures/Screenshots* (catches any other numbered/renamed variant)
  2. Across every folder that exists, find the single most recently modified .png file (excluding
     desktop.ini) — not just the newest file in the first folder found. Write a small Python script to
     `.tmp/` that globs all candidates and compares mtimes, since this needs a loop/comparison across
     multiple directories.
  3. Use the Read tool to load and display that screenshot
  4. If the user provided additional text in the args, treat it as a question or context about the screenshot
  
  Example invocations:
  - /screenshot → just show the latest screenshot
  - /screenshot what's this error? → show screenshot and answer the question
  - /screenshot help me fix this bug → show screenshot and help with the bug
---
