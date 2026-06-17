---
# Per-machine drainer settings. Copy to .claude/drainer.local.md in your project and fill in.
# Everything machine/user-specific lives here; the plugin (engine + shared providers) stays generic.

# Which shared providers to run, plus any config that provider needs. Reference a shared provider by
# name (they live in the plugin's providers/ dir). All sources are harvested every run on one schedule.
channels:
  outlook:                       # work Outlook on the web (browser) — no config, just sign in
    provider: outlook
  teams:                         # Microsoft Teams on the web (browser) — no config, just sign in
    provider: teams
  trello:                        # outreach boards (via the trello-outreach skill)
    provider: trello
    boards:
      - name: "<Board name>"
        id: "<board id>"
    skip_lists: [Abandoned, Finished, Adopted, Templates]
    label_vocab:
      channels: [Email, Teams, Slack]
      features: ["<feature label>"]
      # any label not in channels/features is treated as a contact name
  # slack:                       # example of another config-bearing provider (future)
  #   provider: slack
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
---

# drainer.local

Free-form notes about this machine's drainer setup (which sources are live, quirks, etc.).
Credentials never go here — keep them in your OS credential store / environment.
