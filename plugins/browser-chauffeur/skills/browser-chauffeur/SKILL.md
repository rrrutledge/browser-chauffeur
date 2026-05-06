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

Note **all** installed browsers:
- `msedge` → Edge is available
- `chrome` → Chrome is available
- neither → check if executables exist (see Step 3)

**Step 3 — Launch fresh browser with unique temp profile**

Use a **unique profile directory** for each session to avoid conflicts:

```bash
# Generate unique profile path
TIMESTAMP=$(date +%s)
PROFILE_DIR="$(pwd)/.tmp/cdp-profile-$TIMESTAMP"

# Try Edge first (usually has better Windows SSO integration)
if [ -f "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" ]; then
  powershell -NoProfile -Command "Start-Process 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -ArgumentList '--remote-debugging-port=$PORT','--user-data-dir=$PROFILE_DIR','--no-first-run','--no-default-browser-check'"
  echo "Launched Edge on port $PORT"
  
# Fallback to Chrome
elif [ -f "C:/Program Files/Google/Chrome/Application/chrome.exe" ]; then
  powershell -NoProfile -Command "Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=$PORT','--user-data-dir=$PROFILE_DIR','--no-first-run','--no-default-browser-check'"
  echo "Launched Chrome on port $PORT"
  
else
  echo "No supported browser found - use Mode A (MCP tools)"
  exit 1
fi
```

Wait 3s for browser startup, then verify: `curl -s http://localhost:$PORT/json/version`

**Why fresh browser works:** Windows profile transfers SSO cookies to the temp profile, so corporate apps authenticate automatically without manual login.

**Overlay dismissal:** A fresh browser profile will often show first-run overlays (Edge sync prompts, cookie consent banners, "What's new" modals) that block the real UI. Dismiss these before waiting for app-specific elements. See the overlay dismissal pattern in the Script Output section.

**Step 4 — Validate SSO session (for corporate apps)**

Once CDP is available, verify the browser can actually reach the target app — not just that it launched. Write and run a short validation script that navigates to the target URL and checks whether the app loaded or a login page appeared:

```javascript
const { chromium } = require('playwright');
async function validate() {
  const browser = await chromium.connectOverCDP('http://localhost:<port>');
  const context = browser.contexts()[0] || await browser.newContext();
  const page = await context.newPage();
  await page.goto('<target-url>', { waitUntil: 'domcontentloaded', timeout: 30000 });
  const text = await page.evaluate(() => document.body.innerText);
  // Check for login page indicators
  if (text.includes('Sign in') || text.includes('Enter your password') || text.length < 100) {
    console.log('VALIDATION_FAILED: landed on login page');
  } else {
    console.log('VALIDATION_OK');
  }
  await page.close();
  await browser.close();
}
validate().catch(e => { console.error(e.message); process.exit(1); });
```

- If validation succeeds → record the CDP port. This is the port you will pass to scripts via `--cdp-port`.
- If validation fails (login page) → ask the user to sign in manually in the browser window, then re-validate.

**The CDP port you validate here is what you pass to scripts.** Scripts do not perform browser detection or SSO validation — that is your job during Phase 0.

---

## Running Existing Scripts (Phase 0.5)

**The script is the directions. This skill is the chauffeur.** Never run a Mode B script directly and walk away — always have this skill loaded so the recovery loop is active.

When another skill needs to run a browser automation script, it should invoke browser-chauffeur first. The pattern:

1. **Invoke this skill** before running the script
2. **Complete Phase 0** to get a validated CDP port
3. **Run the script** via Bash: `node scripts/<task>.js --cdp-port=<port>`
4. **ALWAYS do Phase 4.5 analysis** — parse the output for errors regardless of exit code
5. **If errors detected** — autonomously enter Phase 4.5 recovery loop (diagnose, fix, re-run)
6. **If 100% success** — report results, then **close the browser** (close pages you opened; the browser exits when no pages remain)
7. **If recovery exhausted** — show diagnostics and ask for help

