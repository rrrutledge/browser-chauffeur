---
# Per-machine drainer settings. Copy to .claude/drainer.local.md in your project and fill in.
# Everything machine/user-specific lives here; the engine (plugin) stays generic.

# Folder holding this machine's context.md and providers/ (commit it wherever you like, or not).
local_dir: C:\path\to\your\drainer-local
runtime_dir: .tmp/drainer

# The source registry. One entry per active source. provider/worker paths are relative to local_dir.
channels:
  outlook:
    provider: providers/outlook-channel.md
    worker: providers/outlook-worker-prompt.txt
    idPrefix: outlook-
    bodyExt: email.md
    cadence: continuous
  # gmail: { provider: providers/gmail-channel.md, worker: providers/gmail-worker-prompt.txt, idPrefix: gmail-, bodyExt: email.md, cadence: continuous }
  # slack:  { provider: providers/slack-channel.md,  worker: providers/slack-worker-prompt.txt,  idPrefix: slack-,  bodyExt: msg.md,   cadence: continuous }

# Trello (or other) outreach boards drained once a day. The due date IS the queue.
outreach:
  boards:
    - name: "<Board name>"
      id: "<board id>"
  skip_lists: [Abandoned, Finished, Adopted, Templates]
  label_vocab:
    channels: [Email, Teams, Slack]
    features: ["<feature label>"]
    # any label not in channels/features is treated as a contact name

cadence:
  sweep_interval_minutes: 12
  once_a_day_window_start: "04:30"
  once_a_day_window_hours: 8

presence:
  gate_on_presence: true
  idle_threshold_seconds: 600
---

# drainer.local

Free-form notes about this machine's drainer setup (which sources are live, quirks, etc.).
Credentials never go here — keep them in your OS credential store / environment.
