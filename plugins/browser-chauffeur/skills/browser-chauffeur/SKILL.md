---
name: browser-chauffeur
description: REQUIRED for ALL browser automation — both creating NEW scripts AND running existing ones. When user asks to create/write/build a browser automation script, invoke this skill BEFORE writing any code. When running scripts, this skill handles browser launch, CDP setup, and autonomous error recovery (screenshot → diagnose → fix → retry). Never create or run browser automation outside this skill.
allowed-tools: Bash, Write, Edit, Read
---

# Browser Chauffeur

You are operating the browser on the user's behalf. You are the chauffeur — you drive, they direct. Your job is to reach the destination reliably, adapt when the route changes, and never give up without trying an alternate route first.

## How it works

Every task uses the same flow: launch a fresh Edge or Chrome with CDP enabled, validate that the target page loads, write or run a Node.js script that connects via `playwright.chromium.connectOverCDP(...)`, watch the output, and recover autonomously if anything fails. The fresh-browser approach inherits the user's logged-in sessions from their Windows profile (Edge/Chrome cookies transfer to the temp profile), so apps requiring login — corporate SSO or otherwise — authenticate without manual sign-in.

## Prerequisite Check

Verify `node` and the `playwright` npm package are available:
```bash
node --version && node -e "require('playwright'); console.log('ok')"
```

---

## Phase 0: Browser Launch (do this before Phase 1)

**Always launch a fresh browser instance** — never reuse an active browser. This prevents interfering with the user's browsing while still inheriting the credentials in their Windows profile.

**Step 1 — Find an available CDP port**

```bash
python plugins/browser-chauffeur/skills/browser-chauffeur/templates/find-port.py
```

Adjust the path to wherever your skill is mounted. Default range is 9222–9226; prints the first free port.

**Step 2 — Launch the browser**

```bash
python plugins/browser-chauffeur/skills/browser-chauffeur/templates/launch-browser.py --port <port> --url <target-url>
```

This auto-detects Edge first (better Windows SSO integration), falls back to Chrome, generates a unique temp profile, disables the Edge Teams/Chat sidebar that hijacks meeting URLs into a popup, and prints the launched browser's PID. **Save the PID** — you'll need it in Phase 3 to close only the browser you launched, without killing the user's personal browser instances.

Wait 3–5s for the browser to start, then verify CDP is responding:
```bash
curl -s http://localhost:<port>/json/version
```

**Known quirk — Edge sync dialog:** The "We are now syncing your browsing data" dialog on fresh Edge profiles is rendered in Edge's browser chrome layer, outside the page DOM. Playwright cannot see or dismiss it. It does **not** block script execution — scripts can interact with page elements behind it. Do not waste time trying to close it.

**First-run overlays:** A fresh profile may also show in-page overlays (cookie consent banners, "What's new" modals). These DO block element waits — dismiss them via the pattern in **Common Patterns → Overlay Dismissal** below.

**Step 3 — Validate the target loads**

Verify the browser can actually reach the target app, not just that the browser launched. This catches expired sessions, login walls, and consent gates before any real automation runs.

```bash
node plugins/browser-chauffeur/skills/browser-chauffeur/templates/validate-target.js --cdp-port=<port> --url=<target-url>
```

- `VALIDATION_OK` → record the CDP port; this is what you'll pass to scripts via `--cdp-port`.
- `VALIDATION_FAILED: landed on login page` → the user needs to sign in. Use `AskUserQuestion` to prompt them (see **User Intervention** section), then re-validate.

**The CDP port you validate here is what you pass to scripts.** Scripts do not perform browser detection or target validation — that is your job during Phase 0.

---

## Phase 0.5: Running Existing Scripts

**The script is the directions. This skill is the chauffeur.** Never run a browser automation script directly and walk away — always have this skill loaded so the recovery loop is active.

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
2. Read page state with `page.evaluate(() => document.body.innerText)`, or enumerate `page.frames()` if the body is unexpectedly short (see **Iframe detection** below)
3. If the text content doesn't clarify structure (complex visual layout), take a screenshot with `page.screenshot()` and read the image with the Read tool
4. Identify the first action needed

**Never act before orienting.** You cannot guess selectors on a page you haven't inspected.

### Iframe detection (critical for SPAs)

Many enterprise apps (Teams, SharePoint) render content in iframes. If `document.body.innerText` returns almost nothing (< 200 chars) on a page that should have content:

```javascript
const frames = page.frames();
console.log('Frames:', frames.map(f => f.url()));
for (const f of frames) {
  const text = await f.evaluate(() => document.body.innerText).catch(() => '');
  if (text.length > 200) console.log('Frame', f.url(), text.slice(0, 500));
}
```

