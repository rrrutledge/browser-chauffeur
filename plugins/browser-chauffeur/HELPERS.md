# Browser Chauffeur Helpers

Shared utilities for browser automation scripts.

## Setup

To use the helpers in your scripts, you need to link the module so `require('browser-chauffeur-helpers')` resolves correctly:

### One-time setup (per project):

```bash
cd your-project
npm link ~/Dev/mediwareinc/wellsky-claude-code-plugins/plugins/browser-chauffeur
```

This creates a symlink in your project's node_modules so the import works.

### Alternative: Use full path

If you don't want to use npm link, import with the full path:

```javascript
const { dismissOverlays } = require(process.env.HOME + '/Dev/mediwareinc/wellsky-claude-code-plugins/plugins/browser-chauffeur/helpers');
```

## Usage

```javascript
const { chromium } = require('playwright');
const { dismissOverlays, screenshotOnFailure } = require('browser-chauffeur-helpers');

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

### `isLoginPage(page)`

Detects if the current page is likely a login page. Uses conservative logic requiring multiple signals to avoid false positives.

- **Parameters**: `page` - Playwright page object
- **Returns**: Promise<{isLogin: boolean, signals: object, url: string}>
  - `isLogin` - true if the page appears to be a login page
  - `signals` - object with detection signals (hasPasswordField, hasSignInButton, tooShort, lacksNavigation, hasAuthenticatedIndicators, textLength)
  - `url` - current page URL
- **Best Practice**: Check mid-execution if session expired, or validate before starting automation
- **Example**:
  ```javascript
  const result = await isLoginPage(page);
  if (result.isLogin) {
    console.log('Session expired, re-auth needed');
    // Prompt user or handle re-authentication
  }
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
