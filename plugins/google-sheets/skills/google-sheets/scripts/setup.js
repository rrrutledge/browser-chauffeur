// Installs the google-sheets script dependencies (googleapis, google-auth-library) into a stable
// per-user location so every google-sheets script can resolve them, regardless of which directory
// it runs from. Mirrors gmail's setup.js / google-docs's setup.js dependency-bootstrap pattern.
//
//   node setup.js   -> idempotent; skips install if deps already present.

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DEP_HOME = path.join(os.homedir(), '.claude', 'google-sheets');
const DEP_DIR = path.join(DEP_HOME, 'node_modules');
const SCRIPTS_DIR = __dirname;

function present(pkg) {
  try { require.resolve(pkg, { paths: [DEP_DIR] }); return true; } catch { return false; }
}

if (present('google-auth-library') && present('googleapis')) {
  console.log('[OK] google-sheets deps already installed at ' + DEP_DIR);
  process.exit(0);
}

fs.mkdirSync(DEP_HOME, { recursive: true });
fs.copyFileSync(path.join(SCRIPTS_DIR, 'package.json'), path.join(DEP_HOME, 'package.json'));
console.log('[..] Installing google-sheets deps into ' + DEP_HOME + ' (one-time)');
execSync('npm install --omit=dev --no-audit --no-fund', { cwd: DEP_HOME, stdio: 'inherit' });
console.log('[OK] google-sheets deps installed.');
