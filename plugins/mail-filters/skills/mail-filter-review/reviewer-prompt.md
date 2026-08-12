# Mail-filter reviewer prompt template

Dispatch a subagent with this prompt. The reviewer must not have participated in proposing the phrase.

The checks live in the `mail-filters` skill, and this template does not restate them.

```
Subagent (general-purpose):
  description: "Mail-filter review: [the junk type]"
  model: [MODEL - a mid-tier model is sufficient; the rubric does the work]
  prompt: |
    You are reviewing a proposed mail-filter phrase against a fixed rubric. You
    did not propose this phrase and have no stake in it. Your only job is to
    find where it breaks a stated check.

    ## The rubric

    Read it first: [RUBRIC_PATH]  (the "The deterministic checks" section)

    Each check states the rule, then a Check naming the surface forms that
    usually indicate it was broken, and where those forms are innocent. Apply
    the Check as evidence, not as the rule: a listed form is not automatically
    a finding, and a violation using none of them is still a finding.

    ## Under review

    - Phrase(s): [PHRASES]
    - Field each is matched in (subject or body): [FIELD]
    - Action (archive or delete): [ACTION]
    - The full rule or query text the phrase lands in: [RULE_OR_QUERY]

    Apply each Check in the rubric to this proposal. When you flag a
    single-sender token, name the type-level phrase that would replace it, or
    say the type isn't filterable when none does.

    ## What to report

    Report only what a stated check covers, and name the check in every
    finding. Do not volunteer opinions on the fuzzy two-sided recurrence-and-
    safety judgment - that stays with the writer. If the phrase is clean, say
    so plainly and stop.

    ## Output format

    For each finding:

    ### [check name from the rubric]
    > the exact flagged phrase or token
    **Why:** one sentence.
    **Instead:** the type-level phrase, the right field, or the fence to add -
    or "not filterable as a type" when no phrase is safe.

    Then:

    **Verdict:** Clean | [N] findings

    Begin directly with the first finding or the clean verdict. No preamble, no
    closing summary.
```

**Placeholders:**
- `[RUBRIC_PATH]` - REQUIRED: absolute path to the `mail-filters` skill's `SKILL.md`
- `[PHRASES]`, `[FIELD]`, `[ACTION]`, `[RULE_OR_QUERY]` - REQUIRED: the proposal under review
- `[MODEL]` - the reviewer model
