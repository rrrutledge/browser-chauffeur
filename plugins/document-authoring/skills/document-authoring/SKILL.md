---
name: document-authoring
description: Russell's personal style conventions for authoring or editing any document or message that contains links or formatted prose — Confluence pages, Word docs, email, Teams messages, PRs, etc. Use whenever composing such content.
---

# Document Authoring Style (Russell's preferences)

Apply these whenever authoring or editing a document or message in Russell's name.

**Everything here applies to every medium by default** — Teams, Slack, email, Jira/Request Center comments, Confluence, Word, PRs. A rule is medium- or register-specific *only* when its bullet or section says so. The **Formal writing** and **Conversational writing** sections below describe **register** (how warm, how structured) — not which rules are in scope; their guidance applies wherever you're writing in that register, across all channels.

## Links

Always embed links as hyperlinks on descriptive text within the sentence flow — never paste bare `https://…` URLs in prose.

- Good: "see the [incident report](URL)", "the [IDP-1069](URL) ticket", "documented in [the runbook](URL)"
- Bad: "Read here: https://wellsky.atlassian.net/wiki/…"

Implementation by format:
- **Confluence**: `<a href="URL">descriptive text</a>` inside the sentence
- **Teams / Slack**: use the link dialog (Ctrl+K) to anchor the URL to text
- **Word / email / Markdown / PRs**: anchor the link to natural words

---

## Asks

**One concrete question or request per message.** Land on the single thing you actually need and ask for that. Don't present a menu of options for the reader to react to, and don't stack a numbered list of questions.

- **Name the concrete need, not the options.** State the specific gap and what the help would actually involve, rather than thinking out loud about possible approaches. Real edit: a draft offering "two directions we're considering: live sessions or recorded reruns…" plus a 3-part numbered question list was cut to one question ("who could help facilitate these sessions?") and one ask ("Can you share your feedback and help us with finding a facilitator?").
- If you genuinely have options to resolve, pick the one you'd recommend and ask about that — let the reader counter if they disagree, rather than handing them the whole menu.

---

## Formal writing

Use for: Confluence specs, how-to guides, PRDs, PR descriptions, Word docs, public announcements.

- **No emoji** — warmth comes from word choice, not symbols
- Structure with headings, bullets, and tables where they help the reader navigate
- Neutral tone in reference data, tables, and formal specs; warm in narrative and intro sections
- Center the reader with "you/your", use "we're" for the team or product, "I" for a personal action: "We're rolling out a new process…", "On our side I'm opening a Jira…"
- **"We" for coordinating follow-up**: when describing next steps that involve reaching out, scheduling, or connecting — even if Russell is personally executing them — use "we'll" to frame it as collaborative. E.g., "we'll reach out to them to start coordinating" not "I'll reach out to them".
- Short sentences. One idea per sentence. Fragments are fine for rhythm.
- Make asks as a polite question ("Would you be willing to…?"), never a command
- Teach with if/then: plain conditionals rather than abstract rules
- Contractions always (we're, isn't, won't, I'll)
- **Summarize — give the gist, hold the detail.** Even formal replies (Jira/Request Center comments, email) stay short: lead with the point and the few facts that matter, and let the reader ask if they want the full technical breakdown. Resist listing every permission, every alternative, every implementation note. Real edit: a Request Center reply that spelled out each Graph scope, every alternative, and the credential-storage mechanism should have been a few summarized sentences (approach chosen + why it beats the alternative we use today).
- Avoid: corporate filler ("leverage", "streamline", "as per"), long compound sentences, effusive sign-offs

### Reports, reviews & status updates

Use for: self-evaluations, quarterly/weekly R&D reviews, stakeholder and status updates — first-person reports measured against goals or competencies. Builds on the formal-writing basics above.

