// Source for the `browser-chauffeur-helpers` shim that setup.js installs into
// ~/.claude/browser-chauffeur/node_modules/, so a script anywhere on disk can
// require('browser-chauffeur-helpers') without knowing where the plugin lives.
//
// It resolves the helpers when it is required rather than naming a fixed
// location, because the plugin is installed under a version-numbered directory:
// a path chosen at install time points at one specific version and stops being
// right the moment the plugin updates, stranding every script on the old code
// until something rewrites this file. Resolving on each require means an update
// takes effect on its own.
//
// Preference order:
//   1. The plugin registry, which records the version each scope actually has
//      installed. This is the authoritative answer, and it respects a project
//      deliberately held at an older version.
//   2. The newest version present in the plugin cache, for when the registry is
//      missing or unreadable.
//   3. The location that was current when setup.js wrote this file, as a last
//      resort so an unusual install still works.
//
// setup.js substitutes the literal below; everything else is copied verbatim.

const fs = require('fs');
const os = require('os');
const path = require('path');

const PLUGIN = 'browser-chauffeur';
const HOME = os.homedir();
const REGISTRY = path.join(HOME, '.claude', 'plugins', 'installed_plugins.json');
const CACHE = path.join(HOME, '.claude', 'plugins', 'cache');
const BAKED = '__BAKED_HELPERS_PATH__';

// Compare dotted versions numerically, so 1.12.0 ranks above 1.9.1 (a string
// comparison would not).
function isNewer(a, b) {
  const parse = v => String(v).split('.').map(n => parseInt(n, 10) || 0);
  const x = parse(a);
  const y = parse(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const diff = (x[i] || 0) - (y[i] || 0);
    if (diff !== 0) return diff > 0;
  }
  return false;
}

function helpersIn(dir) {
  const candidate = path.join(dir, 'helpers.js');
  return fs.existsSync(candidate) ? candidate : null;
}

// Entries whose projectPath contains the current directory win: that is the
// install actually governing this project. Otherwise take the highest version.
function fromRegistry() {
  const data = JSON.parse(fs.readFileSync(REGISTRY, 'utf8'));
  const cwd = process.cwd().toLowerCase();
  let scoped = null;
  let highest = null;
  for (const [key, installs] of Object.entries((data && data.plugins) || {})) {
    if (key.split('@')[0] !== PLUGIN) continue;
    for (const install of installs || []) {
      if (!install || !install.installPath) continue;
      const project = (install.projectPath || '').toLowerCase();
      if (project && cwd.startsWith(project)) {
        if (!scoped || isNewer(install.version, scoped.version)) scoped = install;
      }
      if (!highest || isNewer(install.version, highest.version)) highest = install;
    }
  }
  const chosen = scoped || highest;
  return chosen ? helpersIn(chosen.installPath) : null;
}

function fromCache() {
  let best = null;
  for (const marketplace of fs.readdirSync(CACHE)) {
    const pluginDir = path.join(CACHE, marketplace, PLUGIN);
    let versions;
    try {
      versions = fs.readdirSync(pluginDir);
    } catch {
      continue;  // this marketplace doesn't carry the plugin
    }
    for (const version of versions) {
      // Check for helpers.js before ranking, so a partial directory can't
      // shadow a complete older one.
      const helpers = helpersIn(path.join(pluginDir, version));
      if (helpers && (!best || isNewer(version, best.version))) {
        best = { version, helpers };
      }
    }
  }
  return best ? best.helpers : null;
}

function fromBaked() {
  return BAKED && fs.existsSync(BAKED) ? BAKED : null;
}

let resolved = null;
for (const attempt of [fromRegistry, fromCache, fromBaked]) {
  try {
    resolved = attempt();
  } catch {
    resolved = null;  // try the next source
  }
  if (resolved) break;
}

if (!resolved) {
  throw new Error(
    'browser-chauffeur-helpers: could not locate helpers.js. Run the plugin\'s '
    + 'templates/setup.js to reinstall the shim.'
  );
}

module.exports = require(resolved);
