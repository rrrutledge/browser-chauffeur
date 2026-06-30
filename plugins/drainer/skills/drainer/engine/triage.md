# drainer triage — the rubric every source uses

Shared by every source (Outlook, Teams, Trello, …). Classification is identical across sources — only
the *mechanics* of enumerating/capturing/clearing differ (those live in each provider doc). Classify
by THIS file; don't restate the buckets elsewhere. This file ONLY classifies — what the loop DOES with
each bucket (own worker vs digest) lives in the driver and SKILL.

## The two questions

For every inbound item ask both questions before assigning a bucket. They are the whole decision — the
buckets below just name the outcome.

1. **"Would Russell actually do something because of this?"** — Not what the sender wants him to do,
   but what Russell himself would decide to act on. A training deadline he'd complete is an action;
   a security alert for a failed login he already knows about isn't — reading it changes nothing he'd
   do. An automated sender does not make something junk — read the content and ask whether it would
   move Russell to act. Volume is irrelevant; actionability is in Russell's response, not the sender's
   intent. **Audience breadth is irrelevant too** — a message sent to a hundred people that names an
   action Russell himself would take (sign the card, complete the survey, RSVP, return the form) is an
   action for *him*, exactly as much as if he were the only recipient. Being one of many recipients
   never downgrades a real action; ask only whether Russell would do the thing.

2. **"Is there an advantage to acting NOW?"** — Even when there is an action, ask whether doing it
   immediately matters. Is someone waiting on Russell? Does it keep a conversation moving? Is there a
   deadline in the next day or two — or has a due date Russell owns already arrived or passed (a tracker
   card, an outreach card, any dated to-do), making this the moment it was queued for? If yes →
   **needs-you** (open a worker tab). If the action could wait a day with no consequence to anyone →
   **fyi** (let the digest surface it). The worker tab is for items where timing matters; the digest
   handles everything else. An owned, now-or-past due date is itself that act-now signal across every
   source — the due date IS the queue, so a due item is needs-you, not fyi.

**Delivery-failure bounces (MAILER-DAEMON / Postmaster):** always **fyi**. They report that someone's
email didn't reach Russell; he may eventually want to contact that person another way, but there's no
urgency, no one is blocked waiting for his reply, and the digest is the right venue.

**"Review and confirm" notifications:** always **fyi**. A notification whose only possible outcome is
"yes, that looks right" is awareness, not work — no action item spawns from reading it. It only spawns
an action in the rare case that the review reveals something unexpected; Russell spots that in the digest
and escalates himself. No tab opens just to confirm something he already knew happened. Automated
confirmations of account actions fall squarely here: a token regenerated, a password changed, a setting
updated, a new device added, a sign-in confirmed. The same principle extends to any automated
notification that reports a completed event — the content is information, not a request.

## The four buckets

Each bucket names an outcome of the two questions; *when* each applies is decided up there, so the
definitions below only say what the label means and what the loop does with it.

- **auto-handle** — there is an action to take, but it is **fully determined by a standing rule** with
  **no judgment call left for Russell**: the same answer every time, decided in advance. Claude can do
  the action autonomously and tell Russell afterward in the digest, rather than opening a tab to ask.
  Use this **only** when a provider's **AUTO-HANDLE** section names a rule that plainly matches this item
  (the rule says exactly what to do and under what condition). The bar is high: any genuine decision left
  — *should* this be approved, *how* to word a reply, *whether* it's the right move — makes it
  **needs-you**. No matching standing rule → not auto-handle. (The worker still performs the action; it
  just never interrupts Russell, and the digest records what was done.)
- **needs-you** — the two questions land on act-now: there is something to DO and now is the time. The
  thing to do may be a reply, a piece of work to kick off (code, a doc, a ticket, a lookup, a system
  update…), a decision, a check, or delegating it to the team — or BOTH (often: do the work, then reply
  about the outcome). This is ONE bucket on purpose; don't split reply-vs-work here. Record a hint:
  **"reply" / "work" / "work-then-reply"**.
  One extension beyond the two questions: a **personal, individually-written** message that shares
  something personal — a one-to-one note, a personal update from a friend or contact, not a
  corporate/automated/mass announcement — is **needs-you (reply)** even when it asks nothing explicitly.
  Replying at a human level *is* the action; the personal tone is the signal and the warmth of what they
  shared is the reason to write back.
- **fyi** — information that leaves Russell nothing to do now: Q1 turns up no action he'd take, or Q2
  says it can wait. He may want to know, but no human reply is owed and nothing is his to act on. The
  digest surfaces it.
- **junk** — no information value AND no action: automated noise, newsletters, pure marketing,
  CI/build notifications, duplicate status churn, chatter not aimed at the user. Junk is also a signal
  to stop it arriving again; *how* to stop it is provider mechanics — each provider's **JUNK-LEARNING**
  section owns the remediation (unsubscribe → source-app notification settings → inbox rule, in that
  order). Triage only labels it junk.

## Containers that point to action items
Some messages are not themselves the content — they POINT to it: a Teams meeting-recording notice links
to AI meeting notes with action items; a LinkedIn/Facebook "X just messaged you" points to a DM on
another service. **Triage classifies from what's in front of it — it does NOT go open the linked
content** (that lookup is the worker's job, and the batched triage step has no browser anyway). When a
container plausibly holds something for Russell, bucket it **needs-you**, with the action being *open
the linked content, see what's there, and act* — the worker then does the lookup (extract each assigned
action item and capture it separately, read and answer the DM, …). Only when the notification itself
plainly carries the whole story and asks nothing (e.g. a recording notice with no notes) is it **fyi**.

## Tie-breakers
- **auto-handle** is never a tie-breaker default: pick it ONLY when a provider AUTO-HANDLE rule clearly
  matches. Any doubt that the rule applies → fall back to **needs-you** (let Russell decide). Better to
  ask once than to auto-act on something that wasn't actually a standing decision.
- Unsure between **needs-you** and **fyi** → **needs-you** (prefer acting).
- Unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
