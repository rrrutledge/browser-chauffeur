// List / create / update events on a personal Outlook calendar via Microsoft Graph.
//
// List upcoming:   node calendar.js --days=14
// List calendars:  node calendar.js --list-calendars            (prints "name<TAB>id")
// List a range:    node calendar.js --list --calendar="InnerSource Commons" \
//                    --start=2026-05-01 --end=2026-05-31 [--tz=America/Chicago] [--json]
//                    (a NAMED calendar over an explicit date range; calendarView expands
//                     recurrences and paginates; --json emits a structured array for scripts)
// Create event:    node calendar.js --create --subject="Dentist" \
//                    --start="2026-06-20T15:00:00" --end="2026-06-20T16:00:00" \
//                    [--location="..."] [--body="..."] [--attendees=a@x,b@y] [--reminder=N]
// Update reminder: node calendar.js --update --subject="Dentist" --reminder=off
// Delete event:    node calendar.js --delete --subject="Dentist" [--all]
//                    (deletes the matching upcoming event; --all deletes every subject match)
//
// Times are interpreted in --tz (default America/Chicago). Events have NO reminder by
// default; --reminder=N turns on a pop-up N minutes before start (0 = at start), --reminder=off
// turns it back off.
//
// Reusable from other scripts (require.main-guarded, so requiring this file does not run the CLI):
//   const { getEvents, getCalendars } = require('<ms-graph>/scripts/calendar.js');
//   const events = await getEvents({ calendar: 'InnerSource Commons', start: '2026-05-01', end: '2026-05-31' });

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

async function deleteEvent(client) {
  if (!args.subject) throw new Error('--delete requires --subject');
  const now = new Date();
  const end = new Date(now.getTime() + 365 * 86400000);
  const data = await client.api('/me/calendarView')
    .query({ startDateTime: now.toISOString(), endDateTime: end.toISOString() })
    .top(100).orderby('start/dateTime').select('subject,id,start').get();
  const matches = (data.value || []).filter(e => e.subject === args.subject);
  if (!matches.length) throw new Error(`No upcoming event with subject "${args.subject}"`);
  if (matches.length > 1 && !args.all) {
    throw new Error(`${matches.length} upcoming events match "${args.subject}"; add --all to delete every match, or narrow the subject.`);
  }
  for (const m of matches) {
    await client.api(`/me/events/${m.id}`).delete();
    console.log(`Deleted: "${m.subject}" (${(m.start && m.start.dateTime) || ''})`);
  }
}

// --- Reusable library functions (param-driven; each builds its own client) ---

// All calendars on the account, as [{ id, name }].
async function getCalendars(client) {
  client = client || await getGraphClient();
  const data = await client.api('/me/calendars').select('id,name').top(100).get();
  return (data.value || []).map(c => ({ id: c.id, name: c.name }));
}

// Resolve a calendar name (case-insensitive) or id to its id.
async function resolveCalendarId(client, nameOrId) {
  const cals = await getCalendars(client);
  const byName = cals.find(c => c.name.toLowerCase() === String(nameOrId).toLowerCase());
  if (byName) return byName.id;
  if (cals.find(c => c.id === nameOrId)) return nameOrId;
  throw new Error(`Calendar not found: "${nameOrId}". Available: ${cals.map(c => c.name).join(', ')}`);
}

// Events on a NAMED calendar over an explicit date range, as
// [{ date, subject, minutes, start, end, allDay }]. calendarView expands recurrences;
// --end is inclusive of the whole day. Paginates through @odata.nextLink.
async function getEvents({ calendar, start, end, tz = 'America/Chicago', client } = {}) {
  if (!calendar || !start || !end) throw new Error('getEvents requires { calendar, start, end }');
  client = client || await getGraphClient();
  const calId = await resolveCalendarId(client, calendar);
  const startISO = new Date(`${start}T00:00:00`).toISOString();
  const endISO = new Date(`${end}T23:59:59`).toISOString();
  const out = [];
  let page = await client.api(`/me/calendars/${calId}/calendarView`)
    .query({ startDateTime: startISO, endDateTime: endISO })
    .header('Prefer', `outlook.timezone="${tz}"`)
    .top(200).orderby('start/dateTime')
    .select('subject,start,end,isAllDay')
    .get();
  while (page) {
    for (const e of page.value || []) {
      const minutes = Math.round((new Date(e.end.dateTime) - new Date(e.start.dateTime)) / 60000);
      out.push({
        date: (e.start.dateTime || '').slice(0, 10),
        subject: e.subject || '(no title)',
        minutes: e.isAllDay ? 0 : minutes,
        start: e.start.dateTime,
        end: e.end.dateTime,
        allDay: !!e.isAllDay,
      });
    }
    const next = page['@odata.nextLink'];
    page = next ? await client.api(next).get() : null;
  }
  return out;
}

module.exports = { getCalendars, resolveCalendarId, getEvents };

// --- CLI (only when run directly, so `require` of this file is side-effect-free) ---
if (require.main === module) {
  (async () => {
    if (args['list-calendars']) {
      for (const c of await getCalendars()) console.log(`${c.name}\t${c.id}`);
      return;
    }
    if (args.list) {
      const events = await getEvents({ calendar: args.calendar, start: args.start, end: args.end, tz: TZ });
      if (args.json) { console.log(JSON.stringify(events, null, 2)); return; }
      console.log(`${events.length} event(s) on "${args.calendar}" ${args.start}..${args.end}:`);
      for (const e of events) console.log(`  ${e.date}  ${String(e.minutes).padStart(4)}m  ${e.subject}`);
      return;
    }
    const client = await getGraphClient();
    if (args.create) return createEvent(client);
    if (args.update) return updateReminder(client);
    if (args.delete) return deleteEvent(client);
    return listUpcoming(client);
  })().catch(e => { console.error('Error:', e.message); process.exit(1); });
}
