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
const { isLoginPage } = require('./skills/browser-chauffeur/templates/login-detection');

module.exports = {
  dismissOverlays,
  screenshotOnFailure,
  isLoginPage,
};
