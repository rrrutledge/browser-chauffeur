---
name: browser-chauffeur
description: REQUIRED for ALL browser automation — both creating NEW scripts AND running existing ones. When user asks to create/write/build a browser automation script, invoke this skill BEFORE writing any code. When running scripts, this skill handles browser detection, CDP setup, and autonomous error recovery (screenshot → diagnose → fix → retry). Never create or run browser automation outside this skill.
allowed-tools: Bash, Write, Edit, Read
---

# Browser Chauffeur

You are operating the browser on the user's behalf. You are the chauffeur — you drive, they direct. Your job is to reach the destination reliably, adapt when the route changes, and never give up without trying an alternate route first.

## Two Modes of Operation

**Mode A — MCP Playwright tools** (`browser_navigate`, `browser_snapshot`, `browser_screenshot`, etc.): Use for public websites or apps that don't require corporate SSO. These open a fresh Chromium window with no existing login session.

**Mode B — Node.js CDP script** via Bash: Use for corporate SSO apps (Teams, SharePoint, Outlook, internal tools). Write a `scripts/<task>.js` file using the `playwright` npm package connected to Chrome or Edge via CDP, then run it with `node scripts/<task>.js`.

**Choose Mode B when:**
- The target app uses Azure AD / Entra ID / corporate SSO
- A fresh browser would land on a login page that requires MFA or corporate credentials
- The user is already logged in to Chrome or Edge

## Prerequisite Check

This skill requires the **playwright MCP plugin** for Mode A. If `browser_snapshot` or related tools are unavailable, tell the user:

"The browser-chauffeur skill requires the playwright MCP plugin. Please install it with: `/plugin marketplace add playwright`"

For Mode B, verify `node` and the `playwright` npm package are available:
```bash
node --version && node -e "require('playwright'); console.log('ok')"
```

---

## Phase 0: Browser Launch (do this before Phase 1)

**Always launch a fresh browser instance** — never reuse an active browser. This prevents interfering with the user's browsing while still having SSO credentials (Windows profile transfers cookies).

**Step 1 — Find an available CDP port**

```bash
for port in 9222 9223 9224 9225; do
  nc -z localhost $port 2>/dev/null || { echo "Port $port available"; break; }
done
```

If all ports busy, use 9226.

**Step 2 — Detect installed browsers**

```bash
powershell -NoProfile -Command "Get-Process msedge,chrome -ErrorAction SilentlyContinue | Select-Object -Unique Name | Format-Table -AutoSize"
```

Note **all** installed browsers: `msedge` → Edge available, `chrome` → Chrome available. If neither, check if executables exist (see Step 3).

**Step 3 — Launch fresh browser with unique temp profile**

See `templates/launch-browser.sh` for the full launch script (Edge-first with Chrome fallback, unique profile dir, Edge sidebar disabled, PID capture). Key constraints:

- Use a **unique profile directory** for each session to avoid conflicts. Use `-PassThru` to capture the browser PID for safe cleanup later.
- **Windows path format:** The `--user-data-dir` argument requires Windows-style backslash paths (e.g., `C:\\Users\\...`). Forward-slash Unix paths from Git Bash silently fail, causing CDP to not bind.
- **Edge sidebar hijack:** Edge with Microsoft 365 accounts has a built-in Teams/Chat sidebar that intercepts Teams URLs into a popup widget instead of a full-page tab. Always disable it with `--disable-features` flags and pass the target URL as a positional argument to open it as a full tab.

Wait 3-5s for browser startup, then verify: `curl -s http://localhost:$PORT/json/version`

**Save the PID** — you will need it in Phase 3 to close only the browser you launched, without killing the user's personal browser instances.

**Why fresh browser works:** Windows profile transfers SSO cookies to the temp profile, so corporate apps authenticate automatically without manual login.

**Overlay dismissal:** A fresh browser profile will often show first-run overlays (cookie consent banners, "What's new" modals) that block the real UI. Dismiss these before waiting for app-specific elements. See **Overlay Dismissal** below.

**Known quirk — Edge sync dialog:** The "We are now syncing your browsing data" dialog on fresh Edge profiles is rendered in Edge's browser chrome layer, outside the page DOM. Playwright cannot see or dismiss it. It does **not** block script execution — scripts can interact with page elements behind it. Do not waste time trying to close it.

**Step 4 — Validate SSO session (for corporate apps)**

Once CDP is available, verify the browser can actually reach the target app — not just that it launched. See `templates/validate-sso.js` for a script that navigates to the target URL and checks whether the app loaded or a login page appeared.

