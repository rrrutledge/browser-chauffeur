// Read / draft / clear personal Gmail (or Google Workspace) mail via IMAP with an app password.
//
// Auth: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment (a 16-char Google App
// Password — requires 2-Step Verification on the account, and IMAP enabled in Gmail settings).
// No OAuth app, no Cloud project, no browser.
//
// Signature: optionally set GMAIL_SIGNATURE_HTML in the environment (an HTML snippet, e.g.
// "Name<br>Title<br><a href=\"...\">...</a>"). IMAP has no API for the account's Gmail-configured
// signature (that's a webmail-only setting), so there's no way to read it automatically — this env
// var is a manually-set stand-in. When set, --draft-new and --reply append it to every staged draft
// (after a blank line; before the quoted original on replies) so it isn't retyped by hand each time.
//
// List inbox:    node gmail.js --list-inbox [--top=50] [--json]
//                (inbox, newest-first; --json emits a structured array for scripts)
// List sent:     node gmail.js --list-sent [--top=50] [--json]
//                (sent mail, newest-first; same output format as --list-inbox)
// Search:        node gmail.js --search=<query> [--folder=all|inbox|sent] [--top=50] [--json]
//                (search for messages matching query; --folder defaults to "all" ([Gmail]/All Mail);
//                 matches headers + body via IMAP TEXT search; newest-first)
// Show one:      node gmail.js --show=<message-id>
//                (<message-id> is the RFC822 Message-ID header, e.g. <abc@mail.gmail.com>; looked up
//                 in All Mail, so it shows regardless of whether the message is still in the inbox)
// List drafts:   node gmail.js --list-drafts [--top=30]
// Draft a reply: node gmail.js --reply --message-id=<id> --body-file=reply.md [--attach=a.pdf,b.png]
//                (appends a DRAFT reply in the thread to [Gmail]/Drafts; never sends; replaces any
//                 prior draft on the same thread; prints a draft-id for --send-draft. <id> is looked up
//                 in the inbox and All Mail — pass the most recent message in the thread, even one the
//                 user sent; a reply to the user's own message keeps its recipients instead of self.
//                 --body-file is Markdown — bold, links, lists all work; HTML tags pass through.
//                 Appends GMAIL_SIGNATURE_HTML, if set, after the body and before the quoted original.)
// Draft new:     node gmail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.md [--cc=c@z] [--attach=a.pdf,b.png]
//                (appends a fresh DRAFT to [Gmail]/Drafts; never sends; prints a draft-id.
//                 --body-file is Markdown — bold, links, lists all work; HTML tags pass through.
//                 Appends GMAIL_SIGNATURE_HTML, if set, after the body.)
//                (--attach takes one path or a comma-separated list; files ride along on the draft)
// Send a draft:  node gmail.js --send-draft --draft-id=<draft-message-id>
//                (promotes one already-staged draft: transmits its exact bytes via SMTP, then removes
//                 it from Drafts — Gmail files the sent copy in Sent. The <draft-message-id> is the
//                 Message-ID that --reply / --draft-new printed when it staged the draft. SENDS REAL MAIL —
//                 only invoke on Russ's explicit per-message say-so after he has reviewed that exact draft.)
// Delete a draft: node gmail.js --delete-draft=<draft-message-id>
//                (discards one staged draft that's no longer wanted — e.g. the outreach it belonged to
//                 was abandoned. Removes it from [Gmail]/Drafts entirely; drafts have no other home, so
//                 this isn't recoverable the way --archive is. The <draft-message-id> is the same id
//                 --reply / --draft-new printed when the draft was staged.)
// Archive one:   node gmail.js --archive=<message-id>
//                (removes the message from the inbox but keeps it in All Mail — the way mail is cleared)
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
const { marked } = require('marked');
const nodemailer = require('nodemailer');
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
const ALLMAIL = '[Gmail]/All Mail';

function client() {
  if (!USER || !PASS) {
    throw new Error('Not signed in: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment.');
  }
  return new ImapFlow({
    host: 'imap.gmail.com', port: 993, secure: true,
    auth: { user: USER, pass: PASS }, logger: false,
  });
}

