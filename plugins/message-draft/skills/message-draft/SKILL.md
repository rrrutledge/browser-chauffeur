---
name: message-draft
description: Draft a message in the active web composer and NEVER send it. Two modes — `teams` (a Teams chat) and `outlook` (an Outlook-web email reply). Browser-chauffeur executes these steps; this skill is the spec. Use whenever staging a Teams chat message or an Outlook email reply for human review. (Supersedes teams-message; `slack` mode is future.)
---

# message-draft

Stage a **draft** in the correct conversation and stop — a human reviews and sends. You drive
through the **browser-chauffeur** skill (never Playwright directly). Pick a mode:

**Voice:** Before composing any message, invoke the **`document-authoring`** skill to write the
content in Russell's voice. Pass the drafted text to the mode steps below for staging.

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
   ⚠️ **Near-duplicate names are real** — there can be several chats with almost the same title
   (seen live: two `SkyStage and H&P` group chats **and** a `H&P and SkyStage`). The title alone is
   NOT enough: gate on the **exact** title (anchor the regex so `SkyStage and H&P` ≠ `H&P and
   SkyStage`) **plus** a second signal unique to the right thread — an expected participant name or
   a known recent message in the conversation body. This gate has correctly blocked wrong-chat sends.
3. **Content is ground truth — read the editable child, not the wrapper.** After typing, verify the
   expected greeting + body (+ links). ⚠️ Reading `div[data-tid="ckeditor"].innerText` can falsely
   return **empty** even when text is present (it lives in a child) — read the inner
   `[contenteditable="true"]` (take the longest `innerText` among composer descendants). For the
   same reason, **a cleared composer is NOT a reliable "sent" confirmation** — confirm a send by
   finding the posted **message bubble** in the thread, not by the composer reading empty.
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
   ⚠️ **Work in the already-loaded tab; avoid `goto`-ing the Teams root** — a full navigation forces
   a slow reload ("We're setting things up…") and is the main source of flakiness. Reuse the open
   tab. Target the global search by the stable `input[data-tid="AUTOSUGGEST_INPUT"]` — its
   **placeholder text changes on focus** (`Search…` → `Press Ctrl+Alt+G…`), so never match on
   placeholder. Insert search text via CDP `Input.insertText` (it lands as the value), but the
   suggestion list only fires after a **real keystroke** — follow with one dispatched key (e.g. a
   space then backspace) to trigger results.
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
4. **Hyperlinks — anchor the URL onto descriptive text already in the message; never leave a bare
   URL in prose** (per `document-authoring`). The robust way is **type-then-select-then-link**, NOT
   type-link-then-keep-typing:
   1. Type the **full plain message** first (the link phrases as ordinary text, e.g. `consolo.emr #4864`).
   2. For each phrase to link, with the composer focused, **programmatically select exactly that text**:
      walk the visible `div[data-tid="ckeditor"]`'s `[contenteditable="true"]` text nodes, build a
      DOM `Range` over the substring, and `window.getSelection().removeAllRanges()/addRange(range)`.
      Skip text nodes already inside an `<a>` so it's **idempotent** (re-run safely; re-query after
      each insert because the DOM splits).
   3. Press **Ctrl+K** — the dialog pre-fills `[data-tid="insertHyperlink-displayText"]` from the
      selection. Set `[data-tid="insertHyperlink-linkAddress"]` (⚠️ `data-tid`, not `id`) and click
      `[data-tid="insertHyperlink-insertButton"]` (⚠️ NOT `role=button` text "Insert" — that fails).
   ⚠️ **Do NOT** insert a link then continue typing at the caret — the following text **bleeds into
   the anchor** (the whole rest of the message becomes part of the link). Selecting a bounded range
   first avoids this entirely. Verify at the end: each `<a>`'s `innerText` is just its phrase
   (short), and the link count matches.
   Note: a **bare** GitHub URL auto-unfurls a preview card; an anchored phrase usually does not
   (cleaner). If an unfurl card appears anyway, it's harmless — Russell can ✕ it.
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
