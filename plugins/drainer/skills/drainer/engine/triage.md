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
- Unsure between **needs-you** and **fyi** → **needs-you** (prefer acting).
- Unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
- Reserve **needs-you** for genuine asks directed at Russell **or personal messages owed a human
  reply**; bias toward **fyi** for impersonal/automated information.
