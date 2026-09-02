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

**A recurring series is one task, not one-per-missed-occurrence.** Outlook's recurrence engine expands
every date the pattern ever produced between its start and today, so a daily or weekly task left
uncleared for a while genuinely has several individually-overdue occurrences sitting in Graph — but
Russell only ever sees ONE drainable item for it (`enumerate` collapses them by series, see the
adapter), and doing it once catches up the whole backlog rather than requiring one CLEAR per missed
occurrence (see CLEAR).

**The second gate, unique to this source:** even once a task is due, the adapter's `enumerate` only
returns it when a live free gap of at least that duration **plus a buffer** currently exists before
Russell's next REAL commitment (a calendar event with someone else on it, or one he didn't organize — a
solo self-owned event, on any calendar, never counts as blocking). The buffer covers the lag between the
gap being detected and Russell actually opening the tab — waiting on tab budget, or just being deep in a
different one when this one pops — so a task's own duration alone isn't the bar; duration + buffer is.
That gap is recomputed fresh every poll cycle, so a task becomes eligible the moment enough room opens up
and simply waits, unenumerated, until then.

**Prefer the longest task that fits.** When several tasks are eligible at once, a long gap shouldn't get
spent on a short task while a longer one could have used it — `enumerate` returns eligible tasks sorted
longest-duration-first, so the cross-source dispatch order (which otherwise ties on priority band and
falls back to arrival order) picks the task that best uses the room available.

No task should ever be sized past about an hour — even a task that might genuinely take two or three
hours gets estimated at one hour, since Russell can always make an hour of progress on it and doesn't
need to wait for a rarer multi-hour gap. That's *why* `lookahead_hours` defaults short (see Config): the
gap check never needs to see further ahead than the longest task plus its buffer.

## Config (`.claude/drainer.local.md` → `providers.physical-task`)
- `calendar` — the dedicated calendar's name (default `Physical Tasks`).
- `lookahead_hours` — how far ahead the gap check looks for the next real commitment (default `2`).
  Kept short on purpose (see "The model" above) — raise it only if a task genuinely needs more than
  about an hour plus its buffer, which shouldn't normally happen.
- `buffer_minutes` — minutes added on top of a task's own duration before it counts as eligible
  (default `20`), covering the gap-detection-to-tab-opened lag described above.
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
- `isRecurring` — whether this is a recurring series rather than a one-off. When true, `date` is the
  most recent overdue occurrence, not necessarily today — a series left uncleared can accumulate
  several missed occurrences (see CLEAR's catch-up behavior).
- `eventId` — the raw Graph id CLEAR acts on: the event's own id for a one-off, or the **series
  master's** id for a recurring one (never a single occurrence's instance id — see CLEAR for why).
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
3. **Note the time, then wait for him to actually do it.** This is interactive — stay with him rather
   than firing a reminder and moving on. Record the current wall-clock time when he says he's starting.
4. **When he confirms done (or it's already handled), log the estimate against the actual time before
   CLEARing** — append one line to `<runtime_dir>/physical-task-log.jsonl` (Edit/Write tool; create the
   file if it doesn't exist yet) with `{"date","subject","estimatedMinutes","actualMinutes","ts"}`,
   `actualMinutes` computed from the start time you noted in step 3 to now. This replaces Russell's old
   habit of dragging the calendar event's start/end times to match reality after the fact — same
   estimate-vs-actual signal, but durable instead of overwritten the moment the event that carried it is
   deleted, so it can actually be reviewed for a pattern over time instead of glanced at once. If he says
   now isn't actually a good moment after all (interrupted, the gap turned out to be needed for something
   else), skip the log entry and CLEAR as deferred instead — don't leave the item dangling unaddressed.
5. **Close out per the standard rules** (`../engine/worker-core.md` §6's close conditions) — this tab
   stays open exactly as long as any other needs-you tab would: until his part is genuinely done.

## CLEAR
What CLEAR means depends on `isRecurring` in the captured item — a one-off event and a recurring
series behave differently under the hood, so don't use the same command for both:

- **One-off, done** — `node calendar.js --delete-event-id=<eventId>`.
- **One-off, deferred** — not a good moment after all, try again another day: `node calendar.js
  --move-event-id=<eventId> --date=YYYY-MM-DD`, picking the day Russell names (or, absent a better
  signal, tomorrow). Keeps the same time-of-day and duration.
- **Recurring, done** — `eventId` is the series master's id (see CAPTURE): `node calendar.js
  --catch-up-series=<eventId>`. A series left uncleared for a while can rack up several overdue
  occurrences (Graph expands every date the pattern ever produced, not just the next one) — this
  deletes ALL of them through today in one shot ("done, series continues"), never the series master
  itself, so every future occurrence is untouched and keeps arriving on its own schedule.
- **Recurring, deferred (today's occurrence only, series unaffected)** — genuinely rare (the whole
  point of the gap check is that this only dispatches when there's room), but if it comes up:
  `node calendar.js --delete-occurrence --subject="<subject>" --date=<dueDate> --calendar="<calendar>"`
  removes just today's instance without touching the series or any earlier backlog. Most of the time,
  simply doing nothing is correct instead — an unfinished recurring item just stays due and dispatches
  again whenever a gap next opens, same as before you looked at it.

Never CLEAR before Russell has actually confirmed one of the outcomes above — unlike a source whose
scope is knowable up front (see `../engine/worker-core.md` §2d), a physical task's completion can only be
observed by asking him.

## JUNK-LEARNING
N/A — every item here is a task Russell put on his own calendar, never inbound noise.

## DRAFT-MODE
N/A by default — most physical tasks need no outbound message. When one genuinely does (mailing a
signed form needs a cover note, dropping something off means texting ahead), that's ordinary work done
in step 2 above through whatever channel it actually needs (email, Slack, message-draft in that
channel's mode) — not a fixed mode for this source.