**Critical:** Exit code 0 ≠ success. Many scripts complete with errors in their output. Phase 4.5 analysis is MANDATORY after every script run, not optional.

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

3. **Verify** — re-read page state immediately after. Confirm the expected change happened: new element appeared, field value set, URL changed, success message shown. If the page state after verification is unexpected (CAPTCHA, error page, or an unrecognized screen), treat it as a blocker and apply Phase 4 recovery before proceeding.

4. **If blocked** — re-snapshot/re-read immediately to diagnose. Common blockers:
   - Modal or overlay in front of the target → dismiss it first, then retry
   - Element not yet rendered → wait with `locator.waitFor()` or `page.waitForSelector()`
   - Stale ref (element re-rendered since last snapshot) → re-snapshot and get fresh ref
   
5. **If layout-dependent** — take a screenshot and read it with the Read tool to see visual context

6. Move to the next step **only after** the current step is confirmed

---

## Phase 3: Wrap Up

1. Take a final snapshot or read confirming the full flow succeeded
2. **Close the browser.** Mode A: call `browser_close`. Mode B: close all pages you opened — if they were the only pages, the browser process exits on its own. Don't leave the browser running after the task is done.
3. **Clean up temp profile** (optional): The browser will auto-clean on exit, but you can manually remove `.tmp/cdp-profile-*` directories to free disk space.
4. Report what was accomplished to the user. Base your report on what you read from the final page state — do not summarize from memory or inference. If specific values were requested (a title, a field value, a count), quote them directly from the page content.
5. If the user asks for a reusable script, write it using the Script Output template below.

**Exception:** If the task ended in a failure that requires user intervention (Phase 4 escalation), leave the browser open so the user can see and interact with the current state.

---

## Phase 4: Script Failure Recovery

When a script fails, **you are the debugger**. Do not show the user an error and ask what to do. Diagnose it yourself, fix it, and re-run.

### The recovery loop

1. **Read the diagnostic screenshot** — scripts save screenshots to `.tmp/diag-*.png` on failure. Use the Read tool to view the image. This tells you what the browser was actually showing: an overlay, a login page, a CAPTCHA, a changed UI, or something else entirely.

2. **Diagnose the cause** from what you see:
   - **Overlay or modal blocking the UI** → add dismissal logic to the script (see overlay dismissal pattern), re-run
   - **Login page** → the browser didn't have SSO credentials. Close it, try the other browser (Edge/Chrome fallback), re-run
   - **UI changed** (different label, restructured DOM, new element) → inspect the current page state to find the new selector, update the script, re-run
   - **New required step** (e.g., a consent prompt, a "What's new" tour) → add handling for it, re-run
   - **The page loaded but the expected element isn't there** → take a fresh screenshot, read it, check if the app changed its layout or the element is in a different frame

3. **Fix the script** — edit the failing section based on what you diagnosed. Don't guess — base every fix on what you actually saw in the screenshot or page state.

4. **Re-run the script** — execute it again and verify it passes the point that previously failed.

5. **Repeat if needed** — a fix may reveal the next failure. Keep going through the loop until the script completes or you've exhausted all browser options.

6. **Escalate only as a last resort** — if you've tried both browsers, dismissed all visible overlays, read multiple screenshots, and the blocker requires user input (new credentials, MFA prompt, policy change), then explain what you found and what you need. Show the screenshot in your explanation.

**Rule:** Never tell the user "the script failed." Always read the diagnostic screenshot, diagnose, fix, and retry at least once before involving the user.

### When running scripts from other skills

If another skill runs a Mode B script and it fails, that skill should follow this same recovery loop. The script saves diagnostic screenshots specifically so that whatever is running it — whether browser-chauffeur or another skill — can read the screenshot with the Read tool, see what went wrong, and fix it autonomously. The screenshots are not for the user; they are for you.

---

## Phase 4.5: Script Completion Analysis (ALWAYS do this after script exits)

When a Mode B script completes (regardless of exit code), **ALWAYS analyze the output**:

### Step 1: Parse Output for Success/Failure Signals

Read the full output and categorize:

