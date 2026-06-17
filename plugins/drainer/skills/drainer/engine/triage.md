# drainer triage — the one rubric every channel uses

Shared by every drainer source (email, Teams, future channels) and by both runners that classify
(the **sweep** and the **harvester**). Classification is identical across channels — only the
*mechanics* of enumerating/capturing/clearing differ (those live in each channel's provider doc).
Classify by THIS file; don't restate the buckets elsewhere. This file ONLY classifies — what the
algorithm DOES with each bucket (own tab vs digest) lives in the driver/SKILL/digest.

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
- **fyi** — informational; the user may want to know but nothing is asked of them (a report, a
  heads-up, a decision someone else made).
- **junk** — no information value AND no action: automated noise, newsletters, pure marketing,
  CI/build notifications, duplicate status churn, chatter not aimed at the user. Every junk item is a
  signal to stop it at the source — propose the channel's filter/rule so it stops arriving and future
  runs spend tokens and attention only on what matters.

These are the only three classes — there is no fourth. An item that turns out to need nothing right
now is still one of these (usually fyi); it isn't a separate "no-op" class.

## Containers that hold action items
Some messages are not themselves actionable but point to content that may contain action items — e.g.
a Teams meeting recording notification links to AI-generated meeting notes with action items assigned
to specific people. Don't classify the notification itself; **open the linked content and classify
based on what's inside.** If there are action items assigned to Russell, each one is a separate
needs-you item (capture them individually, not as one bundle). If the AI notes exist but have no
action items for Russell, it's fyi. If there are no AI notes at all, the recording notification
itself is fyi.

## Tie-breakers
- Unsure between **needs-you** and **fyi** → **needs-you** (prefer acting).
- Unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
- Reserve **needs-you** for genuine asks directed at Russell; bias toward **fyi** otherwise.
