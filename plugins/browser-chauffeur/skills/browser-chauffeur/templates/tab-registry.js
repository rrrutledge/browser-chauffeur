// Tab registry — tracks tabs that chauffeur scripts create, so a later launch
// can reclaim ones orphaned by a crashed/interrupted run.
//
// WHY: connectOverCDP auto-attaches to every open target. When a script dies
// before its finally block runs, the tab it opened stays open forever. Over many
// sessions these orphans pile up and eventually wedge connectOverCDP. Tracking
// each created tab's CDP targetId + the creating process's PID lets the sweep in
// launch-browser.py close ONLY our own orphans (creating process is dead) — never
// an active session's tab, and never a tab the user opened (those are never
// registered here).
//
// RECOMMENDED USAGE — use the bundled openTab/closeTab so opening and closing a
// tab are mechanically inseparable from registering and unregistering it. This
// removes the failure mode where a script opens a tab but forgets to register it
// (making it un-reclaimable) or closes it but forgets to unregister it.
//
//   const { openTab, closeTab } = require('browser-chauffeur-helpers');
//   const page = await openTab(context, 'https://example.com');  // creates + registers (+ optional goto)
//   try { /* work with page */ } finally { await closeTab(page); } // closes + unregisters
//
// closeTab parks (about:blank) instead of closing when it's the browser's last
// tab, so it never accidentally exits the persistent browser.
//
// registerTab/unregisterTab remain exported as the lower-level primitives, but
// prefer openTab/closeTab.
//
// The registry file is shared across all Claude sessions, so reads/writes are
// atomic (write-temp-then-rename) and tolerant of a missing/corrupt file.

const fs = require('fs');
const os = require('os');
const path = require('path');

const REGISTRY = path.join(os.homedir(), '.claude', 'browser-chauffeur', 'created-tabs.json');

function load() {
  try {
    return JSON.parse(fs.readFileSync(REGISTRY, 'utf8'));
  } catch {
    return [];
  }
}

function save(entries) {
  fs.mkdirSync(path.dirname(REGISTRY), { recursive: true });
  // Unique temp name per process so concurrent writers don't clobber the temp.
  const tmp = `${REGISTRY}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(entries));
  fs.renameSync(tmp, REGISTRY);
}

// Record a tab this process created. Returns its CDP targetId (also used to
// unregister). Returns null on failure — registration is best-effort and must
// never break the actual automation.
async function registerTab(context, page) {
  try {
    const session = await context.newCDPSession(page);
    const { targetInfo } = await session.send('Target.getTargetInfo');
    await session.detach().catch(() => {});
    const targetId = targetInfo.targetId;
    const entries = load();
    entries.push({ targetId, nodePid: process.pid, url: page.url(), ts: Date.now() });
    save(entries);
    return targetId;
  } catch {
    return null;
  }
}

// Remove a tab from the registry after it is cleanly closed.
function unregisterTab(targetId) {
  if (!targetId) return;
  try {
    save(load().filter(e => e.targetId !== targetId));
  } catch {
    // best-effort
  }
}

// Associates each page with its registry targetId so closeTab(page) needs only
// the page. WeakMap so entries are GC'd with the page and the page object stays
// unpolluted.
const tabIds = new WeakMap();

// Open a new tab, register it, and (optionally) navigate to url. Returns the
// page. Use this instead of context.newPage() so registration can't be skipped.
async function openTab(context, url) {
  const page = await context.newPage();
  const tabId = await registerTab(context, page);
  tabIds.set(page, tabId);
  if (url) await page.goto(url);
  return page;
}

// Close a tab opened with openTab and unregister it. Parks on about:blank
// instead of closing when it is the browser's last tab (closing it would exit
// the persistent browser and lose all logins). Always unregisters — reaching
// here means the tab is not an orphan.
async function closeTab(page) {
  const context = page.context();
  try {
    if (context.pages().length > 1) {
      await page.close().catch(() => {});
    } else {
      await page.goto('about:blank').catch(() => {});
    }
  } finally {
    unregisterTab(tabIds.get(page));
    tabIds.delete(page);
  }
}

module.exports = { openTab, closeTab, registerTab, unregisterTab, REGISTRY };
