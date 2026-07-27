// One-time setup for browser-chauffeur. Run before first use (SKILL.md calls
// this automatically as part of the prerequisite check).
//
// What it does:
//   1. Installs playwright-core to ~/.claude/browser-chauffeur/ if not already
//      accessible via require('playwright-core').
//   2. Creates a browser-chauffeur-helpers shim in the same location so scripts
//      can require('browser-chauffeur-helpers') from the fallback path.
//
// After setup, all browser-chauffeur scripts fall back to
// ~/.claude/browser-chauffeur/node_modules/ when the package is not installed
// in the current project — no manual npm install or npm link needed.

const os = require('os');
const path = require('path');
const fs = require('fs');
const cp = require('child_process');

const SHARED_DIR = path.join(os.homedir(), '.claude', 'browser-chauffeur');
const SHARED_NM = path.join(SHARED_DIR, 'node_modules');

function playwrightCoreFound() {
  try { require.resolve('playwright-core'); return true; } catch { return false; }
}

function playwrightCoreSharedInstalled() {
  return fs.existsSync(path.join(SHARED_NM, 'playwright-core'));
}

function installPlaywrightCore() {
  fs.mkdirSync(SHARED_DIR, { recursive: true });
  console.log('Installing playwright-core to ~/.claude/browser-chauffeur/ ...');
  const result = cp.spawnSync(
    'npm', ['install', 'playwright-core', '--prefix', SHARED_DIR],
    { stdio: 'inherit', shell: process.platform === 'win32' }
  );
  if (result.status !== 0) {
    console.error('npm install failed — check npm is on PATH and try again.');
    process.exit(1);
  }
}

// Installs helpers-shim.js, which finds the active helpers.js when it is
// required instead of naming one version's path. The plugin lives under a
// version-numbered directory, so a path fixed at setup time goes stale on the
// next update and leaves every script loading the previous version until
// something rewrites the shim. Resolving per require means an update applies by
// itself. The current path is still substituted in as a last-resort fallback.
function writeHelpersShim() {
  const helpersJs = path.resolve(__dirname, '..', '..', '..', 'helpers.js');
  if (!fs.existsSync(helpersJs)) {
    console.warn('Warning: helpers.js not found at', helpersJs, '— skipping shim.');
    return;
  }
  const template = path.join(__dirname, 'helpers-shim.js');
  if (!fs.existsSync(template)) {
    console.warn('Warning: helpers-shim.js not found at', template, '— skipping shim.');
    return;
  }
  const source = fs.readFileSync(template, 'utf8')
    .replace("'__BAKED_HELPERS_PATH__'", JSON.stringify(helpersJs));
  const shimDir = path.join(SHARED_NM, 'browser-chauffeur-helpers');
  fs.mkdirSync(shimDir, { recursive: true });
  fs.writeFileSync(path.join(shimDir, 'index.js'), source);
  fs.writeFileSync(
    path.join(shimDir, 'package.json'),
    JSON.stringify({ name: 'browser-chauffeur-helpers', version: '1.0.0', main: 'index.js' }, null, 2) + '\n'
  );
}

// --- main ---

if (playwrightCoreFound()) {
  console.log('[OK] playwright-core: found in project node_modules');
} else if (playwrightCoreSharedInstalled()) {
  console.log('[OK] playwright-core: found in ~/.claude/browser-chauffeur/');
} else {
  installPlaywrightCore();
  console.log('[OK] playwright-core: installed to ~/.claude/browser-chauffeur/');
}

writeHelpersShim();
console.log('[OK] browser-chauffeur-helpers shim: updated');
console.log('[OK] Setup complete — browser-chauffeur is ready.');
