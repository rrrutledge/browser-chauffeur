// Read / draft / clear personal Gmail (or Google Workspace) mail via IMAP with an app password.
//
// Auth: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment (a 16-char Google App
// Password — requires 2-Step Verification on the account, and IMAP enabled in Gmail settings).
// No OAuth app, no Cloud project, no browser.
//
// List inbox:    node gmail.js --list-inbox [--top=50] [--json]
//                (inbox, newest-first; --json emits a structured array for scripts)
// Show one:      node gmail.js --show=<message-id>
//                (<message-id> is the RFC822 Message-ID header, e.g. <abc@mail.gmail.com>)
// List drafts:   node gmail.js --list-drafts [--top=30]
// Draft a reply: node gmail.js --reply --message-id=<id> --body-file=reply.html [--attach=a.pdf,b.png]
//                (appends a DRAFT reply in the thread to [Gmail]/Drafts; never sends)
// Draft new:     node gmail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.html [--cc=c@z] [--attach=a.pdf,b.png]
//                (appends a fresh DRAFT to [Gmail]/Drafts; never sends)
//                (--attach takes one path or a comma-separated list; files ride along on the draft)
// Trash one:     node gmail.js --trash=<message-id>
//                (moves the message to [Gmail]/Trash — reversible, never a permanent purge)
// Auth glance:   node gmail.js --check
//                (connects and reports the inbox count; non-zero exit on auth failure)

const fs = require('fs');
const path = require('path');
const os = require('os');

// Resolve deps from a stable per-user location so this script works regardless of which plugin copy
// (cache vs marketplace clone) runs it. Seed it once with setup.js. Mirrors ms-graph's graph-client.js.
module.paths.push(path.join(os.homedir(), '.claude', 'gmail', 'node_modules'));

const { ImapFlow } = require('imapflow');
const { simpleParser } = require('mailparser');
const MailComposer = require('nodemailer/lib/mail-composer');

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);

const USER = process.env.GMAIL_ADDRESS;
const PASS = process.env.GMAIL_APP_PASSWORD;
const DRAFTS = '[Gmail]/Drafts';
const TRASH = '[Gmail]/Trash';

function client() {
  if (!USER || !PASS) {
    throw new Error('Not signed in: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment.');
  }
  return new ImapFlow({
    host: 'imap.gmail.com', port: 993, secure: true,
    auth: { user: USER, pass: PASS }, logger: false,
  });
}

const addr = (a) => a ? `${a.name || ''} <${a.address}>`.trim() : '?';
const fromList = (arr) => (arr || []).map(addr).join(', ');
const stripId = (id) => String(id || '').replace(/^<|>$/g, '');
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

async function findUid(c, messageId) {
  // Locate a message in the inbox by its Message-ID header; returns its UID or null.
  const ids = await c.search({ header: { 'message-id': stripId(messageId) } }, { uid: true });
  return ids && ids.length ? ids[ids.length - 1] : null;
}

async function listInbox(c) {
  const top = parseInt(args.top || '50', 10);
  const lock = await c.getMailboxLock('INBOX');
  try {
    const total = c.mailbox.exists;
    if (!total) { if (args.json) console.log('[]'); else console.log('No inbox messages.'); return; }
    const start = Math.max(1, total - top + 1);
    const out = [];
    for await (const m of c.fetch(`${start}:*`, { envelope: true, flags: true, internalDate: true })) {
      const e = m.envelope || {};
      out.push({
        id: e.messageId || `seq-${m.seq}`,
        uid: m.uid,
        subject: e.subject || '(no subject)',
        from: fromList(e.from),
        fromAddress: e.from && e.from[0] ? e.from[0].address : '',
        received: (e.date || m.internalDate || new Date()).toISOString
          ? (e.date || m.internalDate).toISOString() : String(e.date || m.internalDate),
        isRead: m.flags ? m.flags.has('\\Seen') : false,
        preview: '',
      });
    }
    out.reverse(); // newest-first
    if (args.json) { console.log(JSON.stringify(out, null, 2)); return; }
    console.log(`${out.length} inbox message(s) (newest first):`);
    for (const m of out) {
      console.log(`\n--- ${m.received.slice(0, 16)}  |  ${m.isRead ? 'read ' : 'UNREAD'} | ${m.subject}`);
      console.log(`    from: ${m.from}`);
      console.log(`    id:   ${m.id}`);
    }
  } finally { lock.release(); }
}

async function show(c) {
  const lock = await c.getMailboxLock('INBOX');
  try {
    const uid = await findUid(c, args.show);
    if (!uid) { console.log('Message not found in inbox.'); return; }
    const msg = await c.fetchOne(String(uid), { source: true }, { uid: true });
    const parsed = await simpleParser(msg.source);
    console.log(`Subject: ${parsed.subject || ''}`);
    console.log(`From: ${parsed.from ? parsed.from.text : ''}`);
    console.log(`To: ${parsed.to ? parsed.to.text : ''}`);
    if (parsed.cc) console.log(`Cc: ${parsed.cc.text}`);
    console.log(`Date: ${parsed.date ? parsed.date.toISOString() : ''}`);
    console.log('\n' + (parsed.text || clean(parsed.html) || '(no body)'));
  } finally { lock.release(); }
}