- If validation succeeds → record the CDP port. This is the port you will pass to scripts via `--cdp-port`.
- If validation fails (login page) → use `AskUserQuestion` to prompt the user to sign in (see **User Intervention** section), then re-validate.

**The CDP port you validate here is what you pass to scripts.** Scripts do not perform browser detection or SSO validation — that is your job during Phase 0.

---

## Phase 0.5: Running Existing Scripts

**The script is the directions. This skill is the chauffeur.** Never run a Mode B script directly and walk away — always have this skill loaded so the recovery loop is active.

When another skill needs to run a browser automation script, it should invoke browser-chauffeur first. The pattern:

1. **Invoke this skill** before running the script
2. **Complete Phase 0** to get a validated CDP port
3. **Run the script** via Bash: `node scripts/<task>.js --cdp-port=<port>`
4. **ALWAYS do Phase 4 analysis** — parse the output for errors regardless of exit code
5. **If errors detected** — autonomously enter the Phase 4 recovery loop (diagnose, fix, re-run)
6. **If 100% success** — report results, then **close the browser** (close pages you opened; the browser exits when no pages remain)
7. **If recovery exhausted** — show diagnostics and ask for help

**Critical:** Exit code 0 ≠ success. Many scripts complete with errors in their output. Phase 4 analysis is MANDATORY after every script run, not optional.

**Other skills should reference this skill minimally.** For example, a skill that extracts data from a web app should say: "Invoke the browser-chauffeur skill to run `node scripts/<task-name>.js`" — nothing more. Browser-chauffeur handles all error detection, recovery, and reporting automatically.

This ensures the AI is always watching the road, not just handing off directions and hoping for the best.

---

## Phase 1: Orient

Before touching anything:

1. Navigate to the target page or state
2. **Mode A:** Run `browser_snapshot` to read the accessibility tree — this gives you element refs you can act on
3. **Mode B:** Use `page.evaluate(() => document.body.innerText)` or enumerate `page.frames()` to read page state
4. If the snapshot doesn't clarify structure (complex visual layout), take a screenshot with `browser_screenshot` (Mode A) or `page.screenshot()` (Mode B) and read the image with the Read tool
5. Identify the first action needed

**Never act before orienting.** You cannot guess selectors on a page you haven't inspected.

### Iframe detection (critical for SPAs)

Many enterprise apps (Teams, SharePoint) render content in iframes. If `document.body.innerText` returns almost nothing (< 200 chars) on a page that should have content:

```javascript
// In a Mode B script:
const frames = page.frames();
console.log('Frames:', frames.map(f => f.url()));
for (const f of frames) {
  const text = await f.evaluate(() => document.body.innerText).catch(() => '');
  if (text.length > 200) console.log('Frame', f.url(), text.slice(0, 500));
}
```

Find the frame with the real content and target all locators at that frame object instead of the page. Note: `frame.route()` does not exist — routing only works on the page object.

---

## Phase 2: Step-by-Step Execution

For each step in the desired flow:

1. **Interact** — Mode A: use refs from the most recent snapshot (`browser_click`, `browser_type`, etc.). Mode B: use Playwright locators (`page.getByRole(...)`, `frame.locator('[aria-label="..."]')`)

2. **Screenshot after dropdown/menu clicks** — **CRITICAL:** After clicking any button that should reveal a dropdown menu, context menu, or modal dialog:
   - Wait briefly (500ms-1s) for the UI to appear
   - Take a screenshot with `page.screenshot({ path: '.tmp/diag-after-click.png' })`
   - Read the screenshot with the Read tool to SEE what menu items are actually visible
   - Query the DOM for menu items AFTER you've visually confirmed the menu is open

   **Why:** DOM queries alone can miss visual menus. The screenshot shows you exactly what the user would see, including menu items, their text, and layout. This prevents blindly clicking buttons and querying for items that may not be rendered yet or may be in unexpected locations.

3. **Verify** — re-read page state immediately after. Confirm the expected change happened: new element appeared, field value set, URL changed, success message shown. If the page state after verification is unexpected (CAPTCHA, login page, error page, or an unrecognized screen), treat it as a blocker — if it requires human action (CAPTCHA, login), follow the **User Intervention** section; otherwise apply Phase 4 recovery.

4. **If blocked** — re-snapshot/re-read immediately to diagnose. Common blockers:
   - Modal or overlay in front of the target → dismiss it first (see **Overlay Dismissal**), then retry
   - Element not yet rendered → wait with `locator.waitFor()` or `page.waitForSelector()`
   - Stale ref (element re-rendered since last snapshot) → re-snapshot and get fresh ref

