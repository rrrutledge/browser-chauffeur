# drainer triage — the rubric every source uses

Shared by every source (Outlook, Teams, Trello, …). Classification is identical across sources — only
the *mechanics* of enumerating/capturing/clearing differ (those live in each provider doc). Classify
by THIS file; don't restate the buckets elsewhere. This file ONLY classifies — what the loop DOES with
each bucket (own worker vs digest) lives in the driver and SKILL.

## The question

For every inbound item ask: **is there something for Russell to do?** If there is, now is the time — do
it immediately, or kick it off in a tab. Everything Russell is going to do, he does right now.

Answering that is the whole of triage, and the answer is one of four buckets — two when there's something
to do, two when there isn't.

**First, follow pointers — but don't open them here.** Some items aren't the content; they POINT to it (a
Teams meeting-recording notice linking to AI notes with action items; a LinkedIn/Facebook "X messaged
you" pointing to a DM elsewhere). Triage works only from what's in front of it and never opens the link
(the batched step has no browser). So a pointer that plausibly holds something for Russell is itself
something to do — the action is *open it and act* → **needs-you**, and the worker does the lookup (pull
each action item out and capture it separately, read and answer the DM, …). Only a pointer that plainly
carries the whole story and asks nothing — a recording notice with no notes — is just **fyi**.

**Then, for the content in front of you, there's something to do when:**

- it's **an action Russell himself would take** — not what the sender wants him to do, but what he'd
  decide to act on: a reply to write, a form to return, a survey to fill, an RSVP, a decision to make,
  work to kick off (code, a doc, a ticket, a lookup, a system update…), or delegating it to the team. A
  training deadline he'd complete is an action; a security alert for a failed login he already knows
  about is not — reading it changes nothing he'd do.
- it names that action **no matter how broadly it was sent** — audience breadth doesn't change anything,
  and an automated sender doesn't make it junk. A message to a hundred people that names something Russell
  would do (sign the card, submit the goals, RSVP for the offsite) is his action exactly as much as if he
  were the only recipient; ask only whether he'd do the thing.
- **someone reaches out on a human level** — a personal, individually-written note, not a
  corporate/automated/mass announcement. Replying *is* the thing to do even when it asks nothing
  explicitly: acknowledging that he got it and appreciates it counts. The personal tone is the signal;
  the warmth of what they shared is the reason to write back.
- a **dated to-do** comes due — a Trello tracker or outreach card, any dated item, the moment its due
  date arrives or passes. The due date IS the queue: a due item is the action surfacing when it was
  scheduled for.

**When there is something to do, it's one of two buckets:**

- **needs-you** — Russell acts on it now, in its own worker tab. This is the default for anything he'd
  do. It's ONE bucket on purpose; don't split reply-vs-work here. Record a hint:
  **"reply" / "work" / "work-then-reply"**.
- **auto-handle** — the narrow case where a **standing rule fully decides** the action: the same answer
  every time, no judgment left. Claude does it autonomously and reports it in the digest instead of
  opening a tab. These standing rules are defined per source, in `providers/<source>-provider.md` under
  its **AUTO-HANDLE** section (the poller surfaces them at triage time so the match can be made here);
  pick this bucket **only** when one of those rules plainly matches — it says exactly what to do and under
  what condition. Any judgment left — *should* this be approved, *how* to word a reply, *whether* it's the
  right move — keeps it **needs-you**.

**When there's nothing to do, it's one of the other two:**

- **fyi** — Russell may want to know, but there's nothing to act on; no tab opens and the digest surfaces
  it. Delivery-failure bounces (MAILER-DAEMON / Postmaster) land here: they report that an email didn't
  reach him, but there's nothing for him to do about the bounce itself.
- **junk** — not even worth surfacing: automated noise, newsletters, pure marketing, CI/build
  notifications, duplicate status churn, chatter not aimed at the user. Junk is also a signal to stop it
  arriving again; *how* to stop it is provider mechanics — each provider's **JUNK-LEARNING** section owns
  the remediation (unsubscribe → source-app notification settings → inbox rule, in that order).

## Tie-breakers
- **auto-handle** is never a tie-breaker default: pick it ONLY when a provider AUTO-HANDLE rule clearly
  matches. Any doubt that the rule applies → fall back to **needs-you** (let Russell decide). Better to
  ask once than to auto-act on something that wasn't actually a standing decision.
- Unsure whether there's something to do → treat it as **needs-you** (prefer acting).
- Nothing to do, unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
