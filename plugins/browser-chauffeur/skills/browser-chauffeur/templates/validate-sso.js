// SSO validation script — run after launching the browser to verify it can
// actually reach the target app, not just that it launched.
//
// Usage: CDP_PORT=9222 TARGET_URL=https://example.com node validate-sso.js
//
// On VALIDATION_OK, record the CDP port and pass it to subsequent scripts via
// --cdp-port. On VALIDATION_FAILED (login page), use AskUserQuestion to prompt
// the user to sign in (see User Intervention section in SKILL.md), then re-validate.

const { chromium } = require('playwright');

const CDP_PORT = process.env.CDP_PORT || '9222';
const TARGET_URL = process.env.TARGET_URL || 'https://example.com';

async function validate() {
  const browser = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
  const context = browser.contexts()[0] || await browser.newContext();
  const page = await context.newPage();
  await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const text = await page.evaluate(() => document.body.innerText);
  // Check for login page indicators
  if (text.includes('Sign in') || text.includes('Enter your password') || text.length < 100) {
    console.log('VALIDATION_FAILED: landed on login page');
  } else {
    console.log('VALIDATION_OK');
  }
  await page.close();
  await browser.close();
}
validate().catch(e => { console.error(e.message); process.exit(1); });
