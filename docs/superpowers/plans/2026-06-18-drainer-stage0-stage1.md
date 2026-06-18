# Drainer Continuous Keeper — Stage 0 + Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the drainer into a continuous keeper for personal Outlook: a presence-gated headless poller that spawns a worker tab per needs-you item (≤3 concurrent) and queues fyi/junk, plus the Stage 0 provider polish it depends on.

**Architecture:** The drainer engine is *prose a Claude session executes*, with thin deterministic scripts for the parts that must be exact (presence, seen-state, tab spawn, headless run). Stage 0 finalizes the `personal-outlook` provider (read+unread enumerate, prefer-reply). Stage 1 adds `engine/poller-core.md` (the fast-loop procedure) and a new `scripts/` dir, driven by a headless `claude -p` run on a ~5-min cron. Fail-safe throughout: the poller never clears; seen-ids are recorded only after dispatch; losing state means reprocess, never miss.

**Tech Stack:** Node (ms-graph `mail.js`, seen-state helper), PowerShell (presence, Windows Terminal tab spawn via `launch-session.ps1`, `schtasks`), Claude Code headless (`claude -p`), Markdown engine docs.

**Source of truth:** `docs/superpowers/specs/2026-06-17-drainer-continuous-keeper-redesign.md`. Read it first.

**Repo / collaboration notes:**
- Plugin repo `rrrutledge/rrrutledge-claude-code-plugins`. **Per the repo CLAUDE.md, every change under `plugins/<name>/` requires a version bump** in that plugin's `.claude-plugin/plugin.json` in the same PR.
- This clone is sometimes shared by concurrent sessions. **Work in an isolated git worktree** (superpowers:using-git-worktrees) off `origin/main`; never `git add -A` in the shared checkout.
- Stage 0 edits extend the **existing PR #70** branch `feat/drainer-personal-outlook-provider` (already has the provider + `mail.js` `list-unread`/`delete`/`draft-new`). Stage 1 can be a follow-up branch/PR off Stage 0.
- Personal machine runtime: project is `~/Dev/personal-ai-pod` (has `.claude/drainer.local.md` + `drainer-local/context.md`). Credentials (`GRAPH_*`, `TRELLO_*`) are in the PowerShell profile and present in a profile-launched session.

---

## File Structure

