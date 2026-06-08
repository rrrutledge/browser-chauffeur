# Browser Chauffeur Helpers

Shared utilities for browser automation scripts.

## Setup

No manual setup needed. Run the browser-chauffeur setup script once (SKILL.md calls this automatically as part of the prerequisite check):

```bash
node plugins/browser-chauffeur/skills/browser-chauffeur/templates/setup.js
```

This installs `playwright-core` and writes a `browser-chauffeur-helpers` shim to `~/.claude/browser-chauffeur/node_modules/`. Scripts fall back to that location automatically when the package isn't installed in the current project.

## Usage

```javascript
const { chromium } = (() => {
  try { return require('playwright-core'); }
  catch { return require(require('path').join(require('os').homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'playwright-core')); }
})();
const { dismissOverlays, screenshotOnFailure } = (() => {
  try { return require('browser-chauffeur-helpers'); }
  catch { return require(require('path').join(require('os').homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'browser-chauffeur-helpers')); }
})();

async function run() {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const context = browser.contexts()[0];
  const page = context.pages()[0] || await context.newPage();

  try {
    await page.goto('https://example.com');
    await dismissOverlays(page);
    
    // Your automation logic here
    
  } catch (e) {
    await screenshotOnFailure(context, 'example-error');
    throw e;
  }
}

run().catch(console.error);
```

## Available Helpers

### `dismissOverlays(page)`

Dismisses common overlay dialogs (cookie banners, "What's new" modals, etc.) that appear on first visit.

- **Parameters**: `page` - Playwright page object
- **Returns**: Promise<void>
- **Best Practice**: Call after navigation, before waiting for app-specific elements

### `screenshotOnFailure(context, label)`

Takes a diagnostic screenshot when automation fails. Useful in catch blocks.

- **Parameters**: 
  - `context` - Playwright browser context
  - `label` - String label for the screenshot file
- **Returns**: Promise<void>
- **Saves to**: `.tmp/diag-{label}-{timestamp}.png`

### Login detection

**Do not try to detect login state with scripts. Detect it with the LLM via screenshot inspection.**

Text and DOM heuristics cannot reliably distinguish login walls, SSO transit pages, MFA challenges, and slow-hydrating SPAs across the variety of providers and UIs you'll encounter. A screenshot read by the LLM gets it right with zero pattern maintenance.

**Start-of-flow:** use `snapshot-target.js` — it navigates, waits for URL/network/DOM to settle, and saves a screenshot. The chauffeur reads it and decides.

**Mid-flow (e.g. suspect the session expired):** screenshot the page and print the path. The recovery loop reads it.

```javascript
const path = `.tmp/session-check-${Date.now()}.png`;
await page.screenshot({ path });
console.log(`SCREENSHOT: ${path}`);
console.log(`FINAL_URL: ${page.url()}`);
```

## Why Import Instead of Copy?

**Old pattern (bad)**:
- Every script had its own inline copy of helpers
- Improvements never propagated to existing scripts  
- Had to manually update dozens of scripts when fixing bugs

**New pattern (good)**:
- Scripts import from a central module
- Improvements automatically benefit all scripts
- Single source of truth for shared utilities

## Adding New Helpers

1. Create the helper function in `templates/your-helper.js`
2. Export it from `helpers.js`
3. Document it in this file
4. Update the template in `templates/script-template.js` to show the import pattern