function withSignature(html) {
  const sig = process.env.GMAIL_SIGNATURE_HTML;
  return sig ? `${html}<br><br>${sig}` : html;
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

async function listFolder(c, mailbox) {
  const top = parseInt(args.top || '50', 10);
  const lock = await c.getMailboxLock(mailbox);
  try {
    const total = c.mailbox.exists;
    if (!total) { if (args.json) console.log('[]'); else console.log(`No messages in ${mailbox}.`); return; }
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
      });
    }
    out.reverse();
    if (args.json) { console.log(JSON.stringify(out, null, 2)); return; }
    console.log(`${out.length} message(s) in ${mailbox} (newest first):`);
    for (const m of out) {
      console.log(`\n--- ${m.received.slice(0, 16)}  |  ${m.isRead ? 'read ' : 'UNREAD'} | ${m.subject}`);
      console.log(`    from: ${m.from}`);
      console.log(`    id:   ${m.id}`);
    }
  } finally { lock.release(); }
}

async function search(c) {
  const query = String(args.search);
  const top = parseInt(args.top || '50', 10);
  const folderArg = String(args.folder || 'all').toLowerCase();
  const mailbox = folderArg === 'inbox' ? 'INBOX'
    : folderArg === 'sent' ? '[Gmail]/Sent Mail'
    : '[Gmail]/All Mail';
  const lock = await c.getMailboxLock(mailbox);
  try {
    const uids = await c.search({ text: query }, { uid: true });
    if (!uids || !uids.length) {
      if (args.json) console.log('[]'); else console.log(`No messages found matching "${query}" in ${mailbox}.`);
      return;
    }
    const take = uids.slice(-top);
    const out = [];
    for await (const m of c.fetch(take, { envelope: true, flags: true, internalDate: true }, { uid: true })) {
      const e = m.envelope || {};
      out.push({
        id: e.messageId || `uid-${m.uid}`,
        uid: m.uid,
        subject: e.subject || '(no subject)',
        from: fromList(e.from),
        fromAddress: e.from && e.from[0] ? e.from[0].address : '',
        received: (e.date || m.internalDate || new Date()).toISOString
          ? (e.date || m.internalDate).toISOString() : String(e.date || m.internalDate),
        isRead: m.flags ? m.flags.has('\\Seen') : false,
      });
    }
    out.sort((a, b) => (a.received < b.received ? 1 : -1));
    if (args.json) { console.log(JSON.stringify(out, null, 2)); return; }
    console.log(`${out.length} message(s) matching "${query}" in ${mailbox} (newest first):`);
    for (const m of out) {
      console.log(`\n--- ${m.received.slice(0, 16)}  |  ${m.isRead ? 'read ' : 'UNREAD'} | ${m.subject}`);
      console.log(`    from: ${m.from}`);
      console.log(`    id:   ${m.id}`);
    }
  } finally { lock.release(); }
}

async function show(c) {
  // All Mail is a superset of INBOX (everything except Trash/Spam/Drafts), so one lookup there finds
  // a message whether it's still in the inbox or was already archived.
  const lock = await c.getMailboxLock(ALLMAIL);
  let msg;
  try {
    const uid = await findUid(c, args.show);
    if (uid) msg = await c.fetchOne(String(uid), { source: true }, { uid: true });
  } finally { lock.release(); }
  if (!msg) { console.log('Message not found.'); return; }
  const parsed = await simpleParser(msg.source);
  console.log(`Subject: ${parsed.subject || ''}`);
  console.log(`From: ${parsed.from ? parsed.from.text : ''}`);
  console.log(`To: ${parsed.to ? parsed.to.text : ''}`);
  if (parsed.cc) console.log(`Cc: ${parsed.cc.text}`);
  console.log(`Date: ${parsed.date ? parsed.date.toISOString() : ''}`);
  console.log('\n' + (parsed.text || clean(parsed.html) || '(no body)'));
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
  const m = built.toString('utf8', 0, 4096).match(/^Message-ID:\s*(<[^>]+>)/mi);
  return { raw: built, messageId: m ? m[1] : null };
}

