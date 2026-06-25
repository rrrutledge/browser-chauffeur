// Read / draft / send personal Outlook mail via Microsoft Graph.
//
// List unread:   node mail.js --list-unread [--top=30]
//                (inbox unread, newest-first; one block per message with id + webLink)
// List inbox:    node mail.js --list-inbox [--top=50] [--json]
//                (inbox read+unread, newest-first; count-capped by --top; --json emits a
//                 structured array for scripts)
// List drafts:   node mail.js --list-drafts [--top=30]
//                (drafts folder, most-recently-edited first; same block format with id)
// Search:        node mail.js --search="Griffiths" [--top=10]
// Show one:      node mail.js --show=<messageId>
// Draft a reply: node mail.js --reply --message-id=<id> --body-file=reply.html
//                (creates a DRAFT reply-all in the thread; never sends)
// Draft new:     node mail.js --draft-new --to="a@x,b@y" --subject="..." --body-file=msg.html \
//                  [--cc=c@z] [--attach=file1.pdf,file2.png] [--replace] [--text]
//                (creates a fresh DRAFT to specific recipients; never sends. --attach adds file
//                 attachments; --replace first deletes any existing drafts with the same subject
//                 so re-runs don't pile up duplicates; --text treats the body-file as plain text
//                 instead of HTML.)
// Send to self:  node mail.js --send-self --subject="..." --body-file=note.txt
//                (sends a plain-text mail to your own inbox; handy for phone copy-paste)
// Delete one:    node mail.js --delete=<messageId>
//                (moves the message to Deleted Items — reversible, never a permanent purge)

const fs = require('fs');
const path = require('path');
const { getGraphClient } = require('./graph-client');

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);

const addr = (r) => r?.emailAddress ? `${r.emailAddress.name || ''} <${r.emailAddress.address}>` : '?';
const strip = (html) => (html || '')
  .replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();

async function listUnread(client) {
  const data = await client.api('/me/mailFolders/inbox/messages')
    .filter('isRead eq false')
    .orderby('receivedDateTime desc')
    .top(parseInt(args.top || '30', 10))
    .select('id,conversationId,subject,from,toRecipients,receivedDateTime,bodyPreview,webLink')
    .get();
  const msgs = data.value || [];
  if (!msgs.length) { console.log('No unread messages.'); return; }
  console.log(`${msgs.length} unread message(s), newest first:`);
  for (const m of msgs) {
    console.log(`\n--- ${m.receivedDateTime?.slice(0, 16)}  |  ${m.subject}`);
    console.log(`    from: ${addr(m.from)}`);
    console.log(`    id:   ${m.id}`);
    console.log(`    link: ${m.webLink}`);
    console.log(`    > ${(m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 200)}`);
  }
}

async function listInbox(client) {
  // Count-capped by --top (default 50); newest-first, no time window — the keeper drains the
  // whole inbox a batch at a time across cycles.
  const data = await client.api('/me/mailFolders/inbox/messages')
    .orderby('receivedDateTime desc')
    .top(parseInt(args.top || '50', 10))
    .select('id,conversationId,subject,from,toRecipients,receivedDateTime,bodyPreview,webLink,isRead')
    .get();
  const msgs = data.value || [];
  if (args.json) {
    console.log(JSON.stringify(msgs.map(m => ({
      id: m.id, conversationId: m.conversationId, subject: m.subject,
      from: addr(m.from), fromAddress: m.from?.emailAddress?.address || '',
      received: m.receivedDateTime, isRead: m.isRead, webLink: m.webLink,
      preview: (m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 300),
    })), null, 2));
    return;
  }
  if (!msgs.length) { console.log('No inbox messages.'); return; }
  console.log(`${msgs.length} inbox message(s) (newest first):`);
  for (const m of msgs) {
    console.log(`\n--- ${m.receivedDateTime?.slice(0, 16)}  |  ${m.isRead ? 'read ' : 'UNREAD'} | ${m.subject}`);
    console.log(`    from: ${addr(m.from)}`);
    console.log(`    id:   ${m.id}`);
    console.log(`    link: ${m.webLink}`);
    console.log(`    > ${(m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 200)}`);
  }
}

async function del(client) {
  await client.api(`/me/messages/${args.delete}/move`).post({ destinationId: 'deleteditems' });
  console.log(`Moved to Deleted Items (id ${String(args.delete).slice(0, 20)}...). Reversible from the Deleted Items folder.`);
}

async function search(client) {
  const data = await client.api('/me/messages')
    .search(`"${args.search}"`)
    .top(parseInt(args.top || '10', 10))
    .select('id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview')
    .get();
  const msgs = data.value || [];
  if (!msgs.length) { console.log('No messages found.'); return; }
  for (const m of msgs) {
    console.log(`\n--- ${m.receivedDateTime?.slice(0, 16)}  |  ${m.subject}`);
    console.log(`    from: ${addr(m.from)}`);
    console.log(`    to:   ${(m.toRecipients || []).map(addr).join(', ')}`);
    if ((m.ccRecipients || []).length) console.log(`    cc:   ${m.ccRecipients.map(addr).join(', ')}`);
    console.log(`    id:   ${m.id}`);
    console.log(`    > ${(m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 200)}`);
  }
}

