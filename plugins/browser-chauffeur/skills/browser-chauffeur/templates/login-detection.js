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

module.exports = { isLoginPage };
