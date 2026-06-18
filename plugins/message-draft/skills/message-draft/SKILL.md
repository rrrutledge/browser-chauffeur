---
name: message-draft
description: Draft a message and NEVER send it. Two modes — `teams` (a Teams chat, staged in the web composer via browser-chauffeur) and `outlook` (a work-email reply or new email, created as an Outlook draft via the `ms-rest` skill's REST API). Use whenever staging a Teams chat message or a work Outlook email for human review. (Supersedes teams-message; `slack` mode is future.)
---

# message-draft

Stage a **draft** and stop — a human reviews and sends. Pick a mode:

- **`teams`** — a 1:1 or group Teams chat, staged in the web composer (you drive **browser-chauffeur**,
  never Playwright directly).
- **`outlook`** — a work-email reply or new email, created as an Outlook **draft** via the **`ms-rest`**
  skill's REST API (no browser composer). `ms-rest` is the WORK-account Outlook plugin; don't
  confuse it with the personal `ms-graph` skill.
- **`slack`** — future; not implemented.

**Voice:** Before composing any message, invoke the **`document-authoring`** skill to write the
content in Russell's voice. Pass the drafted text to the mode steps below for staging.

**Voice gate (stage-time — load-bearing):** After the draft is staged, read it back from where it
lives (Teams: the composer; Outlook: `ms-rest get <draftId>`) and re-apply the **`document-authoring`**
Conversational writing rules as a review pass. If anything was trimmed, re-stage the gated version
(Teams: re-type it; Outlook: re-create the draft from the gated body). Report `voice-gate=passed` in
the done-criteria once it has run.

## Behavioral preferences

- **Prefer replying to an existing thread over composing a fresh message.** When a relevant thread
  exists, draft a reply on it rather than a new email; only compose new when there's genuinely no
  thread to reply to.

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
   Call `page.bringToFront()` and click `body` to ensure keyboard events land on this tab.
1. **Find the target.**
   - **1:1:** Press `Alt+Shift+N` (new message), wait ~1.5s, then click the **people-picker input**
     (`input#people-picker-input` or `input[aria-label="Enter name, chat, channel, email or tag"]`).
     ⚠️ Do NOT use `input[data-tid="AUTOSUGGEST_INPUT"]` — that is the global search bar at the
     top of the app and routes to search results, not a 1:1 chat composer. Type the recipient's
     **email** (most precise), then **poll** `[role="option"]` until an option's `innerText`
     includes the recipient's **last name** before clicking — default suggestions render first and
     open the wrong person. Name tolerance: display name may differ (`Matt` vs `Matthew`) — match
     last name + first-name prefix.
   - **Group/meeting:** Use the global search bar (`input[data-tid="AUTOSUGGEST_INPUT"]`), type the
     chat name or a distinctive substring, and poll for a chat/group option whose text contains it.
2. **Identity-gate.** Confirm the chat heading (an `h1`/`h2`/`h3` containing the name —
   `[data-tid="chat-header-title"]` does NOT exist in this build) matches before typing. 1:1: last
   name + first-name prefix; group/meeting: a case-insensitive substring of the chat name.
3. **Compose.** Target `div[data-tid="ckeditor"]:visible`. Type the body with `pressSequentially`;
   line breaks via **Shift+Enter**.
4. **Hyperlinks.** Ctrl+K opens an Insert-link dialog; fill `[data-tid="insertHyperlink-displayText"]`
   and `[data-tid="insertHyperlink-linkAddress"]` (⚠️ `data-tid`, not `id`), then click
   `[data-tid="insertHyperlink-insertButton"]` (⚠️ NOT `role=button` with text "Insert" — that
   selector fails). A typed GitHub repo URL also auto-unfurls a card.
5. **@mentions (when asked).** Type `@` then the first few chars of the name, **poll for the
   mention autocomplete dropdown, and click the matching suggestion** so a real mention chip mounts.
   Typing `@Name` as plain text does NOT notify the person — the chip must come from the dropdown.
6. **Leave as draft.** Do NOT press Enter / click Send. Teams shows a **Draft** badge per
   conversation (persists within the live browser session). Verify content, then stop.

## Mode: `outlook`

Creates an Outlook **draft** for the WORK account via the **`ms-rest`** skill's REST API — no browser
composer. The draft lands un-sent in **Drafts** (reviewable on web and mobile) with clickable links;
for a reply, the quoted original sits below the new text. This skill never sends — `ms-rest send-draft`
is gated separately and reserved for Russell's explicit OK.

Two shapes:
- **Reply** to an existing message — needs that message's Outlook REST `id`.
- **New email** — needs subject + recipients.

Run from the repo root: `node .claude/skills/ms-rest/outlook-mail.js <verb>`.

1. **Auth-glance.** `node .claude/skills/ms-rest/outlook-mail.js token`. `Token OK ✅` → ready. If it
   reports no token, follow `ms-rest` AUTH-GLANCE (sign in to Outlook web in the CDP browser once),
   then retry. Never surface a token error — fix it and continue.
2. **Resolve the target (reply only).** If you were handed the source `messageId` (e.g. from the
   channel-watch CAPTURE record), use it. Otherwise locate the message with
   `outlook-mail.js enumerate` (and `get <id>` to confirm), and **identity-gate**: the message's
   sender + subject must match the intended target. Abort on mismatch.
3. **Write the body to a file.** Author the body in Russell's voice (the **Voice** step above), as
   **HTML** with real `<a href="URL">anchor text</a>` links (never a bare URL in prose). Write it to
   a temp file, e.g. `.tmp/outlook-draft.json`:
   - Reply: `{ "comment": "<p>…new reply text…</p>" }`
   - New email: `{ "subject": "…", "body": "<p>…</p>", "to": ["a@b.com"], "cc": [] }`
4. **Create the draft.**
   - Reply: `node .claude/skills/ms-rest/outlook-mail.js create-reply <messageId> --json .tmp/outlook-draft.json`
   - New: `node .claude/skills/ms-rest/outlook-mail.js create-draft --json .tmp/outlook-draft.json`
   It prints `{ draftId, webLink, folder:"Drafts", sent:false }`.
5. **Voice gate + read-back.** `node .claude/skills/ms-rest/outlook-mail.js get <draftId>` and confirm
   the body reads back correctly (greeting + body + clickable links; for a reply, the quoted original
   below the new text). Re-apply the `document-authoring` Conversational rules; if anything was
   trimmed, rewrite the body file and re-run step 4 (the new draft supersedes the old — delete the
   stale one with `delete <draftId>` if needed).
6. **Leave as draft.** Never send. Report where the draft lives (Drafts; `webLink` is the deep link).

## Done-criteria (report this back)

`mode=<teams|outlook> recipient=<who> drafted=true sent=false voice-gate=passed links=<n>` plus a
one-line note of where the draft lives (Outlook: the `webLink`/draftId). If identity-gate failed or
sign-in was needed, say so and that nothing was staged.