async function listDrafts(c) {
  const top = parseInt(args.top || '30', 10);
  const lock = await c.getMailboxLock(DRAFTS);
  try {
    const total = c.mailbox.exists;
    if (!total) { console.log('No drafts.'); return; }
    const start = Math.max(1, total - top + 1);
    const out = [];
    for await (const m of c.fetch(`${start}:*`, { envelope: true })) {
      const e = m.envelope || {};
      out.push({ subject: e.subject || '(no subject)', to: fromList(e.to), date: e.date });
    }
    out.reverse();
    console.log(`${out.length} draft(s):`);
    for (const m of out) console.log(`\n--- ${m.subject}\n    to: ${m.to}`);
  } finally { lock.release(); }
}

function attachments() {
  // --attach=<path> — one path or a comma-separated list. Object.fromEntries collapses a repeated
  // flag to its last value, so the comma-separated form is the way to attach several files.
  if (!args.attach) return undefined;
  const paths = String(args.attach).split(',').map(s => s.trim()).filter(Boolean);
  return paths.map(p => ({ filename: path.basename(p), path: p }));
}

async function buildMime({ to, cc, subject, html, inReplyTo, references }) {
  const mail = {
    from: USER, to, cc, subject,
    html,
    attachments: attachments(),
    inReplyTo: inReplyTo ? `<${stripId(inReplyTo)}>` : undefined,
    references: references,
  };
  const built = await new MailComposer(mail).compile().build();
  return built;
}

async function reply(c) {
  if (!args['message-id'] || !args['body-file']) {
    throw new Error('--reply requires --message-id and --body-file');
  }
  const html = fs.readFileSync(args['body-file'], 'utf8');
  const lock = await c.getMailboxLock('INBOX');
  let orig;
  try {
    const uid = await findUid(c, args['message-id']);
    if (!uid) throw new Error('Original message not found in inbox.');
    const msg = await c.fetchOne(String(uid), { source: true }, { uid: true });
    orig = await simpleParser(msg.source);
  } finally { lock.release(); }

  const when = orig.date ? orig.date.toUTCString() : '';
  const quoted = `<br><br>On ${when}, ${orig.from ? orig.from.text : ''} wrote:<br>` +
    `<blockquote style="margin:0 0 0 .8ex;border-left:1px solid #ccc;padding-left:1ex">` +
    `${orig.html || (orig.text || '').replace(/\n/g, '<br>')}</blockquote>`;
  const refs = [orig.references, orig.messageId].flat().filter(Boolean).join(' ');
  const subject = /^re:/i.test(orig.subject || '') ? orig.subject : `Re: ${orig.subject || ''}`;
  // Reply-all: To = original sender; CC = all original To+CC recipients except the sending address
  const allRecips = [
    ...(orig.to ? orig.to.value : []),
    ...(orig.cc ? orig.cc.value : []),
  ].map(a => a.address).filter(a => a && a.toLowerCase() !== USER.toLowerCase());
  const ccList = args.cc
    ? [...new Set([args.cc, ...allRecips])].join(', ')
    : allRecips.join(', ');
  const raw = await buildMime({
    to: orig.from ? orig.from.text : '', cc: ccList || undefined, subject, html: html + quoted,
    inReplyTo: orig.messageId, references: refs,
  });
  await c.append(DRAFTS, raw, ['\\Draft']);
  console.log(`Draft reply staged in [Gmail]/Drafts (re: "${clean(subject).slice(0, 60)}"). Review in Gmail; never sent.`);
}

async function draftNew(c) {
  if (!args.to || !args.subject || !args['body-file']) {
    throw new Error('--draft-new requires --to, --subject, and --body-file');
  }
  const html = fs.readFileSync(args['body-file'], 'utf8');
  const raw = await buildMime({ to: args.to, cc: args.cc || undefined, subject: args.subject, html });
  await c.append(DRAFTS, raw, ['\\Draft']);
  console.log(`Draft staged in [Gmail]/Drafts to ${args.to}. Review in Gmail; never sent.`);
}

async function trash(c) {
  const lock = await c.getMailboxLock('INBOX');
  try {
    const uid = await findUid(c, args.trash);
    if (!uid) { console.log('Message not found in inbox (already cleared?).'); return; }
    await c.messageMove(String(uid), TRASH, { uid: true });
    console.log(`Moved to [Gmail]/Trash (id ${stripId(args.trash).slice(0, 40)}...). Reversible from Trash.`);
  } finally { lock.release(); }
}

async function check(c) {
  const lock = await c.getMailboxLock('INBOX');
  try { console.log(`Signed in as ${USER}. Inbox has ${c.mailbox.exists} message(s).`); }
  finally { lock.release(); }
}

(async () => {
  const c = client();
  await c.connect();
  try {
    if (args['list-inbox']) return await listInbox(c);
    if (args['list-drafts']) return await listDrafts(c);
    if (args.show) return await show(c);
    if (args.reply) return await reply(c);
    if (args['draft-new']) return await draftNew(c);
    if (args.trash) return await trash(c);
    if (args.check) return await check(c);
    throw new Error('Specify --list-inbox, --list-drafts, --show, --reply, --draft-new, --trash, or --check');
  } finally { await c.logout(); }
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
