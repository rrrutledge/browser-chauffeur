// Read / mark-read a Slack workspace via the Slack Web API.
//
// Auth: token + d-cookie are auto-sniffed from the live CDP browser session and cached at
// ~/.claude/slack-token.json. The CDP browser (Edge on port 9222) must have a Slack tab open
// (app.slack.com/client/<TEAM_ID>). SLACK_BOT_TOKEN / SLACK_COOKIE_D env vars serve as a
// bootstrap fallback when the sniff fails (e.g. browser not running). SLACK_TEAM_ID identifies
// the workspace in localStorage; if unset the first team found is used.
// Requires playwright-core (present via browser-chauffeur). Fetch: Node 18+.
//
// Auth glance:   node slack.js --check
//                (calls auth.test; prints the signed-in user/team; non-zero exit on auth failure)
// List unread:   node slack.js --list-unread [--top=50] [--json]
//                (unread DMs + group DMs + @-mentions + unread subscribed-thread replies, newest-first;
//                 muted conversations are skipped; --json emits a structured array)
// Show one:      node slack.js --show --channel=<C> --ts=<ts> [--thread-ts=<tts>] [--json]
//                (the message text + a chat.getPermalink url; pass --thread-ts for a threaded reply)
// Mark read:     node slack.js --mark --channel=<C> --ts=<ts> [--thread-ts=<tts>]
//                (conversations.mark up to <ts>, or subscriptions.thread.mark when --thread-ts is given —
//                 the conversation/thread's "gone"; reversible, never deletes)

const fs = require('fs');
const path = require('path');
const os = require('os');

const TEAM = process.env.SLACK_TEAM_ID;

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);

// ---- Token cache + CDP sniff ---------------------------------------------------

// Stable user-level path so the cache is found regardless of which repo the skill runs from.
const TOKEN_FILE = path.join(os.homedir(), '.claude', 'slack-token.json');
const EXPIRY_SKEW_S = 120;
const TOKEN_TTL_S = 23 * 3600; // xoxc tokens typically last ~24h; cache for 23h
const CDP_TIMEOUT_MS = 30000;

function readCachedToken() {
  try {
    const meta = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf8'));
    if (meta.token && meta.cookie && meta.exp && meta.exp - EXPIRY_SKEW_S > Date.now() / 1000) return meta;
  } catch {}
  return null;
}

async function sniffToken() {
  const { chromium } = (() => {
    try { return require('playwright-core'); }
    catch { return require(path.join(os.homedir(), '.claude', 'browser-chauffeur', 'node_modules', 'playwright-core')); }
  })();
  // Race against a timeout — connectOverCDP can hang indefinitely on a wedged browser.
  const browser = await Promise.race([
    chromium.connectOverCDP('http://localhost:9222'),
    new Promise((_, reject) => setTimeout(
      () => reject(new Error('CDP connect timed out after 30 s — is Edge running on port 9222?')),
      CDP_TIMEOUT_MS,
    )),
  ]);
  const context = browser.contexts()[0];
  if (!context) {
    await browser.disconnect().catch(() => {});
    throw new Error('No CDP browser context (is Edge running on port 9222?)');
  }
  // Match only the authenticated Slack app tab, not marketing/signin/status pages.
  const page = context.pages().find(p => /app\.slack\.com\/client\//.test(p.url()));
  if (!page) {
    await browser.disconnect().catch(() => {});
    const teamHint = TEAM ? `app.slack.com/client/${TEAM}` : 'app.slack.com/client/<TEAM_ID>';
    throw new Error(`No authenticated Slack tab found in CDP browser — open ${teamHint}`);
  }
  let localToken, cookies;
  try {
    // Fetch token and cookies in parallel — independent CDP round-trips.
    [localToken, cookies] = await Promise.all([
      page.evaluate((teamId) => {
        try {
          const raw = localStorage.getItem('localConfig_v2');
          if (!raw) return null;
          const cfg = JSON.parse(raw);
          if (teamId && cfg.teams && cfg.teams[teamId]) return cfg.teams[teamId].token || null;
          const ids = Object.keys(cfg.teams || {});
          return ids.length ? (cfg.teams[ids[0]].token || null) : null;
        } catch { return null; }
      }, TEAM || ''),
      context.cookies(['https://slack.com', 'https://app.slack.com']),
    ]);
  } finally {
    // disconnect() leaves the remote Edge process running; close() would kill it.
    await browser.disconnect().catch(() => {});
  }
  const dCookie = cookies.find(c => c.name === 'd' && c.domain && c.domain.includes('slack.com'));
  if (!localToken || !localToken.startsWith('xoxc-')) {
    throw new Error('No valid xoxc token in Slack localStorage — is the Slack tab signed in?');
  }
  if (!dCookie) throw new Error('No d session cookie found for slack.com');
  const cookieExp = dCookie.expires && dCookie.expires > 0 ? dCookie.expires : null;
  const meta = {
    token: localToken,
    cookie: dCookie.value,
    exp: cookieExp ? Math.min(cookieExp, Math.floor(Date.now() / 1000) + TOKEN_TTL_S) : Math.floor(Date.now() / 1000) + TOKEN_TTL_S,
    capturedISO: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true });
  fs.writeFileSync(TOKEN_FILE, JSON.stringify(meta, null, 2));
  return meta;
}

