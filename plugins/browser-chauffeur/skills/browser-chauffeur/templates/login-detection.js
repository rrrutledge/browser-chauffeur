// Login page detection — detect if the browser has landed on a login page
// instead of the authenticated app. Useful for checking if a session expired
// during automation, or for validating that the user is logged in before starting.
//
// RECOMMENDED USAGE: Import this module instead of copying:
//
//   const { isLoginPage } = require('browser-chauffeur-helpers');
//
// This ensures all scripts automatically get improvements when this module
// is updated.

/**
 * Detects if the current page is likely a login page.
 *
 * Uses conservative logic requiring multiple signals to avoid false positives
 * where authenticated pages with minimal content are misidentified as login pages.
 *
 * @param {Page} page - Playwright page object
 * @returns {Promise<{isLogin: boolean, signals: object, url: string}>}
 *   - isLogin: true if the page appears to be a login page
 *   - signals: object with detection signals (useful for debugging)
 *   - url: current page URL
 *
 * @example
 *   const result = await isLoginPage(page);
 *   if (result.isLogin) {
 *     console.log('Login required at:', result.url);
 *     // Prompt user to log in
 *   }
 */
async function isLoginPage(page) {
  const text = await page.evaluate(() => document.body.innerText);
  const url = page.url();

  // Individual signals
  const hasPasswordField = text.includes('Enter your password') || text.includes('Password');
  const hasSignInButton = /Sign in|Log in|Login/i.test(text);
  const tooShort = text.length < 100;
  const lacksNavigation = !text.includes('Home') && !text.includes('Dashboard') && !text.includes('Catalog');
  const hasAuthenticatedIndicators = text.includes('Sign out') ||
                                     text.includes('Log out') ||
                                     text.includes('Profile') ||
                                     text.includes('Settings');

  // Conservative detection: Only flag as login page if:
  // - (Has password field AND sign-in button AND lacks navigation AND no auth indicators) OR
  // - (Extremely short content AND no auth indicators)
  const isLogin = (hasPasswordField && hasSignInButton && lacksNavigation && !hasAuthenticatedIndicators) ||
                  (tooShort && !hasAuthenticatedIndicators);

  return {
    isLogin,
    signals: {
      hasPasswordField,
      hasSignInButton,
      tooShort,
      lacksNavigation,
      hasAuthenticatedIndicators,
      textLength: text.length
    },
    url
  };
}

/**
 * Polling wrapper around isLoginPage for SPAs that hydrate incrementally.
 *
 * Single-shot isLoginPage runs immediately after page load and can false-positive
 * on logged-in SPAs (Outlook, Teams, large React apps) whose body text is genuinely
 * short at the moment of measurement. This helper retries the check until either:
 *   - login signals clear (text crosses threshold, auth indicators appear), OR
 *   - the optional anchorSelector renders (definitive "app shell is up"), OR
 *   - the maxWaitMs window expires.
 *
 * Short-circuits in two cases without polling:
 *   - First check already says not-login → returns immediately.
 *   - First check finds an actual <input type="password">/"Enter your password" →
 *     it's a real login form, no point waiting.
 *
 * @param {Page} page - Playwright page object
 * @param {object} [options]
 * @param {number} [options.maxWaitMs=8000] - Total polling budget in ms
 * @param {number} [options.pollMs=1000] - Delay between polls in ms
 * @param {string|null} [options.anchorSelector=null] - Optional CSS selector for a
 *   known app-shell element. If it becomes visible, treat the page as loaded.
 * @returns {Promise<{isLogin: boolean, signals: object, url: string, waitedMs: number}>}
 *
 * @example
 *   const result = await waitForLoadedOrLogin(page, {
 *     anchorSelector: '[data-app-section="CalendarModuleSurface"]'
 *   });
 *   if (result.isLogin) { ... }
 */
async function waitForLoadedOrLogin(page, { maxWaitMs = 8000, pollMs = 1000, anchorSelector = null } = {}) {
  const start = Date.now();
  let result = await isLoginPage(page);

  if (!result.isLogin) return { ...result, waitedMs: 0 };
  if (result.signals.hasPasswordField) return { ...result, waitedMs: 0 };

  const deadline = start + maxWaitMs;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, pollMs));

    if (anchorSelector) {
      const hasAnchor = await page.locator(anchorSelector).first().isVisible().catch(() => false);
      if (hasAnchor) {
        result = await isLoginPage(page);
        return { ...result, waitedMs: Date.now() - start };
      }
    }

    result = await isLoginPage(page);
    if (!result.isLogin) return { ...result, waitedMs: Date.now() - start };
    if (result.signals.hasPasswordField) return { ...result, waitedMs: Date.now() - start };
  }

  return { ...result, waitedMs: Date.now() - start };
}

module.exports = { isLoginPage, waitForLoadedOrLogin };
