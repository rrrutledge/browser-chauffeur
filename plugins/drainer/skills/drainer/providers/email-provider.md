# email-provider — shared logic for all email providers

All email providers (gmail, outlook-graph, outlook-rest) inherit these rules. Each provider's own
file covers only the provider-specific bits: CONFIG, AUTH-GLANCE, SITUATIONAL-CHECK mechanism,
CLEAR, JUNK-LEARNING step 3, and DRAFT-MODE CLI commands. Everything here applies as-is.

---

## CAPTURE shape (shared convention)

Every email provider writes two files per dispatched item:
- `items/<id>.email.md` — header block (From, Received, Link, MessageId) + full body text.
- `items/<id>.json` — `{ "id","source","triage","kind","from","subject","received","snippet","url",`
  `"messageId","emailFile","ts" }`.

`messageId` is the **load-bearing field** — the worker needs it for the reply draft and for CLEAR.
Its exact format varies by provider (RFC822 Message-ID for Gmail; opaque API id for Graph/REST), but
the field name is always `messageId` and it is always present.

---

## SITUATIONAL-CHECK (do this BEFORE drafting any reply)

The captured item is the inbound message at capture time; the conversation may have moved since.

1. **Read the full thread** using your provider's thread-fetch mechanism (see your provider file).
   Cover both directions — messages FROM the contact AND the user's own sent replies. Paginate fully;
   don't stop at the first page.
2. **If the user's most recent message on the thread is already a reply to this sender** → the item is
   done. Close it without a new draft.
3. **Check for an existing draft** using your provider's draft-list command, to avoid staging a
   duplicate if a prior session already started one.

---

## DRAFT-MODE (shared rules — CLI commands are in your provider file)

### Voice gate (mandatory — do this before writing a single word)

Invoke the `document-authoring` skill (call the Skill tool to load it) and read its **Conversational
writing** + **"Never do these"** sections. Compose the draft against what you just read — do not
write from memory. This is a gate: it happens before drafting, not as an after-the-fact check. A
draft written from memory reliably leaks the tokens those rules ban.

### After composing

- The voice loop still applies: after the user sends, diff sent-vs-draft and append a concrete lesson
  to the document-authoring skill's Voice learning loop.
- Write the body as an HTML file, then create the draft via your provider's CLI — **never sent** from
  inside the worker. Show the draft text in the terminal so the user can review it.
- The user edits + sends themselves. Never auto-send; sending is gated behind an explicit OK in the
  top-level interactive session.

### Reply vs fresh note

Pick the mode by who the message goes to:

- **Reply-all on the thread** (responding to inbound mail): use your provider's `--reply` command.
  Always reply-all (not plain reply) to preserve every original To+CC recipient. Include the quoted
  original below the new text. Thread off the **most recent message in the thread** — pass *its*
  `messageId`, even if that last message is one the user sent — so the reply lands where the
  conversation actually stands.
- **Fresh 1:1 (or small-group) note** (e.g. an outreach nudge to a single contact — do NOT reply-all
  a group thread to single someone out): use your provider's `--draft-new` / create-draft command
  with explicit To/Subject/CC.

---

## JUNK-LEARNING (shared priority order)

Stop this junk arriving again — propose, never apply without the user's OK. Work top-down; only fall
through when the step above isn't available:

1. **Unsubscribe** — if the message carries an unsubscribe link (`List-Unsubscribe` header or a
   footer link), propose using it. This is the cleanest stop.
2. **Turn it off at the source app** — if there's no unsubscribe but the sender is an app whose
   notifications the user controls (GitHub notification settings, LinkedIn email preferences, …),
   propose adjusting that app's settings so the email is never sent.
3. **Provider-specific filter/rule** — only when neither above applies. Defer to the **`mail-filters`**
   skill for the breadth decision: it owns the phrase-selection craft (generalize from this one sample
   to the type-level boilerplate phrase — broad enough to recur across senders, strict enough to never
   bury wanted mail) and the per-platform create/delete mechanics. Propose the *type* phrase, not a
   filter for this one sender; match the shape to the mailbox (Gmail subject-scoped vs Outlook
   consolidated bucket); and once Russell OKs the phrase, create the filter (it is reversible,
   searchable config). See your provider file for the platform pointer.