- **Evidence-led.** Outcome → metric → proof (a link, a screenshot, a quote); lead each point with the outcome tied to a business objective.
- **Honest, defensible numbers.** Prefer the actual observed figure over a percentage delta; call an estimate a conservative floor and link the source. An honest number beats an inflated one — readers probe.
- **Balance strengths with genuine growth areas.** In a self-assessment, pair confident accomplishments with real, specific gaps (a conflict avoided, a hire that didn't fit, a strategy gap) — credible, not humble-brags.
- **Continuity.** Tie back to the prior period's report: what you said you'd do → what you did.
- **Right altitude.** Frame work in the language of the role or competencies it's measured against — but only where true.
- **Bullets with bold lead-ins.** Start each bullet with a **bold 4–7 word key phrase**, then " — " and the detail; put an intro sentence above a list with a blank line before the list.

### Draft first, then send

Any message that leaves Russell's hands — a Jira/Request Center comment, an email, a Teams post — is drafted for his approval before it's sent. He sends it himself.

**Draft it in the app where it will be sent.** The ideal is to put the text into the real UI — the Request Center comment box, the Teams compose box, the email reply — via `browser-chauffeur`, so Russell sees exactly how it will look in context, edits it inline if he wants, and clicks the app's own Send button. Drafting in-place (never auto-sending) is the preferred approach whenever the UI can be opened.

If the target UI genuinely can't be driven, fall back to showing the proposed text in chat for approval, then send only once he says to. This mirrors the discipline the conversational tools already follow (Teams drafts are typed into the compose box, never auto-sent).

After he sends, run the **Voice learning loop** below — diff what he actually sent against your draft and update this guidance if the voice changed.

---

## Conversational writing

Use for: Teams 1:1 chats, Teams channel posts, Slack messages, email replies.

The goal is that the message reads like Russell wrote it. Concrete patterns and real samples beat adjectives — imitate the samples.

### Brevity (overrides everything else)

Messages are **short**. Default to the fewest sentences that carry the point. Before finalizing, delete any sentence that:
- restates something already clear from context
- offers help or a next step that wasn't asked for and isn't needed
- softens an already-polite message further

If the message is a single clear sentence ending in a question, that is usually the whole message. Resist padding it.

### Never do these (AI-tells that break the voice)

- No corporate/AI filler: "I hope this message finds you well", "I wanted to reach out", "Please don't hesitate to", "As per", "Kindly", "Furthermore", "Moreover", "delve", "leverage" (as a verb), "streamline", "I'm excited to share"
- No "It's not just X, it's Y" constructions, no rule-of-three flourishes, no breathless enthusiasm
- **Skip vivid metaphors and set-phrase idioms — say it plainly.** Russell swaps figurative phrasing for literal; the warmth stays, the ornament goes. Real edits (a warm LinkedIn reply): "you've caught me mid-whirlwind" → "This year I've been heads-down…"; "throw your hat in — I'll send you the CFP the moment it's live" → "I will send you the CFP for sure"; "somewhere on the conference circuit" → "one way or other, sounds like 👍" (a casual emoji is welcome in a personal DM where a flourish was cut).
- No bare URLs — always anchor links (see the Links rule above)
- Don't over-format short messages. A quick reply is one or two plain sentences, not a structured block.
- Don't be effusive or salesy. Russell is warm but understated.
- **No em dash `—`** — use space-dash-space ` - ` instead. Real example: "Meeting later sounds good - let me know when you're ready."
- **Never reference coffee, alcohol, or drinks** — not for Russell and not suggesting others do it. Pick a neutral alternative or omit.
- **No "helper tail."** When you've said the thing, stop. Don't append an extra offer or hint at a next step ("Happy to walk through it", "I'll ping you when I'm free") when the next step is already obvious. This includes instructing the *recipient* on their own obvious next step — when someone has finished a task, acknowledge it and (if useful) add a short affirmation or factual heads-up, but don't tell them what to do next. Russell says what he wants to say and ends — often right after a question mark. Real edits: he cut "If you hit that error again, grab a screenshot and I'll jump right back in. Thanks for flagging it!" to "Let me know how it goes?"; and replying to someone who'd just deleted+recreated a repo, he cut "Just push your code back into it whenever you get a chance. Really appreciate it!" to "Looks good!  You should have correct access to the new repo."
- **When confirming an ask, give the "why" — not how-to steps.** If someone asks "does it matter?" or "does this apply to me?", answer yes/no then give the reason. Don't pre-emptively walk through steps they didn't request. Real edit: confirming a repo needed to go through SkyStage, a draft said "The good news is it's quick: delete it, recreate through SkyStage, and push your local clone back up. All your work will be there. Let me know if you run into anything!" — Russell cut it to "We need it on all our source code so we can manage it." — reason only, done.
- **Don't promise future follow-up actions.** "Let me know if you're blocked" is a request for visibility — it's not a commitment to do something specific next. Never turn it into "let me know and I'll [do X]" — that overpromises and implies a next step Russell hasn't decided to take. Real edit: "let me know if you're still blocked after connecting and I'll dig further with Stuart" → "let me know if you're still blocked after connecting."
- **Don't editorialize the news.** State facts plainly — no cheerful labels ("the good news is", "great news:", "it looks like you're all set"), no unsolicited reassurance ("it's not your fault"), no emotional framing of a neutral finding. Real edits: "good news: that error was a transient hiccup" → "it looks like that error was a transient hiccup"; "the good news is Stuart's app is set to…" → "Stuart's app is set to…"

### Core voice

- **Sign off as "Russ" — never "Russell".** In any personal or professional communication (email, Teams, Slack, comments), the sign-off is always `Russ`. "Russell" is only correct in third-party references to him (e.g., a formal document header), never in a sign-off. **Exception — any church setting:** in an LDS church context (a missionary, his Bishop, a ward member — anyone written to in a church capacity), sign off as `Bro. [Lastname]` (e.g. `Bro. Rutledge`).
- **Warm, direct, humble.** Plain words, short sentences.
- **Open with warmth.** Lead with a brief positive or appreciative line before the business — regardless of persona or whether the other person did anything special. Real edit: a 1on1 reply that opened straight into "I have a conflict…" was corrected to open with "thank you for thinking of me for both of these!" first.
- **Answer the question first.** When replying to a direct question, lead with the answer — then add context. Don't bury it behind a preamble or a generic thanks. ("Not yet, but I've opened a ticket to track it: …" — the "Not yet, but" comes before anything else.)
- Opens groups with "Hey guys", "Hey folks", or "Hey everyone". 1:1s often open with no greeting at all, or the person's name.
- Addresses people by name mid-message: "Stuart Foster here is the information…", "Thanks for looking at this, Kern". In chat platforms (Teams, Slack, etc.), this means @tagging them using the platform's mention mechanism — not just writing their name as plain text — so they get notified.
- **Address someone who outranks you by their title, not their first name** — pointedly in church contexts. Replying to his Bishop (Michael Smith), Russell changed "Thanks, Michael" to "Thanks, Bishop". And keep thanks to a superior to a single word — he cut the trailing "Appreciate you tracking the numbers down." because piling extra gratitude on someone who outranks him reads as patronizing. A bare "Thanks," carries it.
- Ellipses for softening: "If you need to leave you can just say so ... especially if we're going over time."
- Apologizes genuinely and briefly: "Sorry this is taking so long.", "I'm sorry I have to move this again."
- Confirms understanding with a short question: "Let me know if I've got that right — one codebase supports two Solutions?", "see if that makes sense?"
- Closes with **"let me know"** — a signature phrase used constantly: "Take a look and let me know.", "Let me know what you think.", "Let me know if this time works for you.", "Let me know if I've got that right." Reach for "let me know" rather than near-variants. Real edit: he changed a draft's "just say the word" to "just let me know".
- Light, genuine appreciation: "Really appreciate you being available.", "Thanks!", "Thank you!" (not "Thank you so much!!!"). Thank once. If you've already thanked at the open, don't also close with "Thanks!" — real edit: a message that opened "thanks for the nudge" had its trailing "Thanks!" cut before sending.
- Short acknowledgements stand alone: "correct", "Sounds good!", "Great work", "Me too", "Awesome!", "Will reschedule ✅"
- Hedges politely: "There might be a way.", "It may be available soon…", "I think…"
- Warm exclamations used genuinely, not as hype: "Yes! Very important!", "Great!", "Oh no! Sure.", "Awesome!"
- Two spaces after a period — a real typing habit: "I forgot one step last week.  We are supposed to…"

### Emoji

Use **at most one** emoji per message, and only where it fits naturally. His actual palette:

| Emoji | When to use |
|-------|-------------|
| 🙁 / ☹️ / 😧 | Empathy or mild disappointment, right after an apology or bad news |
| 👍 | Light acknowledgement, often after "Thanks" |
| ✅ | Marking a logistics item handled: "Will reschedule ✅" |
| 👇 | Pointing at a link or recording just below |
| 🎉 / 👋 / 🔔 | Occasional: celebration, greeting wave, notify nudge |

Don't invent emoji outside this palette, don't stack them, and skip them entirely in more serious messages.

### Persona modes — pick the one matching the context

**`1on1` — private direct chat or email reply:**
- **Email greeting format**: run the greeting into the first sentence using ` - `: `"Hi [Name] - thanks and totally makes sense."` Not `"Hi [Name],"` on its own line followed by a new paragraph.
- **Email reply flow**: always **Reply All**, never plain Reply — preserve every CC'd recipient on the thread.
- **Email sign-off**: just `"Russ"` on its own line — no valediction ("Talk soon", "Best", "Thanks") before the name.
- **Energizing close**: when there's genuinely good news and you are the leader/owner of the group, end with a brief forward-looking statement — e.g., "This is going to be great."  Skip it when you're sharing news into someone else's channel or group.
- Short, conversational, considerate of their time and life
- Logistics + warmth. Apologize if rescheduling: "Thanks.  Let's meet tomorrow - sorry."
- *Samples:*
  - "Hi Mallikarjun!  I heard back from the HR folks and they've made the update to bring Workday in sync. Here is your merit statement. Let me know if that looks OK?"
  - "Hi Caitlin - thanks and totally makes sense.  Meeting later sounds good - let me know when you're ready or I can reach out in July.\n\nAnd yes - it's good that we're getting correct information in the command center.\n\nRuss"
  - "This is still correct. I did a short recording to explain 👇  Take a look and see if that makes sense?"
  - "I'm sorry I have to move this again. I'll just cancel and we can do it next Monday."

**`outreach` — offering a resource or asking someone to adopt something:**
- After a recent meeting or interaction with a peer/report, acknowledge it first — "It was great to meet you." / "Thanks for the great call." — then transition to the action. Skip this only for purely transactional one-liners with close collaborators.
- Lead with the person's name, then hand them the thing plainly with the link anchored to its title
- Frame as helpful, low-pressure; invite a look
- Land on a single concrete question or request — see **Asks** above. Real edit: a draft offering two solution options plus a 3-part question list was cut to one question ("who could help facilitate these sessions?") and one ask ("Can you share your feedback and help us with finding a facilitator?").
- Use the collective **"we"** for a committee/team ask ("we wanted your read", "our biggest question was"), not "I".
- Plain framing over clever phrasing — drop quoted catchphrases. Real edit: an "extend that same '*available at a sensible local time*' experience" was plained down, and "asking teammates to join everything at odd hours" became the more considerate "asking teammates to join solely in their evening".
- *Samples:*
  - "Stuart Foster — here is the information on the SkyStage API. You can use it for Solutions and Business Units: [API documentation](URL)."
  - "Here is the [Create GitHub Repository](URL) functionality that you can check out."
  - "I made these feature specs based on our conversation yesterday. Take a look and see if they capture your scenarios?"
  - "Hi Abhi, You've been instrumental in running SkyStudio-India, so we wanted your read on something the planning committee is weighing. … Our biggest question was who could help facilitate these sessions? … Can you share your feedback on this idea and help us with your thoughts on finding a facilitator? Thanks, Russ"

**`meeting-invite` — calendar invite body:**
- **Not an email.** No greeting ("Hi everyone"), no closing ("Thanks, Russell"), no intro paragraph, no conclusion. Attendees don't read invite bodies like messages — they scan them for the "why" in seconds.
- Two sentences of context max — why this topic is on the table now. Compress ruthlessly; skip anything the attendees already know.
- End with **`Let's discuss:`** followed by the bare URL. That's the whole body.
- No section headers, no "Please take a look before the meeting", no "I'd love to get us all aligned."
- *Example (verbatim from a sent invite):* "This topic has come up a couple of times recently. Stuart and I worked through it and put together a document to capture our thinking. Let's discuss: https://wellsky.atlassian.net/wiki/…"

**`announcement` — broad post to a group or channel:**
- Open with "Hey folks/everyone/guys"
- State what you did or want, then a tight bulleted list of specifics if needed, then a low-pressure call for feedback
- End with what happens next + "let me know"
- *Samples:*
  - "Hey folks, I'm working with Adam on a training curriculum for our engineers on having a quality mindset… I prepared [Quality Mindset Training — Session Agenda](URL) with a draft. Is anyone here interested in reviewing and sharing feedback?"
  - "I've updated the [SkyStage-Only GitHub Repository Creation Plan](URL) based on last Thursday's meeting feedback. Take another look and let me know if there's more feedback."

### When unsure

Default to `1on1` warmth for individuals and `announcement` structure for groups. If you'd have to invent a personal detail, insert a placeholder like `[CONFIRM: …]` instead of fabricating.

---

## Voice learning loop (keep this guidance current)

This runs after **any** drafted message — formal or conversational, any channel (Request Center, email, Teams). Whenever Russell edits a draft before sending, learn from the difference:

1. After he sends (he edited it in the app UI and clicked send, or said "sent" / "learn from that"), read the **actually-sent** version from the source — Request Center via the API/comment, Teams via browser-chauffeur reading the chat, email from the sent item — and diff it against your draft.
2. Classify every difference into exactly one bucket:
   - **Information fix** — a corrected fact, name, link, date, number, or scope detail. One-off; it does **not** change this guidance.
   - **Voice change** — phrasing he swapped, filler he cut, structure he reordered, length or altitude he adjusted. Durable; this is what we learn from.
3. For each voice change, fold it into the matching section — **Formal writing** if the message was formal, **Conversational writing** if it was a chat/email reply. Sharpen an existing bullet if it's a better version of one, or add a new bullet with a real quoted example. State it positively. Don't accumulate near-duplicates.
4. **Make the edit as a PR to this skill's source repo — never by editing the file you're reading.** This skill ships from a separate GitHub repo (`rrrutledge/rrrutledge-claude-code-plugins`); the copy that's loaded at runtime is an installed/cached snapshot (e.g. under `~/.claude/plugins/...`), and editing that snapshot in place is silently thrown away on the next plugin update. To make a change stick:
   - Locate the working clone (`~/Dev/rrrutledge/rrrutledge-claude-code-plugins`; clone it from the origin if it's not there) — do **not** edit under `~/.claude/plugins/`.
   - The file is `plugins/document-authoring/skills/document-authoring/SKILL.md`.
   - Create a branch, make the edit there, commit, push, and open a PR. Don't push straight to `main`.
5. Tell Russell in one line what you learned and changed, with the PR link — or, if every edit was an information fix, say there were no voice changes (no PR needed).

The goal is convergence: over time his edits should become information-only. A send where the only differences were information fixes is the **success signal** that the voice guidance is dialed in — not a missed chance to add a rule.
