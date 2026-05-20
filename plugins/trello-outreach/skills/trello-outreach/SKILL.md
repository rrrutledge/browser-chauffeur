---
skill: trello-outreach
description: Create and update Trello cards, labels, and checklists for outreach tracking boards. Board IDs and configuration come from CLAUDE.local.md — check there first.
instructions: |-
  ## Trello Outreach Skill

  Board configuration (IDs, lists, labels) lives in CLAUDE.local.md. Read it first.

  ---

  ## trello_utils

  Shared library at `~/OneDrive/Claude/scripts/trello_utils.py`. Import with:

  ```python
  sys.stdout.reconfigure(encoding='utf-8')  # required on Windows for Unicode output
  sys.path.insert(0, os.path.expanduser('~/OneDrive/Claude/scripts'))
  from trello_utils import (
      get_trello_session, trello_request,
      get_board_lists, get_board_cards, get_board_labels,
      create_card, update_card, delete_card,
      create_label, add_label_to_card, get_or_create_list,
  )
  ```

  `get_trello_session()` reads TRELLO_API_KEY and TRELLO_TOKEN from Windows Credential
  Manager — no credential handling needed in the script.

  ---

  ## Checklists (not in trello_utils — use trello_request directly)

  ```python
  checklist = trello_request('POST', '/checklists', session, body={'idCard': card_id, 'name': 'Actions'})
  trello_request('POST', f'/checklists/{checklist["id"]}/checkItems', session, body={'name': 'Contact identified', 'pos': 'bottom'})
  ```

  ---

  ## Updating from transcripts

  Batch-update cards based on meeting transcript follow-ups using:
  `~/OneDrive/Claude/scripts/update-trello-from-transcript.py`

  **Usage:**
  ```bash
  python ~/OneDrive/Claude/scripts/update-trello-from-transcript.py config.json
  ```

  **Config format:**
  ```json
  {
    "board_id": "board-id-here",
    "abandoned_list_name": "Abandoned",
    "updates": [
      {
        "search": ["keyword1", "keyword2"],
        "search_type": "name",
        "action": "due_date",
        "days_offset": 1,
        "desc": "Description"
      },
      {
        "search": ["Secrets Migration"],
        "search_type": "label",
        "action": "due_date",
        "days_offset": 1,
        "desc": "All cards with Secrets Migration label"
      },
      {
        "search": ["keyword"],
        "search_type": "name",
        "action": "abandon",
        "desc": "Description"
      }
    ]
  }
  ```

  **Search types:**
  - `"name"` (default): Search card names and descriptions for keywords
  - `"label"`: Find cards with a label matching the search term (case-insensitive, partial match OK)
  - When searching by label, all cards with that label will be affected

  **Actions:**
  - `due_date`: Set card due date (requires days_offset)
  - `abandon`: Move card to the abandoned list

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
