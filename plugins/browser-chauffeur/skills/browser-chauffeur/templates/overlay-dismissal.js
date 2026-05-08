// Overlay dismissal — call after navigating to a target app, before
// waiting for app-specific elements. A fresh browser profile will show
// first-run overlays (Edge sync prompts, cookie banners, "What's new"
// modals) that block the real UI and cause element waits to time out.
//
// MIRRORED IN templates/script-template.js — these same helpers are
// inlined there so a copy-pasted script runs as a single file. If you
// change `dismissOverlays` or `poll` here, update the inline copy in
// script-template.js too. See the SELF-CONTAINED ON PURPOSE block at
// the top of script-template.js for the full rationale.

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
      await poll(500);
    }
  }
}

// Short delay between dismissals so overlay animations finish before we look
// for the next one. Bounded (≤500ms) and only used in this small loop, so it
// doesn't fall under the "no fixed delays" ban for general script logic.
async function poll(ms) {
  return new Promise(r => setTimeout(r, ms));
}

module.exports = { dismissOverlays, poll };
