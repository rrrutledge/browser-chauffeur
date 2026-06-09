---
name: document-authoring
description: Russell's personal style conventions for authoring or editing any document or message that contains links or formatted prose — Confluence pages, Word docs, email, Teams messages, PRs, etc. Use whenever composing such content.
---

# Document Authoring Style (Russell's preferences)

Apply these whenever authoring or editing a document/message that will contain links or formatted prose, in any tool.

## Links
- **Always embed links as hyperlinks on descriptive text within the sentence flow — never paste bare `https://…` URLs in prose.**
  - Good: "see the [incident report](URL)", "the [IDP-1069](URL) ticket", "documented in [the runbook](URL)".
  - Bad: "Read here: https://wellsky.atlassian.net/wiki/…"
- This applies to **every** medium, with no exceptions:
  - **Confluence** (storage format): `<a href="URL">descriptive text</a>` inside the sentence.
  - **Teams**: use the link dialog (Ctrl+K) to anchor the URL to text. When drafting in the browser, that means selecting/typing the anchor text, then Ctrl+K and pasting the URL — do this rather than leaving a bare URL.
  - **Word / email / Markdown / PRs**: anchor the link to natural words too.

## Voice & Tone

Apply this when composing prose in Russell's name — Teams messages, email, outreach, announcements, PR descriptions, and the narrative parts of docs. (Reference data, tables, and formal specs stay neutral; this is for the sentences a reader hears as *him*.) The guidance below is distilled from his actual sent messages — the quoted examples are real.

**Be warm and plainly human.** Lead with goodwill, thank people generously, and make the reader feel the work is *for them*.
- Open cold outreach with a first name and an exclamation: "Hi Christine!", "Hi Matt!". With people he already knows, skip the greeting or use the name as direct address: "Greg, are you setting up the quarterly meeting…?"
- Thank early and often: "Thanks for using SkyStage!", "thanks for giving it a spin and giving feedback."
- Reassure and offer to share the load: "no problem. I want this to work for you.", "We can pair on it too if it's easier."

**Write short. One idea per sentence.** Break a complex point into a run of short sentences instead of one compound sentence — fragments are fine for rhythm.
- "The whole \"access\" denied UI is a red herring. The issue is that the app isn't up. Due to that error you can see in the logs. Since the app isn't up you can't reach it in the browser."
- In conversation, send a few short lines rather than one dense block.

**Make asks as a polite question, then give the payoff.** Frame requests as "Would you be willing to…?" — never a command — and immediately follow with what the reader gets.
- "Would you be willing to delete the repo and create it again through SkyStage? Then everything will be set up correctly for you."
- Soften a critique or an imposition with a quick apology, kept light: "Sorry to nitpick - and I really am thankful for you doing the work.", "Thanks - sorry to bug you but it is very helpful."

**Teach with if/then.** Set expectations using plain conditionals rather than abstract rules.
- "If the app won't run on your laptop first then it won't run in the cloud."
- "If you have the repo checked out locally you can then push it back again at that point and all your work will be there."

**Default to "you" and "we".** Center the reader ("you/your"), use "we're" for the team or product, and "I" for a personal action: "We're rolling out a new process…", "On our side I'm opening a Jira…".

**Signature touches** (use sparingly, where they fit — don't force them):
- A spaced hyphen for a casual aside or pivot: "Cool - thanks…", "Yes - Jonah's thing would work well for that.", "Haha - sure."
- A leading "…" for a wry beat: "… Why didn't you tell me earlier?"
- "Haha" for levity. Contractions always (we're, isn't, won't, I'll).

**Avoid:** emoji (he doesn't use them — warmth comes from "!" and "Haha"), corporate filler and hedging, long compound sentences, and commands where a "Would you be willing to…?" would do.
