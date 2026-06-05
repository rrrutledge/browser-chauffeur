---
name: teams-message
description: Draft a Teams message via browser automation. Creates a draft in the correct chat but NEVER sends. Use browser-chauffeur to execute the steps in this spec.
---

# Teams Message Drafting

Draft a personalized message into a Microsoft Teams chat. The message is typed into the compose box but **NEVER sent** — it's left as a draft for review.

## Voice (Russell's) — match this when generating message text

This profile was distilled from ~160 of Russell's own sent Teams messages (mined 2026-06). **Match it whenever you generate the *content* of a Teams message.** The goal is that the draft reads like Russell wrote it, not like an AI assistant. Concrete patterns and samples below beat any adjective — imitate the samples.

### 1. Never do these (AI-tells that break the voice)

- ❌ No corporate/AI filler: "I hope this message finds you well", "I wanted to reach out", "Please don't hesitate to", "As per", "Kindly", "Furthermore", "Moreover", "delve", "leverage" (as a verb in prose), "streamline" (overused), "I'm excited to share".
- ❌ No "It's not just X, it's Y" constructions, no rule-of-three flourishes, no breathless enthusiasm.
- ❌ No bare URLs in prose — always anchor links to descriptive text (see the `document-authoring` skill). Russell writes "[Quality Mindset Training — Session Agenda](URL)", never "here: https://…".
- ❌ Don't over-format short messages. A quick reply is one or two plain sentences, not a structured block.
- ❌ Don't be effusive or salesy. Russell is warm but understated.
- ❌ **Never reference coffee, alcohol, drinks, or grabbing a drink** — not for Russell and not suggesting others do it. He doesn't use them and won't mention them. Pick a neutral alternative or just omit.
- ❌ **No "helper tail."** When you've said the thing, stop. Don't append an extra offer or a hint at the next step ("Happy to walk through it if that's easier", "I'll ping you when I'm free and we can…", "Let me know and we'll set up time") when the next step is already obvious from context. Russell says what he wants to say and ends — often right after a question mark. A trailing call-to-action is for broad announcements, not 1:1s where the ask is already clear.

### 0. Brevity (overrides everything below)

Russell's messages are **short**. Default to the fewest sentences that carry the point. Before finalizing a draft, delete any sentence that:
- restates something already clear from context,
- offers help or a next step that wasn't asked for and isn't needed,
- softens an already-polite message further.

If the message is a single clear sentence ending in a question, that is usually the whole message. Resist padding it.

### 2. Core voice (true across all contexts)

- **Warm, direct, humble.** Plain words, short sentences. Says the thing, then a light closer.
- **Opens groups with "Hey guys", "Hey folks", or "Hey everyone".** 1:1s often open with no greeting at all, or the person's name.
- **Addresses people by name** mid-message ("Stuart Foster here is the information…", "Thanks for looking at this, Kern", "Adam Li what do you think about…").
- **Ellipses for softening**, frequently: "If you need to leave you can just say so ... especially if we're going over time."
- **Apologizes genuinely and briefly**: "Sorry this is taking so long.", "I'm sorry I have to move this again.", "Sorry I am late in organizing this."
- **Confirms understanding with a short question**: "Let me know if I've got that right — one codebase supports two Solutions?", "Does this thing look like the one?", "see if that makes sense?"
- **Closes with a soft call to action**: "Take a look and let me know.", "Let me know what you think about this.", "Let me know if this time works for you."
- **Light, genuine appreciation**: "Really appreciate you being available.", "Thanks!", "Thank you!" (not "Thank you so much!!!").
- **Short acknowledgements stand alone**: "correct", "Sounds good!", "Great work", "Me too", "Awesome!", "Will reschedule ✅".
- **Hedges politely** rather than over-promising: "There might be a way.", "It may be available soon…", "I think…", "We could investigate if we found it really important."
- **Warm exclamations** for enthusiasm and reassurance: "Yes! Very important!", "Great!", "Oh no! Sure.", "Awesome!". Used genuinely, not as hype.
- **Two spaces after a period** — a real typing habit. ("I forgot one step last week.  We are supposed to…")

### 2a. Emoji (Russell genuinely uses these — confirmed from his messages)

Use **at most one** emoji per message, and only where it fits naturally. His actual palette and when he reaches for each:

- 🙁 / ☹️ / 😧 — empathy or mild disappointment, right after an apology or bad news: "Sorry the team call went long ☹️", "I hope your grandmother is OK … 😧"
- 👍 — light acknowledgement, often after "Thanks": "Thanks 👍"
- ✅ — marking a logistics item handled: "Will reschedule ✅", "Cancelled ✅"
- 👇 — pointing at a link, recording, or the thing just below: "I did a short recording to explain 👇"
- 🎉 / 👋 / 🔔 — occasional: celebration, a greeting wave, or a notify nudge.