5. **If layout-dependent** — take a screenshot and read it with the Read tool to see visual context

6. Move to the next step **only after** the current step is confirmed

---

## Phase 3: Wrap Up

1. Take a final snapshot or read confirming the full flow succeeded
2. **Close the browser.** Mode A: call `browser_close`. Mode B: kill only the browser PID you saved in Phase 0 Step 3 with `powershell -NoProfile -Command "Stop-Process -Id <PID> -Force"`. **Never** kill all browser processes (e.g., `Get-Process msedge | Stop-Process`) — that destroys the user's personal browser sessions.
3. **Clean up temp profile** (optional): The browser will auto-clean on exit, but you can manually remove `.tmp/cdp-profile-*` directories to free disk space.
4. Report what was accomplished to the user. Base your report on what you read from the final page state — do not summarize from memory or inference. If specific values were requested (a title, a field value, a count), quote them directly from the page content.
5. If the user asks for a reusable script, write it using `templates/script-template.js`.

**Exception:** If the task ended in a failure that requires user intervention (Phase 4 escalation), leave the browser open so the user can see and interact with the current state.

---

## User Intervention — Proper Alerting (MANDATORY)

Sometimes the browser hits a blocker that only a human can resolve. These all fall into one category: **the user needs to go do something in the browser window.** Whether it's a CAPTCHA, a login page, an MFA prompt, or a cookie consent wall that can't be auto-dismissed — the response is the same.

**NEVER just log to the terminal and hope the user sees it.** The user may not be watching terminal output, especially during long-running batch scripts. You MUST use `AskUserQuestion` to create a visible, blocking prompt.

### What triggers user intervention

- **CAPTCHAs / human verification** — Cloudflare "Verify you are human", Zillow "Press & Hold", reCAPTCHA, hCaptcha, Arkose Labs. Cannot be solved programmatically. Do NOT retry or switch browsers — escalate immediately.
- **Login pages** — SSO didn't carry over, or the session expired mid-run. You may try the other browser first (Edge/Chrome fallback), but if that also shows a login page, escalate immediately.
- **MFA prompts** — requires the user's phone/authenticator.
- **Unresolvable consent/terms walls** — cookie banners or terms pages that can't be auto-dismissed by the overlay dismissal pattern.

### Required `AskUserQuestion` pattern

```
AskUserQuestion with options:
- "Done, I solved it" — user completed the action
- "Can't find the browser" — user needs help locating the window
```

Include in the question text: what site triggered the blocker, what kind of challenge it is (CAPTCHA, login, MFA), and that they need to switch to the browser window.

### If user can't find the browser

Attempt to bring the window to the foreground, then re-prompt with `AskUserQuestion`.

### Monitoring long-running scripts

When running a batch script that may encounter these blockers mid-run:

1. Set up a **Monitor** on the script's output watching for intervention keywords (`CAPTCHA DETECTED`, `VALIDATION_FAILED`, `login page`, `Sign in`, etc.)
2. When the Monitor fires, **immediately use `AskUserQuestion`** — don't wait for the script to finish
3. After the user confirms resolution, verify the script continued past the blocker

### After the user resolves the blocker

- Leave the browser open — the user needs the same session
- Re-run or continue the script — the browser session should now be past the blocker
- If the same blocker reappears, escalate again with `AskUserQuestion` — don't silently retry

---

## Phase 4: Failure Recovery (ALWAYS run after a script exits)

When a Mode B script completes — **regardless of exit code** — analyze the output and recover autonomously. **Exit code 0 ≠ success.** Many scripts complete with errors in their output. Trust verification output and visual evidence, not exit codes. **Don't ask permission to debug — that's your job as the chauffeur.**

### Step 1: Parse output for success/failure signals

Read the full output and categorize:

- **Explicit success** — `Verification passed`, `✅`, `All checks passed` AND no error patterns → proceed to reporting.
- **Human action required** (see **User Intervention**) — diagnostic screenshot shows a CAPTCHA, login page, or MFA prompt; or output contains `CAPTCHA DETECTED`, `VALIDATION_FAILED`, or similar → use `AskUserQuestion` immediately. Do NOT retry autonomously.
- **Explicit failure** — `Verification FAILED`, `VERIFY FAIL:`; error counts (`5 errors`, `3 collision(s)`, `12 errors remain`); error keywords (`Error:`, `still present`, `not found`, `timeout`, `could not`); or items reported as "still present" or "not moved/deleted" → trigger autonomous recovery (Step 2).
- **Ambiguous (missing verification)** — no "Verification passed" or "Verification FAILED" in output, but has completion indicators (`Done`, `Summary:`, task-specific output) → likely an older script without verification. If output looks clean (no errors/exceptions), treat as success. If output contains exceptions or is suspiciously short (< 50 chars), investigate.
- **Crashed/incomplete** — exception stack trace in output, output ends mid-step (no completion message), or very short output with no summary → trigger autonomous recovery (Step 2).

