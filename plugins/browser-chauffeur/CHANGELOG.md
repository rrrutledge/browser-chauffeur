# Changelog

## [1.9.0] - 2026-07-02

Stops the persistent browser accumulating tabs until it crashes. The 1.8.0 orphan sweep only reclaims *registered* tabs whose creating process died — a tab opened without the `openTab` helper is never registered, so it leaked forever. This adds a backstop that catches those, and tightens the docs so ad-hoc scripts always register their tabs.

### Added
- **Age-out + count-cap backstop in `launch-browser.py`.** The tab sweep (renamed `sweep_orphan_tabs` → `sweep_tabs`) now runs three layers on every browser reuse: (1) orphan reap (unchanged — registered tab, creating process gone), (2) **age-out** — close any tab idle longer than `TAB_TTL_SECONDS` (default 15 min), and (3) **count cap** — if more than `MAX_TABS` (default 10) remain, close the least-recently-active until back at the ceiling. Tabs opened without `openTab` (never registered) are adopted into the registry on first sight so their activity can drive layers 2–3. It never closes a tab an active script still owns, and never the browser's last page. This is safe because the chauffeur browser is a dedicated automation instance, separate from the user's personal browser. Both thresholds are env-overridable (`BROWSER_CHAUFFEUR_TAB_TTL`, `BROWSER_CHAUFFEUR_MAX_TABS`).
- **Least-recently-active eviction.** The sweep evicts by last activity, not creation time, so a tab a worker keeps returning to survives while genuinely idle tabs are reaped first. Activity is tracked automatically: `openTab`/`registerTab` stamp `lastActive`, and the sweep bumps it whenever it sees a tab's URL/title change between runs — no cooperation needed from the scripts that touched the tab. New `findTab(context, predicate)` / `touchTab(context, page)` helpers (exported from `browser-chauffeur-helpers`) mark a *reused* tab active; using them is an eviction-ordering optimization, not a correctness requirement (skipping them never leaks or breaks — the backstop still holds).
- **Session-scoped tab ownership.** A tab is now owned by the **Claude session** that opened it, not the short-lived node script — a single session fires many scripts (act, screenshot, retry), so the tab must outlive any one of them. `openTab`/`touchTab` record an owner PID + session id from `BROWSER_CHAUFFEUR_OWNER_PID` / `BROWSER_CHAUFFEUR_OWNER_SESSION` (falling back to the node process when unset, i.e. ad-hoc use); the launcher `scripts/launch-session.ps1` exports them as the session's long-lived host PID + `--session-id`. The sweep keeps a tab alive as long as its owning session's window is open and reclaims it when the window closes. The count cap evicts idle/unowned tabs before any live session's tabs, touching an owned tab only as a last resort at the hard ceiling to prevent a crash. Registry field renamed `nodePid` → `ownerPid` (old entries still read).

