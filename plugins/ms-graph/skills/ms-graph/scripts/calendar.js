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
// Create recurring: node calendar.js --create-recurring --subject="Drop off Ryan" \
//                    --start=06:35 --end=06:55 --days=MO,TU,TH \
//                    --range-start=2026-08-31 --range-end=2026-10-31 \
//                    [--location="..."] [--reminder=N]
//                    (weekly recurrence; --days from MO,TU,WE,TH,FR,SA,SU; --range-end is inclusive)
// Delete one occurrence of a recurring series:
//                   node calendar.js --delete-occurrence --subject="Drop off Ryan" --date=2026-09-14
// Reschedule one occurrence of a recurring series (same day, different time):
//                   node calendar.js --reschedule-occurrence --subject="Drive Ryan" \
//                     --date=2026-08-31 --start=06:35 --end=06:55
// Update one occurrence's subject/body (recurring series, same day and time):
//                   node calendar.js --update-occurrence --subject="Youth Activities" \
//                     --date=2026-09-09 --new-subject="Youth Activities - Fun & Fitness: Line Dancing" \
//                     [--body="..."] [--calendar="Family Commitments"]
// --delete-occurrence / --reschedule-occurrence / --update-occurrence all take an optional
// --calendar=<name> to scope the series lookup to a secondary calendar (default: primary
// "Calendar") - needed when the recurring series lives somewhere other than the default calendar.
// Delete a plain (non-recurring) event by subject + date:
//                   node calendar.js --delete-event --subject="Dentist" --date=2026-06-20
// Update reminder: node calendar.js --update --subject="Dentist" --reminder=off
//                    [--date=YYYY-MM-DD]  (narrows to one day when the subject isn't unique)
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

const WEEKDAY_CODES = { MO: 'monday', TU: 'tuesday', WE: 'wednesday', TH: 'thursday', FR: 'friday', SA: 'saturday', SU: 'sunday' };

async function createRecurringEvent(client) {
  if (!args.subject || !args.start || !args.end || !args.days || !args['range-start'] || !args['range-end']) {
    throw new Error('--create-recurring requires --subject, --start=HH:MM, --end=HH:MM, --days=MO,TU,..., --range-start=YYYY-MM-DD, --range-end=YYYY-MM-DD');
  }
  const daysOfWeek = String(args.days).split(',').map(d => WEEKDAY_CODES[d.trim().toUpperCase()]);
  if (daysOfWeek.some(d => !d)) {
    throw new Error(`--days must be a comma list from ${Object.keys(WEEKDAY_CODES).join(',')}`);
  }
  const rangeStart = args['range-start'];
  const event = {
    subject: args.subject,
    start: { dateTime: `${rangeStart}T${args.start}:00`, timeZone: TZ },
    end: { dateTime: `${rangeStart}T${args.end}:00`, timeZone: TZ },
    isReminderOn: false,
    recurrence: {
      pattern: { type: 'weekly', interval: 1, daysOfWeek, firstDayOfWeek: 'sunday' },
      range: { type: 'endDate', startDate: rangeStart, endDate: args['range-end'], recurrenceTimeZone: TZ },
    },
  };
  if (args.location) event.location = { displayName: args.location };
  if (args.reminder !== undefined && args.reminder !== 'off') {
    event.isReminderOn = true;
    event.reminderMinutesBeforeStart = parseInt(args.reminder, 10) || 0;
  }
  const created = await client.api('/me/events').post(event);
  console.log(`Created recurring: "${created.subject}" ${args.days} ${args.start}-${args.end} ${rangeStart}..${args['range-end']} (${created.id.slice(0, 16)}...)`);
}

