// Screenshot-on-failure — call from catch blocks when the app fails to load,
// and from any browser fallback loop so each failed attempt produces a
// screenshot for debugging. The screenshots help diagnose whether the failure
// was a login page, an overlay, a CAPTCHA, or something else.
//
// MIRRORED IN templates/script-template.js — this same helper is inlined
// there so a copy-pasted script runs as a single file. If you change
// `screenshotOnFailure` here, update the inline copy in script-template.js
// too. See the SELF-CONTAINED ON PURPOSE block at the top of
// script-template.js for the full rationale.

const fs = require('fs');

async function screenshotOnFailure(context, label) {
  const diagPage = context.pages()[0];
  if (!diagPage) return;
  fs.mkdirSync('.tmp', { recursive: true });
  const screenshotPath = `.tmp/diag-${label}-${Date.now()}.png`;
  await diagPage.screenshot({ path: screenshotPath }).catch(() => {});
  console.log(`  Diagnostic screenshot: ${screenshotPath}`);
}

module.exports = { screenshotOnFailure };
