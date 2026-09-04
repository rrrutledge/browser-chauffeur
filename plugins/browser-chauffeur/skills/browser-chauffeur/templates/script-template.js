// Browser automation script template. Scripts receive a validated CDP port
// from browser-chauffeur Phase 0 via --cdp-port. They do NOT contain browser
// detection, fallback, or target-load validation — that is handled by Claude
// interactively during Phase 0 before any script runs.
//
// Each script opens its own tab with openTab (never bare newPage — openTab
// registers the tab so the launcher's sweep can reclaim it), works in it, and
// closes it with closeTab when done. The browser is persistent — it stays
// running across tasks so logins survive. closeTab guards against closing the
// last tab (which would exit the browser and lose all sessions).

const { chromium } = (() => {
  try { return require('playwright-core'); }
  catch { return require(require('path').join(require('os').homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'playwright-core')); }
})();

const { dismissOverlays, openTab, closeTab, screenshotOnFailure, reapTabs } = (() => {
  try { return require('browser-chauffeur-helpers'); }
  catch { return require(require('path').join(require('os').homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'browser-chauffeur-helpers')); }
})();

// --- browser connection ---
// Splits only on the FIRST "=" — a bare .split('=')[1] truncates any value that
// itself contains "=" (a URL query string, a CSS attribute selector). Any
// ad-hoc script adding its own --flag=value argument (e.g. --url=) should copy
// this helper rather than reintroducing the bare split pattern.
function argValue(flag) {
  const prefix = `--${flag}=`;
  const arg = process.argv.find(a => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : undefined;
}

const cdpPort = argValue('cdp-port') || '9222';

// connectOverCDP auto-attaches to EVERY open target to build its page tree. On a
// persistent profile that has accumulated many tabs — or has a single wedged
// renderer — that enumeration can hang indefinitely (Playwright's own `timeout`
// option only bounds the socket connect, not post-connect target enumeration).
// Race it against a hard timeout so a wedged browser fails fast instead of
// hanging forever.
const CONNECT_TIMEOUT_MS = 30000;

function attachOnce() {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(
        `connectOverCDP did not complete within ${CONNECT_TIMEOUT_MS}ms on port ${cdpPort}. ` +
        `The persistent profile likely has too many open tabs or a wedged renderer.`
      )),
      CONNECT_TIMEOUT_MS,
    );
  });
  return Promise.race([chromium.connectOverCDP(`http://localhost:${cdpPort}`), timeout])
    .finally(() => clearTimeout(timer));
}

// Attach, and on a wedge, self-heal: reap orphaned and over-the-cap tabs, then
// retry the attach once. The wedge is almost always an accumulation of tabs left
// open by ended sessions, so clearing them is exactly what unblocks the connect —
// and doing it here means a wedge heals on its own instead of stopping the run
// for a human to close tabs by hand. reapTabs is best-effort; a genuinely
// unrecoverable browser (a wedged renderer no reap can free) still surfaces the
// actionable error on the second failure.
async function connectBrowser() {
  try {
    return await attachOnce();
  } catch (first) {
    console.error(`${first.message} Reaping stale tabs and retrying the attach once...`);
    reapTabs(cdpPort);
    try {
      return await attachOnce();
    } catch (second) {
      throw new Error(
        `${second.message} Auto-reap did not free it — a renderer may be wedged. ` +
        `Reset the profile with cleanup-browser.py --reset (then re-launch and log in again), or retry.`
      );
    }
  }
}

async function run() {
  const browser = await connectBrowser();
  const contexts = browser.contexts();
  const context = contexts.length > 1
    ? (contexts.find(ctx => ctx.pages().some(p => p.url().startsWith('http'))) ?? contexts[0])
    : (contexts[0] ?? await browser.newContext());
  // openTab creates the tab AND registers it in one step, so a later launch can
  // reclaim it if this script crashes before closeTab runs (see tab-registry.js).
  const page = await openTab(context);

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
    // closeTab closes (or parks, if it's the last tab) AND unregisters in one
    // step. Reaching finally means this tab is not an orphan; only tabs whose
    // script crashed before this point stay registered for the sweep to reclaim.
    await closeTab(page);
    await browser.close().catch(() => {});
  }
}

run().catch(e => { console.error(e.message); process.exit(1); });
