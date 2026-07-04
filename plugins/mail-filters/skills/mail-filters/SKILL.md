---
name: mail-filters
description: Russell's calibrated strategy for mail filters/rules that auto-archive never-process mail at the mail server, before it ever reaches the drainer or the inbox. Use when deciding whether a piece of junk deserves a filter and, if so, what phrase that filter should match and how to create it — in Gmail (filters) or Outlook (rules). Teaches the phrase-selection craft (broad enough to recur across senders, strict enough to never bury wanted mail) and the per-platform create/delete mechanics.
---

# Mail Filters — auto-archive the never-process mail before it reaches you

This skill captures a strategy Russell has tuned by hand for over two decades, most heavily in his
personal Outlook. Its job is narrow and high-leverage: decide when a piece of mail belongs to a whole
**category that never needs processing**, and encode that as a server-side filter so mail of that type
is archived automatically — never surfacing in the inbox, never reaching the drainer.

Archiving is not deleting. An archived message stays fully searchable; the filter only means "don't
actively show me this or notify me about it." So a filter is safe, reversible config — you can always
find an archived message later, and you can always delete a filter.

## The one decision this skill owns

In the age of a drainer that processes mail immediately, incoming mail has three states:

1. **Auto-archive at the mail server** — never needs processing; filtered out *before* the drainer
   sees it. **This skill owns exactly this line.**
2. **FYI** — reaches the drainer, surfaced as informational, no action needed.
3. **Needs work / act now** — reaches the drainer, requires action.

The split between (2) and (3) is the **drainer's triage** layer, not this skill's. This skill answers
only one question: **does this mail ever need to reach the drainer at all?** When the answer is no for
a whole category, a filter removes that work entirely — which beats processing it quickly, because the
best per-message cost is zero.

> Historical note for context only: these rules were born when email was the primary channel and a
> human had to answer within hours, so they once sorted *human urgency* into inbox / low-priority /
> junk tiers. With immediate AI processing, the low-priority tier is obsolete — there is no "read it
> eventually," only "process it now" or "never process it." Treat any surviving low-priority routing
> in the live rule sets as cruft to retire, not a pattern to copy.

## The craft: choosing the phrase (the heart of the skill)

The whole strategy turns on one skill: **never build a filter for a single sender's single message.**
If one company sent this type of mail, others will too, now and in the future. So the filter should
catch the **type**, across every sender — and the way it does that is by matching a **phrase**, chosen
with judgment.

### The two-sided test

A candidate phrase has to pass both sides at once:

- **Recurrence** — would this exact phrase plausibly appear in the *same type* of notification from
  **other** companies, or in future mail of this type? If it is specific to this one company, either
  pick a more generic fragment or pin the rule to that sender (see below).
- **Safety** — could this phrase **ever** appear in a message you *would* want to see — a human-written
  note, or a wanted transactional mail? Try to construct a plausible good-mail example that contains
  the phrase. If you can, the phrase is too broad.

When the two sides conflict, **tighten** — lengthen the fragment until the safety side passes. Erring
strict is deliberate: a too-narrow phrase that misses a variant costs you one more sibling phrase
later; a too-broad phrase buries real mail. This is why the real rule sets contain near-duplicate
phrasings — variants captured over time, rather than one phrase broadened past the safety line.

### The method, from a single junk sample

1. **Name the type, not the sender.** Ask "what *kind* of machine notification is this?" — delivery
   confirmation, policy-change announcement, receipt, one-time passcode, auto-reply, statement-ready.
2. **Find the intrinsic boilerplate.** Scan the subject and body for the words the *sending system*
   emits by template — the words that are there because a machine generated this notification, not
   because of this particular company. Prefer a distinctive multi-word fragment over a single common
   word.
3. **Run the two-sided test** on the candidate.
4. **Tighten until safe**, accept that variants may slip through, and plan to add sibling phrases as
   they surface.
5. **Pick the mechanism that fences it** for the platform (next section).

