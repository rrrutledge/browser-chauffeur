// Read / mark-read InnerSource Commons Slack via the Slack Web API with a personal xoxc token.
//
// Auth: set SLACK_BOT_TOKEN (despite the name, a personal xoxc- USER token — sniffed from the browser),
// SLACK_COOKIE_D (the xoxd- session `d` cookie — the xoxc token is invalid_auth without it), and
// SLACK_TEAM_ID (T04PXKRM0 for InnerSource Commons). No bot app, no OAuth scopes to manage. The xoxc
// token expires periodically; when --check reports invalid_auth, re-sniff it per the token-refresh doc
// (personal-ai-pod/docs/slack-token-refresh.md). Zero npm deps — uses Node's built-in fetch (Node 18+).
//
// Auth glance:   node slack.js --check
//                (calls auth.test; prints the signed-in user/team; non-zero exit on auth failure)
// List unread:   node slack.js --list-unread [--top=50] [--json]
//                (unread DMs + group DMs + @-mentions of you in channels, newest-first; --json emits a
//                 structured array for scripts — each item carries channel, ts, from, subject, preview)
// Show one:      node slack.js --show --channel=<C> --ts=<ts> [--json]
//                (the message text + a chat.getPermalink url; --json emits {channel,ts,from,text,permalink})
// Mark read:     node slack.js --mark --channel=<C> --ts=<ts>
//                (conversations.mark up to <ts> — the conversation's "gone"; reversible, never deletes)

const TOKEN = process.env.SLACK_BOT_TOKEN;
const COOKIE = process.env.SLACK_COOKIE_D;
const TEAM = process.env.SLACK_TEAM_ID;

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);

function requireAuth() {
  if (!TOKEN || !COOKIE) {
    throw new Error('Not signed in: set SLACK_BOT_TOKEN (xoxc) and SLACK_COOKIE_D (xoxd `d` cookie) in the environment.');
  }
}

// One Slack Web API call. The xoxc user token goes in the Authorization header; the matching xoxd `d`
// cookie rides along in the Cookie header (most api/ paths and all client.* paths reject the token alone).
async function call(method, params = {}) {
  const body = new URLSearchParams(params).toString();
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Cookie': `d=${COOKIE}`,
      'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
    },
    body,
  });
  const json = await res.json();
  if (!json.ok) throw new Error(`${method} failed: ${json.error || 'unknown'}`);
  return json;
}

const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const tsToIso = (ts) => new Date(parseFloat(ts) * 1000).toISOString();

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

// Resolve <@U...> mentions in message text to readable @Name for previews.
async function renderText(text) {
  let out = text || '';
  const ids = [...new Set([...out.matchAll(/<@([A-Z0-9]+)>/g)].map(m => m[1]))];
  for (const id of ids) out = out.replaceAll(`<@${id}>`, `@${await userName(id)}`);
  return clean(out);
}

// Unread messages in one conversation: history since last_read, newest-first, excluding our own and
// pure system join/leave noise. Returns the raw message objects (ts-descending).
async function unreadMessages(channel, lastRead, myId, limit = 30) {
  // Fetch recent history and filter to unread client-side. (Passing `oldest=last_read` is unreliable —
  // some conversations carry a last_read value Slack rejects with invalid_ts_oldest.)
  const r = await call('conversations.history', { channel, limit: String(limit) });
  return (r.messages || [])
    .filter(m => m.ts && parseFloat(m.ts) > parseFloat(lastRead || '0'))
    .filter(m => m.user && m.user !== myId)
    .filter(m => !m.subtype || m.subtype === 'thread_broadcast' || m.subtype === 'me_message')
    .sort((a, b) => parseFloat(b.ts) - parseFloat(a.ts));
}

