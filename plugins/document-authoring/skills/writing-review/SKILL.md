---
name: writing-review
description: Review authored prose against Russell's authoring rules - code comments, docstrings, SKILL.md and skill prose, READMEs, repo docs, config prose, Confluence pages, email, Teams and Slack messages. Use after writing or editing any of these, before handing the work over, and when asked to check a diff or document for voice and style compliance.
---

# Writing review

Checks prose against the shared rubric in `authoring-rules` and reports what fails.
This is the counterpart to code review: same posture, different rubric.

## Why this exists as a separate agent

A writer holds two things at once - the rule and the goal it conflicts with.
The goal is active and the rule is passive, so under pressure the goal wins.
A docstring author working on "explain why this script exists" writes "in place of the snippets it used to author fresh into `.tmp/`" while holding a rule against exactly that, because the rule is not what they are thinking about.

A reviewer has no competing goal.
Reviewing is the whole job, so there is nothing for the rule to lose to.
This is the same reason code review catches what the author read past.

**Dispatch the reviewer as a subagent, always.**
Running the check inline, in the session that wrote the prose, reproduces the exact blindness the review exists to correct.
The reviewer must come to the text cold.

## When to run it

- After authoring or editing any shipped prose, before handing the work to Russell.
- On a diff, when asked to check a branch or PR.
- On a single document, when asked to check it directly.

## How to run it

1. Collect the text under review.
   For a diff: `git diff <base>..<head>` restricted to prose-bearing files.
   For a document: the file itself.
2. Skip `.tmp/`.
   Plans, specs, handoffs, and staged commit messages live there, and they are change-explanations rather than shipped artifacts.
   Different rules apply to them, so reviewing them against this rubric produces false findings.
3. Dispatch a subagent using `reviewer-prompt.md`, giving it the text and the rubric path.
4. Report the findings to Russell.
   Apply the ones that are right; say which you applied and which you disagreed with, and why.

## Scope

Report only what a stated rule in `authoring-rules` covers, and name the rule in every finding.
General writing opinions stay out.
A reviewer that volunteers unsourced taste gets argued with, then ignored, and takes the sourced findings down with it.

When the prose is an outward message rather than a shipped artifact, load `document-authoring` as well and review against its message-specific rules too.