### Step 2: Autonomous recovery loop

When errors are detected, **you are the debugger**. Do not show the user an error and ask what to do. Diagnose, fix, and re-run. Don't ask user permission — enter the loop.

1. **Read the diagnostic screenshot** — scripts save screenshots to `.tmp/diag-*.png` on failure. Use the Read tool to view the image. This tells you what the browser was actually showing: an overlay, a login page, a CAPTCHA, a changed UI, or something else entirely. Take additional screenshots of the failure page if needed.

2. **Diagnose the cause** from what you see:
   - **CAPTCHA, login page, or MFA prompt** → requires human action. Follow **User Intervention** — use `AskUserQuestion` immediately. For login pages, you may also try the other browser (Edge/Chrome fallback) first, but if that also shows a login page, escalate.
   - **Overlay or modal blocking the UI** → add dismissal logic to the script (see **Overlay Dismissal**), re-run.
   - **UI changed** (different label, restructured DOM, new element) → inspect the current page state to find the new selector, update the script, re-run.
   - **New required step** (e.g., a consent prompt, a "What's new" tour) → add handling for it, re-run.
   - **Selector timing issues** (element not yet visible), **elements scrolled out of view**, or **the expected element is in a different frame** → take a fresh screenshot, read it, find the correct selector or frame.

3. **Use diagnostic patterns** from `templates/diagnostic-patterns.js` to inspect failing selectors — element visibility test, button enumeration, timing comparisons.

4. **Fix the script** — edit the failing section based on what you diagnosed. Don't guess — base every fix on what you actually saw in the screenshot or page state.

5. **Re-run the script** — execute it again and verify it passes the point that previously failed.

6. **Repeat** through the loop until verification passes OR you've exhausted options (3+ iterations with different approaches, or you've tried both browsers and dismissed all visible overlays). Then escalate via `AskUserQuestion` (see **User Intervention**) explaining what you found and what you need.

### Step 3: Reporting

**Only report to user when:**
- ✅ **100% success achieved** → "Fixed N issues: [brief summary]. Verification now passing."
- ❌ **Exhausted all recovery options** → Show diagnostics, explain what you tried, what you found, ask for help.

**Rule:** Never tell the user "the script failed." Always read the diagnostic screenshot, diagnose, fix, and retry at least once before involving the user.

### Common error patterns (signal "autonomous recovery needed")

```
Error: Could not X
VERIFY FAIL: "Event name" still present
Verification FAILED — some events still remain
Delete button not found in popup
Timeout 30000ms exceeded
could not find Start date field
X moved, Y errors
Summary shows non-zero error counts
```

### When running scripts from other skills

If another skill runs a Mode B script and it fails, that skill should follow this same recovery loop. The script saves diagnostic screenshots specifically so that whatever is running it — whether browser-chauffeur or another skill — can read the screenshot with the Read tool, see what went wrong, and fix it autonomously. The screenshots are not for the user; they are for you.

---

## Phase 5: Script Validation (when creating Mode B scripts)

**CRITICAL:** When you write a new browser automation script, **immediately validate it before running** or reporting completion. Scan `scripts/<task>.js` for violations of **Script Quality Standards** (below): fixed delays (`waitForTimeout`, `setTimeout`), missing verification code, CSS class selectors, or missing browser connection logic. If you find any, edit the script to fix them, explain what was wrong and what you fixed, then re-scan to confirm clean. **Do not ask permission** — violations are always wrong.

---

## Common Patterns

**Overlay Dismissal** — A fresh browser profile will show first-run overlays — Edge sync prompts ("We are now syncing your browsing data"), cookie consent banners, "What's new" modals. These block the real UI and cause element waits to time out. See `templates/overlay-dismissal.js` for the `dismissOverlays(page)` helper. Call it immediately after navigating to the target app, **before** waiting for app-specific elements. Include it in every Mode B script.

**Screenshot on Failure** — Scripts save screenshots to `.tmp/diag-*.png` on failure so the recovery loop can read them. See `templates/screenshot-on-failure.js` for the `screenshotOnFailure(context, label)` helper. Use it in catch blocks when the app fails to load, and in any browser fallback loop so each failed attempt produces a screenshot for debugging.

