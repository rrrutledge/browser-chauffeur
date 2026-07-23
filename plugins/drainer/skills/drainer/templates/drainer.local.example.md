---
# Per-machine drainer settings. Copy to .claude/drainer.local.md in your project and fill in.
# Everything machine/user-specific lives here; the plugin (engine + providers) stays generic.

# Which providers to run, plus any config each needs. Reference a provider by name (they live in the
# plugin's providers/ dir). All sources are harvested every run on one schedule.
providers:
  orphan-sessions: {}         # crash-recovered Claude Code sessions (session-mgr) — no config; always dispatches first
  outlook: {}                    # work Outlook on the web (browser) — no config, just sign in
  outlook-graph: {}           # personal Outlook.com via the Microsoft Graph API (ms-graph; no browser)
  teams: {}                      # Microsoft Teams on the web (browser) — no config, just sign in
  trello:                        # outreach boards (via the trello-outreach skill)
    boards:
      - name: "<Board name>"
        id: "<board id>"
    skip_lists: [Abandoned, Finished, Adopted, Templates]
    label_vocab:
      channels: [Email, Teams, Slack]
      features: ["<feature label>"]
      # any label not in channels/features is treated as a contact name
  # slack:                       # example of another config-bearing provider (future)
  #   workspace: your-workspace  # the <workspace>.slack.com subdomain

# Credentials never go here — keep them in your OS credential store / environment
# (e.g. TRELLO_KEY / TRELLO_TOKEN for the trello provider).

# A folder you control, holding context.md (your world + standing rules). Commit it wherever, or not.
local_dir: C:\path\to\your\drainer-local
runtime_dir: .tmp/drainer

# Actual poll cadence is the DrainerKeeper scheduled task's own repeat interval, not a config
# value here - the poller has no internal cadence knob.
presence:
  idle_threshold_seconds: 600

# Continuous-keeper (run-poller.py) knobs.
target_open_tabs: 12          # target total live Claude Code tabs system-wide (worker tabs + the drainer
                             # itself + any tab opened by hand) — dispatch as fast as possible below this,
                             # hold and retry on later cycles once it's reached (fail-safe throttle).
max_messages_per_cycle: 50   # how many inbox items each cycle enumerates (newest-first, NO time window);
                             # the keeper drains the whole inbox a batch at a time across cycles to zero.

# Worker model per item — the poller picks by triage complexity (simple -> worker_model,
# complex -> worker_model_complex). Set an EXPLICIT model so workers don't inherit a 1M-context
# session default the account may lack credits for. Use standard-context ids (no [1m]).
worker_model: claude-sonnet-5            # simple items (quick replies, trivial actions)
worker_model_complex: claude-opus-4-8    # complex items (multi-step work, code, delicate messages)
triage_model: claude-sonnet-5            # the per-cycle batched triage call (also pinned, standard context)

# EOD digest (run-digest.py) — the once-a-day interactive slow loop.
digest_model: claude-opus-4-8   # the digest session (summarize fyi, group junk); standard context
orphan_grace_minutes: 15        # the poller re-queues any item whose source object is still unhandled with
                                # no live worker process on it - there is no time limit on an open tab.
                                # This grace only stops a just-spawned tab (process not up yet) from being
                                # misread as dead.
digest_time: "17:00"            # wall-clock time (HH:MM, 24h) the daily digest task fires (used by the installer).
---

# drainer.local

Free-form notes about this machine's drainer setup (which sources are live, quirks, etc.).
Credentials never go here — keep them in your OS credential store / environment.
