---
skill: screenshot
description: Auto-invoke when the user mentions taking a screenshot, sharing a screenshot, or references "this screenshot" without providing a file path. Loads the most recent screenshot from the Windows Screenshots folder.
instructions: |-
  Read and display the most recent screenshot from the Windows Screenshots folder.
  
  Steps:
  1. Auto-detect the Screenshots folder by checking these locations in order:
     - ~/OneDrive/Pictures/Screenshots 1 (this machine's actual OneDrive screenshot folder — OneDrive
       renamed the original "Screenshots" folder to "Screenshots 1" after a sync conflict; this is the
       one the OS actually writes new screenshots to)
     - ~/Pictures/Screenshots (standard Windows location, no OneDrive)
     - ~/OneDrive/Pictures/Screenshots (OneDrive personal, no " 1" suffix — older/other machines)
     - ~/OneDrive*/Pictures/Screenshots (OneDrive for Business - use glob to find)
  2. Find the latest .png file in the Screenshots folder (excluding desktop.ini)
  3. Use the Read tool to load and display the screenshot
  4. If the user provided additional text in the args, treat it as a question or context about the screenshot
  
  Use Bash with glob patterns to find the folder:
  - First try: test -d "$USERPROFILE/OneDrive/Pictures/Screenshots 1"
  - Then try: test -d "$USERPROFILE/Pictures/Screenshots"
  - Then try: ls -d "$USERPROFILE"/OneDrive*/Pictures/Screenshots 2>/dev/null | head -1
  
  Example invocations:
  - /screenshot → just show the latest screenshot
  - /screenshot what's this error? → show screenshot and answer the question
  - /screenshot help me fix this bug → show screenshot and help with the bug
---