async function show(client) {
  const m = await client.api(`/me/messages/${args.show}`)
    .select('subject,from,toRecipients,ccRecipients,receivedDateTime,body').get();
  console.log(`Subject: ${m.subject}`);
  console.log(`From: ${addr(m.from)}`);
  console.log(`To: ${(m.toRecipients || []).map(addr).join(', ')}`);
  if ((m.ccRecipients || []).length) console.log(`Cc: ${m.ccRecipients.map(addr).join(', ')}`);
  console.log('\n' + strip(m.body?.content));
}

async function listDrafts(client) {
  const data = await client.api('/me/mailFolders/drafts/messages')
    .orderby('lastModifiedDateTime desc')
    .top(parseInt(args.top || '30', 10))
    .select('id,subject,toRecipients,lastModifiedDateTime,bodyPreview')
    .get();
  const msgs = data.value || [];
  if (!msgs.length) { console.log('No drafts.'); return; }
  console.log(`${msgs.length} draft(s), most-recently-edited first:`);
  for (const m of msgs) {
    console.log(`\n--- ${m.lastModifiedDateTime?.slice(0, 16)}  |  ${m.subject}`);
    console.log(`    to: ${(m.toRecipients || []).map(addr).join(', ')}`);
    console.log(`    id: ${m.id}`);
    console.log(`    > ${(m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 200)}`);
  }
}

async function reply(client) {
  if (!args['message-id'] || !args['body-file']) {
    throw new Error('--reply requires --message-id and --body-file');
  }
  const html = fs.readFileSync(args['body-file'], 'utf8');
  const draft = await client.api(`/me/messages/${args['message-id']}/createReplyAll`).post({});
  const quoted = draft.body?.content || '';
  await client.api(`/me/messages/${draft.id}`).patch({ body: { contentType: 'html', content: html + quoted } });
  console.log(`Draft reply created in thread (id ${draft.id.slice(0, 20)}...). Review in Outlook Drafts.`);
}

// Reusable: create a draft message (never sends). Returns the created draft.
//   createDraft(client, { to, subject, body, cc, attach, replace, contentType })
//   - attach: a path or comma-separated string or array of paths -> file attachments
//   - replace: delete any existing drafts with the same subject first (avoids duplicates)
async function createDraft(client, { to, subject, body = '', cc, attach, replace = false, contentType = 'html' } = {}) {
  if (!to || !subject) throw new Error('createDraft requires { to, subject }');
  client = client || await getGraphClient();
  if (replace) {
    const existing = await client.api('/me/mailFolders/drafts/messages')
      .filter(`subject eq '${String(subject).replace(/'/g, "''")}'`)
      .select('id,subject').top(20).get();
    for (const m of existing.value || []) await client.api(`/me/messages/${m.id}`).delete();
  }
  const recip = (s) => String(s).split(',').map(a => ({ emailAddress: { address: a.trim() } }));
  const message = { subject, body: { contentType, content: body }, toRecipients: recip(to) };
  if (cc) message.ccRecipients = recip(cc);
  const attachPaths = Array.isArray(attach)
    ? attach
    : (attach ? String(attach).split(',').map(s => s.trim()).filter(Boolean) : []);
  if (attachPaths.length) {
    message.attachments = attachPaths.map(p => ({
      '@odata.type': '#microsoft.graph.fileAttachment',
      name: path.basename(p),
      contentBytes: fs.readFileSync(p).toString('base64'),
    }));
  }
  return client.api('/me/messages').post(message);
}

async function draftNew(client) {
  if (!args.to || !args.subject || !args['body-file']) {
    throw new Error('--draft-new requires --to, --subject, and --body-file');
  }
  const body = fs.readFileSync(args['body-file'], 'utf8');
  const draft = await createDraft(client, {
    to: args.to, subject: args.subject, body, cc: args.cc,
    attach: args.attach, replace: !!args.replace, contentType: args.text ? 'text' : 'html',
  });
  const extra = args.attach ? ' with attachment' : '';
  console.log(`Draft created to ${args.to} (id ${draft.id.slice(0, 20)}...)${extra}. Review in Outlook Drafts; never sent.`);
}

async function sendSelf(client) {
  if (!args.subject || !args['body-file']) {
    throw new Error('--send-self requires --subject and --body-file');
  }
  const me = await client.api('/me').select('mail,userPrincipalName').get();
  const me_addr = me.mail || me.userPrincipalName;
  const content = fs.readFileSync(args['body-file'], 'utf8');
  await client.api('/me/sendMail').post({
    message: {
      subject: args.subject,
      body: { contentType: 'text', content },
      toRecipients: [{ emailAddress: { address: me_addr } }],
    },
    saveToSentItems: true,
  });
  console.log(`Sent to self (${me_addr}): "${args.subject}"`);
}

module.exports = { createDraft };

// --- CLI (only when run directly, so `require` of this file is side-effect-free) ---
if (require.main === module) {
  (async () => {
    const client = await getGraphClient();
    if (args['list-unread']) return listUnread(client);
    if (args['list-inbox']) return listInbox(client);
    if (args['list-drafts']) return listDrafts(client);
    if (args.search) return search(client);
    if (args.show) return show(client);
    if (args.reply) return reply(client);
    if (args['draft-new']) return draftNew(client);
    if (args['send-self']) return sendSelf(client);
    if (args.delete) return del(client);
    throw new Error('Specify --list-unread, --list-inbox, --list-drafts, --search, --show, --reply, --draft-new, --send-self, or --delete');
  })().catch(e => { console.error('Error:', e.message); process.exit(1); });
}
