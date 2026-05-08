#!/usr/bin/env bash
# Browser launch reference for Mode B (CDP scripts).
#
# Variables expected from caller: $PORT (CDP port), $TARGET_URL (initial URL).
#
# Use a unique profile directory for each session to avoid conflicts. Use
# -PassThru to capture the browser PID for safe cleanup later.
#
# Windows path format: --user-data-dir requires Windows-style backslash paths
# (e.g., C:\\Users\\...). Forward-slash Unix paths from Git Bash silently fail,
# causing CDP to not bind.
#
# Edge sidebar hijack: Edge with Microsoft 365 accounts has a built-in
# Teams/Chat sidebar that intercepts Teams URLs into a popup widget instead of
# a full-page tab. Disable it with --disable-features flags and pass the target
# URL as a positional argument to open it as a full tab.

# Generate unique profile path (Windows-style backslashes required)
TIMESTAMP=$(date +%s)
PROFILE_DIR="C:\\path\\to\\project\\.tmp\\cdp-profile-$TIMESTAMP"

# Try Edge first (usually has better Windows SSO integration)
if [ -f "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" ]; then
  BROWSER_PID=$(powershell -NoProfile -Command "\$proc = Start-Process 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -ArgumentList '--remote-debugging-port=$PORT','--user-data-dir=$PROFILE_DIR','--no-first-run','--no-default-browser-check','--disable-features=msEdgeSidebarV2,msEdgeSidebar,msEdgeChatAndNotification,msTeamsLeftChrome,EdgeSidebar,msEdgeSidebarPwaIntegration','--start-maximized','$TARGET_URL' -PassThru; \$proc.Id")
  echo "Launched Edge on port $PORT (PID $BROWSER_PID)"

# Fallback to Chrome
elif [ -f "C:/Program Files/Google/Chrome/Application/chrome.exe" ]; then
  BROWSER_PID=$(powershell -NoProfile -Command "\$proc = Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=$PORT','--user-data-dir=$PROFILE_DIR','--no-first-run','--no-default-browser-check','--start-maximized','$TARGET_URL' -PassThru; \$proc.Id")
  echo "Launched Chrome on port $PORT (PID $BROWSER_PID)"

else
  echo "No supported browser found - use Mode A (MCP tools)"
  exit 1
fi
