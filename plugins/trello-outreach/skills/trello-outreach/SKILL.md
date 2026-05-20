---
skill: trello-outreach
description: Create and update Trello cards, labels, and checklists for outreach tracking boards. Board IDs and configuration come from CLAUDE.local.md — check there first.
instructions: |-
  ## Trello Outreach Skill

  Board configuration (IDs, lists, labels) lives in CLAUDE.local.md. Read it first.

  ---

  ## Scripts

  All scripts are in the `scripts/` directory next to this SKILL.md file.

  ### trello_utils.py

  Shared Trello API library. Import it from your `.tmp/` scripts:

  ```python
  sys.stdout.reconfigure(encoding='utf-8')  # required on Windows for Unicode output
  sys.path.insert(0, '<path-to-skill>/scripts')
  from trello_utils import (
      get_trello_session, trello_request,
      get_board_lists, get_board_cards, get_board_labels,
      create_card, update_card, delete_card,
      create_label, add_label_to_card, get_or_create_list,
  )
  ```

  `get_trello_session()` reads TRELLO_API_KEY and TRELLO_TOKEN from Windows Credential
  Manager — no credential handling needed in the script.

  ### update-trello-from-transcript.py

  Batch-update cards based on meeting transcript follow-ups. See the script's
  docstring for the full config JSON format.

  ```bash
  python <path-to-skill>/scripts/update-trello-from-transcript.py config.json
  ```

  ---

  ## Checklists

  Checklists aren't in trello_utils — use `trello_request` directly:

  ```python
  checklist = trello_request('POST', '/checklists', session, body={'idCard': card_id, 'name': 'Actions'})
  trello_request('POST', f'/checklists/{checklist["id"]}/checkItems', session, body={'name': 'Contact identified', 'pos': 'bottom'})
  ```

  ---

  ## Verification output

  End every script with a printed summary and exactly one of:
  - `Verification passed ✅`
  - `Verification FAILED - N errors`

  Exit code 0 does not mean success — trust the printed output.

  ---

  ## Label colors

  `green`, `yellow`, `orange`, `red`, `purple`, `blue`, `sky`, `lime`, `pink`, `black`
---
