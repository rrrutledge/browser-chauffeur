// Installs the Graph script dependencies (@azure/msal-node, @microsoft/microsoft-graph-client)
// into a stable per-user location so every ms-graph script can resolve them, regardless of
// which directory it runs from. Mirrors browser-chauffeur's dependency-bootstrap pattern.
//
//   node setup.js   -> idempotent; skips install if deps already present.

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DEP_HOME = path.join(os.homedir(), '.claude', 'ms-graph');
const DEP_DIR = path.join(DEP_HOME, 'node_modules');
const SCRIPTS_DIR = __dirname;

function present(pkg) {
  try { require.resolve(pkg, { paths: [DEP_DIR] }); return true; } catch { return false; }
}

if (present('@azure/msal-node') && present('@microsoft/microsoft-graph-client')) {
  console.log('[OK] ms-graph deps already installed at ' + DEP_DIR);
  process.exit(0);
}

fs.mkdirSync(DEP_HOME, { recursive: true });
// Copy the package.json next to the install target, then install there.
fs.copyFileSync(path.join(SCRIPTS_DIR, 'package.json'), path.join(DEP_HOME, 'package.json'));
console.log('[..] Installing ms-graph deps into ' + DEP_HOME + ' (one-time)');
execSync('npm install --omit=dev --no-audit --no-fund', { cwd: DEP_HOME, stdio: 'inherit' });
console.log('[OK] ms-graph deps installed.');