// Resolves which series (of possibly several sharing a subject - an old expired series left in
// place, a duplicate created by mistake) actually has an occurrence on `date`. Checking every
// candidate's /instances rather than taking the first match is what makes --delete-occurrence and
// --reschedule-occurrence safe to point at a subject without knowing in advance which series (if
// any) is the live one.
async function resolveOccurrenceForDate(client, subject, date, calendarId) {
  const escaped = String(subject).replace(/'/g, "''");
  const base = calendarId ? `/me/calendars/${calendarId}/events` : '/me/events';
  const found = await client.api(base)
    .filter(`subject eq '${escaped}' and type eq 'seriesMaster'`)
    .select('id,subject').top(10).get();
  const candidates = found.value || [];
  for (const master of candidates) {
    const instances = await client.api(`/me/events/${master.id}/instances`)
      .query({ startDateTime: `${date}T00:00:00`, endDateTime: `${date}T23:59:59` })
      .header('Prefer', `outlook.timezone="${TZ}"`)
      .select('id,subject,start,end')
      .get();
    const occurrences = instances.value || [];
    if (occurrences.length) return { master, occurrences, candidateCount: candidates.length };
  }
  return { master: null, occurrences: [], candidateCount: candidates.length };
}

// Deletes a single occurrence of a recurring series (e.g. a day the athlete has no practice)
// without touching the rest of the series. Graph requires resolving the series master first,
// then asking it for the specific day's occurrence id via /instances - a calendarView-expanded
// occurrence id is not itself deletable.
async function deleteOccurrence(client) {
  if (!args.subject || !args.date) {
    throw new Error('--delete-occurrence requires --subject and --date=YYYY-MM-DD [--calendar=<name>]');
  }
  const calendarId = args.calendar ? await resolveCalendarId(client, args.calendar) : null;
  const { master, occurrences, candidateCount } = await resolveOccurrenceForDate(client, args.subject, args.date, calendarId);
  if (!candidateCount) {
    throw new Error(`No recurring series found with subject "${args.subject}"${args.calendar ? ` on calendar "${args.calendar}"` : ''} (a non-recurring event with that exact subject doesn't count)`);
  }
  if (!master) {
    console.log(`No occurrence of "${args.subject}" on ${args.date} across ${candidateCount} matching series (already removed, or none scheduled that day).`);
    return;
  }
  for (const occ of occurrences) {
    await client.api(`/me/events/${occ.id}`).delete();
    console.log(`Deleted occurrence of "${master.subject}" on ${args.date}`);
  }
}

// Moves a single occurrence of a recurring series to a different time on the same day, without
// touching the rest of the series - e.g. an existing "drive to school" reminder becomes that day's
// earlier "drive to practice" time instead of leaving both a stale normal-time reminder and a
// separately-created event competing for the same drive.
async function rescheduleOccurrence(client) {
  if (!args.subject || !args.date || !args.start || !args.end) {
    throw new Error('--reschedule-occurrence requires --subject, --date=YYYY-MM-DD, --start=HH:MM, --end=HH:MM [--calendar=<name>]');
  }
  const calendarId = args.calendar ? await resolveCalendarId(client, args.calendar) : null;
  const { master, occurrences, candidateCount } = await resolveOccurrenceForDate(client, args.subject, args.date, calendarId);
  if (!candidateCount) {
    throw new Error(`No recurring series found with subject "${args.subject}"${args.calendar ? ` on calendar "${args.calendar}"` : ''} (a non-recurring event with that exact subject doesn't count)`);
  }
  if (!master) {
    throw new Error(`No occurrence of "${args.subject}" on ${args.date} across ${candidateCount} matching series to reschedule`);
  }
  for (const occ of occurrences) {
    await client.api(`/me/events/${occ.id}`).patch({
      start: { dateTime: `${args.date}T${args.start}:00`, timeZone: TZ },
      end: { dateTime: `${args.date}T${args.end}:00`, timeZone: TZ },
    });
    console.log(`Rescheduled "${master.subject}" on ${args.date} to ${args.start}-${args.end}`);
  }
}

// Updates one occurrence's subject and/or body without touching its time - e.g. tagging a
// recurring "Youth Activities" placeholder with that week's actual activity once it's known,
// without creating a competing one-off event or renaming the whole series.
async function updateOccurrence(client) {
  if (!args.subject || !args.date || (!args['new-subject'] && !args.body)) {
    throw new Error('--update-occurrence requires --subject, --date=YYYY-MM-DD, and --new-subject and/or --body [--calendar=<name>]');
  }
  const calendarId = args.calendar ? await resolveCalendarId(client, args.calendar) : null;
  const { master, occurrences, candidateCount } = await resolveOccurrenceForDate(client, args.subject, args.date, calendarId);
  if (!candidateCount) {
    throw new Error(`No recurring series found with subject "${args.subject}"${args.calendar ? ` on calendar "${args.calendar}"` : ''} (a non-recurring event with that exact subject doesn't count)`);
  }
  if (!master) {
    throw new Error(`No occurrence of "${args.subject}" on ${args.date} across ${candidateCount} matching series to update`);
  }
  const patch = {};
  if (args['new-subject']) patch.subject = args['new-subject'];
  if (args.body) patch.body = { contentType: 'text', content: args.body };
  for (const occ of occurrences) {
    await client.api(`/me/events/${occ.id}`).patch(patch);
    console.log(`Updated occurrence of "${master.subject}" on ${args.date}${args['new-subject'] ? ` -> "${args['new-subject']}"` : ''}`);
  }
}

// Deletes a plain (non-recurring) event by subject + date - e.g. a one-off event created in
// error, or one being replaced by a differently-timed one-off.
async function deleteEvent(client) {
  if (!args.subject || !args.date) {
    throw new Error('--delete-event requires --subject and --date=YYYY-MM-DD');
  }
  const data = await client.api('/me/calendarView')
    .query({ startDateTime: `${args.date}T00:00:00`, endDateTime: `${args.date}T23:59:59` })
    .header('Prefer', `outlook.timezone="${TZ}"`)
    .select('id,subject,start')
    .get();
  const matches = (data.value || []).filter(e => e.subject === args.subject);
  if (!matches.length) {
    console.log(`No event "${args.subject}" on ${args.date} (already removed).`);
    return;
  }
  for (const m of matches) {
    await client.api(`/me/events/${m.id}`).delete();
    console.log(`Deleted "${m.subject}" on ${args.date}`);
  }
}

// --date narrows the search to one day - needed when the subject isn't unique across the year
// (e.g. several one-off events sharing a subject on different dates). Without --date, keeps the
// original behavior: first upcoming match within the next 365 days.
async function updateReminder(client) {
  if (!args.subject || args.reminder === undefined) {
    throw new Error('--update requires --subject and --reminder=N|off [--date=YYYY-MM-DD]');
  }
  let data;
  if (args.date) {
    data = await client.api('/me/calendarView')
      .query({ startDateTime: `${args.date}T00:00:00`, endDateTime: `${args.date}T23:59:59` })
      .header('Prefer', `outlook.timezone="${TZ}"`)
      .select('subject,id,start')
      .get();
  } else {
    const now = new Date();
    const end = new Date(now.getTime() + 365 * 86400000);
    data = await client.api('/me/calendarView')
      .query({ startDateTime: now.toISOString(), endDateTime: end.toISOString() })
      .top(100).orderby('start/dateTime').select('subject,id,start').get();
  }
  const matches = (data.value || []).filter(e => e.subject === args.subject);
  if (!matches.length) {
    throw new Error(`No ${args.date ? `event on ${args.date}` : 'upcoming event'} with subject "${args.subject}"`);
  }
  const patch = args.reminder === 'off'
    ? { isReminderOn: false }
    : { isReminderOn: true, reminderMinutesBeforeStart: parseInt(args.reminder, 10) || 0 };
  for (const match of matches) {
    await client.api(`/me/events/${match.id}`).patch(patch);
    console.log(`Updated reminder on "${match.subject}"${args.date ? ` (${args.date})` : ''} -> ${args.reminder}`);
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
    if (args['create-recurring']) return createRecurringEvent(client);
    if (args['delete-occurrence']) return deleteOccurrence(client);
    if (args['reschedule-occurrence']) return rescheduleOccurrence(client);
    if (args['update-occurrence']) return updateOccurrence(client);
    if (args['delete-event']) return deleteEvent(client);
    if (args.create) return createEvent(client);
    if (args.update) return updateReminder(client);
    return listUpcoming(client);
  })().catch(e => { console.error('Error:', e.message); process.exit(1); });
}
