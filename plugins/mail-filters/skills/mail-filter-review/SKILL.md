---
name: mail-filter-review
description: Review a proposed mail-filter phrase against the deterministic rules in the mail-filters skill - no company/brand/product/person token, phrase scoped to the field it lives in, master domain-exclusion fence on every broad bucket. Use before showing Russell any filter phrase to approve, and whenever the drainer's junk-learning or digest step proposes one.
---

# Mail-filter review

Runs a proposed filter phrase through the deterministic checks in the `mail-filters` skill, before Russell ever sees it to approve.
This is the counterpart to `writing-review`: same posture, a different and narrower rubric.

## Why this exists as a separate agent

The phrase-selection craft has a fuzzy core - the two-sided recurrence-and-safety judgment - and a set of rules that are decidable from the proposed phrase and rule alone.
The fuzzy core stays with the writer.
The decidable rules are what slip: a session proposing a filter for one junk sample is holding the sample in mind, so the company or brand token that makes the phrase a single-sender rule rides along uncaught.
Alaska, KBB, and IMDb each reached a proposed phrase this way.

A reviewer coming to the phrase cold has no sample in mind and no goal the rule can lose to.
Catching the single-sender token is its whole job, the same reason a cold `writing-review` catches the voice slip the author stared past.

**Dispatch the reviewer as a subagent, always.**
Running the check inline, in the session that proposed the phrase, reproduces the exact blindness the review exists to correct.

## The rubric

The checks live in the `mail-filters` skill's **The deterministic checks** section, stated once there so the writer composes against the same rules the reviewer checks.
Read that section; this skill does not restate the checks.

## When to run it

The `mail-filters` skill invokes this at one point: the show-literal-rule gate, the checkpoint every proposed phrase passes through before a rule is created.
So it runs whenever a phrase is proposed - a manual filter, the drainer's per-provider `JUNK-LEARNING` step, or the daily digest's junk step - because they all reach that gate by following the `mail-filters` skill.
Nothing separate is wired at each call site.

## How to run it

1. Collect what's under review: the proposed phrase(s), the field each is matched in (subject or body), the action (archive or delete), and the full rule or query text the phrase lands in (so the fence check can read it).
2. Dispatch a subagent using `reviewer-prompt.md`, giving it that material and the rubric path.
3. Revise against the findings you accept - generalize a flagged token away to a type-level phrase, move a phrase to the field it actually occurs in, add the missing fence - then dispatch a **fresh** reviewer on the revised phrase.
   A reviewer that has already seen an earlier proposal reads its own prior findings rather than the phrase in front of it.
4. Repeat from step 2 until the reviewer returns clean, a finding stands that you genuinely disagree with, or you have run three rounds.

**The loop finishes before the show-literal-rule gate.**
Russell approves the phrase that survived review, not the rounds it took.
A phrase the reviewer flags as carrying a single-sender token, and that you cannot generalize to a type-level phrase, is one this junk type isn't filterable by - stop it at the source instead (per the `mail-filters` JUNK-LEARNING order), rather than showing Russell a brand-named rule.

## Standing to disagree

You may reject a finding, and sometimes you should: a capitalized token can be a generic type-word (a subject-prefix convention like `Accepted:`, a template word like `Passcode`) rather than a brand, and the reviewer flags surface forms as evidence, not as automatic violations.
Before rejecting, state in one sentence why the flagged token is not a single-sender token - that it names the *kind* of notification, not the sender.
A rejection you cannot put in those terms is the brand token slipping through again, so generalize the phrase instead.

## Learning from rejected findings

A rejected finding says the rule is tighter than practice or its Check is too broad.
**Russell rejects one** - strong signal: fold the refinement into the `mail-filters` skill's checks as a PR against this repo.
**The writer rejects one** - weak signal alone, since the writer has an interest in the finding being wrong; act on it when the same rejection recurs across independent sessions, and note it in the PR that carries the work.
The success signal is convergence: over time the reviewer should return clean on the first round.
