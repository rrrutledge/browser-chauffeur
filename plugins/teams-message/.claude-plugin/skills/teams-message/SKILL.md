---
name: teams-message
description: Draft a Teams message via browser automation. Creates a draft in the correct chat but NEVER sends. Use browser-chauffeur to execute the steps in this spec.
---

# Teams Message Drafting

Draft a personalized message into a Microsoft Teams chat. The message is typed into the compose box but **NEVER sent** — it's left as a draft for review.

## How to execute this command

**Invoke the `browser-chauffeur` skill and have it drive the browser through the steps below.** There is no monolithic drafting script — browser-chauffeur navigates, reads the page, and types the message according to the spec in this file. Use a persistent Edge profile so the Teams login session is reused.

**On ad-hoc scripts during execution:** browser-chauffeur will naturally write small task-scoped Node/Playwright scripts as it works (search for person, type segment, insert link, etc.). That's expected and fine — the rule against scripts is about avoiding a single brittle monolith that has to anticipate every Teams UI quirk in advance. Keep those scripts in `.tmp/` and let them die with the session. The durable knowledge belongs in this spec (invariants, selectors, business rules).

## Input

You need:
- **Recipient name** (first + last, e.g., "Matthew Johnson")
- **Recipient email** (WellSky email, e.g., "matthew.johnson@wellsky.com")
- **Message content** — either:
  - Markdown with inline links: `[display text](URL)`
  - OR structured segments: `[{text: "Hi Matt!"}, {link: {display: "repo name", href: "URL"}}, ...]`

## Output

A draft message in the recipient's chat on Teams, visible in the compose box with a "Draft" badge. The message is NOT sent.

## Invariants (ALWAYS true — load-bearing, survives UI changes)

These are architectural truths about Teams web. Violating any of them is how a draft once got typed into the **wrong chat** (polluting a real conversation). Enforce ALL of them:

### 1. The composer is NOT unique
Teams keeps every recently-open chat's `div[data-tid="ckeditor"]` mounted in the DOM. Targeting "the" composer (e.g., `.first()`) + global keyboard typing can land your text in a **different chat's** compose box.

