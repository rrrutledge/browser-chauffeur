# outlook provider — Outlook on the web (browser)

A **shared** provider: works for any Outlook-on-the-web mailbox (`https://outlook.office.com/mail/`)
— personal or work — because there's no tenant/domain baked in; you just sign in as yourself. No
config. Implements `../engine/channel-provider.md`; classify by `../engine/triage.md` (this file is
only the mechanics). Use the **browser-chauffeur** skill for all browser work. id prefix: `outlook-`;
body file: `<id>.email.md`.

## AUTH-GLANCE
Open `https://outlook.office.com/mail/`. Decide ONLY: SIGNED IN (mailbox + message list visible) or
NOT (a Microsoft/SSO sign-in, "Pick an account", or password screen). If NOT signed in, surface a
sign-in prompt to the user (leave the tab open) and stop reading mail until they confirm.

## ENUMERATE
Work from the inbox LIST view (do NOT open messages). Each row shows sender, subject, a preview line,
and time — enough to triage. Consider the most recent ~30 messages, READ OR UNREAD (an already-read
mail can still be an unhandled action); scroll as needed. Build a stable id:
`outlook-<YYYYMMDD-HHMM of received>-<sender-slug>-<first-3-subject-words-slug>` (lowercase,
non-alphanumerics → single dashes; ≤48 chars). Triage from the row alone; only if a row is genuinely
undecidable may you open that ONE message to disambiguate (never open more than 2 per pass).

## CAPTURE (needs-you)
Open the ONE message (only because it's needs-you) and capture it:
- **Deep link** = the open message's browser address (its Outlook deep link), else
  `https://outlook.office.com/mail/`.
- Write `items/<id>.email.md` — header block (From, To, Cc, Date, Subject, Link) + the full body.
- Write `items/<id>.json`:
  `{ "id","channel":"outlook","triage":"needs-you","kind":"reply|work|work-then-reply","from",`
  `"subject","received","snippet","whatsAsked":"<1-2 lines>","url":"<deep link>",`
  `"emailFile":"<abs path to .email.md>","ts":"<ISO now>" }`

## CLEAR
DELETE the email (Outlook → Deleted Items; reversible — just narrate it). This is the email "gone."

## JUNK-LEARNING
Propose an **Outlook rule** (a sender/subject/body match that files or deletes the sender going
forward) so this junk stops arriving — the goal is to spend tokens/attention only on what matters.
Propose, never apply without the user's OK.

## DRAFT-MODE
`message-draft` skill, `outlook` mode.

## WORKER-PROMPT
`outlook-worker-prompt.txt`.
