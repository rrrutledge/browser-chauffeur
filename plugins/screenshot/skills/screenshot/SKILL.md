---
skill: screenshot
description: Auto-invoke when the user mentions taking a screenshot, sharing a screenshot, or references "this screenshot" without providing a file path. Loads the most recent screenshot from the Windows Screenshots folder.
instructions: |-
  Read and display the most recent screenshot across all candidate Screenshots folders.

  Candidate folders (a machine can have more than one actively receiving screenshots at once):

  - ~/OneDrive/Pictures/Screenshots 1
  - ~/Pictures/Screenshots
  - ~/OneDrive/Pictures/Screenshots
  - ~/OneDrive*/Pictures/Screenshots (OneDrive for Business - use glob to find)

  Steps:

  1. **Run the folder-scan script** to get the latest screenshot's path: `python "<plugin_dir>/skills/screenshot/scripts/find_latest_screenshot.py"` (resolve `<plugin_dir>` to this plugin's install directory).
     The script scans every candidate folder that exists, collects .png files from all of them (excluding desktop.ini), and prints the path of the single most-recently-modified file across the combined set.
  2. **Load and display the screenshot** at that path, using the Read tool.
  3. **Treat extra args as context** - if the user provided additional text in the args, treat it as a question or context about the screenshot.
---