**Solution:** Always target the **`:visible`** composer (only the active chat's is visible) **AND bind every keystroke to that locator** (`compose.press(...)` / `compose.pressSequentially(...)`), never `page.keyboard.type`.

### 2. Identity-gate before AND during typing
Confirm the active chat's heading matches the person's first + last name **before the first keystroke**, and **re-assert before every segment**. Abort the moment it stops matching — never keep typing into a chat you can't confirm.

### 3. Content is ground truth
Declare success only by reading the composer back: expected key phrases present + expected link count + still-on-correct-chat. This makes selector drift fail *loudly* instead of corrupting silently.

### 4. Never press Enter in the composer
Enter sends the message. Soft breaks are **Shift+Enter**. (Enter inside the Ctrl+K link dialog is fine — that's the dialog, not the composer.)

### 5. Name tolerance
A person's formal name (`Matthew`) may differ from their Teams display name (`Matt`). Match on **last name + first-name prefix** (4+ chars), not exact first name.

### 6. Pick the loaded Teams tab
Browser-chauffeur can spawn multiple Teams tabs, including blank/loading ones. The script should select the Teams page with the **largest `document.body.innerText` length** (loaded app ≈ 9000+ chars), not just the first match.

## Selectors (last-known-good, Teams web 2026-06 — verify, expect drift)

Treat these as hints. If one stops matching, fall back to the structural rule in the invariant and **update this list**.

| Purpose | Selector | Notes |
|---------|----------|-------|
| New-chat people picker | `input#people-picker-input` or `input[aria-label="Enter name, chat, channel, email or tag"]` | ⚠️ Revealed ONLY after pressing `Alt+Shift+N` (new message). **Not** `AUTOSUGGEST_INPUT` — that is the global search bar at the top of the app, which lands in search results, not a 1:1 chat. |
| Global search bar (avoid for chat) | `input[data-tid="AUTOSUGGEST_INPUT"]` | Global app search — do NOT use this to open a 1:1 chat. Use `Alt+Shift+N` + people-picker instead. |
| Person result | `[role="option"]` | **Poll** until an option's `innerText` matches the recipient's last name. Default suggestions render first; clicking one before polling opens the wrong person. |
| Chat heading | `h1`, `h2`, or `h3` containing the name | ⚠️ `[data-tid="chat-header-title"]` does **not** exist in this build — use headings. |
| Composer | `div[data-tid="ckeditor"]:visible` | ⚠️ NOT unique without `:visible` — see invariant 1. |
| Link dialog inputs | `[data-tid="insertHyperlink-displayText"]`, `[data-tid="insertHyperlink-linkAddress"]` | ⚠️ `data-tid`, **not** `id`. Ctrl+K opens it; fill both. |
| Link dialog Insert button | `[data-tid="insertHyperlink-insertButton"]` | ⚠️ Use `data-tid`, NOT `role=button` with text "Insert" — that selector fails. |

## Steps (what browser-chauffeur should do)

### 1. Pick the correct Teams tab
From the CDP-connected browser context, select the Teams page with the **largest `document.body.innerText.length`** — this is the fully-loaded Teams app, not a blank/loading tab.

### 2. Search + open the 1:1 chat
- Call `page.bringToFront()`, click `body`, then press `Escape` to dismiss any open panels — this ensures keyboard events land on the right tab.
- Press `Alt+Shift+N` to open the new-message flow; wait ~1.5s.
- Click the **people-picker input** (`input#people-picker-input` or `input[aria-label="Enter name, chat, channel, email or tag"]`). ⚠️ This is NOT `AUTOSUGGEST_INPUT` — that's the global search bar and will route you to search results instead of opening a 1:1 chat.
- Type the recipient's **email** (most reliable search key).
- **Poll** `[role="option"]` until an option's `innerText` includes the recipient's **last name**.
  - Default suggestions render first; acting on them opens the wrong person.
  - Timeout after 15s if no match → exit with error code 2 (person not found).
- Click the matching person option; press Enter; wait ~2.5s for the chat to render.

### 3. Identity gate (hard check before typing)
- Read all headings: `[data-tid="chat-header-title"], h1, h2, h3`
- Verify at least one heading contains the recipient's **last name** AND **first name (or 4+ char prefix)**
- If no match → take screenshot, exit with error code 2 (identity gate failed, skip this person)

### 4. Target the visible composer
- Locate `div[data-tid="ckeditor"]:visible` (only the active chat's is visible)
- Click it, clear it (Ctrl+A, Delete)
- Sleep ~300ms

### 5. Type the message segments
Walk the message segments in order. Before each segment:
- **Re-assert identity**: verify the chat heading still matches the recipient
- If mismatch → screenshot, exit with error code 3 (active chat changed mid-typing)

For each segment:
- **Text segment** (`{text: "..."}` or markdown paragraph):
  - Split on `\n`
  - For each line: type via `compose.pressSequentially(line, {delay: 8})`
  - Between lines: `compose.press('Shift+Enter')` (NOT Enter — Enter sends!)
- **Link segment** (`{link: {display, href}}` or markdown `[text](url)`):
  - Press Ctrl+K to open link dialog
  - Wait for `[data-tid="insertHyperlink-displayText"]` to be visible
  - Fill display text: `dispInput.fill(display)`
  - Fill URL: `addrInput.fill(href)`
  - Sleep ~200ms
  - Click Insert button: `[data-tid="insertHyperlink-insertButton"]` (⚠️ NOT role=button/text — that fails)
  - Sleep ~900ms (link chip mount / unfurl)

After all segments, sleep ~2.5s (for repo card unfurl + autosave debounce if applicable).

### 6. Verify from composer content (ground truth)
- Read composer text: `compose.innerText()`
- Count links: `compose.locator('a').count()`
- Check expected phrases are present (caller defines these)
- Check expected link count matches
- Re-verify identity: still on correct chat

If all checks pass → screenshot, exit 0 (success).  
If any check fails → screenshot, exit 1 (verification failed).

## Safety rails (mandatory)

1. **Never send.** Only Shift+Enter (soft breaks) and Ctrl+K (links) in the composer. Enter is never pressed.
2. **Identity guard.** Draft only after the chat heading matches the recipient's first + last name; otherwise skip and report.
3. **Drafts are session-bound.** They live in the browser session — send them before signing out / clearing the session.

## Exit codes (for scripts created by browser-chauffeur)

- **0** — ✅ Verification passed, draft staged
- **1** — ❌ Verification FAILED (staged but content check failed — e.g., link flaked, wrong text)
- **2** — Person not found in search, OR identity gate failed (skip this person, flag for manual)
- **3** — Active chat changed mid-typing (focus stolen by pane/modal — close it, re-run)

## Recovery guidance

When browser-chauffeur detects an error:

- **Exit 2 (person not found / identity gate)** — check the screenshot; the person may not be in Teams, or the display name differs more than the prefix allows. **Skip + flag for manual handling.**
- **Exit 3 (chat changed mid-typing)** — focus was stolen by a Copilot pane or modal. The wrong chat's composer is untouched (keys are locator-bound). Close the intruding pane, re-run.
- **Exit 1 (verification failed)** — staged but incomplete (e.g., a Ctrl+K link flaked, <expected links). Check the screenshot; clear that chat's compose box and re-run.

## Teams UI quirks (observed 2026-06)

- **Search delay:** Person results don't appear instantly — poll with ~500ms sleep, timeout at 15s.
- **Name mismatch:** Formal name ("Matthew") may differ from Teams display ("Matt") — match last name + first-name prefix.
- **Multi-tab:** Teams tabs can be blank/loading (BODYLEN ~0–100) — pick the one with largest body text.
- **Drafts persist** per conversation (Teams shows a "Draft" badge) but only within the live browser session — send before signing out.

## Example invocation

```
/browser-chauffeur execute the teams-message skill to draft a message to:
- Name: Matthew Johnson
- Email: matthew.johnson@wellsky.com
- Message: Hi Matt! I saw you created this repo: [mediwareinc/test-repo](https://github.com/mediwareinc/test-repo)

Would you be willing to delete it and [create it again](https://skystage.wellsky.cloud/github-repo-creation) through SkyStage? See the [docs](https://wellsky.atlassian.net/wiki/...) for details.
```

Browser-chauffeur will create ad-hoc scripts in `.tmp/` to execute the steps, parse markdown links into segments, type the message following all invariants, verify content, and report success or failure.