async function dropDraftsInThread(c, threadIds) {
  // Before staging a fresh reply, remove any prior \Draft on the same thread so only one draft per
  // thread ever exists — kills the "opened the wrong (stale) draft" hazard. A reply draft's In-Reply-To
  // is the message it answers, so match against EVERY message-id in the thread (the full references
  // chain) — that way switching which message we reply to still clears an earlier draft on the thread.
  const ids = (Array.isArray(threadIds) ? threadIds : [threadIds]).map(stripId).filter(Boolean);
  const lock = await c.getMailboxLock(DRAFTS);
  try {
    const found = new Set();
    for (const id of ids) {
      const uids = await c.search({ header: { 'in-reply-to': id } }, { uid: true });
      (uids || []).forEach(u => found.add(u));
    }
    if (found.size) {
      const arr = [...found];
      await c.messageDelete(arr, { uid: true });
      return arr.length;
    }
    return 0;
  } finally { lock.release(); }
}

async function reply(c) {
  if (!args['message-id'] || !args['body-file']) {
    throw new Error('--reply requires --message-id and --body-file');
  }
  const html = marked.parse(fs.readFileSync(args['body-file'], 'utf8'));
  let orig;
  for (const mailbox of ['INBOX', ALLMAIL]) {
    const lock = await c.getMailboxLock(mailbox);
    try {
      const uid = await findUid(c, args['message-id']);
      if (!uid) continue;
      const msg = await c.fetchOne(String(uid), { source: true }, { uid: true });
      orig = await simpleParser(msg.source);
      break;
    } finally { lock.release(); }
  }
  if (!orig) throw new Error('Original message not found in inbox or All Mail.');

  const when = orig.date ? orig.date.toUTCString() : '';
  const quoted = `<br><br>On ${when}, ${orig.from ? orig.from.text : ''} wrote:<br>` +
    `<blockquote style="margin:0 0 0 .8ex;border-left:1px solid #ccc;padding-left:1ex">` +
    `${orig.html || (orig.text || '').replace(/\n/g, '<br>')}</blockquote>`;
  const refs = [orig.references, orig.messageId].flat().filter(Boolean).join(' ');
  const subject = /^re:/i.test(orig.subject || '') ? orig.subject : `Re: ${orig.subject || ''}`;
  const dropped = await dropDraftsInThread(c, refs.split(/\s+/));
  // Pick recipients by who wrote the message we're answering:
  // - normal reply (someone else's message): To = its sender; CC = its other To+CC recipients.
  // - follow-up to our OWN sent message (the most-recent message is ours): keep its recipients, so the
  //   nudge goes to the people we wrote to (To/CC) rather than back to ourselves.
  const fromSelf = orig.from && orig.from.value.some(
    a => a.address && a.address.toLowerCase() === USER.toLowerCase());
  const to = fromSelf
    ? (orig.to ? fromList(orig.to.value) : '')
    : (orig.from ? orig.from.text : '');
  const ccSource = fromSelf
    ? (orig.cc ? orig.cc.value : [])
    : [...(orig.to ? orig.to.value : []), ...(orig.cc ? orig.cc.value : [])];
  const allRecips = ccSource
    .map(a => a.address).filter(a => a && a.toLowerCase() !== USER.toLowerCase());
  const ccList = args.cc
    ? [...new Set([args.cc, ...allRecips])].join(', ')
    : allRecips.join(', ');
  const { raw, messageId } = await buildMime({
    to, cc: ccList || undefined, subject, html: withSignature(html) + quoted,
    inReplyTo: orig.messageId, references: refs,
  });
  await c.append(DRAFTS, raw, ['\\Draft']);
  const note = dropped ? ` (replaced ${dropped} prior draft on this thread)` : '';
  console.log(`Draft reply staged in [Gmail]/Drafts (re: "${clean(subject).slice(0, 60)}")${note}. Review in Gmail; never sent.`);
  if (messageId) console.log(`draft-id: ${messageId}`);
}

async function draftNew(c) {
  if (!args.to || !args.subject || !args['body-file']) {
    throw new Error('--draft-new requires --to, --subject, and --body-file');
  }
  const html = marked.parse(fs.readFileSync(args['body-file'], 'utf8'));
  const { raw, messageId } = await buildMime({ to: args.to, cc: args.cc || undefined, subject: args.subject, html: withSignature(html) });
  await c.append(DRAFTS, raw, ['\\Draft']);
  console.log(`Draft staged in [Gmail]/Drafts to ${args.to}. Review in Gmail; never sent.`);
  if (messageId) console.log(`draft-id: ${messageId}`);
}

