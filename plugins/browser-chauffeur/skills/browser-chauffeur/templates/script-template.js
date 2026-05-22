// Browser automation script template. Scripts receive a validated CDP port
// from browser-chauffeur Phase 0 via --cdp-port. They do NOT contain browser
// detection, fallback, or target-load validation — that is handled by Claude
// interactively during Phase 0 before any script runs.
//
// Each script opens its own tab (newPage), works in it, and closes it when
// done. The browser is persistent — it stays running across tasks so logins
// survive. The finally block guards against closing the last tab (which would
// exit the browser and lose all sessions).

const { chromium } = require('playwright');
const fs = require('fs');

// Import shared helpers from browser-chauffeur templates
// This ensures scripts automatically get improvements when helpers are updated
const { dismissOverlays } = require('browser-chauffeur-helpers');

// --- browser connection ---
const cdpPort = process.argv.find(a => a.startsWith('--cdp-port='))?.split('=')[1] || '9222';

async function connectBrowser() {
  return chromium.connectOverCDP(`http://localhost:${cdpPort}`);
}

// --- screenshotOnFailure helper ---
async function screenshotOnFailure(context, label) {
  const diagPage = context.pages()[0];
  if (!diagPage) return;
  fs.mkdirSync('.tmp', { recursive: true });
  const screenshotPath = `.tmp/diag-${label}-${Date.now()}.png`;
  await diagPage.screenshot({ path: screenshotPath }).catch(() => {});
  console.log(`  Diagnostic screenshot: ${screenshotPath}`);
}

async function run() {
  const browser = await connectBrowser();
  const contexts = browser.contexts();
  const context = contexts.length > 1
    ? (contexts.find(ctx => ctx.pages().some(p => p.url().startsWith('http'))) ?? contexts[0])
    : (contexts[0] ?? await browser.newContext());
  const page = await context.newPage();

  const results = { succeeded: [], failed: [] };

  try {
    // Script navigates to its target URL. The browser is already validated
    // for SSO during Phase 0, so navigation will succeed.
    // await page.goto('https://target-url-here.example.com');

    // Dismiss first-run overlays before app-specific waits
    await dismissOverlays(page);

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
  } catch (e) {
    await screenshotOnFailure(context, 'run-failed');
    throw e;
  } finally {
    const allPages = context.pages();
    if (allPages.length > 1) {
      await page.close().catch(() => {});
    } else {
      await page.goto('about:blank').catch(() => {});
    }
    await browser.close().catch(() => {});
  }
}

run().catch(e => { console.error(e.message); process.exit(1); });
