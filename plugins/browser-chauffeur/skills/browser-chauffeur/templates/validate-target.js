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
    // Wait for network to settle so SPAs can render (with fallback timeout)
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    const text = await page.evaluate(() => document.body.innerText);

    // Improved login detection: look for strong signals, not just "Sign in" which
    // could appear in navigation or user menus on authenticated pages
    const hasPasswordField = text.includes('Enter your password') || text.includes('Password');
    const hasSignInButton = /Sign in|Log in|Login/i.test(text);
    const tooShort = text.length < 100;
    const lacksNavigation = !text.includes('Home') && !text.includes('Dashboard') && !text.includes('Catalog');

    // Consider it a login page if: very short content, OR (password field present AND lacks navigation)
    if (tooShort || (hasPasswordField && lacksNavigation)) {
      needsLogin = true;
      console.log('VALIDATION_FAILED: landed on login page');
      console.log('LOGIN_PAGE_URL:', page.url());
      console.log(`Detection reason: tooShort=${tooShort}, hasPassword=${hasPasswordField}, lacksNav=${lacksNavigation}`);
      console.log('Leaving page open for user login. Re-run this script after logging in.');
    } else {
      console.log('VALIDATION_OK');
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
