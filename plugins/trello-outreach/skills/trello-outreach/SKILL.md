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
      find_card_by_name, create_card_from_template,
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

  ## Card templates

  Some boards keep **template cards** — real cards flagged `isTemplate: true` that
  hold a reusable description and set of checklists. The template *definition lives
  on the board itself*, not in code: to change the process, edit the template card
  in Trello. This skill only knows how to *apply* a template.

  Which boards have templates, the template card names, and when to apply each one
  are board-specific — read CLAUDE.local.md.

  To create a new card from a template, copying its checklists:

  ```python
  tpl = find_card_by_name(board_id, 'TEMPLATE: Sponsorship Renewal', session)
  card = create_card_from_template(list_id, tpl['id'], 'Acme Sponsorship Renewal 2027', session)
  # keep defaults to 'checklists'; pass keep='checklists,labels,attachments' for more
  ```

  Template cards are returned by `get_board_cards` like any other card (flagged
  `isTemplate`), so filter them out when iterating real cards:
  `[c for c in get_board_cards(...) if not c.get('isTemplate')]`.

  ---

  ## Verification output

  End every script with a printed summary and exactly one of:
  - `Verification passed ✅`
  - `Verification FAILED - N errors`

  Exit code 0 does not mean success — trust the printed output.

  ---

  ## Verifying mutations (read-after-write)

  Trello's bulk `GET /boards/{id}/cards` endpoint can return STALE `idLabels` (and other card fields) for some time after a mutation — observed in practice as recently-added labels not appearing in bulk reads even when correctly applied. The per-card endpoint `GET /cards/{id}` is authoritative and returns fresh data immediately.

  After any mutation (label add/remove, comment, card move, etc.), verify with a per-card GET — never re-fetch bulk board cards to check whether a mutation took effect:

  ```python
  trello_request('POST', f"/cards/{card_id}/idLabels", session, body={'value': label_id})
  for attempt in range(3):
      time.sleep(0.5)
      check = trello_request('GET', f"/cards/{card_id}", session, params={'fields': 'idLabels'})
      if label_id in check.get('idLabels', []):
          break
  ```

  This pattern also doubles as a free retry — Trello mutations occasionally fail silently (no exception raised) and a re-POST resolves it.

  ---

  ## Label colors

  `green`, `yellow`, `orange`, `red`, `purple`, `blue`, `sky`, `lime`, `pink`, `black`
---