Find the frame with the real content and target all locators at that frame object instead of the page. Note: `frame.route()` does not exist — routing only works on the page object.

### Out-of-process iframes (cross-origin, site isolation)

When `frameLocator(...).locator(...)` times out at 30s on a page with nested iframes — common in SCORM players, Workday Learning, SuccessFactors, and other LMS wrappers — the iframe is probably **out-of-process**. Chrome's site isolation runs each cross-origin iframe as a separate OS process with its own CDP target. Playwright's `connectOverCDP` connects only to the page target; the iframe's target is independent.

**How to detect:** `page.frames()` shows the iframe with an empty URL, or `page.accessibility.snapshot()` returns only the parent frame's tree without the iframe's content.

**How to attach directly:**

```javascript
const { CDPSession, httpJson, evalIn } = require('./templates/cdp-session');

// 1. List all CDP targets — look for type=iframe
const targets = await httpJson(`http://localhost:${cdpPort}/json`);
const iframeTarget = targets.find(t => t.type === 'iframe' && t.url.includes('target-domain.com'));

// 2. Open a direct WebSocket to the iframe's debugger URL
const session = new CDPSession(iframeTarget.webSocketDebuggerUrl);
await session.ready;

// 3. Collect execution contexts (one per same-origin nested frame inside the iframe)
const ctxs = [];
session.on(m => { if (m.method === 'Runtime.executionContextCreated') ctxs.push(m.params.context); });
await session.send('Runtime.enable');
await new Promise(r => setTimeout(r, 1500)); // let existing contexts arrive