async function getToken(force) {
  if (!force) {
    const cached = readCachedToken();
    if (cached) return cached;
  }
  try {
    return await sniffToken();
  } catch (sniffErr) {
    if (process.env.SLACK_BOT_TOKEN && process.env.SLACK_COOKIE_D) {
      if (force) {
        // Re-sniff failed after invalid_auth — retrying the same stale env-var token would be
        // silent and misleading; surface a clear error instead.
        throw new Error(`Token re-sniff failed (${sniffErr.message}) and env-var credentials appear stale. `
          + 'Update SLACK_BOT_TOKEN/SLACK_COOKIE_D or open a Slack tab in the CDP browser.');
      }
      // First-time env-var fallback: cache for 1 h so subsequent call()s skip the sniff.
      const meta = {
        token: process.env.SLACK_BOT_TOKEN,
        cookie: process.env.SLACK_COOKIE_D,
        exp: Math.floor(Date.now() / 1000) + 3600,
        capturedISO: new Date().toISOString(),
      };
      try { fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true }); fs.writeFileSync(TOKEN_FILE, JSON.stringify(meta, null, 2)); } catch {}
      return meta;
    }
    throw new Error(`${sniffErr.message} (alternatively, set SLACK_BOT_TOKEN + SLACK_COOKIE_D env vars)`);
  }
}

// One Slack Web API call. Token + d-cookie come from the cache/sniff; on invalid_auth the token
// is re-sniffed once and the call retried (transparent to callers).
async function call(method, params = {}) {
  let meta = await getToken(false);
  const body = new URLSearchParams(params).toString();
  const doFetch = (tok, cookie) => fetch(`https://slack.com/api/${method}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${tok}`,
      'Cookie': `d=${cookie}`,
      'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
    },
    body,
  }).then(r => r.json());
  let json = await doFetch(meta.token, meta.cookie);
  if (!json.ok && json.error === 'invalid_auth') {
    try { fs.unlinkSync(TOKEN_FILE); } catch {}
    meta = await getToken(true);
    json = await doFetch(meta.token, meta.cookie);
  }
  if (!json.ok) throw new Error(`${method} failed: ${json.error || 'unknown'}`);
  return json;
}

const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const tsToIso = (ts) => new Date(parseFloat(ts) * 1000).toISOString();
const newer = (a, b) => parseFloat(a) > parseFloat(b || '0');

// ---- name/info resolution (cached within one run) ----
const userCache = new Map();
async function userName(id) {
  if (!id) return '?';
  if (userCache.has(id)) return userCache.get(id);
  let name = id;
  try {
    const r = await call('users.info', { user: id });
    const u = r.user || {};
    name = u.real_name || (u.profile && u.profile.real_name) || u.name || id;
  } catch { /* fall back to the id */ }
  userCache.set(id, name);
  return name;
}

const convCache = new Map();
async function convInfo(channel) {
  if (convCache.has(channel)) return convCache.get(channel);
  let info = {};
  try { info = (await call('conversations.info', { channel })).channel || {}; } catch { /* ignore */ }
  convCache.set(channel, info);
  return info;
}

// The set of channel/DM ids the user has muted. Slack stores this per-conversation under
// all_notifications_prefs.channels[id].muted; the legacy comma-string `muted_channels` pref is empty on
// modern accounts. A muted conversation should never surface as a drainer item — muting IS the stop.
async function mutedSet() {
  try {
    const prefs = (await call('users.prefs.get')).prefs || {};
    let anp = prefs.all_notifications_prefs;
    if (typeof anp === 'string') anp = JSON.parse(anp);
    const chans = (anp && anp.channels) || {};
    const muted = new Set(Object.keys(chans).filter(id => chans[id] && chans[id].muted === true));
    // Fold in the legacy pref too, if present.
    for (const id of String(prefs.muted_channels || '').split(',').filter(Boolean)) muted.add(id);
    return muted;
  } catch {
    return new Set();  // fail-open: better to surface than to silently drop everything
  }
}