**Explicit success:**
- Contains: `Verification passed`, `✅`, `All checks passed`
- AND no error patterns present
- → Script succeeded, proceed to reporting

**Explicit failure:**
- Contains: `Verification FAILED`, `VERIFY FAIL:`
- Error counts: `5 errors`, `3 collision(s)`, `12 errors remain`
- Error keywords: `Error:`, `still present`, `not found`, `timeout`, `could not`
- Items reported as "still present" or "not moved/deleted"
- → Trigger autonomous recovery (Step 2)

**Ambiguous (missing verification):**
- No "Verification passed" or "Verification FAILED" in output
- BUT has completion indicators: `Done`, `Summary:`, task-specific output
- → Likely an older script without verification. If output looks clean (no errors/exceptions), treat as success. If output contains exceptions or is suspiciously short (< 50 chars), investigate.

**Crashed/incomplete:**
- Exception stack trace in output
- Output ends mid-step (no completion message)
- Very short output with no summary
- → Trigger autonomous recovery (Step 2)

### Step 2: Autonomous Recovery Decision

**IF errors detected** → Enter autonomous recovery loop (do NOT ask user):

1. **Take screenshots** of the browser state on the failure page
2. **Create diagnostic scripts** to inspect failing selectors (see examples below)
3. **Read screenshots** with the Read tool to see actual UI vs. expected
4. **Identify root cause** from visual evidence:
   - Selector timing issues (element not yet visible)
   - Overlays/modals blocking interaction
   - UI structure changed from expectations
   - Elements scrolled out of view
5. **Fix the script** based on findings
6. **Re-run** the full script
7. **Repeat** until verification passes OR you've exhausted options (3+ iterations with different approaches)

### Step 3: Reporting

**Only report to user when:**
- **100% success achieved** → Report: "Fixed N issues: [brief summary]. Verification now passing."
- **Exhausted all recovery options** → Show diagnostics, explain what you tried, what you found, ask for help

**Critical Rule:** "Script ran to completion" ≠ "task succeeded"
- Trust verification output, not exit codes
- Trust visual evidence from screenshots, not assumptions
- Don't ask permission to debug - that's your job as the chauffeur

### Diagnostic Script Examples

**Pattern 1: Element visibility test**
```javascript
const element = page.locator('selector');
const isVisible = await element.isVisible({ timeout: 3000 }).catch(() => false);
console.log('Element visible:', isVisible);
await page.screenshot({ path: '.tmp/diag-element.png' });
```

**Pattern 2: Button enumeration**
```javascript
const buttons = await page.evaluate(() => {
  return Array.from(document.querySelectorAll('button')).map(btn => ({
    text: btn.textContent?.trim(),
    ariaLabel: btn.getAttribute('aria-label'),
    visible: btn.offsetParent !== null
  })).filter(b => b.visible && (b.text || b.ariaLabel));
});
console.log('Buttons:', JSON.stringify(buttons, null, 2));
```

**Pattern 3: Timing test**
```javascript
console.log('Immediately after click:');
await page.screenshot({ path: '.tmp/diag-1-immediate.png' });

await page.waitForLoadState('networkidle', { timeout: 3000 }).catch(() => {});
console.log('After networkidle:');
await page.screenshot({ path: '.tmp/diag-2-after-wait.png' });
```

### Common Error Patterns

Watch for these patterns in output that signal "autonomous recovery needed":

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

---

## Common Anti-Patterns (Real Failures)

### Anti-Pattern 1: Text-Based Filters Match Multiple Elements

**Problem:**
```javascript
// ❌ Can match both parent <div> and child <button>
const btn = page.locator('button').filter({ hasText: /^Power-ups$/i });
await btn.click(); // Error: "locator resolved to 2 elements"
```

**Why it fails:** If a parent div contains the text "Power-ups" and so does the child button, the filter matches BOTH elements. Playwright strict mode requires exactly one match.

**Solution - Use semantic selectors instead:**
```javascript
// ✅ Much more reliable
const btn = page.getByRole('button', { name: /Power-ups/i });
await btn.click();
```

