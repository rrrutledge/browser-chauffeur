# Script Quality Standards

**All browser automation scripts must comply with these requirements.** Reference this file when writing AND when validating scripts (Phase 5 in SKILL.md). See `templates/script-template.js` for a complete reference script that satisfies all of these.

## ❌ BANNED: Fixed Delays

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

## ❌ BANNED: Retry Loops in Scripts

**Never add retry logic inside a script:**
```javascript
// ❌ WRONG - script retrying its own failures
for (let attempt = 1; attempt <= 3; attempt++) {
  const result = await doAction(page, item);
  if (result.success) break;
  console.log(`Retry ${attempt}/3...`);
}
```

**Why:** Retries paper over the real problem. If the script does the right thing — waits for the correct DOM signals before acting — it works the first time, just like a human using the UI. When a wait times out, the script should fail clearly, and browser-chauffeur's recovery loop diagnoses the failure (via screenshots), fixes the script, and re-runs it. Scripts are the directions; the chauffeur handles road closures.

**Instead, wait for the right signal:**
```javascript
// ✅ CORRECT - wait for the element that proves readiness
await deleteBtn.waitFor({ state: 'visible', timeout: 5000 });
await deleteBtn.click();
```

## ❌ BANNED: Opening Tabs Without `openTab`

**Never create a tab with `context.newPage()`, and never navigate a fresh self-created page with `page.goto()`:**
```javascript
// ❌ WRONG - unregistered tab, invisible to the orphan sweep
const page = await context.newPage();
await page.goto('https://example.com');
```

**Why:** `openTab` records each tab in the shared registry so the launcher's sweep can reclaim it. A tab opened with bare `newPage()` is never registered — the orphan sweep can't see it, so it lingers until the age/count backstop reaps it or the browser crashes under the accumulation.

**Always create tabs with `openTab` and close them with `closeTab` in `finally`:**
```javascript
// ✅ CORRECT - creates + registers in one step (goto happens if you pass a URL)
const { openTab, closeTab } = require('browser-chauffeur-helpers');
const page = await openTab(context, 'https://example.com');
try { /* work */ } finally { await closeTab(page); }
```

Tabs you *found* (didn't create) are not yours — don't pass them to `closeTab`.

## ✅ REQUIRED: Verification Code

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

## ✅ REQUIRED: Semantic Selectors

Use `aria-label`, `role`, visible text — **never CSS class selectors** (they change across deployments).

## ✅ REQUIRED: Browser Connection

Scripts receive `--cdp-port=<port>` from Claude. Connect with the hardened `connectBrowser()` helper from `script-template.js`, which wraps `chromium.connectOverCDP('http://localhost:<port>')` in a 30s `Promise.race` timeout — **never call `connectOverCDP` bare**, or the script can hang forever when the persistent profile is overloaded or has a wedged renderer (see SKILL.md "Resilient Connection"). No browser detection logic in scripts. They do **not** contain browser detection, login validation, or the Edge/Chrome fallback — that is handled by Claude interactively during Phase 0 before any script runs.

## ✅ REQUIRED: Navigation

Scripts must navigate to their target URL themselves — don't assume the browser is already there. Since Phase 0 already validated that the target loads, navigating again is just a reload and keeps the script self-contained.

## Additional Requirements

- `console.log` after each major step for progress tracking
- Check `page.frames()` when `body.innerText` is unexpectedly short
- Use `page.route()` for request interception (not `frame.route()` — it doesn't exist)
- Include `dismissOverlays(page)` after navigation (see Common Patterns in SKILL.md)
- Save a diagnostic screenshot in catch blocks (see Common Patterns in SKILL.md)
- Create tabs with `openTab` and close them with `closeTab` in `finally` (see **BANNED: Opening Tabs Without `openTab`** above). The `script-template.js` reference already does this.
