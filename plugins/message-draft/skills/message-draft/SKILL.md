---
name: message-draft
description: Draft a message in the active web composer and NEVER send it. Two modes — `teams` (a Teams chat) and `outlook` (an Outlook-web email reply). Browser-chauffeur executes these steps; this skill is the spec. Use whenever staging a Teams chat message or an Outlook email reply for human review. (Supersedes teams-message; `slack` mode is future.)
---

# message-draft

Stage a **draft** in the correct conversation and stop — a human reviews and sends. You drive
through the **browser-chauffeur** skill (never Playwright directly). Pick a mode:

- **`teams`** — a 1:1 or group Teams chat, addressed by person name/email.
- **`outlook`** — a reply to a specific Outlook-web email.
- **`slack`** — future; not implemented.

## Load-bearing invariants (apply to ALL modes — violating these has typed into the WRONG place)

1. **The composer is not unique — target the `:visible` one and bind every keystroke to it.**
   Web apps keep many editors mounted (Teams keeps every recent chat's `div[data-tid="ckeditor"]`
   in the DOM). Resolve the **visible** composer locator and send keystrokes via
   `compose.press(...)` / `compose.pressSequentially(...)` — never global `page.keyboard.type`,
   or text leaks into another conversation.
2. **Identity-gate before AND during typing.** Confirm the active conversation header matches the
   intended recipient (Teams: first+last name; Outlook: the expected sender/subject) BEFORE the
   first keystroke, and re-assert before each segment. Abort on mismatch.
3. **Content is ground truth.** After typing, read the composer back and verify the expected
   greeting + body (+ links) are present. Let selector drift fail loudly, not silently.
4. **Never press Enter in the composer — it sends.** Use **Shift+Enter** for line breaks.
   (Enter is fine inside a link-insert dialog.)
5. **Selectors below are last-known-good (web UIs, 2026-06) — expect drift.** The invariants
   don't drift; rediscover selectors live via browser-chauffeur (screenshot → inspect) when they do.

## Mode: `teams`

Addresses either a **1:1 chat** (recipient name + email) or a **group/meeting chat** (chat name).
Inputs: the address, message body, optional hyperlinks (display text + URL), optional @mentions.

0. **Pick the loaded Teams tab.** Select the Teams page with the **largest
   `document.body.innerText` length** (a loaded app ≈ 9000+ chars; blank/loading tabs are ~0–100).
1. **Find the target.** Search box `input[data-tid="AUTOSUGGEST_INPUT"]` (clear first: Ctrl+A,
   Delete). **1:1** — type the email (most precise), then **poll the results** until an option's
   text matches the recipient name before clicking (default suggestions render first → wrong
   person): `[role="option"][data-tid^="AUTOSUGGEST_SUGGESTION_TOPHITS8:orgid:"]` or `…PEOPLE8:orgid:`.
   Name tolerance: display name may differ from the formal name (e.g. `Matt` vs `Matthew`) — match
   last name + first-name prefix. **Group/meeting** — type the chat name (or a distinctive
   substring) and poll for a chat/group option whose text contains it.
2. **Identity-gate.** Confirm the chat heading (an `h1`/`h2`/`h3` containing the name —
   `[data-tid="chat-header-title"]` does NOT exist in this build) matches before typing. 1:1: last
   name + first-name prefix; group/meeting: a case-insensitive substring of the chat name.
3. **Compose.** Target `div[data-tid="ckeditor"]:visible`. Type the body with `pressSequentially`;
   line breaks via **Shift+Enter**.
4. **Hyperlinks.** Ctrl+K opens an Insert-link dialog; fill `[data-tid="insertHyperlink-displayText"]`
   and `[data-tid="insertHyperlink-linkAddress"]` (⚠️ `data-tid`, not `id`), then its `Insert`
   button. A typed GitHub repo URL also auto-unfurls a card.
5. **@mentions (when asked).** Type `@` then the first few chars of the name, **poll for the
   mention autocomplete dropdown, and click the matching suggestion** so a real mention chip mounts.
   Typing `@Name` as plain text does NOT notify the person — the chip must come from the dropdown.
6. **Leave as draft.** Do NOT press Enter / click Send. Teams shows a **Draft** badge per
   conversation (persists within the live browser session). Verify content, then stop.

## Mode: `outlook`

Inputs: the target message (deep link or enough to locate it in the mailbox), reply body,
reply-all vs reply (default: **Reply**, sender only), optional hyperlinks.

1. **Open the message.** Navigate to its deep link if given, else open
   `https://outlook.office.com/mail/` and open the message from the list. Confirm signed in
   (mailbox visible) — if a Microsoft/Okta sign-in shows, report auth-needed and stop.
2. **Identity-gate.** Confirm the open message's sender + subject match the intended target
   before composing. Abort on mismatch.
3. **Start the reply.** Click **Reply** (or Reply all if asked). This opens the reply composer
   — typically an inline editor at the bottom of the reading pane (a `div[role="textbox"]`
   / `[contenteditable="true"]` reply body; the Reply button often carries
   `aria-label="Reply"` or sits in the message toolbar). Rediscover live if these drift.
4. **Compose.** Target the **visible** reply textbox; type the body with `pressSequentially`;
   line breaks via Enter are fine in the Outlook body (Outlook does NOT send on Enter — Send is
   Ctrl+Enter or the Send button). To be safe, never press **Ctrl+Enter** and never click
   **Send**.
5. **Hyperlinks.** Use the composer's Insert-link control (toolbar link button or Ctrl+K),
   filling display text + address, for clean anchor text.
6. **Leave as draft.** Outlook **auto-saves** the reply to the Drafts folder. Do NOT click Send.
   Verify the draft body reads back correctly (greeting + body + links), then stop and report
   where the draft is (it appears in Drafts and inline under the original thread).

## Done-criteria (report this back)

`mode=<teams|outlook> recipient=<who> drafted=true sent=false links=<n>` plus a one-line note of
where the draft lives. If identity-gate failed or sign-in was needed, say so and that nothing was typed.