async function sendDraft(c) {
  // Promote ONE staged draft to a real send. Transmits the draft's exact bytes via Gmail SMTP, then
  // removes it from Drafts (Gmail auto-files the sent copy in Sent). This is the only path that emits
  // real mail — gated upstream on Russ's explicit per-message instruction after he reviewed this draft.
  if (!args['draft-id']) throw new Error('--send-draft requires --draft-id (the Message-ID printed when the draft was staged)');
  const id = stripId(args['draft-id']);
  const lock = await c.getMailboxLock(DRAFTS);
  let source, uid, parsed;
  try {
    const uids = await c.search({ header: { 'message-id': id } }, { uid: true });
    if (!uids || !uids.length) throw new Error(`No draft with Message-ID <${id}> in [Gmail]/Drafts. Re-stage the draft and use the draft-id it prints.`);
    uid = uids[uids.length - 1];
    const msg = await c.fetchOne(String(uid), { source: true }, { uid: true });
    source = msg.source;
    parsed = await simpleParser(source);
  } finally { lock.release(); }

  const rcpt = [...(parsed.to ? parsed.to.value : []), ...(parsed.cc ? parsed.cc.value : [])]
    .map(a => a.address).filter(Boolean);
  if (!rcpt.length) throw new Error('Draft has no recipients; refusing to send.');

  const transport = nodemailer.createTransport({
    host: 'smtp.gmail.com', port: 587, secure: false,
    auth: { user: USER, pass: PASS },
  });
  await transport.sendMail({ envelope: { from: USER, to: rcpt }, raw: source });

  const dlock = await c.getMailboxLock(DRAFTS);
  try { await c.messageDelete([uid], { uid: true }); } finally { dlock.release(); }
  console.log(`Sent to ${rcpt.join(', ')} (subject: "${clean(parsed.subject || '').slice(0, 60)}"). Draft removed; copy is in [Gmail]/Sent.`);
}

async function deleteDraft(c) {
  const id = stripId(args['delete-draft']);
  const lock = await c.getMailboxLock(DRAFTS);
  try {
    const uids = await c.search({ header: { 'message-id': id } }, { uid: true });
    if (!uids || !uids.length) { console.log(`No draft with Message-ID <${id}> in [Gmail]/Drafts (already deleted?).`); return; }
    await c.messageDelete(uids, { uid: true });
    console.log(`Deleted draft <${id}> from [Gmail]/Drafts.`);
  } finally { lock.release(); }
}

async function archive(c) {
  const lock = await c.getMailboxLock('INBOX');
  try {
    const uid = await findUid(c, args.archive);
    if (!uid) { console.log('Message not found in inbox (already cleared?).'); return; }
    // Moving to All Mail drops the INBOX label while keeping the message — Gmail's archive. Unlike
    // Trash there's no 30-day purge timer; the message just leaves the inbox.
    await c.messageMove(String(uid), ALLMAIL, { uid: true });
    console.log(`Archived (left the inbox, kept in All Mail) id ${stripId(args.archive).slice(0, 40)}.... Find it in All Mail or search.`);
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
    if (args['list-inbox']) return await listFolder(c, 'INBOX');
    if (args['list-drafts']) return await listDrafts(c);
    if (args.show) return await show(c);
    if (args.reply) return await reply(c);
    if (args['draft-new']) return await draftNew(c);
    if (args['send-draft']) return await sendDraft(c);
    if (args['delete-draft']) return await deleteDraft(c);
    if (args.archive) return await archive(c);
    if (args['list-sent']) return await listFolder(c, '[Gmail]/Sent Mail');
    if (args.search) return await search(c);
    if (args.check) return await check(c);
    throw new Error('Specify --list-inbox, --list-sent, --search, --list-drafts, --show, --reply, --draft-new, --send-draft, --delete-draft, --archive, or --check');
  } finally { await c.logout(); }
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