Prefer `getByRole`, `getByLabel`, `aria-label` over text filters.

### Anti-Pattern 2: page.evaluate Clicks Don't Trigger Framework Events

**Problem:**
```javascript
// ❌ Fires a native DOM click but does NOT trigger React/Fluent UI synthetic event handlers
await page.evaluate(() => {
  document.querySelector('button.confirm').click();
});
```

**Why it fails:** React, Angular, and Fluent UI use synthetic event systems that listen for events dispatched through the browser's event pipeline. A raw `element.click()` in evaluate fires a native DOM click that bypasses these frameworks. The UI may update visually (element disappears, dialog closes), but the framework never processes the action — so **no API call goes to the server**. The change vanishes on page refresh.

**Solution — Use Playwright's event dispatch:**
```javascript
// ✅ For unstable elements (menus that re-render and detach during click):
await locator.dispatchEvent('click');

// ✅ For elements that fail stability checks but are actually clickable:
await locator.click({ force: true });

// ✅ For stable elements (always prefer this):
await locator.click();
```

Use `page.evaluate` for **reading** DOM state (querying elements, checking visibility, extracting text). Never use it for **clicking** elements that trigger server-side actions.

### Anti-Pattern 3: Don't Diagnose Click Failures from Error Messages

**Problem:** When a click times out or fails with "intercepts pointer events", don't try to guess what's wrong from the error message.

**Solution - Look at the screenshot:**
```javascript
try {
  await element.click({ timeout: 5000 });
} catch (e) {
  // Take screenshot immediately
  await page.screenshot({ path: '.tmp/click-failed.png' });
  console.log('Click failed - see .tmp/click-failed.png');
  throw e;
}
```

Then **use the Read tool to view the screenshot**. You'll SEE what's actually blocking:
- Modal overlay in front of element
- Element scrolled out of view
- Wrong element selected
- Element not yet rendered

Diagnose visually, not from error text. Then fix based on what you SEE (dismiss overlay, scroll element into view, use better selector, add wait, etc.).

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

**All browser automation scripts must comply with these requirements.** Reference this section when writing AND when validating scripts.

### BANNED: Fixed Delays

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

### REQUIRED: Verification Code

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

This enables Phase 4.5 autonomous recovery.

### REQUIRED: Semantic Selectors

Use `aria-label`, `role`, visible text — **never CSS class selectors** (they change across deployments).

### REQUIRED: Browser Connection

Scripts receive `--cdp-port=<port>` from Claude. Connect with `chromium.connectOverCDP('http://localhost:<port>')` — no browser detection logic in scripts.

### REQUIRED: Navigation

Scripts must navigate to their target URL themselves — don't assume the browser is already there.

### Additional Requirements

- `console.log` after each major step for progress tracking
- Check `page.frames()` when `body.innerText` is unexpectedly short
- Use `page.route()` for request interception (not `frame.route()` — it doesn't exist)

---

## Phase 0.5: Script Validation (when creating Mode B scripts)

**CRITICAL:** When you write a new browser automation script, **immediately validate it before running** or reporting completion.

### Step 1: Scan for Violations

After writing script to `scripts/<task>.js`, scan for violations of **Script Quality Standards** (above):
- Fixed delays (`waitForTimeout`, `setTimeout`)
- Missing verification code
- CSS class selectors
- Missing browser connection logic

### Step 2: Auto-Fix if Violations Found

If you detect violations:
1. **Edit the script** to fix them
2. **Explain what was wrong** and what you fixed
3. **Re-scan** to confirm clean

**Do not ask permission** - violations are always wrong.

---

## Script Output

Scripts receive a validated CDP port from Phase 0 via `--cdp-port`. They do **not** contain browser detection, fallback, or SSO validation logic — that is handled by Claude interactively during Phase 0 before any script runs.

### Connecting to the browser

Every script should parse `--cdp-port` and connect directly:

```javascript
const { chromium } = require('playwright');

const cdpPort = process.argv.find(a => a.startsWith('--cdp-port='))?.split('=')[1] || '9222';

async function run() {
  const browser = await chromium.connectOverCDP(`http://localhost:${cdpPort}`);
  const context = browser.contexts()[0] || await browser.newContext();
  const page = await context.newPage();

  try {
    // Script navigates to its target URL and performs the task.
    // The browser is already validated for SSO — navigation will succeed.
    console.log('Done.');
  } finally {
    await page.close();
    await browser.close();
  }
}

