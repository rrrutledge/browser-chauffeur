---
description: Close this session and its Windows Terminal tab in one shot, no double "exit"
---

Close this Claude Code session and its hosting terminal tab together, the same way a
drainer worker self-closes when it's done.

Run, via the Bash tool:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/resume-sessions/scripts/end-session.py"
```

This fires the plugin's `SessionEnd` hooks with the real payload (so the live-session
registry is cleaned up correctly), then kills the tab's hosting process tree. If
`CLAUDE_HOST_PID` isn't set (e.g. this tab wasn't launched through a profile that sets
it), the script prints why and exits without closing anything — in that case just tell
the user and let them close the tab normally with `exit`.

Do not narrate or summarize before running this — there's no session left to report
back to once it fires.
