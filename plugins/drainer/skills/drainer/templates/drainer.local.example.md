---
# Per-machine drainer settings. Copy to .claude/drainer.local.md in your project and fill in.
# Everything machine/user-specific lives here; the plugin (engine + providers) stays generic.

# Which providers to run, plus any config each needs. Reference a provider by name (they live in the
# plugin's providers/ dir). All sources are harvested every run on one schedule.
providers:
  outlook: {}                    # work Outlook on the web (browser) — no config, just sign in
  personal-outlook: {}           # personal Outlook.com via the Microsoft Graph API (ms-graph; no browser)
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

# One schedule for everything; set it for the fastest-arriving source. Cheap sources ride along.
cadence:
  harvest_interval_minutes: 12

presence:
  gate_on_presence: true
  idle_threshold_seconds: 600

# Continuous-keeper (run-poller.py) knobs.
max_open_tabs: 3              # max concurrent needs-you worker tabs dispatched-but-not-cleared; a burst
                             # beyond this is held and retried on later cycles (fail-safe throttle).
max_messages_per_cycle: 50   # how many inbox items each cycle enumerates (newest-first, NO time window);
                             # the keeper drains the whole inbox a batch at a time across cycles to zero.

# Worker model per item — the poller picks by triage complexity (simple -> worker_model,
# complex -> worker_model_complex). Set an EXPLICIT model so workers don't inherit a 1M-context
# session default the account may lack credits for. Use standard-context ids (no [1m]).
worker_model: claude-sonnet-4-6          # simple items (quick replies, trivial actions)
worker_model_complex: claude-opus-4-8    # complex items (multi-step work, code, delicate messages)
triage_model: claude-sonnet-4-6          # the per-cycle batched triage call (also pinned, standard context)
---

# drainer.local

Free-form notes about this machine's drainer setup (which sources are live, quirks, etc.).
Credentials never go here — keep them in your OS credential store / environment.