run().catch(e => { console.error('Error:', e.message); process.exit(1); });
```

Scripts should still navigate to their target URL (not assume the page is pre-loaded). Since Phase 0 already validated the SSO session, navigating again is just a reload and keeps the script self-contained.

### Overlay dismissal (include in every Mode B script)

A fresh browser profile will show first-run overlays — Edge sync prompts ("We are now syncing your browsing data"), cookie consent banners, "What's new" modals. These block the real UI and cause element waits to time out. Dismiss them before waiting for app-specific elements:

```javascript
async function dismissOverlays(page) {
  const overlayButtons = [
    page.getByRole('button', { name: 'Got it' }),
    page.getByRole('button', { name: 'Dismiss' }),
    page.getByRole('button', { name: 'Close' }),
    page.getByRole('button', { name: /Not now/i }),
  ];
  for (const btn of overlayButtons) {
    if (await btn.count()) {
      console.log('  Dismissing overlay...');
      await btn.first().click();
      await poll(500);
    }
  }
}
```

Call `dismissOverlays(page)` immediately after navigating to the target app, **before** waiting for app-specific elements like navigation buttons.

### Screenshot-on-failure (include in every Mode B script)

When a connection or page load fails, save a diagnostic screenshot before moving on. This helps diagnose whether the failure was a login page, an overlay, a CAPTCHA, or something else:

```javascript
async function screenshotOnFailure(context, label) {
  const diagPage = context.pages()[0];
  if (!diagPage) return;
  fs.mkdirSync('.tmp', { recursive: true });
  const screenshotPath = `.tmp/diag-${label}-${Date.now()}.png`;
  await diagPage.screenshot({ path: screenshotPath }).catch(() => {});
  console.log(`  Diagnostic screenshot: ${screenshotPath}`);
}
```

Use this in catch blocks when the app fails to load, and in the browser fallback loop so each failed attempt produces a screenshot for debugging.

### Full script template

```javascript
// --- browser connection module (see above) ---

async function run() {
  const browser = await connectBrowser();
  const context = browser.contexts()[0] ?? await browser.newContext();
  const page = context.pages()[0] ?? await context.newPage();

  const results = { succeeded: [], failed: [] };

  try {
    // --- steps go here ---
    // Use semantic selectors: getByRole, getByLabel, locator('[aria-label="..."]')
    // Use element-based waits: locator.waitFor(), page.waitForURL(), page.waitForLoadState()
    // Check page.frames() if content appears empty — it may be in an iframe
    // Track results as you go (push to succeeded/failed arrays)

    // --- VERIFICATION (required) ---
    // Re-check the goal: did the task actually complete?
    // Example: navigate back to source, confirm items moved/deleted
    // Example: validate extracted data has required fields
    
    const failCount = results.failed.length;
    const successCount = results.succeeded.length;
    
    console.log(`Summary: ${successCount} succeeded, ${failCount} failed`);
    
    if (failCount === 0) {
      console.log('Verification passed ✅');
    } else {
      console.error(`Verification FAILED - ${failCount} errors remain`);
      results.failed.forEach(item => console.error('  -', item));
    }
  } finally {
    await browser.close();
  }
}

run().catch(e => { console.error(e.message); process.exit(1); });
```

### Rules for scripts

All scripts must comply with **Script Quality Standards** (see above). Key points:

- **No fixed delays** — use element-based waits only
- **Verification code required** — output explicit pass/fail
- **Semantic selectors** — `aria-label`, `role`, text (no CSS classes)
- **Browser connection** — accept `--cdp-port`, connect via CDP
- **Navigate to target** — don't assume browser is on the right page

See **Script Quality Standards** section for complete requirements and examples.
