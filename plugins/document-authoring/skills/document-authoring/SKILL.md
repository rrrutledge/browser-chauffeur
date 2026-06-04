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
