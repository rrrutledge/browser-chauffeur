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

**First, recognize pointers (a.k.a. containers) — but don't open them here.** Some items aren't the
content; they POINT to it, holding the real thing elsewhere: a Teams meeting-recording notice linking to
AI notes with action items; a LinkedIn/Facebook "X messaged you" pointing to a DM elsewhere; a bank or
portal "you have a message waiting"; a newsletter whose body sits behind a hosted "view in browser" link
(Smore, Finalsite, a Mailchimp campaign). Triage **recognizes** the pointer and routes it but never opens
it (the batched step has no browser); the stage that acts — a worker, or the digest for an fyi — opens and
reads it per the resolve-a-pointer step (`worker-core.md` § 2b). So a pointer that plausibly holds
something for Russell is itself something to do — *open it and act* → **needs-you**, and the worker does
the lookup (pull each action item out and capture it separately, read and answer the DM, …). A pointer
that plainly carries the whole story and asks nothing — a recording notice with no notes — is **fyi**.
**Don't pre-judge a pointer's bucket by whether its content sits behind a login.** Triage has no browser
and can't know the bucket unfetched, so route anything that isn't obviously whole-story-fyi to
**needs-you** and leave the resolving to § 2b, which opens it and **re-triages the real content on its own
merits** — landing needs-you, fyi, or junk from what it actually says. Whether a sign-in exists doesn't
decide it here.

**Then, for the content in front of you, there's something to do when:**

- it's **an action Russell himself would take** — not what the sender wants him to do, but what he'd
  decide to act on: a reply to write, a form to return, a survey to fill, an RSVP, a decision to make,
  work to kick off (code, a doc, a ticket, a lookup, a system update…), or delegating it to the team. A
  training deadline he'd complete is an action; a security alert for a failed login he already knows
  about is not - reading it changes nothing he'd do. An **automated notification that something he owns is
  broken or failing** - a failed build or CI run on a repo he maintains, a monitor/health alert on a
  service he runs, a **service/integration notice that something he (or an organization he runs) configured
  has stopped working or needs reconnecting** (a dropped integration, disconnected social accounts, an
  expired connection, e.g. a Hootsuite "social networks disconnected" notice), a job-failure or
  broken-link report - is work to do (go fix it), the same as any other work he'd kick off; a passing,
  routine, subscription-digest, or already-known-good status is not. A **CI or Actions FAILURE on a pull
  request he authored** is his to fix (go fix the failure): the failure itself is the signal, and it stays
  needs-you even when the same repo's routine success notices and subscription mail are fyi/junk; use the
  failure-vs-success distinction, not the repo, to sort GitHub notification mail. A **job-application step
  he'd take** — a pending interview or assessment invite/reminder from a hiring platform, an
  application-status action — is his action (do the interview, take the next step), the automated send
  notwithstanding.
- it names that action **no matter how broadly it was sent** — audience breadth doesn't change anything,
  and an automated sender doesn't make it junk. A message to a hundred people that names something Russell
  would do (sign the card, submit the goals, RSVP for the offsite) is his action exactly as much as if he
  were the only recipient; ask only whether he'd do the thing.
- **someone reaches out on a human level** — a personal, individually-written note, not a
  corporate/automated/mass announcement. Replying *is* the thing to do even when it asks nothing
  explicitly: acknowledging that he got it and appreciates it counts. The personal tone is the signal;
  the warmth of what they shared is the reason to write back. **Treat a 1:1 direct message from a real
  person as this case by default** — exactly two participants, Russell and the other person; a private
  one-on-one DM is personal outreach, so it's **needs-you** (hint: "reply") even when it's just a short
  remark or a closing "sounds good"; the minimum action is a quick acknowledgment or 👍 reaction on their
  message. **This default does not extend to a group DM** (three or more participants) — a closing remark
  or agreement there may be aimed at someone else in the thread, not Russell, so treat it as fyi unless it
  names Russell directly or leaves an actual open ask. A group or meeting message that names Russell
  directly counts the same as the 1:1 case; only automated, mass, or not-aimed-at-him chatter (including a
  closing remark addressed to someone else in a group thread) stays fyi.