// Resolve <@U...> mentions in message text to readable @Name for previews.
async function renderText(text) {
  let out = text || '';
  const ids = [...new Set([...out.matchAll(/<@([A-Z0-9]+)>/g)].map(m => m[1]))];
  for (const id of ids) out = out.replaceAll(`<@${id}>`, `@${await userName(id)}`);
  return clean(out);
}

// Unread top-level messages in one conversation: recent history filtered to ts > last_read, excluding our
// own and pure system join/leave noise. (Passing oldest=last_read is unreliable — some conversations
// carry a last_read value Slack rejects with invalid_ts_oldest — so we filter client-side.)
async function unreadMessages(channel, lastRead, myId, limit = 30) {
  const r = await call('conversations.history', { channel, limit: String(limit) });
  return (r.messages || [])
    .filter(m => m.ts && newer(m.ts, lastRead))
    .filter(m => m.user && m.user !== myId)
    .filter(m => !m.subtype || m.subtype === 'thread_broadcast' || m.subtype === 'me_message')
    .sort((a, b) => parseFloat(b.ts) - parseFloat(a.ts));
}

async function listUnread() {
  const me = (await call('auth.test')).user_id;
  const muted = await mutedSet();
  const counts = await call('client.counts');
  const items = [];

  // DMs (im) and group DMs (mpim): one item per conversation, keyed to the latest unread message.
  for (const kind of ['ims', 'mpims']) {
    for (const c of counts[kind] || []) {
      if (!c.has_unreads || muted.has(c.id)) continue;
      const msgs = await unreadMessages(c.id, c.last_read, me);
      if (!msgs.length) continue;
      const latest = msgs[0];
      const info = await convInfo(c.id);
      const from = await userName(latest.user);
      const preview = (await Promise.all(msgs.slice(0, 5).reverse().map(m => renderText(m.text)))).join(' / ');
      const subject = kind === 'ims' ? `DM from ${from}` : `Group DM (${info.name || 'group'})`;
      const channelName = kind === 'ims' ? `@${from}` : (info.name ? `mpdm:${info.name}` : 'group DM');
      items.push({
        id: `${c.id}:${latest.ts}`, channel: c.id, channelType: kind === 'ims' ? 'im' : 'mpim',
        ts: latest.ts, threadTs: '', from, fromId: latest.user, subject, channelName,
        received: tsToIso(latest.ts), isRead: false, unreadCount: msgs.length,
        preview: clean(preview).slice(0, 600),
      });
    }
  }

  // Channel @-mentions (top-level): one item per mentioning message (since last_read) that names me.
  for (const c of counts.channels || []) {
    if (!c.mention_count || c.mention_count < 1 || muted.has(c.id)) continue;
    const msgs = await unreadMessages(c.id, c.last_read, me);
    const mentions = msgs.filter(m => (m.text || '').includes(`<@${me}>`));
    if (!mentions.length) continue;
    const info = await convInfo(c.id);
    const chName = info.name ? `#${info.name}` : c.id;
    for (const m of mentions) {
      const from = await userName(m.user);
      items.push({
        id: `${c.id}:${m.ts}`, channel: c.id, channelType: 'channel',
        ts: m.ts, threadTs: '', from, fromId: m.user, subject: `@mention in ${chName}`, channelName: chName,
        received: tsToIso(m.ts), isRead: false, unreadCount: 1,
        preview: (await renderText(m.text)).slice(0, 600),
      });
    }
  }

  // Subscribed threads with unread replies: one item per thread, keyed to the latest unread reply. A
  // thread carries its OWN read cursor (root_msg.last_read) separate from the channel's, so thread
  // replies never appear in conversations.history above — they're enumerated here.
  try {
    const view = await call('subscriptions.thread.getView', { limit: '50' });
    for (const t of view.threads || []) {
      const root = t.root_msg || {};
      const channel = root.channel;
      if (!channel || muted.has(channel)) continue;
      if (!newer(root.latest_reply, root.last_read)) continue;  // no unread replies
      const unread = (t.latest_replies || [])
        .filter(m => m.ts && newer(m.ts, root.last_read) && m.user && m.user !== me)
        .sort((a, b) => parseFloat(b.ts) - parseFloat(a.ts));
      if (!unread.length) continue;
      const latest = unread[0];
      const info = await convInfo(channel);
      const chName = info.name ? `#${info.name}` : channel;
      const from = await userName(latest.user);
      const mentioned = unread.some(m => (m.text || '').includes(`<@${me}>`));
      const preview = (await Promise.all(unread.slice(0, 5).reverse().map(m => renderText(m.text)))).join(' / ');
      items.push({
        id: `${channel}:${latest.ts}`, channel, channelType: 'thread',
        ts: latest.ts, threadTs: root.thread_ts || root.ts, from, fromId: latest.user,
        subject: mentioned ? `@mention in thread in ${chName}` : `Thread reply in ${chName}`,
        channelName: chName, received: tsToIso(latest.ts), isRead: false, unreadCount: unread.length,
        preview: clean(preview).slice(0, 600),
      });
    }
  } catch { /* threads view unavailable — DMs/mentions still enumerate */ }

  items.sort((a, b) => parseFloat(b.ts) - parseFloat(a.ts));
  const top = parseInt(args.top || '50', 10);
  const out = items.slice(0, top);

  if (args.json) { console.log(JSON.stringify(out, null, 2)); return; }
  if (!out.length) { console.log('No unread DMs, mentions, or thread replies.'); return; }
  console.log(`${out.length} unread item(s) (newest first):`);
  for (const it of out) {
    console.log(`\n--- ${it.received.slice(0, 16)}  |  ${it.subject}`);
    console.log(`    from: ${it.from}  (${it.channelName})`);
    console.log(`    id:   ${it.id}${it.threadTs ? `  thread:${it.threadTs}` : ''}`);
    console.log(`    text: ${it.preview.slice(0, 160)}`);
  }
}

