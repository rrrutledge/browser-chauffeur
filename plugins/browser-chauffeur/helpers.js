// Browser Chauffeur Helpers
// Central export of all shared browser automation utilities
//
// Usage in scripts:
//   const { dismissOverlays, screenshotOnFailure, isLoginPage } = require('browser-chauffeur-helpers');
//
// This module is aliased as 'browser-chauffeur-helpers' so scripts can
// import without knowing the full plugin path.

const { dismissOverlays } = require('./skills/browser-chauffeur/templates/overlay-dismissal');
const { screenshotOnFailure } = require('./skills/browser-chauffeur/templates/screenshot-on-failure');
const { isLoginPage, waitForLoadedOrLogin } = require('./skills/browser-chauffeur/templates/login-detection');
const { cleanupStaleState } = require('./skills/browser-chauffeur/templates/cleanup-stale-state');
const { verifyAfterMutation } = require('./skills/browser-chauffeur/templates/verify-after-mutation');

module.exports = {
  dismissOverlays,
  screenshotOnFailure,
  isLoginPage,
  waitForLoadedOrLogin,
  cleanupStaleState,
  verifyAfterMutation,
};
