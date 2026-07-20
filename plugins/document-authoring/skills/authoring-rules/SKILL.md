---
name: authoring-rules
description: Russell's medium-independent rules for any text that ships - code comments, docstrings, SKILL.md and other skill prose, READMEs, repo docs, config prose, PR bodies, commit messages, Confluence pages, email, Teams and Slack messages. Load when authoring or editing any of these, and when reviewing authored text against the rules.
---

# Authoring rules (shared rubric)

Every rule here is an **artifact rule**: you can tell whether it was followed by reading the finished text alone.
That is what makes this set shared.
The writer loads it to compose against; a reviewer loads the same file to check against, so the two can never drift.

Rules that constrain *how you get there* rather than what lands (draft then revisit, verify line by line, run the overlap search before adding a bullet) are writer-only and live in `document-authoring`.
A reviewer holding only the output cannot evaluate them.

Medium-specific rules - register, warmth, personas, emoji, sign-offs, asks, nudges - also live in `document-authoring`.
They are reviewable, but only for outward messages.

---

## The rules

**Present tense in shipped artifacts; before/after only in change-explanations.**
Where the text lands decides which applies, not how useful the history feels.
- *Ships and stays* (docs, `SKILL.md`, README, code comments, docstrings, config prose): every sentence answers "how does this work today".
- *Explains a change* (chat with Russell, a PR body, a commit message): before/after is the point.

Rationale is in scope; provenance is not.
"Deletes the entry so a later run doesn't re-litigate it" is a why with no history in it.
**Check:** does the sentence parse without knowing a previous state? If it leans on "used to", "no longer", "instead of the old", "we tried X", "this replaces", or "by hand", it fails.

**State guidance positively.**
Describe the desired behavior directly; a correction names only what to do, not the rejected alternative alongside it.
Reserve a negative for a real, tempting failure mode a positive instruction won't prevent on its own, and write it as a single standalone guardrail.
**Check:** does a "don't do X, do Y" couplet appear where "do Y" alone would carry it?

**No helper tail.**
Stop the moment the point is made.
Treat any sentence after the main point as guilty until proven necessary: cut reassurance, offers, hedges, restated context, and invitations to react.
**Check:** does this sentence hand the reader something they don't already have? If a real decision is still open, ask it as one direct question and stop there too.

**No em dash.**
Use a spaced hyphen ` - ` instead.
**Check:** grep the text for `—`.

**Anchor every link on descriptive text.**
Write "see the [incident report](URL)", never a bare `https://…` in prose.
**Check:** does a bare URL appear outside a code block?

**Name the specific thing, not the category.**
"token cost" not "cost", "the deploy" not "it".
**Check:** can you point at what each noun refers to without reading around it?

**Short sentences, one idea each.**
Fragments are fine for rhythm.

**Bold lead-ins on bullets.**
Start each bullet with a bold 4-7 word key phrase, then the detail.
Put an intro sentence above a list, with a blank line before the list.

**No corporate or AI filler.**
"leverage" as a verb, "streamline", "as per", "delve", "I wanted to reach out", "I hope this finds you well", "Furthermore", "Moreover".
Also: no "it's not just X, it's Y" constructions, no rule-of-three flourishes, no breathless enthusiasm.

**Semantic line breaks in markdown source.**
Within a paragraph or a multi-sentence bullet, start each sentence on a new line.
Rendered output is identical, but a one-sentence edit then touches one line instead of marking the whole paragraph changed in the diff.
**Check:** markdown source only. Not a rendered-output rule, so it never applies to a message composed in a web UI.

---

## Where the rules pull against each other

These tensions are real, not drafting mistakes.
Each is resolved by a stated boundary rather than by judgment in the moment, so the writer isn't left arbitrating mid-sentence.

| Tension | Boundary that resolves it |
|---|---|
| "Explain the why" vs present-tense-only | Rationale (why it behaves this way now) is in scope. Provenance (what it replaced) is not. |
| "Be useful" vs no helper tail | Usefulness goes in the substance. A closing offer adds nothing the reader doesn't have. |
| "Be precise about the failure" vs state guidance positively | A negative is allowed when the failure mode is real and tempting, and then only as one standalone guardrail. |

When a rule and an active writing goal pull opposite ways, the goal usually wins by default, because the goal is what you're holding in mind while composing.
That is the failure this rubric exists to make checkable, and the reason a reviewer reading cold catches what the author stared past.