### Worked examples

The canonical lesson is the phrase that started this skill. A rule matching **`privacy policy`**
matched almost every message in the mailbox, because "Privacy Policy" sits in nearly every marketing
and transactional footer. The fix targets the boilerplate of the *announcement itself* — the words a
human never writes and only the notification carries:

| Junk type | ❌ Too broad — buries good mail | ✅ Calibrated — intrinsic system boilerplate |
| --- | --- | --- |
| Policy / terms change | `privacy policy` (every footer) | `updated our privacy` · `we're updating our` |
| Delivery | `delivered` (a person says it) | `Your shipment was delivered` · `out for delivery` |
| Receipts / orders | `receipt` · `order` | `Your … receipt` (subject shape) · `Thanks for your order` |
| Sign-in codes | `code` | `One Time Passcode` · `Code for signing in` · `verification code` |
| Calendar responses | `meeting` | `Accepted:` (subject-prefix convention) |
| Auto-replies | `out` | `Automatic reply:` · `I am out of the office` · `OOO Re:` |

The through-line: match the phrase the sending machine puts there by template, as a distinctive
fragment, scoped to where it is reliable.

## Platform mechanics — how each platform fences a broad match

Both platforms solve the same tension — broad enough to not need a filter per company, narrow enough
to never archive good mail — with different tools. Match the shape to whichever mailbox the junk hit.

### Gmail — one filter per pattern, scoped to the subject

Gmail's fence is **subject-scoping**. A Gmail filter matches a search query; scope the query to
`subject:(…)` so a phrase in a footer or quoted body can't trigger it. Reserve a body match
(`has the words`, i.e. an unscoped query) for a phrase so distinctive it could not appear anywhere you
care.

- **Type-level subject catch** (covers every sender of the type): `subject:(One Time Passcode)`,
  `subject:(Your shipment was delivered)`, `subject:(statement is available)`,
  `subject:(Automatic reply:)`.
- **Company-scoped combo** when the phrase isn't a universal type but the sender is a known noise
  source: `from:eventbrite subject:(Your event is published)`,
  `from:techcu subject:(Scheduled System Maintenance)`.
- **Action:** for pure noise, **Skip the Inbox (Archive it)** plus **Mark as read**. For mail you want
  archived but not marked read, just Skip the Inbox.
- **Multilingual variants** are their own siblings — the German, Dutch, French, and Spanish forms of an
  auto-reply or a delivery notice each get their own `subject:(…)` filter.

### Outlook — consolidated buckets fenced by a sender-domain exclusion whitelist

Outlook rules can hold many conditions and run top-to-bottom, which enables a richer shape:

- **Consolidated, numbered buckets.** Pack many subject phrases of the same kind into one rule rather
  than one rule per phrase (e.g. a single "Corporate Subjects" rule with dozens of subject strings).
  When a rule fills up, spill into the next-numbered sibling ("Corporate Subjects 2", "3", …). Adding a
  new junk phrase then means appending a string to the current bucket, not creating a new rule.
- **The sender-domain exclusion whitelist — the load-bearing safety mechanism.** Every broad
  subject-or-body bucket ends with *"…except when the sender's address contains:"* a list of
  **real-person and family/school domains** — `outlook.com`, `gmail.com`, `hotmail.com`, `yahoo.com`,
  `icloud.com`, `live.com`, `comcast.net`, `aol.com`, plus the family and school domains that matter to
  you. This is Outlook's equivalent of Gmail's subject-scoping: it lets the subject match be broad,
  because the domain fence guarantees the rule can **never** archive mail from a human's personal
  mailbox. Keep this exclusion list on every broad bucket.
- **Body matches pinned to a sender.** A body match is the dangerous kind, so in Outlook it is always
  fenced by an `AND from:<sender>` — e.g. body `You paid $` **and** from `service@paypal.com`. Pinning
  the body phrase to the one sender that emits it is the safest way to match on body text.