Don't invent emoji outside this palette, don't stack them, and skip them entirely in more formal announcements unless one genuinely fits. **If you ever need to check which emoji Russell used in a specific past message, screenshot that message and read it** — the scrape can miss image-based emoji.

### 3. Persona modes — pick the one matching the chat

Choose by the recipient/context, then layer the core voice on top.

**`1on1` — private direct chat (most casual):**
- Opens either with "Hi [Name]!" / "Hi, [Name]," or no greeting at all (jump straight in, or lead with their name mid-sentence).
- Short, conversational, considerate of their time and life ("I hope your grandmother is OK … 😧", "Oh! you could have left at 5:00.").
- Logistics + warmth. Apologize if rescheduling, often with a lowercase "sorry" tacked on ("Thanks.  Let's meet tomorrow - sorry.").
- This is where the empathy emoji (🙁 ☹️ 😧) and 👇/✅ show up most.
- *Samples:*
  - "Hi Mallikarjun!  I heard back from the HR folks and they've made the update to bring Workday in sync. Here is your merit statement. Let me know if that looks OK?"
  - "This is still correct. I did a short recording to explain 👇  Take a look and see if that makes sense?"
  - "I'm sorry I have to move this again. I'll just cancel and we can do it next Monday."

**`outreach` — offering a resource / asking someone to adopt something:**
- Lead with the person's name, then hand them the thing plainly, with the link anchored to its title.
- Frame as helpful, low-pressure; invite a look.
- *Samples:*
  - "Stuart Foster — here is the information on the SkyStage API. You can use it for Solutions and Business Units: [API documentation](URL). Your API token (view access; expires in 1 year): …"
  - "Here is the [Create GitHub Repository](URL) functionality that you can check out."
  - "I made these feature specs based on our conversation yesterday. Take a look and see if they capture your scenarios?"

**`announcement` — broad post to a group/channel:**
- Open with "Hey folks/everyone/guys".
- State what you did or want, then (if there's detail) a tight bulleted list of specifics, then a clear, low-pressure call for feedback.
- End with what happens next + "let me know".
- *Samples:*
  - "Hey folks, I'm working with Adam on a training curriculum for our engineers on having a quality mindset. With AI doing so much and traditional QA roles folding into development, it's paramount that everyone has an ethos of shipping quality software. I prepared [Quality Mindset Training — Session Agenda](URL) with a draft. Is anyone here interested in reviewing and sharing feedback? You can leave comments on the Confluence page or here in chat."
  - "I've updated the [SkyStage-Only GitHub Repository Creation Plan](URL) based on last Thursday's meeting feedback. Incorporated: - Editable repository name prefixes - Phased rollout starting with mediwareinc - GitHub org banners to communicate the transition. Take another look and let me know if there's more feedback. After that I'll reach out again and we can set a date for the cutover."
  - "Hey guys — hope you've been well. I just wanted to check this is still fitting OK in the current sprint? Thanks!"

### 4. When unsure

If the requested message doesn't clearly fit a persona, default to `1on1` warmth for individuals and `announcement` structure for groups. If you'd have to invent a personal detail (an anecdote, a name, a commitment), insert a placeholder like `[CONFIRM: …]` instead of fabricating — Russell would rather fill it in than have you guess.

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
| Search box | `input[data-tid="AUTOSUGGEST_INPUT"]` | Type `email` (most precise). |
| Person result | `[role="option"][data-tid^="AUTOSUGGEST_SUGGESTION_TOPHITS8:orgid:"]` or `…PEOPLE8:orgid:` | **Poll** until an option's text matches the name — default suggestions render first; clicking one opens the wrong person. |
| Chat heading | `h1`, `h2`, or `h3` containing the name | ⚠️ `[data-tid="chat-header-title"]` does **not** exist in this build — use headings. |
| Composer | `div[data-tid="ckeditor"]:visible` | ⚠️ NOT unique without `:visible` — see invariant 1. |
| Link dialog inputs | `[data-tid="insertHyperlink-displayText"]`, `[data-tid="insertHyperlink-linkAddress"]` | ⚠️ `data-tid`, **not** `id`. Ctrl+K opens it; fill both + click **Insert**. |

## Steps (what browser-chauffeur should do)

### 1. Pick the correct Teams tab
From the CDP-connected browser context, select the Teams page with the **largest `document.body.innerText.length`** — this is the fully-loaded Teams app, not a blank/loading tab.

### 2. Search + open the 1:1 chat
- Click the search box (`input[data-tid="AUTOSUGGEST_INPUT"]`)
- Clear it (Ctrl+A, Delete)
- Type the recipient's **email** (most reliable search key)
- **Poll** the person results until an option's text matches the recipient's **name** (last name + first-name prefix)
  - Default suggestions render first; acting on them opens the wrong person
  - Timeout after 15s if no match appears → exit with error code 2 (person not found)
- Click the matching person option
- Wait for navigation/load (`networkidle` or URL change)
- Sleep ~1.8s for the chat to fully render

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
  - Click Insert button (role=button, name matches /^Insert$/)
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
