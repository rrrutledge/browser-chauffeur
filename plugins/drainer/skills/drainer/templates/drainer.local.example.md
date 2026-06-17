---
# Per-machine drainer settings. Copy to .claude/drainer.local.md in your project and fill in.
# Everything machine/user-specific lives here; the plugin (engine + shared providers) stays generic.

# Which shared providers to run. Reference the bundled ones by name (they live in the plugin's
# providers/ dir); a custom one would point at local_dir/providers/<name>-channel.md instead.
channels:
  outlook:                       # Outlook on the web (browser) — no config, just sign in
    provider: outlook
    cadence: continuous
  teams:                         # Microsoft Teams on the web (browser) — no config, just sign in
    provider: teams
    cadence: continuous

# Outreach (Trello) — drained once a day; the due date IS the queue. Handled via the trello-outreach
# skill. Credentials come from TRELLO_KEY / TRELLO_TOKEN in the environment.
outreach:
  provider: trello
  cadence: daily
  boards:
    - name: "<Board name>"
      id: "<board id>"
  skip_lists: [Abandoned, Finished, Adopted, Templates]
  label_vocab:
    channels: [Email, Teams, Slack]
    features: ["<feature label>"]
    # any label not in channels/features is treated as a contact name

# A folder you control, holding context.md and any CUSTOM providers/. (Shared providers need no
# local_dir.) Commit it wherever you like, or not.
local_dir: C:\path\to\your\drainer-local

runtime_dir: .tmp/drainer

cadence:
  continuous_interval_minutes: 12
  daily_window_start: "04:30"
  daily_window_hours: 8

presence:
  gate_on_presence: true
  idle_threshold_seconds: 600
---

# drainer.local

Free-form notes about this machine's drainer setup (which sources are live, quirks, etc.).
Credentials never go here — keep them in your OS credential store / environment.
