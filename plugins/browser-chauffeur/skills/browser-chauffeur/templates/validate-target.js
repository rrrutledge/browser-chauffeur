// Target validation script — run after launching the browser to verify the
// CDP-connected browser can actually reach the target app, not just that it
// launched. Catches expired sessions, login walls, and consent gates before
// any real automation runs.
//
// Usage: node validate-target.js --cdp-port=9222 --url=https://example.com
//
// On VALIDATION_OK, record the CDP port and pass it to subsequent scripts via
// --cdp-port. On VALIDATION_FAILED (login page), use AskUserQuestion to prompt
// the user to sign in (see User Intervention section in SKILL.md), then re-validate.

const { chromium } = require('playwright');
const { isLoginPage } = require('../../../helpers');

const cdpPort = process.argv.find(a => a.startsWith('--cdp-port='))?.split('=')[1] || '9222';
const targetUrl = process.argv.find(a => a.startsWith('--url='))?.split('=')[1];

if (!targetUrl) {
  console.error('Usage: node validate-target.js --cdp-port=<port> --url=<url>');
  process.exit(1);
}

async function validate() {
  const browser = await chromium.connectOverCDP(`http://localhost:${cdpPort}`);
  // Prefer contexts that already have a real http page — Edge sometimes launches
  // a welcome popup window as a separate context and it may sort before the main window.
  const contexts = browser.contexts();
  const context = contexts.length > 1
    ? (contexts.find(ctx => ctx.pages().some(p => p.url().startsWith('http'))) ?? contexts[0])
    : (contexts[0] ?? await browser.newContext());
  const page = await context.newPage();
  let needsLogin = false;
  try {
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Wait for network idle, then verify page has stabilized by comparing screenshots
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    // Take screenshots and compare until page stops changing (SPA fully rendered)
    let previousScreenshot = null;
    let stabilized = false;
    const maxAttempts = 5;

    for (let attempt = 0; attempt < maxAttempts && !stabilized; attempt++) {
      const currentScreenshot = await page.screenshot();

      if (previousScreenshot) {
        // Compare screenshots - if identical, page has stabilized
        stabilized = Buffer.compare(currentScreenshot, previousScreenshot) === 0;
        if (!stabilized && attempt < maxAttempts - 1) {
          // Page still changing - wait briefly and check again
          await new Promise(r => setTimeout(r, 1000));
        }
      }

      previousScreenshot = currentScreenshot;
    }

    // Use shared login detection helper
    const loginCheck = await isLoginPage(page);

    if (loginCheck.isLogin) {
      // Take screenshot for visual verification before prompting user
      const screenshotPath = '.tmp/login-detection.png';
      await page.screenshot({ path: screenshotPath, fullPage: false });

      needsLogin = true;
      console.log('VALIDATION_FAILED: potential login page detected');
      console.log('LOGIN_PAGE_URL:', loginCheck.url);
      console.log(`SCREENSHOT: ${screenshotPath}`);
      const s = loginCheck.signals;
      console.log(`Detection: tooShort=${s.tooShort}, password=${s.hasPasswordField}, signIn=${s.hasSignInButton}, lacksNav=${s.lacksNavigation}, hasAuth=${s.hasAuthenticatedIndicators}`);
      console.log('');
      console.log('IMPORTANT: Check the screenshot to confirm this is actually a login page.');
      console.log('If the screenshot shows you are already logged in, this is a false positive.');
      console.log('Leaving page open. Re-run this script after confirming login state.');
    } else {
      console.log('VALIDATION_OK');
      console.log(`Page loaded successfully. Content length: ${loginCheck.signals.textLength} chars`);
    }
  } finally {
    // If login is needed, leave the page open so user can complete it.
    // Otherwise, clean up the validation tab.
    if (!needsLogin) {
      const allPages = context.pages();
      if (allPages.length > 1) {
        await page.close().catch(() => {});
      } else {
        await page.goto('about:blank').catch(() => {});
      }
    }
    await browser.close().catch(() => {});
  }
}
validate().catch(e => { console.error(e.message); process.exit(1); });
