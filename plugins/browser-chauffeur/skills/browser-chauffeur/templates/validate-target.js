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
  const context = browser.contexts()[0] || await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('Sign in') || text.includes('Enter your password') || text.length < 100) {
      console.log('VALIDATION_FAILED: landed on login page');
    } else {
      console.log('VALIDATION_OK');
    }
  } finally {
    await page.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}
validate().catch(e => { console.error(e.message); process.exit(1); });