### Changed
- SKILL.md — Phase 0 documents the three-layer, least-recently-active sweep; Phase 1 makes `openTab` the only sanctioned way to create a tab (standalone guardrail against `context.newPage()`/bare `page.goto()`) and uses `findTab` on the reuse path; "Resilient Connection" explains why an unregistered tab escapes the orphan sweep and how the backstop covers it.
- `script-quality-standards.md` — new **BANNED: Opening Tabs Without `openTab`** section.
- `templates/tab-registry.js`, `templates/script-template.js`, `HELPERS.md` — header/example text upgraded from "prefer `openTab`" to "always `openTab`, never bare `newPage`"; HELPERS.md documents `openTab`/`closeTab`/`findTab`/`touchTab`.
- `scripts/launch-session.ps1` (repo launcher) — exports `BROWSER_CHAUFFEUR_OWNER_PID` (the session's host process) and `BROWSER_CHAUFFEUR_OWNER_SESSION` (the Claude session id) so every tab a session opens is owned by that session and cleaned up when its window closes.

## [1.8.0] - 2026-06-08

Makes `connectOverCDP` reliable on the persistent profile by addressing the root cause — tab accumulation — instead of only the symptom.

### Added
- **Orphan-tab sweep.** `launch-browser.py` now reclaims tabs left behind by chauffeur scripts that crashed before cleanup. New `templates/tab-registry.js` records each created tab's CDP `targetId` and the creating process's PID in `~/.claude/browser-chauffeur/created-tabs.json`. On every reuse, the launcher closes a tracked tab **only when its creating process is gone** (a genuine orphan), via the raw CDP HTTP `/json/close` endpoint (which never auto-attaches, so it can't hang). It never touches an active session's tab, never touches tabs the user opened (those are never registered), and never closes the browser's last page. This keeps the open-target count low so `connectOverCDP` stays fast and reliable.
- **`openTab(context, url)` / `closeTab(page)` helpers** (exported from `browser-chauffeur-helpers`) bundle tab creation with registration and tab close with unregistration, so a script can't open a tab without making it reclaimable or close one without cleaning up the registry. `registerTab`/`unregisterTab` remain available as lower-level primitives. `closeTab` also parks on `about:blank` instead of closing when it's the browser's last tab, so it never exits the persistent browser.
- `script-template.js` uses `openTab`/`closeTab` (self-cleanup on every run; the sweep is the backstop for crashes).

### Fixed
- `connectOverCDP` no longer hangs indefinitely when the persistent profile is overloaded or has a wedged renderer. Playwright auto-attaches to every open target to build its page tree, and one stuck renderer blocks the whole handshake past any timeout (Playwright's own `{ timeout }` bounds only the socket connect, not target enumeration). `connectBrowser()` in `script-template.js` now races the connect against a 30s hard `Promise.race` timeout as a backstop, so it fails fast with an actionable error instead of hanging forever.
- Removed dangerous recovery guidance. The previous draft told the AI to run `cleanup-browser.py --reset` on a connect timeout — which kills the shared browser for **every** concurrent session and wipes all logins. Recovery is now non-destructive: re-run the launcher (sweeps orphans), retry once, then escalate to the user; never auto-reset the shared browser to fix one's own connect.

### Changed
- SKILL.md — Phase 0 documents the automatic sweep; new "Resilient Connection" section explains the root-cause + backstop design; Phase 3 tab-cleanup and the Phase 4 recovery branch updated for the registry and non-destructive recovery.
- `script-quality-standards.md` — scripts must use the hardened `connectBrowser()` wrapper and register/unregister tabs they create.

## [1.7.1] - 2026-06-04

### Changed
- SKILL.md Phase 3 Step 6: replaced "write a reusable script using `script-template.js`" with guidance to create an instruction-driven spec (SKILL.md with business rules, invariants, selectors, safety rails) for recurring automation needs. Browser-chauffeur creates ad-hoc scripts in `.tmp/` that adapt when selectors drift, rather than a single brittle monolith. See the `teams-message` skill as an example.

## [1.7.0] - 2026-05-29

### Fixed
- Scripts no longer fail with `Cannot find module 'playwright'` on machines where playwright is not installed in the current project. `playwright-core` (the lightweight API-only package) is now auto-installed to `~/.claude/browser-chauffeur/` on first use via the new `setup.js` script, and all templates fall back to that location when the package is not found in the local `node_modules`.
- Switched from `playwright` (full package including bundled browser binaries) to `playwright-core` (API only). Browser-chauffeur connects to an existing Edge/Chrome via CDP — it never launches browsers through Playwright — so the full package was unnecessary.

### Added
- `templates/setup.js` — new one-time setup script. Installs `playwright-core` to `~/.claude/browser-chauffeur/` if not already accessible, and creates a `browser-chauffeur-helpers` shim in the same location. The SKILL.md prerequisite check now runs this script instead of a bare `require` check.

### Changed
- SKILL.md prerequisite check replaced with `node setup.js` — self-healing, no manual `npm install` needed.
- README prerequisite section corrected: removed the incorrect "Requires the playwright MCP plugin" instruction. `playwright-core` is handled automatically.
- HELPERS.md setup section rewritten: removed the hardcoded `npm link` and environment-specific path instructions; describes the auto-install mechanism instead.

## [1.6.0] - 2026-05-28

### Changed
- **BREAKING:** `validate-target.js` renamed to `snapshot-target.js`. The script no longer decides whether the user is logged in — it navigates, waits for URL/network/DOM stability, saves a screenshot, and prints `SCREENSHOT: <path>` + `FINAL_URL: <url>`. The caller (Claude) reads the screenshot with the Read tool and decides. Replaces the previous `VALIDATION_OK` / `VALIDATION_FAILED: potential login page detected` verdict. Output marker changed from `VALIDATION_READY` to `SNAPSHOT_READY`.
- SKILL.md Phase 0 Step 2 rewritten: always read the screenshot — no false-positive recovery branch needed because there is only one decision point (the LLM looking at the screenshot).
- Added `--target-anchor` short-circuit using `locator.waitFor({ state: 'visible' })` for slow-hydrating SPAs.
- Added `waitForUrlStable` inside `snapshot-target.js` (no consecutive URL changes for 2.5s, max 15s). Handles transient SSO pages (Okta "Verifying your identity") that would otherwise be screenshotted mid-redirect.

### Removed
- **BREAKING:** `templates/login-detection.js` deleted entirely. The `isLoginPage(page)` and `waitForLoadedOrLogin(page, options)` helpers no longer export from `browser-chauffeur-helpers`.
  - **Why:** text/DOM heuristics produced both false positives (slow-hydrating SPAs flagged as login pages) and false negatives. Two real-world misses: Trello's "Sign up to see this board" wall has no password field and >100 chars so the detector said "not login"; Okta's "Verifying your identity" SSO transit page has 190 chars (above the too-short threshold) and no password field so the detector also said "not login." Both required user intervention but slipped through as `VALIDATION_OK`.
  - **Migration:** screenshot the page and let the LLM inspect it. For start-of-flow: use `snapshot-target.js` — output is a screenshot path + final URL, and the chauffeur decides. For mid-flow session-expiry checks: `await page.screenshot({ path })` + `console.log` the path; the recovery loop reads it.

## [1.5.0] - 2026-05-27

### Fixed
- `launch-browser.py` no longer crashes on Windows (cp1252 consoles) when printing success/error status. Replaced `✓` and `⚠️` with ASCII equivalents `[OK]` and `[!]`. The browser launched fine — only the success print crashed, leaving callers without PORT/PID output.

### Added
- `cleanupStaleState(page)` helper in `templates/cleanup-stale-state.js` — call at the top of any multi-step batch script to clear leftover dialogs from a previous aborted run. Detects visible `[role="dialog"]`, `[role="alertdialog"]`, and `[role="menu"]` elements, clicks safe-close buttons in priority order (`Cancel` → `Discard` → `OK` → `Close`), falls back to Escape, loops until clear. Exported from `browser-chauffeur-helpers`.
- `verifyAfterMutation(page, predicate, opts)` helper in `templates/verify-after-mutation.js` — safe post-mutation verification for SPAs with virtualized grids. Waits a settle period then retries the predicate up to N times before declaring failure. Prevents false negatives from checking DOM before the SPA's render pass flushes. Exported from `browser-chauffeur-helpers`.
- Anti-Pattern 7 in `anti-patterns.md`: **Fluent UI icon-button exact-match failures** — `getByRole('button', { name: 'Save', exact: true })` and `/^Save$/` regex filters consistently miss Fluent UI buttons because a private-use Unicode font glyph is prepended to `textContent`. Fix: use `page.locator('button:has(span.fui-Button__icon)').filter({ hasText: 'Save' }).first()`. Applies to Outlook web, Teams web, SharePoint, OneDrive.
- Anti-Pattern 8 in `anti-patterns.md`: **Confirmation dialogs without `role` attribute** — some apps render centered `<div>` dialogs with no `role`, causing `[role="dialog"]` detection to return nothing and the confirmation step to be skipped silently. Fix: geometry-based modal detector (`getBoundingClientRect` centering check + button count). Signal: primary action click produces no navigation or network request.
- SKILL.md Common Patterns now documents `cleanupStaleState` and `verifyAfterMutation` with usage guidance.

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