// Fetch one message — from the thread (conversations.replies) when --thread-ts is given, else the
// channel timeline (conversations.history). A threaded reply is not reliably returned by history.
async function fetchOne(channel, ts, threadTs) {
  if (threadTs && threadTs !== ts) {
    const r = await call('conversations.replies', { channel, ts: threadTs, limit: '100' });
    return (r.messages || []).find(m => m.ts === ts) || null;
  }
  const r = await call('conversations.history',
    { channel, latest: ts, oldest: ts, inclusive: 'true', limit: '1' });
  return (r.messages || [])[0] || null;
}

async function show() {
  if (!args.channel || !args.ts) throw new Error('--show requires --channel and --ts');
  const m = await fetchOne(args.channel, args.ts, args['thread-ts']);
  if (!m) { console.log('Message not found.'); return; }
  const from = await userName(m.user);
  const text = await renderText(m.text);
  let permalink = '';
  try { permalink = (await call('chat.getPermalink', { channel: args.channel, message_ts: args.ts })).permalink || ''; }
  catch { /* permalink optional */ }
  if (args.json) {
    console.log(JSON.stringify({ channel: args.channel, ts: args.ts, threadTs: args['thread-ts'] || '',
      from, fromId: m.user, received: tsToIso(args.ts), text, permalink }, null, 2));
    return;
  }
  console.log(`From: ${from}`);
  console.log(`When: ${tsToIso(args.ts)}`);
  if (permalink) console.log(`Link: ${permalink}`);
  console.log(`\n${text || '(no text)'}`);
}

async function mark() {
  if (!args.channel || !args.ts) throw new Error('--mark requires --channel and --ts');
  if (args['thread-ts']) {
    await call('subscriptions.thread.mark',
      { channel: args.channel, thread_ts: args['thread-ts'], ts: args.ts, read: '1' });
    console.log(`Marked thread ${args['thread-ts']} in ${args.channel} read up to ${args.ts}. Reversible.`);
    return;
  }
  await call('conversations.mark', { channel: args.channel, ts: args.ts });
  console.log(`Marked ${args.channel} read up to ${args.ts}. Reversible — re-reading the conversation re-surfaces it.`);
}

async function check() {
  const r = await call('auth.test');
  console.log(`Signed in as ${r.user} (${r.team}, team ${r.team_id}). user_id ${r.user_id}.`);
}

(async () => {
  if (args.check) return await check();
  if (args['list-unread']) return await listUnread();
  if (args.show) return await show();
  if (args.mark) return await mark();
  throw new Error('Specify --check, --list-unread, --show, or --mark');
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
