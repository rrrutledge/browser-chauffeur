// Browser Chauffeur Helpers
// Central export of all shared browser automation utilities
//
// Usage in scripts:
//   const { dismissOverlays, screenshotOnFailure } = require('browser-chauffeur-helpers');
//
// This module is aliased as 'browser-chauffeur-helpers' so scripts can
// import without knowing the full plugin path.
//
// Login detection: deliberately not provided. Detect login state with the
// LLM via screenshot inspection — see snapshot-target.js (start-of-flow)
// and the HELPERS.md "Login detection" section (mid-flow pattern).

const { dismissOverlays } = require('./skills/browser-chauffeur/templates/overlay-dismissal');
const { screenshotOnFailure } = require('./skills/browser-chauffeur/templates/screenshot-on-failure');
const { cleanupStaleState } = require('./skills/browser-chauffeur/templates/cleanup-stale-state');
const { verifyAfterMutation } = require('./skills/browser-chauffeur/templates/verify-after-mutation');
const { openTab, closeTab, registerTab, unregisterTab } = require('./skills/browser-chauffeur/templates/tab-registry');

module.exports = {
  dismissOverlays,
  screenshotOnFailure,
  cleanupStaleState,
  verifyAfterMutation,
  openTab,
  closeTab,
  registerTab,
  unregisterTab,
};