- a **marketplace/member message carries a real question from a buyer or seller** - an eBay, Etsy,
  Facebook-Marketplace, or similar member-to-member message where a real person is asking Russell
  something about a transaction: a buyer waiting on a tracking number, a shipment or refund query, a
  question about an item he's selling or buying. The automated relay it arrives through (a
  `members.ebay.com`-style forwarding address, "so-and-so sent a message about <item>") does not make it
  junk - a person asking a direct question is the signal, exactly as a plain email would be, so it's
  **needs-you** (hint: "reply"). The generic marketplace promo/notification stream - deals, "items you
  might like", price-drop alerts, offer or listing-view counts, nobody asking anything - stays **junk**.
- a **dated to-do** comes due — a Trello tracker or outreach card, any dated item, the moment its due
  date arrives or passes. The due date IS the queue: a due item is the action surfacing when it was
  scheduled for.
- **Russell sent it to himself** — a note from his own address is a deliberate self-note, not noise.
  Evaluate it by content exactly as you would any other item: **needs-you** when the content implies an
  action, fyi when it's just something to re-read. Never junk for being terse or self-addressed — and not
  for looking scam-like or arriving empty either; a self-note is a task captured for a worker, so treat it
  as the task, never as spam to filter, however much the content resembles junk.

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
  it. Common cases that land here:
  - **Delivery-failure bounces** (MAILER-DAEMON / Postmaster) — **needs-you** when someone Russell was
    actually trying to reach didn't get it: a primary **To** recipient, especially a lone address (e.g. a
    Google Docs comment bounced from `comments-noreply@docs.google.com`), which he now has to deliver
    another way. fyi when the failed address wasn't the real target — a CC, or one of many on a mailing
    list — so the message still reached who it was for.
  - **Completed-event notices** — an automated notification that something already finished (a token
    regenerated, a password changed, a setting updated, a sign-in confirmed); reading it changes nothing
    Russell would do. It would become an action only if the notice revealed something unexpected, and
    Russell catches that in the digest and escalates himself.
  - **Newsletters from an institution Russell has a real relationship with** — his children's school,
    his HOA, his church, a community he belongs to — are fyi, not junk; the test is the relationship, not
    that it's a bulk send. (A link-hosted one is a pointer the digest opens — see "recognize pointers"
    above.)
- **junk** — not even worth surfacing: automated noise, pure marketing, cold newsletters (a sender
  Russell has no relationship with), generic marketplace promo (deals, "items you might like"; but a
  member *question* from a buyer/seller is needs-you, see the marketplace bullet above), passing or
  duplicate automated status churn (an automated *something-you-own-is-broken/failing* alert is
  needs-you, see the action bullet above), chatter not aimed at the user.
  Junk is also a signal to stop it arriving again; *how* to stop it is provider mechanics — each
  provider's **JUNK-LEARNING** section owns the remediation (unsubscribe → source-app notification
  settings → inbox rule, in that order).

**Phishing is junk with a sharper disposition - mark it.** Mail that isn't merely unwanted but
*deceptive* - a spoofed or lookalike sender domain (a throwaway domain dressed up as a real brand, e.g. a
"CarShield" ad from `info@nvr.nivobuscaf.com`), a credential-harvest or fake-account-alert lure, a
payment or gift-card scam - is still **junk**, but stamp its `kind` as **`phishing`**. That marker routes
it, at digest time, to the provider's **report-phishing** action (report the message to the mail provider
so its filter learns, then move it out of the inbox) instead of an ordinary archive, rule, or unsubscribe:
a stronger disposition that is still reversible (the message stays recoverable from Junk/Spam). Reserve the
mark for mail built to trick: when a message is only low-quality marketing rather than deceptive, leave it
plain junk. The provider capability and the digest's report-on-approval handling live in
`providers/<source>-provider.md` → REPORT-PHISHING and `engine/digest-core.md` step 3.

## Tie-breakers
- **auto-handle** is never a tie-breaker default: pick it ONLY when a provider AUTO-HANDLE rule clearly
  matches. Any doubt that the rule applies → fall back to **needs-you** (let Russell decide). Better to
  ask once than to auto-act on something that wasn't actually a standing decision.
- Unsure whether there's something to do → treat it as **needs-you** (prefer acting).
- Nothing to do, unsure between **fyi** and **junk** → **fyi** (prefer keeping eyes on it).