**Stage 0 (extend PR #70 branch):**
- Modify: `plugins/ms-graph/skills/ms-graph/scripts/mail.js` — add `--list-inbox` (read+unread, windowed).
- Modify: `plugins/ms-graph/skills/ms-graph/SKILL.md` — document `--list-inbox`.
- Modify: `plugins/drainer/skills/drainer/providers/personal-outlook-provider.md` — ENUMERATE uses `--list-inbox`; DRAFT-MODE prefer-reply (already drafted in PR #70 — verify).
- Modify: `plugins/message-draft/skills/message-draft/SKILL.md` — add the reply-preference rule.
- Bump: `plugins/ms-graph/.claude-plugin/plugin.json`, `plugins/drainer/.claude-plugin/plugin.json`, `plugins/message-draft/.claude-plugin/plugin.json`.

**Stage 1 (new branch/PR):**
- Create: `plugins/drainer/skills/drainer/engine/poller-core.md` — the continuous fast-loop procedure.
- Create: `plugins/drainer/skills/drainer/scripts/seen-state.js` — seen-ids + needs-you status + digest-queue helper (Node).
- Create: `plugins/drainer/skills/drainer/scripts/presence.ps1` — Windows idle-seconds gate.
- Create: `plugins/drainer/skills/drainer/scripts/spawn-worker.ps1` — open a Windows Terminal tab running a worker session on one item (wraps `launch-session.ps1`).
- Create: `plugins/drainer/skills/drainer/scripts/run-poller.ps1` — the cron entry point: presence-gate → invoke `claude -p` with the poller prompt → (optional `-DryRun`).
- Create: `plugins/drainer/skills/drainer/scripts/register-schedule.ps1` — register/unregister the ~5-min scheduled task (run only after manual validation).
- Modify: `plugins/drainer/skills/drainer/SKILL.md` — point continuous mode at `poller-core.md`; list `personal-outlook`.
- Modify: `plugins/drainer/skills/drainer/templates/drainer.local.example.md` — add `max_open_tabs`, `inbox_window_days`.
- Bump: `plugins/drainer/.claude-plugin/plugin.json`.

---

## STAGE 0 — Provider polish

### Task 1: `mail.js --list-inbox` (read + unread, windowed)

**Files:**
- Modify: `plugins/ms-graph/skills/ms-graph/scripts/mail.js`
- Modify: `plugins/ms-graph/skills/ms-graph/SKILL.md`

The spec's ENUMERATE must see read **and** unread mail (goal: empty inbox, not just zero-unread). `--list-unread` stays; add `--list-inbox [--since-days=N] [--top=N]` returning recent inbox items regardless of read state, newest-first, each block carrying id + webLink (same format as `--list-unread`).

- [ ] **Step 1: Add the `listInbox` function.** In `mail.js`, after `listUnread`, add:

```javascript
async function listInbox(client) {
  const days = parseInt(args['since-days'] || '7', 10);
  // ISO cutoff without Date.now() pitfalls: use Graph's relative filter via receivedDateTime.
  const cutoff = new Date(Date.now() - days * 864e5).toISOString();
  const data = await client.api('/me/mailFolders/inbox/messages')
    .filter(`receivedDateTime ge ${cutoff}`)
    .orderby('receivedDateTime desc')
    .top(parseInt(args.top || '50', 10))
    .select('id,conversationId,subject,from,toRecipients,receivedDateTime,bodyPreview,webLink,isRead')
    .get();
  const msgs = data.value || [];
  if (!msgs.length) { console.log('No inbox messages in window.'); return; }
  console.log(`${msgs.length} inbox message(s) in last ${days}d, newest first:`);
  for (const m of msgs) {
    console.log(`\n--- ${m.receivedDateTime?.slice(0, 16)}  |  ${m.isRead ? 'read ' : 'UNREAD'} | ${m.subject}`);
    console.log(`    from: ${addr(m.from)}`);
    console.log(`    id:   ${m.id}`);
    console.log(`    link: ${m.webLink}`);
    console.log(`    > ${(m.bodyPreview || '').replace(/\s+/g, ' ').slice(0, 200)}`);
  }
}
```

- [ ] **Step 2: Wire the dispatch + header.** Add `if (args['list-inbox']) return listInbox(client);` to the dispatcher block (before `--list-unread` is fine), update the error string and the top-of-file usage comment to include `--list-inbox`.

- [ ] **Step 3: Syntax-check.** Run: `node --check plugins/ms-graph/skills/ms-graph/scripts/mail.js` — Expected: no output (OK).

- [ ] **Step 4: Live smoke test.** Run from the scripts dir: `node mail.js --list-inbox --since-days=2 --top=5` — Expected: a list mixing `read`/`UNREAD` items with ids + webLinks. (Requires a profile-launched session so `GRAPH_*` are present + ms-graph signed in.)

- [ ] **Step 5: Document.** In `SKILL.md` `mail.js` bullets, add: `- List inbox (read+unread, windowed): \`node mail.js --list-inbox [--since-days=7] [--top=50]\``.

- [ ] **Step 6: Commit.** `git add` the two files; `git commit -m "feat(ms-graph): add --list-inbox (read+unread, windowed) for drainer enumerate"`.

### Task 2: personal-outlook ENUMERATE + DRAFT-MODE

**Files:**
- Modify: `plugins/drainer/skills/drainer/providers/personal-outlook-provider.md`

- [ ] **Step 1: Point ENUMERATE at `--list-inbox`.** Change the ENUMERATE section so it runs `node mail.js --list-inbox --since-days=<inbox_window_days, default 7>` and triages read+unread; dedup against seen-state is the poller's job. Keep the stable-id scheme (`poutlook-<YYYYMMDD-HHMM>-<sender>-<subj3>`).

- [ ] **Step 2: Verify DRAFT-MODE prefers reply.** Confirm the DRAFT-MODE section (added in PR #70) leads with `--reply` for thread responses and only uses `--draft-new` for a genuinely new 1:1 with no existing thread. Tighten wording if needed so reply-to-existing is the default.

- [ ] **Step 3: Commit.** `git commit -m "feat(drainer): personal-outlook enumerate read+unread; prefer reply in DRAFT-MODE"`.

### Task 3: reply-preference into message-draft

**Files:**
- Modify: `plugins/message-draft/skills/message-draft/SKILL.md`

- [ ] **Step 1: Read the skill** to find where behavioral/voice rules live.

- [ ] **Step 2: Add the rule** (in the rules/preferences area): "**Prefer replying to an existing thread over composing a fresh message.** When a relevant thread exists, draft a reply on it rather than a new email; only compose new when there's genuinely no thread to reply to."

- [ ] **Step 3: Bump** `plugins/message-draft/.claude-plugin/plugin.json` (patch).

- [ ] **Step 4: Commit.** `git commit -m "feat(message-draft): prefer replying to an existing thread over a new compose"`.

### Task 4: Stage 0 version bumps + push PR #70

- [ ] **Step 1: Bump** `plugins/ms-graph` and `plugins/drainer` plugin.json (minor) if not already at the intended version.
- [ ] **Step 2: Push** the branch; confirm PR #70 reflects all Stage 0 changes.
- [ ] **Step 3: Hand the updated PR #70 to Russell for review** (his stated preference: one review, in final shape, ideally after the Stage 1 dry-run shows it working).

---

## STAGE 1 — The continuous Outlook keeper

> Do Stage 1 on a fresh branch off `origin/main` (after Stage 0 merges) or off the Stage 0 branch. New `scripts/` dir under the drainer skill.

### Task 5: seen-state helper (`seen-state.js`)

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/seen-state.js`
- Test: `plugins/drainer/skills/drainer/scripts/seen-state.test.js` (node:test)

State lives under the project's `runtime_dir` (e.g. `~/Dev/personal-ai-pod/.tmp/drainer/`). Three concerns: processed message-ids, needs-you status (dispatched→cleared), and the fyi/junk digest queue. JSON files, atomic writes (write temp + rename). **Fail-safe: a missing/corrupt file reads as "nothing seen."**

Interface (CLI so the prose poller can call it; also unit-tested as a module):
- `node seen-state.js seen <runtimeDir> <source> <id>` → prints `yes`/`no`.
- `node seen-state.js record <runtimeDir> <source> <id> <triage>` → records id (+ status `dispatched` for needs-you); idempotent.
- `node seen-state.js open-count <runtimeDir> <source>` → prints count of needs-you items `dispatched` and not `cleared`.
- `node seen-state.js clear <runtimeDir> <source> <id>` → marks a needs-you item `cleared`.
- `node seen-state.js queue-add <runtimeDir> <source> <id> <json-file>` → append a captured fyi/junk item to the digest queue.
- `node seen-state.js queue-list <runtimeDir>` / `queue-clear <runtimeDir> <id>`.

- [ ] **Step 1: Write failing tests** for: record→seen returns yes; unknown id returns no; corrupt file → seen returns no (no throw); open-count reflects record minus clear; queue add/list/clear round-trips. (node:test + a temp dir.)
- [ ] **Step 2: Run** `node --test seen-state.test.js` → Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `seen-state.js` with atomic writes (`fs.writeFileSync(tmp); fs.renameSync(tmp, path)`), try/catch JSON parse → default empty, and the CLI dispatch.
- [ ] **Step 4: Run** `node --test seen-state.test.js` → Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(drainer): seen-state helper (fail-safe seen-ids, needs-you status, digest queue)"`.

### Task 6: presence gate (`presence.ps1`)

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/presence.ps1`

Exit 0 if the user is **present** (idle < threshold AND session unlocked); exit 1 if away/locked. Idle via `GetLastInputInfo` P/Invoke; lock via presence of `LogonUI` process (a common Windows heuristic).

- [ ] **Step 1: Implement** with a `-IdleThresholdSeconds` param (default 600). Print `present`/`away` and set exit code.
- [ ] **Step 2: Manual test.** Run it active → `present`, exit 0. (Locking to test the away path is optional/manual.)
- [ ] **Step 3: Commit.** `git commit -m "feat(drainer): presence gate (idle + lock detection)"`.

### Task 7: worker-tab spawn (`spawn-worker.ps1`)

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/spawn-worker.ps1`

Open a new Windows Terminal tab in the current window running a fresh `claude` worker session seeded to handle ONE captured item, reusing the existing `~/OneDrive/Claude/scripts/launch-session.ps1` pattern. Params: `-RepoDir`, `-ItemFile` (abs path to `items/<id>.json`), `-Model` (default `claude-opus-4-8[1m]`).

- [ ] **Step 1: Implement.** Write the seed to `<RepoDir>/.tmp/drainer/seeds/<id>.txt` containing: "You are a drainer worker. Read `~/.claude/CLAUDE.md`, then follow the drainer `engine/worker-core.md` for the single item at `<ItemFile>`. Its `source` names the provider; read that provider's CLEAR + DRAFT-MODE. Draft-only, never send. Write `items/<id>.done` last." Then invoke `wt.exe -w 0 new-tab -d <RepoDir> --title "drain:<id>" powershell -NoExit -NoProfile -File <launch-session.ps1> -Model <Model> -SeedFile <seed>` (per the launcher gotchas in `~/.claude/CLAUDE.md`).
- [ ] **Step 2: Manual test.** Create a dummy `items/test.json` and run; a titled tab should open and the worker session should start on it. Close it after.
- [ ] **Step 3: Commit.** `git commit -m "feat(drainer): spawn-worker (one Windows Terminal tab per needs-you item)"`.

### Task 8: poller engine doc (`poller-core.md`)

**Files:**
- Create: `plugins/drainer/skills/drainer/engine/poller-core.md`
- Modify: `plugins/drainer/skills/drainer/SKILL.md`

The prose procedure the headless poller follows each cycle. Content (from the spec, made concrete):
1. Run `presence.ps1`; if away → exit silently.
2. Read `.claude/drainer.local.md` (providers, `runtime_dir`, `max_open_tabs`, `inbox_window_days`, presence) + `context.md`.
3. For each enabled provider: AUTH-GLANCE; ENUMERATE candidates; for each, compute the stable id and call `seen-state.js seen` — skip if yes; triage the rest per `triage.md`.
4. Dispatch: **needs-you** → if `seen-state.js open-count` < `max_open_tabs`: CAPTURE to `items/<id>.json`, `spawn-worker.ps1`, then `seen-state.js record … needs-you`; if at cap, skip (do NOT record — retried next cycle). **fyi/junk** → CAPTURE to a queue file, `seen-state.js queue-add`, `seen-state.js record … fyi|junk`.
5. **Never clear.** Workers clear needs-you on completion; the digest clears fyi/junk after review.
6. **Dry-run:** if invoked dry-run, do steps 1–3 and print a triage report (counts + per-item call + intended action) but skip all of step 4's side effects.

- [ ] **Step 1: Write `poller-core.md`** with the above as a numbered procedure, cross-referencing `triage.md`, `worker-core.md`, the provider contract, and the scripts by path.
- [ ] **Step 2: Update `SKILL.md`** — add a "Continuous mode" note pointing at `engine/poller-core.md` (the fast loop) alongside the existing batch `driver-core.md`; add `personal-outlook` to the provider list (already done in PR #70 — verify).
- [ ] **Step 3: Commit.** `git commit -m "feat(drainer): poller-core continuous fast-loop procedure"`.

### Task 9: headless runner (`run-poller.ps1`)

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/run-poller.ps1`

The cron entry point. Params: `-RepoDir` (the drainer project, e.g. personal-ai-pod), `-DryRun` (switch). Steps: run `presence.ps1` (unless `-DryRun`); if away, exit 0 silently. Otherwise invoke headless Claude: `claude -p "<poller prompt>"` with cwd = RepoDir, where the prompt says: "Follow the drainer `engine/poller-core.md` for one fast cycle. <dry-run?>". The prompt must instruct reading the skill from the installed plugin.

- [ ] **Step 1: Implement** the runner; on `-DryRun`, pass a dry-run instruction and skip presence.
- [ ] **Step 2: Manual dry-run** (the Stage 1 tryout step 1): `powershell -File run-poller.ps1 -RepoDir ~/Dev/personal-ai-pod -DryRun` → Expected: a triage report over the backlog, no tabs, no clears. **Review with Russell; tune `context.md`/rubric.**
- [ ] **Step 3: Manual live, capped** (tryout step 2): run without `-DryRun` → ≤`max_open_tabs` worker tabs open; walk them end-to-end; confirm draft-only + clear-on-done + seen-state.
- [ ] **Step 4: Commit.** `git commit -m "feat(drainer): run-poller headless cron entry point (+ --dry-run)"`.

### Task 10: scheduled task (`register-schedule.ps1`) — only after manual validation

**Files:**
- Create: `plugins/drainer/skills/drainer/scripts/register-schedule.ps1`
- Modify: `plugins/drainer/skills/drainer/templates/drainer.local.example.md` (document `max_open_tabs`, `inbox_window_days`)

- [ ] **Step 1: Implement** register/unregister of a ~5-min `schtasks` job that runs `run-poller.ps1 -RepoDir <project>`. Params `-RepoDir`, `-IntervalMinutes` (default 5), `-Remove`.
- [ ] **Step 2: Add config keys** to the example template with comments.
- [ ] **Step 3: Do NOT auto-register.** Leave registration to Russell once the manual capped runs are trusted (tryout step 3).
- [ ] **Step 4: Bump** `plugins/drainer/.claude-plugin/plugin.json` (minor) and commit. `git commit -m "feat(drainer): scheduled-task registration for the 5-min keeper loop"`.

---

## Self-review checklist (done while writing)

- **Spec coverage:** poller (T8/T9), seen-state fail-safe (T5), presence gate (T6/T9), worker-tab spawn (T7), max_open_tabs cap (T5 open-count + T8 dispatch), dry-run (T8/T9), never-clear (T8), EOD digest = **Stage 2 (out of scope here)**, backlog sweep = **Stage 3**, read+unread enumerate (T1/T2), prefer-reply (T2/T3). ✓
- **No placeholders:** deterministic scripts carry real code/interfaces; engine-doc tasks carry the full procedure content. Test code for the one pure-logic module (seen-state) is TDD'd.
- **Type/name consistency:** `seen-state.js` verbs (`seen`/`record`/`open-count`/`clear`/`queue-add`/`queue-list`/`queue-clear`) are referenced identically in T8. `max_open_tabs`, `inbox_window_days`, `runtime_dir` consistent across T1/T5/T8/T10.

## Out of scope (later stages, own plans)
- **Stage 2:** EOD digest tab (fyi summaries + junk source-stop proposals + reconciliation sweep).
- **Stage 3:** one-time backlog sweep of old read mail.
- **Stage 4+:** Gmail provider, Trello into the loop, more sources.
- Renaming the plugin to `Skimmer`.
