# Changelog

## [1.4.0] - 2026-05-27

### Fixed
- `validate-target.js` no longer false-positives on logged-in SPAs that hydrate incrementally (Outlook, Teams, large React apps). Login detection now polls for up to 8s when body text is short but no password field is present, waiting for the app shell to render before declaring failure.

### Added
- `--target-anchor=<css-selector>` flag on `validate-target.js` to short-circuit polling as soon as a known app-shell element renders (e.g. `--target-anchor='[data-app-section="CalendarModuleSurface"]'` for Outlook calendar).
- `waitForLoadedOrLogin(page, options)` helper exported from `browser-chauffeur-helpers` for any script that needs the same polling behavior. Single-shot `isLoginPage` is unchanged.

## [1.3.0] - 2026-05-19

### Fixed
- `validate-target.js` now leaves the login page open indefinitely when validation fails, instead of closing it after a fraction of a second. Users can now actually complete the login before the page disappears.
- Browser state now stored globally at `~/.claude/browser-chauffeur/state.json` (instead of `./.tmp/browser-chauffeur.json`) so all Claude instances can discover and reuse the same persistent browser session, **eliminating repeated logins to the same sites**.
- Persistent profile now at `~/.claude/browser-chauffeur/profile/` (instead of `./.tmp/cdp-profile-chauffeur/`) for global access. **Login once, reuse everywhere.**
- `launch-browser.py` now verifies the CDP port actually responds after launch. Detects Edge process sharing preventing port binding and provides troubleshooting steps.
- Browser reuse logic now only checks if CDP port responds (not PID match). Edge process sharing can change PIDs, but as long as CDP is alive, browser is reusable. Fixes instance 2+ failing to reuse instance 1's browser.

### Added
- `cleanup-browser.py` utility for profile management:
  - `--size`: Report persistent profile size and warn if over 1GB
  - `--clean-old`: Remove accumulated fresh-mode profiles from `.tmp/`
  - `--reset`: Kill persistent browser and delete profile (forces fresh login)
  - `--all`: All of the above
- Profile Management section in SKILL.md documenting when and how to reset the browser

## [1.2.0] - 2026-05-15

### Added
- Persistent browser mode (now the default) — a single browser stays running across tasks so logins and sessions survive. Each task opens its own tab and closes it when done.
- `launch-browser.py` automatically detects an already-running persistent browser and reuses it instead of launching a new one. State is tracked in `.tmp/browser-chauffeur.json`.
- Port finding integrated into `launch-browser.py` for persistent mode — no separate `find-port.py` step needed.

### Changed
- Scripts now always create a new tab (`context.newPage()`) instead of reusing an existing page. Tab is closed in `finally` with a guard to keep at least one tab open so the browser doesn't exit.
- Phase 0 simplified from 3 steps (find-port → launch → validate) to 2 steps (ensure-browser → validate).
- Phase 3 no longer kills the browser or deletes the profile — the persistent browser and its sessions stay alive.
- `--fresh` flag available on `launch-browser.py` for one-off sessions that need a clean profile (old behavior).
- Corrected "How it works" to remove incorrect claim about inheriting cookies from the Windows profile — sessions persist because the same browser profile is reused, not because cookies transfer.

## [1.1.2] - 2026-05-13

### Fixed
- `launch-browser.py` now prints `PROFILE_DIR=<path>` alongside `PID=<pid>` so callers can clean up the temp profile after use
- SKILL.md Phase 3 now mandates deleting the temp profile directory after closing the browser — Chromium does not auto-clean user data directories, causing profiles to accumulate and fill disk (discovered as ~46 GB of stale `cdp-profile-*` directories)
- Removed incorrect claim that "The browser will auto-clean on exit"

## [1.1.1] - 2026-05-11

### Fixed
- Edge welcome popup window (a separate small browser window on fresh profiles) no longer hijacks automation — context selection in `validate-target.js` and `script-template.js` now prefers the context with a real http page rather than blindly taking `contexts()[0]`
- Added `--suppress-message-center-popups` and Edge feature disables (`msEdgeSyncPromoRollout`, `msEdgeWelcomePageEnabled`) to `launch-browser.py` to reduce popup frequency

## [1.0.0] - 2026-04-30

### Added
- Initial release
- Two-mode browser automation: MCP Playwright tools (Mode A) and Node.js CDP scripts (Mode B)
- Phase 0: Automated browser detection, CDP launch, and SSO validation
- Phase 0.5: Script runner with mandatory output analysis
- Phase 1-3: Orient, step-by-step execution, and wrap-up methodology
- Phase 4: Script failure recovery loop with screenshot-driven debugging
- Phase 4.5: Script completion analysis with autonomous recovery for partial failures
- Self-healing patterns: overlay dismissal, iframe detection, screenshot-on-failure
- Full script template with connection, overlay, and verification patterns
