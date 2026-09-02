# physical-task provider — a dedicated calendar of physical-world to-dos (Microsoft Graph API)

A provider for the one class of work nobody but Russell can do: something in the physical world (AI
can't run to the mailbox, can't drive to the branch). Everything else he needs to get done — however
long it takes, digital or not — is drained through Trello or the other sources; **this provider exists
only for the timing problem physical action has and nothing else does**: it needs to surface right when
there's actually enough free time before his next real commitment, not just whenever the day arrives.

Read and cleared entirely through the **Microsoft Graph API** via the **`ms-graph`** skill's
`calendar.js` — no browser. Implements `../engine/provider.md`; classify by `../engine/triage.md`
(though see AUTO-HANDLE-ADJACENT below — this source's triage bucket is decided deterministically,
not by the AI triage call). id prefix: `physical-task-`.

> Two-file provider: the **reading/gap mechanics** (enumerate, the due+gap filter, the id scheme) live
> in the sibling **`physical-task-adapter.py`** that the poller drives. This doc is the **worker-facing**
> prose — AUTH-GLANCE, the captured item shape, CLEAR, and the one thing every other provider's prose
> doesn't need to say: what "do the item" even means when the work is physical.

## The model
A task's placement on the dedicated calendar (default name **"Physical Tasks"**, configurable) IS its
due date — the same "Start now-or-earlier is startable" idea Trello uses, just expressed as a calendar
day instead of a field. Nothing here ever moves a task to keep it visible; an undone one simply keeps
coming back every cycle until CLEAR deletes it (done) or moves it to a later day (deferred). The event's
own duration (end minus start) is Russell's own estimate of how long the task takes — carried over
unchanged from the old habit of sizing a to-do to a calendar block, just no longer tied to a specific
clock hour.

**The second gate, unique to this source:** even once a task is due, the adapter's `enumerate` only
returns it when a live free gap of at least that duration currently exists before Russell's next REAL
commitment (a calendar event with someone else on it, or one he didn't organize — a solo self-owned
event, on any calendar, never counts as blocking). That gap is recomputed fresh every poll cycle, so a
task becomes eligible the moment enough room opens up and simply waits, unenumerated, until then.

## Config (`.claude/drainer.local.md` → `providers.physical-task`)
- `calendar` — the dedicated calendar's name (default `Physical Tasks`).
- `lookahead_hours` — how far ahead the gap check looks for the next real commitment (default `48`).
- `exclude` — calendar names to leave out of the gap check (e.g. a read-only subscription that
  shouldn't count as blocking).
No credentials here — sign in once via `ms-graph`; the MSAL token cache is machine-local.

## AUTH-GLANCE
Run `node calendar.js --list-calendars`. If it prints calendars, you're signed in. If it errors with
"Not signed in" or an auth error, do the `ms-graph` one-time sign-in (`node scripts/auth.js` via
browser-chauffeur), then retry — never surface the token error to Russell.

## CAPTURE
`items/<id>.json`:
`{ "id","source":"physical-task","triage":"needs-you","kind":"work","subject","date","minutes",`
`"isRecurring","calendar","eventId","url","ts":"<ISO now>" }`
- `subject` — the task itself, in Russell's own words (however he named the calendar event).
- `date` — the day it became due (YYYY-MM-DD); may be well in the past for something that's sat undone.
- `minutes` — the duration Russell estimated (the event's own length) — also the size of the free gap
  that made this item eligible to dispatch right now.
- `isRecurring` — whether this is one occurrence of a recurring series (Outlook's own recurrence
  handles the next occurrence automatically; you're only ever looking at today's).
- `eventId` — the raw Graph event/occurrence id CLEAR acts on.
- `url` — the event's Outlook `webLink`, so Russell can open the actual calendar item if he wants to.

## Why this item bypassed the usual triage judgment
`run-poller.py` routes every `physical-task` item straight to `needs-you`/`work`, the same deterministic
shortcut it uses for a started Trello card or an orphaned session — never through the AI triage call.
There's nothing to judge: the adapter's `enumerate` already established the task is due AND a real gap
for it exists right now, and that combination is definitionally "go do this." A physical task is never
`fyi` or `junk` — there's no inbound noise to distinguish it from, only Russell's own to-dos.

## WORKER — what "do the item" means for physical work
Every other source's step 3 ("do the action") means Claude does the work. Here it doesn't — the task is
physical, so **Russell** does it, and your job is the surrounding logistics:
1. **Lead with the task and the window** — restate the subject, and say plainly that this is the moment
   for it: "you've got about `<minutes>` minutes before your next real commitment, and this needs about
   that long." Link the event (`url`) so he can glance at the calendar item itself if useful.
2. **Do any prep work that IS digital** before handing it over — look up an address, print or open a
   form, pull up an account number, draft a note that needs to go with him. Anything you can genuinely
   do to make the physical step faster, do it now, the same as step 3 in the generic worker flow.
3. **Wait for him to actually do it, then ask.** This is interactive — stay with him rather than firing
   a reminder and moving on. When he confirms he's done (or that circumstances changed and it's already
   handled), CLEAR as done. If he says now isn't actually a good moment after all (interrupted, the gap
   turned out to be needed for something else), CLEAR as deferred instead — don't leave the item
   dangling unaddressed.
4. **Close out per the standard rules** (`../engine/worker-core.md` §6's close conditions) — this tab
   stays open exactly as long as any other needs-you tab would: until his part is genuinely done.

## CLEAR
Two outcomes, both via `calendar.js`, acting on the captured `eventId`:
- **Done** — Russell confirms he actually did it (or it's already handled): `node calendar.js
  --delete-event-id=<eventId>`. Works identically for a one-off event or a single recurring
  occurrence's instance id — a recurring series' other occurrences are untouched, and Outlook's own
  recurrence pattern brings the next one due on its own schedule; nothing here has to re-create it.
- **Deferred** — not a good moment after all, try again another day: `node calendar.js
  --move-event-id=<eventId> --date=YYYY-MM-DD`, picking the day Russell names (or, absent a better
  signal, tomorrow). Keeps the same time-of-day and duration; a recurring occurrence detaches from its
  series the same way dragging it in the Outlook UI would, exactly like the old carry-forward script's
  crossing-boundary case — expected, not an error.

Never CLEAR before Russell has actually confirmed one of the two outcomes above — unlike a source whose
scope is knowable up front (see `../engine/worker-core.md` §2d), a physical task's completion can only be
observed by asking him.

## JUNK-LEARNING
N/A — every item here is a task Russell put on his own calendar, never inbound noise.

## DRAFT-MODE
N/A by default — most physical tasks need no outbound message. When one genuinely does (mailing a
signed form needs a cover note, dropping something off means texting ahead), that's ordinary work done
in step 2 above through whatever channel it actually needs (email, Slack, message-draft in that
channel's mode) — not a fixed mode for this source.