async function listUnread() {
  const me = (await call('auth.test')).user_id;
  const counts = await call('client.counts');
  const items = [];

  // DMs (im) and group DMs (mpim): one item per conversation, keyed to the latest unread message.
  for (const kind of ['ims', 'mpims']) {
    for (const c of counts[kind] || []) {
      if (!c.has_unreads) continue;
      const msgs = await unreadMessages(c.id, c.last_read, me);
      if (!msgs.length) continue;
      const latest = msgs[0];
      const info = await convInfo(c.id);
      const from = await userName(latest.user);
      const preview = (await Promise.all(msgs.slice(0, 5).reverse().map(m => renderText(m.text)))).join(' / ');
      const subject = kind === 'ims'
        ? `DM from ${from}`
        : `Group DM (${info.name || 'group'})`;
      const channelName = kind === 'ims' ? `@${from}` : (info.name ? `mpdm:${info.name}` : 'group DM');
      items.push({
        id: `${c.id}:${latest.ts}`, channel: c.id, channelType: kind === 'ims' ? 'im' : 'mpim',
        ts: latest.ts, from, fromId: latest.user, subject, channelName,
        received: tsToIso(latest.ts), isRead: false, unreadCount: msgs.length,
        preview: clean(preview).slice(0, 600),
      });
    }
  }

  // Channel @-mentions: one item per mentioning message (since last_read) that names me.
  for (const c of counts.channels || []) {
    if (!c.mention_count || c.mention_count < 1) continue;
    const msgs = await unreadMessages(c.id, c.last_read, me);
    const mentions = msgs.filter(m => (m.text || '').includes(`<@${me}>`));
    if (!mentions.length) continue;
    const info = await convInfo(c.id);
    const chName = info.name ? `#${info.name}` : c.id;
    for (const m of mentions) {
      const from = await userName(m.user);
      items.push({
        id: `${c.id}:${m.ts}`, channel: c.id, channelType: 'channel',
        ts: m.ts, from, fromId: m.user, subject: `@mention in ${chName}`, channelName: chName,
        received: tsToIso(m.ts), isRead: false, unreadCount: 1,
        preview: (await renderText(m.text)).slice(0, 600),
      });
    }
  }

  items.sort((a, b) => parseFloat(b.ts) - parseFloat(a.ts));
  const top = parseInt(args.top || '50', 10);
  const out = items.slice(0, top);

  if (args.json) { console.log(JSON.stringify(out, null, 2)); return; }
  if (!out.length) { console.log('No unread DMs or mentions.'); return; }
  console.log(`${out.length} unread item(s) (newest first):`);
  for (const it of out) {
    console.log(`\n--- ${it.received.slice(0, 16)}  |  ${it.subject}`);
    console.log(`    from: ${it.from}  (${it.channelName})`);
    console.log(`    id:   ${it.id}`);
    console.log(`    text: ${it.preview.slice(0, 160)}`);
  }
}

async function show() {
  if (!args.channel || !args.ts) throw new Error('--show requires --channel and --ts');
  const r = await call('conversations.history',
    { channel: args.channel, latest: args.ts, oldest: args.ts, inclusive: 'true', limit: '1' });
  const m = (r.messages || [])[0];
  if (!m) { console.log('Message not found.'); return; }
  const from = await userName(m.user);
  const text = await renderText(m.text);
  let permalink = '';
  try { permalink = (await call('chat.getPermalink', { channel: args.channel, message_ts: args.ts })).permalink || ''; }
  catch { /* permalink optional */ }
  if (args.json) {
    console.log(JSON.stringify({ channel: args.channel, ts: args.ts, from, fromId: m.user,
      received: tsToIso(args.ts), text, permalink }, null, 2));
    return;
  }
  console.log(`From: ${from}`);
  console.log(`When: ${tsToIso(args.ts)}`);
  if (permalink) console.log(`Link: ${permalink}`);
  console.log(`\n${text || '(no text)'}`);
}

async function mark() {
  if (!args.channel || !args.ts) throw new Error('--mark requires --channel and --ts');
  await call('conversations.mark', { channel: args.channel, ts: args.ts });
  console.log(`Marked ${args.channel} read up to ${args.ts}. Reversible — re-reading the conversation re-surfaces it.`);
}

async function check() {
  const r = await call('auth.test');
  console.log(`Signed in as ${r.user} (${r.team}, team ${r.team_id}). user_id ${r.user_id}.`);
}

(async () => {
  requireAuth();
  if (args.check) return await check();
  if (args['list-unread']) return await listUnread();
  if (args.show) return await show();
  if (args.mark) return await mark();
  throw new Error('Specify --check, --list-unread, --show, or --mark');
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
