// Browser automation script template. Scripts receive a validated CDP port
// from browser-chauffeur Phase 0 via --cdp-port. They do NOT contain browser
// detection, fallback, or target-load validation — that is handled by Claude
// interactively during Phase 0 before any script runs.
//
// Scripts should still navigate to their target URL (not assume the page is
// pre-loaded). Since Phase 0 already validated that the target loads,
// navigating again is just a reload and keeps the script self-contained.
//
// =====================================================================
// SELF-CONTAINED ON PURPOSE — DO NOT replace these helpers with require()
// =====================================================================
// poll, dismissOverlays, and screenshotOnFailure are inlined below.
// They also live as standalone files:
//   - templates/overlay-dismissal.js   (poll + dismissOverlays)
//   - templates/screenshot-on-failure.js (screenshotOnFailure)
//
// Why duplicated: a script copy-pasted from this template lands at
// scripts/<task>.js, where `require('./overlay-dismissal')` would not
// resolve. Keeping the helpers inline means the template is a real
// starting point — the model can paste it and run it without rewriting
// the imports.
//
// HOW TO UPDATE: if you change any of these helpers, edit BOTH places:
//   1. The inline copy in this file
//   2. The matching standalone file in templates/
// The standalone files have a reciprocal "MIRRORED HERE" header pointing
// back at this file so future maintainers don't miss the second copy.
// =====================================================================

const { chromium } = require('playwright');
const fs = require('fs');

// --- browser connection ---
const cdpPort = process.argv.find(a => a.startsWith('--cdp-port='))?.split('=')[1] || '9222';

async function connectBrowser() {
  return chromium.connectOverCDP(`http://localhost:${cdpPort}`);
}

// --- inlined helpers (mirrors overlay-dismissal.js / screenshot-on-failure.js) ---
async function poll(ms) { return new Promise(r => setTimeout(r, ms)); }

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
  const context = browser.contexts()[0] ?? await browser.newContext();
  const page = context.pages()[0] ?? await context.newPage();

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
    await browser.close();
  }
}

run().catch(e => { console.error(e.message); process.exit(1); });