**Common Anti-Patterns** — See `anti-patterns.md` for detailed examples covering: text-based filter ambiguity, `page.evaluate` clicks not triggering React/Fluent UI synthetic events, diagnosing click failures from screenshots not error text, phantom `display:none` dialogs left in the DOM, and role-vs-tag selector gaps (semantic HTML buttons that aren't `[role="button"]`).

---

## Key Rules

**Selectors:** Prefer `aria-label`, `role`, and text-based selectors over CSS classes. CSS classes change across deployments and tenants; semantic attributes don't.

**Strict mode:** A locator matching multiple elements throws. Prefer `getByRole('button', { name: '...' })` over bare `aria-label` when both a wrapper `div` and the `button` itself share the same label. Use `.first()` only when you've confirmed the elements are genuinely equivalent.

**Waits:** Never use fixed delays — this includes both Playwright's `waitForTimeout` and raw `new Promise(r => setTimeout(r, N))`. Use `locator.waitFor()`, `page.waitForURL()`, `page.waitForLoadState()`, or `page.waitForFunction()` instead. Fixed delays make scripts slower when the page is fast and still flaky when it's slow. The only acceptable `setTimeout` is a short poll interval (≤300 ms) inside an active loop that exits as soon as a condition is met.

**Verification:** Always re-read page state after save/submit actions. A form can silently fail to save. Trust nothing without checking.

**Variant UIs:** The same application can render completely different DOM on different tenants or account types. When a selector fails in a new context, re-snapshot there and find the equivalent element — never assume one tenant's refs work on another.

**Overlay detection:** When a click doesn't land, snapshot first to check for modal overlays or portal elements blocking the target. Dismiss them before retrying.

**Two-pass element reveal:** Some UIs hide form inputs behind clickable summary rows. If expected inputs aren't in the snapshot, click the summary row, re-snapshot, then find the revealed inputs.

**Hard verification after mutating actions:** After any create, update, or delete action, navigate away from the page and back (or close and reopen it) to confirm the change persisted server-side. DOM changes alone (element disappearing, success toast appearing) do NOT prove the server processed the action — the UI may have updated optimistically while the API call silently failed or never fired. Never report a mutating action as successful until you've seen the result survive a fresh page load.

**Snapshot vs Screenshot:**
- Snapshot/innerText is primary — gives actionable content and element structure
- Screenshot is the fallback — use when spatial/visual layout matters (diagnosing why a click doesn't land, reading a visual overlay)

---

## Script Quality Standards

**All browser automation scripts must comply with these requirements.** Reference this section when writing AND when validating scripts (see Phase 5). See `templates/script-template.js` for a complete reference script that satisfies all of these.

### ❌ BANNED: Fixed Delays

**Never use:**
```javascript
await page.waitForTimeout(1000);
await new Promise(r => setTimeout(r, 1000));
```

**Why:** Wastes time when ready sooner, fails when page is slow. You don't know what you're waiting for.

**Always use element/condition-based waits:**
```javascript
await locator.waitFor({ state: 'visible', timeout: 5000 });
await page.waitForLoadState('networkidle');
await page.waitForFunction(() => document.readyState === 'complete');
```

**Exception:** Short poll loops (≤300ms interval) with a deadline when no waitable locator exists.

### ✅ REQUIRED: Verification Code

**Every script must output explicit success/failure:**
```javascript
// ❌ WRONG - no verification
console.log('Done.');

// ✅ CORRECT - explicit verification
if (failCount === 0) {
  console.log('Verification passed ✅');
} else {
  console.error(`Verification FAILED - ${failCount} errors`);
}
```

This enables Phase 4 autonomous recovery.

### ✅ REQUIRED: Semantic Selectors

Use `aria-label`, `role`, visible text — **never CSS class selectors** (they change across deployments).

### ✅ REQUIRED: Browser Connection

Scripts receive `--cdp-port=<port>` from Claude. Connect with `chromium.connectOverCDP('http://localhost:<port>')` — no browser detection logic in scripts. They do **not** contain browser detection, fallback, or SSO validation — that is handled by Claude interactively during Phase 0 before any script runs.

### ✅ REQUIRED: Navigation

Scripts must navigate to their target URL themselves — don't assume the browser is already there. Since Phase 0 already validated the SSO session, navigating again is just a reload and keeps the script self-contained.

### Additional Requirements

- `console.log` after each major step for progress tracking
- Check `page.frames()` when `body.innerText` is unexpectedly short
- Use `page.route()` for request interception (not `frame.route()` — it doesn't exist)
- Include `dismissOverlays(page)` after navigation (see **Overlay Dismissal**)
- Save a diagnostic screenshot in catch blocks (see **Screenshot on Failure**)