- **Sender-scoped subject buckets.** When the sender is pinned, the subject phrase can be looser —
  `from:discover.com` + subject `Activate 5%`, `from:amazon.com` + subject `Your Amazon.com order`.
- **Native message-type conditions.** Outlook can match *"the message is a Meeting Response"* or
  *"…Meeting Request"* directly — archive calendar accept/decline noise without matching any subject.
- **Positive keep-in-inbox overrides, placed first.** A short list of rules that force wanted mail to
  stay — a known human sender, a specific subject you always want to see — placed **above** the broad
  archive buckets and set to *stop processing more rules*, so an allow beats a later broad archive.
  **Ordering matters:** the allow rules and the most specific rules sit at the top; the broad buckets
  sit below them.
- **Homoglyph catch.** Spam that disguises words with lookalike Unicode letters gets a dedicated
  subject rule matching those confusable characters.

## Creating and deleting a filter

Both platforms are driven through the browser. Invoke the **browser-chauffeur** skill so the recovery
loop is active, complete its Phase 0 to get a validated CDP port, then run the automation against that
port.

### Gmail (filters)

The right Google account matters — verify it before mutating. `mail.google.com/mail/u/1/` and
`u/0/` are different accounts; read the active account label
(`a[aria-label*="Google Account"]`) and confirm it is the intended mailbox first.

- **Read all filters:** open `https://mail.google.com/mail/u/<n>/#settings/filters` and collect every
  filter row — each row's text carries its `Matches:` criteria and `Do this:` actions. (Selecting all
  filters and using Gmail's **Export** yields the same set as a `mailFilters` XML file.)
- **Create a filter:** click the **Advanced search options** control (its `aria-label` is
  "Advanced search options"; the visible tooltip "Show search options" is misleading). If the criteria
  form is already open the toggle is hidden — reload to reset. The criteria inputs are label-less; fill
  each by matching its row's visible label (From, To, Subject, Has the words, Doesn't have) to the
  input on the same row by vertical position, set the value, and dispatch `input`/`change` events.
  Click **Create filter**, then in the actions panel check **Skip the Inbox (Archive it)** and, for
  pure noise, **Mark as read**; click the blue **Create filter** to finalize and wait for the panel to
  detach.
- **Delete a filter:** the per-row `delete` link does not fire Gmail's handler through automation. What
  works: **check the filter row's checkbox, click the bottom "Delete" button, and confirm the dialog.**

### Outlook (rules)

Drive the OWA rules UI at `https://outlook.live.com/mail/0/options/mail/rules`. Reading every rule's
full detail benefits from clicking **Show all descriptions** first. To create or edit, use **Add rule**
(or a rule's **Edit**), where you can add multiple subject/body/sender conditions, the "except when the
sender's address contains" exclusion, and the move-to-Archive action.

The Graph endpoint `GET/POST /me/mailFolders/inbox/messageRules` can read and write rules
programmatically, but it requires the `MailboxSettings.ReadWrite` scope, which the personal-account
app registration does not currently grant — so the browser path is the reliable one until that scope
is added.

## Wiring the drainer

The drainer's per-provider `JUNK-LEARNING` step defers here for the breadth decision instead of
re-deriving it each time. When the drainer reaches the filter step for a piece of junk:

1. **Generalize on sight.** Run the phrase-selection method above on the single sample — name the type,
   find the intrinsic boilerplate, apply the two-sided test, tighten until safe. Propose the *type*
   phrase, not a filter for this one sender.
2. **Match the shape to the mailbox** — the Gmail subject-scoped form for a Gmail account, the Outlook
   consolidated-bucket-plus-exclusion form for an Outlook account.
3. **Propose, then create on Russell's OK.** A filter is reversible, searchable config, so once Russell
   approves the proposed phrase, create it via the mechanics above — no need to leave it as a manual
   to-do. (This is distinct from outward messages, which are always staged for Russell to send
   himself; a filter is inbound config he can undo.)
