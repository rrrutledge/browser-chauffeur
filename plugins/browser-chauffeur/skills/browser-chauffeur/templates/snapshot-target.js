// Snapshot the target — navigate to a URL, wait for the page to settle, and
// save a screenshot of whatever's on screen. Generic utility: the caller
// decides what to do with the screenshot (verify login state, confirm an
// app is loaded, capture before/after a mutation, etc.).
//
// Usage: node snapshot-target.js --cdp-port=9222 --url=https://example.com [--target-anchor=<selector>]
//
// Behavior: navigates to --url, waits for URL stability (no redirects for
// 2.5s, max 15s), network idle, and DOM render stability, then saves a
// screenshot. Prints the screenshot path + the URL the browser actually
// landed on. Makes no claims about page contents — the caller inspects the
// screenshot with the Read tool.
//
// --target-anchor: optional CSS selector. When provided, the script returns
// as soon as the anchor element becomes visible instead of running the
// screenshot-stability loop. Useful for slow-hydrating SPAs that animate
// indefinitely (so screenshot diffing never settles) but expose a stable
// app-shell element (e.g. '[data-app-section="CalendarModuleSurface"]' for
// Outlook calendar).

const { chromium } = (() => {
  try { return require('playwright-core'); }
  catch { return require(require('path').join(require('os').homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'playwright-core')); }
})();

const cdpPort = process.argv.find(a => a.startsWith('--cdp-port='))?.split('=')[1] || '9222';
const targetUrl = process.argv.find(a => a.startsWith('--url='))?.split('=')[1];
const targetAnchor = process.argv.find(a => a.startsWith('--target-anchor='))?.split('=')[1] || null;

if (!targetUrl) {
  console.error('Usage: node snapshot-target.js --cdp-port=<port> --url=<url> [--target-anchor=<css-selector>]');
  process.exit(1);
}

// Resolves once the URL stops changing for `settleMs` consecutive ms, or
// after `maxMs` total. Captures the destination URL after any client-side
// redirect chain — SSO handshakes, region/locale routing, AB-test
// redirects — instead of screenshotting an in-flight redirect.
async function waitForUrlStable(page, settleMs = 2500, maxMs = 15000) {
  const start = Date.now();
  let lastUrl = page.url();
  let lastChange = Date.now();
  while (Date.now() - start < maxMs) {
    await new Promise(r => setTimeout(r, 200));
    const url = page.url();
    if (url !== lastUrl) {
      lastUrl = url;
      lastChange = Date.now();
    } else if (Date.now() - lastChange >= settleMs) {
      return;
    }
  }
}

async function snapshot() {
  const browser = await chromium.connectOverCDP(`http://localhost:${cdpPort}`);
  // Prefer contexts that already have a real http page — Edge sometimes launches
  // a welcome popup window as a separate context and it may sort before the main window.
  const contexts = browser.contexts();
  const context = contexts.length > 1
    ? (contexts.find(ctx => ctx.pages().some(p => p.url().startsWith('http'))) ?? contexts[0])
    : (contexts[0] ?? await browser.newContext());
  const page = await context.newPage();

  try {
    const navStart = Date.now();
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

    await waitForUrlStable(page, 2500, 15000);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    if (targetAnchor) {
      await page.locator(targetAnchor).first()
        .waitFor({ state: 'visible', timeout: 8000 })
        .catch(() => {});
    } else {
      // Screenshot-diff stability: take screenshots until two consecutive
      // captures are byte-identical (page has stopped rendering) or attempts run out.
      let previousScreenshot = null;
      let stabilized = false;
      const maxAttempts = 5;
      for (let attempt = 0; attempt < maxAttempts && !stabilized; attempt++) {
        const currentScreenshot = await page.screenshot();
        if (previousScreenshot) {
          stabilized = Buffer.compare(currentScreenshot, previousScreenshot) === 0;
          if (!stabilized && attempt < maxAttempts - 1) {
            await new Promise(r => setTimeout(r, 1000));
          }
        }
        previousScreenshot = currentScreenshot;
      }
    }

    const screenshotPath = `.tmp/snapshot-target-${Date.now()}.png`;
    await page.screenshot({ path: screenshotPath, fullPage: false });

    const finalUrl = page.url();
    const elapsedMs = Date.now() - navStart;

    console.log('SNAPSHOT_READY');
    console.log(`SCREENSHOT: ${screenshotPath}`);
    console.log(`FINAL_URL: ${finalUrl}`);
    console.log(`ELAPSED_MS: ${elapsedMs}`);
    console.log('');
    console.log('Read the screenshot with the Read tool to see what is on the page.');
  } finally {
    // Leave the tab open. The caller may want to interact with the page
    // next, hand it to the user (e.g. to complete a sign-in), or close it.
    await browser.close().catch(() => {});
  }
}

snapshot().catch(e => { console.error(e.message); process.exit(1); });