// 4. Find the context you want (filter by origin) and evaluate in it
const ctxId = ctxs.find(c => c.origin.includes('target-domain.com'))?.id;
const title  = await evalIn(session, ctxId, 'document.title');
```

`playwright-core/lib/utilsBundle` exports the `ws` package, so no extra `npm install` is needed.

**How to click in the iframe — always use `Runtime.evaluate`, never OS coordinates:**

```javascript
// ✅ Invokes the React/framework click handler synchronously
await evalIn(session, ctxId, `document.getElementById(${JSON.stringify(buttonId)}).click()`);
```

See **Anti-Patterns → OS Coordinates Don't Reach Cross-Origin Iframe Content** and **Tab Key Is Unreliable Across Cross-Origin Iframe Boundaries** for the failure modes this replaces.

---

## Phase 2: Step-by-Step Execution

For each step in the desired flow:

1. **Interact** — use Playwright locators (`page.getByRole(...)`, `frame.locator('[aria-label="..."]')`)

2. **Screenshot after dropdown/menu clicks** — **CRITICAL:** After clicking any button that should reveal a dropdown menu, context menu, or modal dialog:
   - Wait briefly (500ms-1s) for the UI to appear
   - Take a screenshot with `page.screenshot({ path: '.tmp/diag-after-click.png' })`
   - Read the screenshot with the Read tool to SEE what menu items are actually visible
   - Query the DOM for menu items AFTER you've visually confirmed the menu is open

   **Why:** DOM queries alone can miss visual menus. The screenshot shows you exactly what the user would see, including menu items, their text, and layout. This prevents blindly clicking buttons and querying for items that may not be rendered yet or may be in unexpected locations.

3. **Verify** — re-read page state immediately after. Confirm the expected change happened: new element appeared, field value set, URL changed, success message shown. If the page state after verification is unexpected (CAPTCHA, login page, error page, or an unrecognized screen), treat it as a blocker — if it requires human action (CAPTCHA, login), follow the **User Intervention** section; otherwise apply Phase 4 recovery.

4. **If blocked** — re-read page state immediately to diagnose. Common blockers:
   - Modal or overlay in front of the target → dismiss it first (see **Overlay Dismissal**), then retry
   - Element not yet rendered → wait with `locator.waitFor()` or `page.waitForSelector()`
   - Stale locator (element re-rendered since last query) → re-query for a fresh handle

5. **If layout-dependent** — take a screenshot and read it with the Read tool to see visual context

6. Move to the next step **only after** the current step is confirmed

### Lazy-loaded content (scroll-and-stabilize)

Some SPAs (Articulate Rise, OpenSesame, content platforms) load page sections as the user scrolls. A "Continue" button may be absent or disabled when you first arrive — it only appears after the full lesson content has rendered. Clicking before all content loads will silently fail or navigate to the wrong place.

**Pattern:** scroll in viewport-sized steps and wait for page height to stabilize before acting:

```javascript
async function scrollAndStabilize(frame) {
  let prevHeight = 0, stableCount = 0;
  for (let pass = 0; pass < 30; pass++) {
    const info = await frame.evaluate(() => ({
      h: document.documentElement.scrollHeight,
      vh: window.innerHeight,
      sy: window.scrollY,
    }));
    await frame.evaluate(y => window.scrollTo(0, y), info.sy + Math.max(info.vh * 0.6, 300));
    await new Promise(r => setTimeout(r, 600)); // short poll — exit as soon as stable
    const after = await frame.evaluate(() => ({
      h: document.documentElement.scrollHeight,
      sy: window.scrollY,
      vh: window.innerHeight,
    }));
    const atBottom = after.sy + after.vh + 30 >= after.h;
    if (after.h === prevHeight && atBottom) {
      if (++stableCount >= 2) break; // two consecutive stable reads at bottom — done
    } else {
      stableCount = 0;
    }
    prevHeight = after.h;
  }
}
```

Call this before looking for the advance button. The 600 ms poll per step is acceptable here because it exits as soon as the condition is met — it is not a fixed delay.

---

## Phase 3: Wrap Up

1. Take a final read confirming the full flow succeeded
2. **Close the browser.** Kill only the browser PID you saved in Phase 0 Step 2 with `powershell -NoProfile -Command "Stop-Process -Id <PID> -Force"`. **Never** kill all browser processes (e.g., `Get-Process msedge | Stop-Process`) — that destroys the user's personal browser sessions.
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
- **Login pages** — the user isn't signed in, or the session expired mid-run. You may try the other browser first (Edge/Chrome fallback), but if that also shows a login page, escalate immediately.
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

When a script completes — **regardless of exit code** — analyze the output and recover autonomously. **Exit code 0 ≠ success.** Many scripts complete with errors in their output. Trust verification output and visual evidence, not exit codes. **Don't ask permission to debug — that's your job as the chauffeur.**

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
   - **None of the above looks right** → the failure may be a known anti-pattern. **Read `anti-patterns.md`** and check whether your symptoms match: a locator returning multiple matches in strict mode, a `page.evaluate` click that updates the UI but doesn't persist server-side, a click that "succeeds" but produces no DOM change, a `[role="dialog"]` presence check that returns true after the dialog closed, or a `getByRole('button')` returning nothing for a visibly-clickable element. Each entry has a tested fix.

3. **Use diagnostic patterns** from `templates/diagnostic-patterns.js` to inspect failing selectors — element visibility test, button enumeration, timing comparisons.

4. **Fix the script** — edit the failing section based on what you diagnosed. Don't guess — base every fix on what you actually saw in the screenshot or page state.

5. **Re-run the script** — execute it again and verify it passes the point that previously failed.

6. **Repeat** through the loop until verification passes OR you've exhausted options (3+ iterations with different approaches, or you've tried both browsers and dismissed all visible overlays). Then escalate via `AskUserQuestion` (see **User Intervention**) explaining what you found and what you need.

### Step 3: Reporting

**Only report to user when:**
- ✅ **100% success achieved** → "Fixed N issues: [brief summary]. Verification now passing."
- ❌ **Exhausted all recovery options** → **Leave the browser open at the failure state** (Phase 3 Exception covers this) and tell the user to look at the browser window — the visible page often makes the issue obvious at a glance, faster than any diagnostic summary. Then show your diagnostics, explain what you tried and what you found, and ask for help.

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

If another skill runs a script and it fails, that skill should follow this same recovery loop. The script saves diagnostic screenshots specifically so that whatever is running it — whether browser-chauffeur or another skill — can read the screenshot with the Read tool, see what went wrong, and fix it autonomously. The screenshots are not for the user; they are for you.

---

## Phase 5: Script Validation (when creating scripts)

**CRITICAL:** When you write a new browser automation script, **immediately validate it before running** or reporting completion. Scan `scripts/<task>.js` for violations of `script-quality-standards.md`: fixed delays (`waitForTimeout`, `setTimeout`), missing verification code, CSS class selectors, or missing browser connection logic. If you find any, edit the script to fix them, explain what was wrong and what you fixed, then re-scan to confirm clean. **Do not ask permission** — violations are always wrong.

---

## Common Patterns

**Overlay Dismissal** — A fresh browser profile will show first-run overlays — Edge sync prompts ("We are now syncing your browsing data"), cookie consent banners, "What's new" modals. These block the real UI and cause element waits to time out. See `templates/overlay-dismissal.js` for the `dismissOverlays(page)` helper. Call it immediately after navigating to the target app, **before** waiting for app-specific elements. Include it in every script.

**Screenshot on Failure** — Scripts save screenshots to `.tmp/diag-*.png` on failure so the recovery loop can read them. See `templates/screenshot-on-failure.js` for the `screenshotOnFailure(context, label)` helper. Use it in catch blocks when the app fails to load, and in any browser fallback loop so each failed attempt produces a screenshot for debugging.

**Common Anti-Patterns** — Most of these failure modes are now prevented by positive rules in **Key Rules** below (Selectors, Strict mode, Selector fallback, Actions vs reads, Visibility-not-presence). `anti-patterns.md` is the symptom-recognition reference for when a failure has already occurred — covers: text-based filter ambiguity, `page.evaluate` clicks not triggering React/Fluent UI synthetic events, diagnosing click failures from screenshots not error text, phantom `display:none` dialogs left in the DOM, and role-vs-tag selector gaps (semantic HTML buttons that aren't `[role="button"]`).

---

## Key Rules

**Selectors:** Prefer `aria-label`, `role`, and text-based selectors over CSS classes. CSS classes change across deployments and tenants; semantic attributes don't.

**Strict mode:** A locator matching multiple elements throws. Prefer `getByRole('button', { name: '...' })` over bare `aria-label` when both a wrapper `div` and the `button` itself share the same label. Use `.first()` only when you've confirmed the elements are genuinely equivalent.

**Selector fallback:** If `getByRole` or `[role="..."]` returns nothing for a visible element, broaden to the underlying HTML tag (`li`, `a`, `span`). Older or semantic UIs use real elements as action targets without a `role` attribute, and role-based selectors skip them entirely. To discover the true tag, enumerate by *direct* text content (not `innerText`, which inherits children's text).

**Waits:** Never use fixed delays — this includes both Playwright's `waitForTimeout` and raw `new Promise(r => setTimeout(r, N))`. Use `locator.waitFor()`, `page.waitForURL()`, `page.waitForLoadState()`, or `page.waitForFunction()` instead. Fixed delays make scripts slower when the page is fast and still flaky when it's slow. The only acceptable `setTimeout` is a short poll interval (≤300 ms) inside an active loop that exits as soon as a condition is met.

**Actions vs reads:** Use Playwright's locator API (`locator.click()`, `locator.fill()`, `locator.dispatchEvent('click')`) for any action that should trigger a server call or framework event. Reserve `page.evaluate` for *reading* DOM state. A native `element.click()` inside `evaluate` bypasses framework synthetic event handlers (React, Fluent UI) — the UI may update visually while no API call fires, and the change vanishes on refresh.

**Verification:** Always re-read page state after save/submit actions. A form can silently fail to save. Trust nothing without checking.

**Variant UIs:** The same application can render completely different DOM on different tenants or account types. When a selector fails in a new context, re-read there and find the equivalent element — never assume one tenant's selectors work on another.

**Overlay detection:** When a click doesn't land, check for modal overlays or portal elements blocking the target before retrying. Dismiss them first.

**Visibility, not presence:** When checking whether an element is *shown* (dialogs, menus, backdrops, tooltips), filter by computed visibility (`display`, `visibility`, `offsetParent`), not by `querySelector(...) !== null`. Many frameworks (Google products, Fluent UI, Material) keep dialog DOM mounted and toggle `display: none` to hide closed steps — bare presence checks return true for elements the user can't see, and recovery loops will spin trying to "close" something that's already closed.

**Two-pass element reveal:** Some UIs hide form inputs behind clickable summary rows. If expected inputs aren't visible, click the summary row, re-read, then find the revealed inputs.

**Hard verification after mutating actions:** After any create, update, or delete action, navigate away from the page and back (or close and reopen it) to confirm the change persisted server-side. DOM changes alone (element disappearing, success toast appearing) do NOT prove the server processed the action — the UI may have updated optimistically while the API call silently failed or never fired. Never report a mutating action as successful until you've seen the result survive a fresh page load.

**InnerText vs Screenshot:** `innerText` / accessibility queries are primary — they give actionable content and element structure. Screenshots are the fallback — use them when spatial/visual layout matters (diagnosing why a click doesn't land, reading a visual overlay).

**DOM state for progress detection:** Never use pixel-diff or screenshot comparison to detect SPA progression. Pixel values change for irrelevant reasons (background animation, playback progress bar, animated UI elements). Find a DOM-readable indicator — page counter (`Screen X of Y`), URL fragment, breadcrumb, lesson number — and compare its value before and after a click. If the indicator doesn't change, the click had no effect.

**Media gating:** If a course or media player shows no advance button but audio/video is playing (`!audio.paused && !audio.ended && audio.duration > 1`), treat the absence as "narration in progress," not stuck. Wait for the media's remaining duration plus a buffer before resetting the stuck counter. Only declare genuinely stuck when both conditions are true: no advance button AND no active media. Never time out the iteration loop while media is alive.

---

## Script Quality Standards

All scripts must comply with `script-quality-standards.md` — banned patterns (fixed delays), required patterns (verification, semantic selectors, CDP connection, navigation), and additional requirements (progress logging, frame fallback, overlay dismissal, screenshot-on-failure). See `templates/script-template.js` for a complete reference script that satisfies all of these.
