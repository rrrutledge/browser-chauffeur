---
skill: screenshot
description: Auto-invoke when the user mentions taking a screenshot, sharing a screenshot, or references "this screenshot" without providing a file path. Loads the most recent screenshot from the Windows Screenshots folder.
instructions: |-
  Read and display the most recent screenshot across all candidate Screenshots folders.

  Candidate folders (a machine can have more than one actively receiving screenshots at once,
  e.g. after a OneDrive sync conflict renames one to "Screenshots 1" - never assume only one is live):
  - ~/OneDrive/Pictures/Screenshots 1
  - ~/Pictures/Screenshots
  - ~/OneDrive/Pictures/Screenshots
  - ~/OneDrive*/Pictures/Screenshots (OneDrive for Business - use glob to find)

  Steps:
  1. Run `python "<plugin_dir>/skills/screenshot/scripts/find_latest_screenshot.py"` (resolve
     `<plugin_dir>` to this plugin's install directory). The script scans every candidate folder
     that exists, collects .png files from all of them (excluding desktop.ini), and prints the
     path of the single most-recently-modified file across the combined set.
  2. Use the Read tool to load and display the screenshot at that path.
  3. If the user provided additional text in the args, treat it as a question or context about the screenshot.

  Example invocations:
  - /screenshot → just show the latest screenshot
  - /screenshot what's this error? → show screenshot and answer the question
  - /screenshot help me fix this bug → show screenshot and help with the bug
---
