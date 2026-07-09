// Read / create personal Outlook contacts (People) via Microsoft Graph.
//
// List:    node contacts.js --list [--top=50]
//          (all contacts, alphabetical by display name)
// Search:  node contacts.js --search="Foster"
// Create:  node contacts.js --create --name="Stuart Foster" [--email=a@x] [--phone=555-1234] \
//            [--company=Acme] [--job-title=Director]
//          (creates a new personal contact; requires the Contacts.ReadWrite scope)

const { getGraphClient } = require('./graph-client');

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);

function printContact(c) {
  console.log(`\n--- ${c.displayName}`);
  if ((c.emailAddresses || []).length) console.log(`    email: ${c.emailAddresses.map(e => e.address).join(', ')}`);
  if ((c.mobilePhone || (c.businessPhones || []).length)) {
    const phones = [c.mobilePhone, ...(c.businessPhones || [])].filter(Boolean);
    console.log(`    phone: ${phones.join(', ')}`);
  }
  if (c.companyName) console.log(`    company: ${c.companyName}${c.jobTitle ? ` (${c.jobTitle})` : ''}`);
  console.log(`    id: ${c.id}`);
}

async function list(client) {
  const data = await client.api('/me/contacts')
    .orderby('displayName')
    .top(parseInt(args.top || '50', 10))
    .select('id,displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle')
    .get();
  const contacts = data.value || [];
  if (!contacts.length) { console.log('No contacts.'); return; }
  console.log(`${contacts.length} contact(s):`);
  contacts.forEach(printContact);
}

async function search(client) {
  const data = await client.api('/me/contacts')
    .filter(`startswith(displayName,'${String(args.search).replace(/'/g, "''")}')`)
    .select('id,displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle')
    .get();
  const contacts = data.value || [];
  if (!contacts.length) { console.log('No matching contacts.'); return; }
  contacts.forEach(printContact);
}

async function create(client) {
  if (!args.name) throw new Error('--create requires --name');
  const contact = { displayName: args.name };
  if (args.email) contact.emailAddresses = [{ address: args.email, name: args.name }];
  if (args.phone) contact.mobilePhone = args.phone;
  if (args.company) contact.companyName = args.company;
  if (args['job-title']) contact.jobTitle = args['job-title'];
  const created = await client.api('/me/contacts').post(contact);
  console.log(`Created contact "${created.displayName}" (id ${created.id}).`);
}

if (require.main === module) {
  (async () => {
    const client = await getGraphClient();
    if (args.list) return list(client);
    if (args.search) return search(client);
    if (args.create) return create(client);
    throw new Error('Specify --list, --search, or --create');
  })().catch(e => { console.error('Error:', e.message); process.exit(1); });
}
