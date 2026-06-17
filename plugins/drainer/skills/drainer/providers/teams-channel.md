# teams provider — Microsoft Teams on the web (browser)

A provider for Microsoft Teams on the web (`https://teams.microsoft.com/`) — you sign in as yourself,
no tenant baked in. No config. Implements `../engine/channel-provider.md`; classify by
`../engine/triage.md`. Use the **browser-chauffeur** skill for all browser work. id prefix: `teams-`;
body file: `<id>.msg.md`.

## Teams footguns (IRREVERSIBLE — never violate)
- **Enter SENDS** in a Teams composer. Triage/capture only READ — never type into a composer here.
  All composing happens later in the worker via the `message-draft` skill (`teams` mode), which owns
  the footguns (identity-gate the chat, target the visible composer, Shift+Enter for newlines, never
  press a bare Enter).
- **Heavy iframes:** keep to ONE browser-driving context; don't open many tabs.

## AUTH-GLANCE
Open `https://teams.microsoft.com/`. Decide ONLY: SIGNED IN (chat/activity list visible) or NOT (a
Microsoft/SSO sign-in, "Pick an account", or password screen). If NOT signed in, surface a sign-in
prompt to the user (leave the tab open) and stop reading Teams until they confirm.

## ENUMERATE
Click the **Unread** filter, then list unread DMs (1:1), group chats, and channels you're a member of
— most-recent-activity first. Some builds show conversation NAMES ONLY (no previews in the rail), so
you may have to OPEN each unread to read it (opening MARKS IT READ — accepted). Click the EXACT
conversation row, **anchored on its name** (rail groups nest child names, so a loose substring match
hits the parent; match `^<name>$`). Identity-confirm the open chat (header name matches the row).
Build a stable id: `teams-<YYYYMMDD-HHMM of latest msg>-<sender-or-chat-slug>-<first-3-msg-words-slug>`
(lowercase, non-alphanumerics → single dashes; ≤52 chars).

## MEETING RECORDING MESSAGES
A meeting-recording notification (recording/transcript link or "Meeting ended" summary) is a
container — see `../engine/triage.md § Containers that hold action items`. Open the meeting's AI notes
and look for action items assigned to **you**; each one becomes its own needs-you item (capture
separately, `whatsAsked` = the action item text). If AI notes exist but none are yours, it's fyi. If
no AI notes exist, the notification is fyi.

## CAPTURE (needs-you)
- **Deep link** (see below) — the real per-message/chat link as `url`.
- Write `items/<id>.msg.md` — header block (Chat/From, Type [dm|group|channel], Latest, Link) + the
  recent messages.
- Write `items/<id>.json`:
  `{ "id","channel":"teams","triage":"needs-you","kind":"reply|work|work-then-reply","from":"<person`
  `or chat name>","chatType":"dm|group|channel","received","snippet","whatsAsked":"<1-2 lines>",`
  `"url":"<deep link>","msgFile":"<abs path to .msg.md>","ts":"<ISO now>" }`

### Deep-link capture (real link, graceful fallback)
Build `url` from the open conversation, best-effort, in order:
1. **Message link** —
   `https://teams.microsoft.com/l/message/<chatId>/<messageId>?context=%7B%22contextType%22%3A%22chat%22%7D`
   - `chatId`: the selected conversation's DOM node `[id^="chat-list-item_"]` → strip the
     `chat-list-item_` prefix (e.g. `19:...@thread.v2`).
   - `messageId`: the latest message node's id — try `data-mid`, then `data-message-id`, then a
     numeric id on the message container (ms-epoch). Best-effort.
2. **Chat link** (no messageId) — `https://teams.microsoft.com/l/chat/<chatId>/conversations`.
3. **Base URL** fallback — `https://teams.microsoft.com/`.
Selectors are last-known-good (Teams web, 2026-06) — expect drift; if they don't resolve, screenshot
→ inspect the live DOM to rediscover the id-bearing node, then fall back down the chain. A "Copy link"
item in a message's `…` overflow menu is an alternate source if the DOM ids move.

## CLEAR
MARK the conversation READ in the browser (Teams has no delete/trash; mark-read is the "gone," and
reversible — just narrate it). Opening it in triage already marks it read.

## JUNK-LEARNING
None. Teams junk is just cleared (marked read) — you manage your own Teams mutes; don't propose mutes
or rules.

## DRAFT-MODE
`message-draft` skill, `teams` mode.

## WORKER-PROMPT
`teams-worker-prompt.txt`.
