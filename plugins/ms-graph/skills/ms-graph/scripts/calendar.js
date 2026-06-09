// List / create / update events on a personal Outlook calendar via Microsoft Graph.
//
// List upcoming:   node calendar.js --days=14
// Create event:    node calendar.js --create --subject="Dentist" \
//                    --start="2026-06-20T15:00:00" --end="2026-06-20T16:00:00" \
//                    [--location="..."] [--body="..."] [--attendees=a@x,b@y] [--reminder=N]
// Update reminder: node calendar.js --update --subject="Dentist" --reminder=off
//
// Times are interpreted in --tz (default America/Chicago). Events have NO reminder by
// default; --reminder=N turns on a pop-up N minutes before start (0 = at start), --reminder=off
// turns it back off.

const { getGraphClient } = require('./graph-client');

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const m = a.match(/^--([^=]+)(?:=(.*))?$/);
    return m ? [m[1], m[2] ?? true] : [a, true];
  })
);
const TZ = args.tz || 'America/Chicago';

async function listUpcoming(client) {
  const days = parseInt(args.days || '14', 10);
  const now = new Date();
  const end = new Date(now.getTime() + days * 86400000);
  const data = await client.api('/me/calendarView')
    .query({ startDateTime: now.toISOString(), endDateTime: end.toISOString() })
    .header('Prefer', `outlook.timezone="${TZ}"`)
    .top(100).orderby('start/dateTime')
    .select('subject,start,end,location,isReminderOn,reminderMinutesBeforeStart')
    .get();
  const events = data.value || [];
  if (!events.length) { console.log(`No events in the next ${days} days.`); return; }
  console.log(`${events.length} event(s) in the next ${days} days:\n`);
  for (const e of events) {
    const start = (e.start?.dateTime || '?').replace('T', ' ').slice(0, 16);
    const loc = e.location?.displayName ? ` @ ${e.location.displayName}` : '';
    const rem = e.isReminderOn ? `  🔔${e.reminderMinutesBeforeStart}m` : '';
    console.log(`  ${start}  ${e.subject}${loc}${rem}`);
  }
}

async function createEvent(client) {
  if (!args.subject || !args.start || !args.end) {
    throw new Error('--create requires --subject, --start, --end (ISO local, e.g. 2026-06-20T15:00:00)');
  }
  const event = {
    subject: args.subject,
    start: { dateTime: args.start, timeZone: TZ },
    end: { dateTime: args.end, timeZone: TZ },
    isReminderOn: false,
  };
  if (args.location) event.location = { displayName: args.location };
  if (args.body) event.body = { contentType: 'text', content: args.body };
  if (args.attendees) {
    event.attendees = String(args.attendees).split(',').map(a => ({
      emailAddress: { address: a.trim() }, type: 'required',
    }));
  }
  if (args.reminder !== undefined && args.reminder !== 'off') {
    event.isReminderOn = true;
    event.reminderMinutesBeforeStart = parseInt(args.reminder, 10) || 0;
  }
  const created = await client.api('/me/events').post(event);
  console.log(`Created: "${created.subject}" on ${created.start.dateTime} (${created.id.slice(0, 16)}...)`);
}

async function updateReminder(client) {
  if (!args.subject || args.reminder === undefined) {
    throw new Error('--update requires --subject and --reminder=N|off');
  }
  const now = new Date();
  const end = new Date(now.getTime() + 365 * 86400000);
  const data = await client.api('/me/calendarView')
    .query({ startDateTime: now.toISOString(), endDateTime: end.toISOString() })
    .top(100).orderby('start/dateTime').select('subject,id,start').get();
  const match = (data.value || []).find(e => e.subject === args.subject);
  if (!match) throw new Error(`No upcoming event with subject "${args.subject}"`);
  const patch = args.reminder === 'off'
    ? { isReminderOn: false }
    : { isReminderOn: true, reminderMinutesBeforeStart: parseInt(args.reminder, 10) || 0 };
  await client.api(`/me/events/${match.id}`).patch(patch);
  console.log(`Updated reminder on "${match.subject}" -> ${args.reminder}`);
}

(async () => {
  const client = await getGraphClient();
  if (args.create) return createEvent(client);
  if (args.update) return updateReminder(client);
  return listUpcoming(client);
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
