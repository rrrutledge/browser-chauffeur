# drainer triage — the rubric every source uses

Shared by every source (Outlook, Teams, Trello, …). Classification is identical across sources — only
the *mechanics* of enumerating/capturing/clearing differ (those live in each provider doc). Classify
by THIS file; don't restate the buckets elsewhere. This file ONLY classifies — what the loop DOES with
each bucket (own worker vs digest) lives in the driver and SKILL.

## The one question

For every inbound item ask **"What does this want Russell to do?"** Answer that BEFORE assigning a
bucket. If the answer is anything other than "nothing," it's **needs-you**. An automated sender does
not make something junk — read the content and ask what it wants (a training deadline wants the
training done; a code-scan alert wants a fix; a reminder wants the thing it's reminding about).
Volume is irrelevant; actionability is in the content, not the count.

## The three buckets

- **needs-you** — there is something to DO: a reply, a piece of work to kick off (code, a doc, a
  ticket, a lookup, a system update…), a decision, a check, or delegating it to the team — or BOTH
  (often: do the work, then reply about the outcome). This is ONE bucket on purpose; don't try to
  decide reply-vs-work here. Record a hint: **"reply" / "work" / "work-then-reply"**.
  A **personal, individually-written** message that shares something personal — a one-to-one note, a
  personal update from a friend or contact, not a corporate/automated/mass announcement — is
  **needs-you (reply)** even when it asks nothing explicitly: replying at a human level *is* the action.
  The personal tone is the signal; the warmth of what they shared is the reason to write back.
- **fyi** — **impersonal** information: the user may want to know but nothing is asked and no human reply
  is owed (a report, an automated heads-up, a decision someone else made, a mass/corporate announcement).
- **junk** — no information value AND no action: automated noise, newsletters, pure marketing,
  CI/build notifications, duplicate status churn, chatter not aimed at the user. Every junk item is a
  signal to stop it arriving, in this **priority order** (best outcome = never received again):
  1. **Unsubscribe** — if the email carries an unsubscribe link, propose using it.
  2. **Turn it off at the source app** — if there's no unsubscribe but the sender is an app whose
     notifications you control (GitHub notification settings, LinkedIn email preferences, …), propose
     adjusting those settings so the email is never sent.
  3. **Inbox rule** — only when neither of the above applies, fall back to the source's filter/rule
     (e.g. an Outlook.com rule) to file or delete it on arrival.
  Always propose; never unsubscribe, change app settings, or add a rule without the user's OK.

## Containers that hold action items
Some messages are not themselves actionable but point to content that may contain action items — e.g.
a Teams meeting recording notification links to AI-generated meeting notes with action items assigned
to specific people. Don't classify the notification itself; **open the linked content and classify
based on what's inside.** If there are action items assigned to Russell, each one is a separate
needs-you item (capture them individually, not as one bundle). If the AI notes exist but have no
action items for Russell, it's fyi. If there are no AI notes at all, the recording notification
itself is fyi.

A **message-notification email** is the same shape: e.g. LinkedIn/Facebook "X just messaged you" or a
forum "you have a reply" is only a pointer to a message living on another service. The notification
carries too little to classify — **open the underlying message and classify by its content.** If no
provider yet reaches that service, treat the notification as **needs-you**: the action is to open that
service, read the message, and respond there.

## Tie-breakers
- Unsure between **needs-you** and **fyi** → **needs-you** (prefer acting).
- Unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
- Reserve **needs-you** for genuine asks directed at Russell **or personal messages owed a human
  reply**; bias toward **fyi** for impersonal/automated information.
