// Overlay dismissal — call after navigating to a target app, before
// waiting for app-specific elements. A fresh browser profile will show
// first-run overlays (Edge sync prompts, cookie banners, "What's new"
// modals) that block the real UI and cause element waits to time out.
//
// RECOMMENDED USAGE: Import this module instead of copying:
//
//   const { dismissOverlays } = require('browser-chauffeur-helpers');
//
// This ensures all scripts automatically get improvements when this module
// is updated. The old pattern of copying/inlining helpers meant improvements
// never propagated to existing scripts.

async function dismissOverlays(page) {
  const overlayButtons = [
    page.getByRole('button', { name: 'Got it' }),
    page.getByRole('button', { name: 'Dismiss' }),
    page.getByRole('button', { name: 'Close' }),
    page.getByRole('button', { name: /Not now/i }),
  ];
  for (const btn of overlayButtons) {
    if (await btn.count()) {
      console.log('  Dismissing overlay...');
      await btn.first().click();
      // Wait for the button to actually disappear (state-based wait)
      // instead of a fixed delay - follows Browser Chauffeur best practices
      await btn.first().waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
    }
  }
}

module.exports = { dismissOverlays };
