---
name: skill-authoring
description: Russell's design rubric for a Claude Code skill's structure - the description written for triggering, progressive disclosure that keeps SKILL.md lean, action-oriented sections, and when to split a skill versus add a section. Load when authoring or editing a SKILL.md, and when reviewing one against the rules.
---

# Skill-authoring rubric (skill design)

`authoring-rules` and `document-authoring` cover the prose voice of any text that ships.
This rubric adds the layer above the sentences: whether a `SKILL.md` is *shaped* like a skill that loads at the right moment and stays cheap to hold.
It applies only to a `SKILL.md` file, and it layers on top of the prose rubric rather than replacing it - a skill file is reviewed against both.

Each rule states the behavior, then a **Check** giving the surface forms that usually indicate it was broken, and where those forms are innocent.
The forms are evidence, not the rule: one appearing is not automatically a violation, and a violation that uses none of them is still a violation.

A skill is loaded by a reader who is mid-task and deciding whether this file helps them now.
Every rule here serves that reader: it fires for them at the right moment, and once loaded it earns the space it takes.

---

## The rules

**Write the `description` for the moment of loading, in the reader's situation.**
The description is read by someone deciding whether to pull this skill in, so it states the situations, tasks, and trigger words that should load it.
The name of the job and the cues that signal it are what let the right reader find it.
**Check:** a description that only characterizes what the skill contains ("conventions for X", "a rubric of Y") with no load-time condition; missing trigger situations a reader would search by. Innocent: a description that names both the trigger and the content in a few words, where the content phrase is what the reader recognizes the situation by.

**Keep `SKILL.md` to the map and the always-needed core; push situational detail into referenced files.**
The main file is loaded in full every time the skill triggers, so it carries what every use needs - the flow, the rules that always apply, the pointers - and hands off detail that only some uses need to a referenced file loaded on demand.
An exhaustive option table, a long worked example, or a per-case procedure that most triggers never reach belongs behind a reference, named from the main file.
**Check:** a `SKILL.md` long enough that a reader loads far more than a given task needs; a full reference table, an extended transcript, or a rarely-hit procedure inlined where a pointer to a separate file would carry it. Innocent: detail short enough that splitting it would cost more indirection than the load saves, and a core rule that genuinely applies on every use.

**Organize by what the reader does, in imperatives.**
A skill's sections are the reader's decisions and actions - "when X, do Y", "to do Z, run this" - so the structure matches the task the reader arrived with.
Lead with the action; background earns its place only where an action depends on it.
**Check:** sections built as theory or history the reader must translate into steps themselves; a passive description of how something works where a directive is what the moment calls for. Innocent: a short rationale attached to a directive so the reader knows when the directive stops applying.

**Let the description name one coherent job; a second unrelated trigger is a second skill.**
A skill is one triggerable unit of work, and its description names one situation that loads it.
When content would fire in a genuinely different situation - a different task, a different reader, a different moment - it is its own skill with its own description, so its reader finds it under the trigger that matches.
Related detail that only makes sense once the skill has already loaded stays a section or a referenced file.
**Check:** a description naming two unrelated load conditions joined by "and also"; a major section whose trigger has nothing to do with the description that would pull the file in. Innocent: sub-topics that share the one triggering situation and are only reached once the skill is already loaded.

**Name the skill as the reader refers to the job.**
The directory and `name` match the task the description promises, so the name the reader invokes and the name they'd search for are the same.
**Check:** a name describing the implementation or an internal detail rather than the job the reader loads it for; a name that diverges from the situation the description names. Innocent: an established name kept stable because readers and other skills already point to it.

**One concept, one canonical place.**
This is the shared rule in `authoring-rules`; a skill obeys it across its own files and its links to sibling skills, pointing to the canonical home rather than restating it.
See that rubric for the rule and its Check.

---

## How a skill file gets reviewed against this

`writing-review` is the pass that runs a `SKILL.md` through this rubric, the way it runs an outward message through `document-authoring`.
The reviewer loads this file as the extra rubric whenever the text under review is a `SKILL.md`; `reviewer-prompt.md` in `writing-review` says how.
Rules belong here, never in the prompt - a rule stated in the prompt drifts from the copy the reviewer reads.
