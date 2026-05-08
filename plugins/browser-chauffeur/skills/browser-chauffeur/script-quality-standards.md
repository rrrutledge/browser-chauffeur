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

Scripts receive `--cdp-port=<port>` from Claude. Connect with `chromium.connectOverCDP('http://localhost:<port>')` — no browser detection logic in scripts. They do **not** contain browser detection, fallback, or login validation — that is handled by Claude interactively during Phase 0 before any script runs.

## ✅ REQUIRED: Navigation

Scripts must navigate to their target URL themselves — don't assume the browser is already there. Since Phase 0 already validated that the target loads, navigating again is just a reload and keeps the script self-contained.

## Additional Requirements

- `console.log` after each major step for progress tracking
- Check `page.frames()` when `body.innerText` is unexpectedly short
- Use `page.route()` for request interception (not `frame.route()` — it doesn't exist)
- Include `dismissOverlays(page)` after navigation (see Common Patterns in SKILL.md)
- Save a diagnostic screenshot in catch blocks (see Common Patterns in SKILL.md)
