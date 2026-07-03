// Tab registry — tracks tabs that chauffeur scripts create, so a later launch
// can reclaim ones whose owning session has ended.
//
// WHY: connectOverCDP auto-attaches to every open target. When a session ends
// before its tabs are closed, they stay open forever. Over many sessions these
// pile up and eventually wedge connectOverCDP. Each tab is recorded with its CDP
// targetId + the OWNING SESSION (the long-lived Claude session that opened it —
// see ownerInfo below), so the sweep in launch-browser.py keeps a tab alive
// exactly as long as its session's window is open and reclaims it when that
// window closes — never an active session's tab, and never a tab the user opened
// (those are never registered here). The owner is the session, NOT the ephemeral
// node script: one session fires many short-lived scripts (act, screenshot,
// retry), so the tab must outlive any single script.
//
// REQUIRED USAGE — always use the bundled openTab/closeTab so opening and
// closing a tab are mechanically inseparable from registering and unregistering
// it. Never open a tab with bare context.newPage(): an unregistered tab is
// invisible to the launch-browser.py orphan sweep, so it leaks until the
// age/count backstop reaps it or the browser crashes under the accumulation.
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

// The owner of a tab is the Claude session that opened it — recorded so the
// launcher's sweep keeps the tab alive exactly as long as that session's window
// is open, and reclaims it when the window closes. The session launcher
// (launch-session.ps1) exports BROWSER_CHAUFFEUR_OWNER_PID (the long-lived host
// process whose liveness the sweep checks) and BROWSER_CHAUFFEUR_OWNER_SESSION
// (the Claude session id, for traceability). For a session you start yourself,
// set OWNER_PID in your shell profile (see SKILL.md "Tying tab ownership to a
// session"). If neither is set, ownership falls back to this short-lived node
// process — the tab is then reclaimed soon after this script finishes, not at
// session end.
function ownerInfo() {
  const envPid = Number(process.env.BROWSER_CHAUFFEUR_OWNER_PID);
  return {
    ownerPid: Number.isInteger(envPid) && envPid > 0 ? envPid : process.pid,
    ownerSession: process.env.BROWSER_CHAUFFEUR_OWNER_SESSION || null,
  };
}

// Resolve a page's CDP targetId (the registry's stable key across processes).
async function targetIdOf(context, page) {
  const session = await context.newCDPSession(page);
  try {
    const { targetInfo } = await session.send('Target.getTargetInfo');
    return targetInfo.targetId;
  } finally {
    await session.detach().catch(() => {});
  }
}

// Record a tab this session created. Returns its CDP targetId (also used to
// unregister). Returns null on failure — registration is best-effort and must
// never break the actual automation. `lastActive` drives the launcher's sweep:
// it evicts the least-recently-active tab first, so it starts equal to `ts`.
async function registerTab(context, page) {
  try {
    const targetId = await targetIdOf(context, page);
    const now = Date.now();
    const entries = load();
    entries.push({ targetId, ...ownerInfo(), url: page.url(), ts: now, lastActive: now });
    save(entries);
    return targetId;
  } catch {
    return null;
  }
}

// Mark a tab active for the current session. findTab calls this for you on the
// reuse path, so you rarely call it directly — reach for it only when you hold
// a found tab across a long flow and want to keep it fresh. It bumps lastActive
// (so the sweep doesn't treat the tab as idle while you're using it) and claims
// ownership for the current session. Adopts the tab into the registry if it
// wasn't opened via openTab. Best-effort.
async function touchTab(context, page) {
  try {
    const targetId = await targetIdOf(context, page);
    const now = Date.now();
    const { ownerPid, ownerSession } = ownerInfo();
    const entries = load();
    const existing = entries.find(e => e.targetId === targetId);
    if (existing) {
      existing.lastActive = now;
      existing.url = page.url();
      existing.ownerPid = ownerPid;
      existing.ownerSession = ownerSession;
    } else {
      entries.push({ targetId, ownerPid, ownerSession, url: page.url(), ts: now, lastActive: now });
    }
    save(entries);
  } catch {
    // best-effort
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

// Find an existing tab by predicate and mark it active, so a tab a worker keeps
// returning to keeps its place in the eviction order and isn't reaped as idle.
// Returns the matching page, or null (caller then opens one with openTab).
// Prefer this over a bare context.pages().find(...) on the tab-reuse path.
async function findTab(context, predicate) {
  const page = context.pages().find(predicate);
  if (page) await touchTab(context, page);
  return page || null;
}

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

module.exports = { openTab, closeTab, findTab, touchTab, registerTab, unregisterTab, REGISTRY };
