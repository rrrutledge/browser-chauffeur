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

    // Wait longer for SPAs to fully render - many false positives happen because
    // the page is still loading when we check
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    // Extra 2s buffer for any post-network-idle rendering
    await page.waitForTimeout(2000);

    const text = await page.evaluate(() => document.body.innerText);

    // Conservative login detection: require MULTIPLE strong signals
    // to reduce false positives where authenticated pages are misidentified
    const hasPasswordField = text.includes('Enter your password') || text.includes('Password');
    const hasSignInButton = /Sign in|Log in|Login/i.test(text);
    const tooShort = text.length < 100;
    const lacksNavigation = !text.includes('Home') && !text.includes('Dashboard') && !text.includes('Catalog');
    const hasAuthenticatedIndicators = text.includes('Sign out') || text.includes('Log out') || text.includes('Profile') || text.includes('Settings');

    // Only flag as login page if: (password field + sign-in button + lacks navigation) OR extremely short content
    // Do NOT flag if authenticated indicators are present (user menu, logout button, etc.)
    const likelyLoginPage = (hasPasswordField && hasSignInButton && lacksNavigation && !hasAuthenticatedIndicators) ||
                            (tooShort && !hasAuthenticatedIndicators);

    if (likelyLoginPage) {
      // Take screenshot for visual verification before prompting user
      const screenshotPath = '.tmp/login-detection.png';
      await page.screenshot({ path: screenshotPath, fullPage: false });

      needsLogin = true;
      console.log('VALIDATION_FAILED: potential login page detected');
      console.log('LOGIN_PAGE_URL:', page.url());
      console.log(`SCREENSHOT: ${screenshotPath}`);
      console.log(`Detection: tooShort=${tooShort}, password=${hasPasswordField}, signIn=${hasSignInButton}, lacksNav=${lacksNavigation}, hasAuth=${hasAuthenticatedIndicators}`);
      console.log('');
      console.log('IMPORTANT: Check the screenshot to confirm this is actually a login page.');
      console.log('If the screenshot shows you are already logged in, this is a false positive.');
      console.log('Leaving page open. Re-run this script after confirming login state.');
    } else {
      console.log('VALIDATION_OK');
      console.log(`Page loaded successfully. Content length: ${text.length} chars`);
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
