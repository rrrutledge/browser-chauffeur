---
skill: trello-outreach
description: Create and update Trello cards, checklists, and labels on any Trello tracking board. Board IDs and per-board configuration come from the project's trello-boards.yaml registry — check there first.
instructions: |-
  ## Trello Skill

  Works on any Trello tracking board. It's the mechanics layer: card/checklist/label CRUD plus the
  Trello gotchas. When and why to open a card is project policy (e.g. personal-ai-pod's CLAUDE.md and
  initiatives), not this skill.

  Board configuration — board names, IDs, purposes, per-board lists/labels, and template-card notes —
  lives in the project's `trello-boards.yaml` registry (the single source of truth, shared with the
  drainer's trello provider). Read it first.

  ---

  ## Before creating a card — search the boards first

  When the thing to track is a **named entity** — a sponsor, a company, a contact, a target role —
  it very likely already has a card somewhere in the funnel; that's what the outreach boards are.
  So before creating one, **search every board in `trello-boards.yaml` for an existing card for that
  entity, and update that card instead.** Creating is the fallback once the search comes up empty,
  never the first move. (This applies to any card keyed to a person or organization; a genuinely new
  one-off admin task with no entity behind it can skip straight to creating.)

  ```python
  from trello_utils import get_trello_session, get_board_cards
  s = get_trello_session()
  BOARDS = {  # from trello-boards.yaml — every board, so the search is complete
      'Summit Sponsorship Outreach': 'mvL6EGtH',
      'Executive Director Outreach': 'hpvdRw3G',
      # ...the rest of the registry...
  }
  entity = 'JetBrains'
  hits = [(b, c) for b, bid in BOARDS.items()
          for c in get_board_cards(bid, s)
          if entity.lower() in (c.get('name', '') + ' ' + c.get('desc', '')).lower()]
  ```

  - **A card exists → update it, don't duplicate.** Fold the new development into the existing card:
    advance/reschedule it, post a dated comment recording what happened, and set the next due date.
    The existing card is the source of truth and carries the entity's whole history — keep it there.
  - **Nothing matches → create on the entity's OWN board.** A sponsor/company or its contact belongs
    on that campaign's outreach board (match by the registry `purpose`/`initiative`), not as a generic
    reminder on a catch-all board. Put the card where that entity's funnel lives so it isn't orphaned
    from its history.

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

  ## Blocked cards

  Creating or editing a card that's blocked on another card finishing: apply the ⛔ Blocked label and add
  a `Blocked-by: <upstream-shortlink>` line to the description, together, in the same operation.

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
  are board-specific — read `trello-boards.yaml`.

  To create a new card from a template, copying its checklists:

  ```python
  tpl = find_card_by_name(board_id, 'TEMPLATE: Sponsorship Renewal', session)
  card = create_card_from_template(list_id, tpl['id'], 'Acme Sponsorship Renewal 2027', session)
  # keep defaults to 'checklists'; pass keep='checklists,labels,attachments' for more
  ```

  Template cards are returned by `get_board_cards` like any other card (flagged
  `isTemplate`), so filter them out when iterating real cards:
  `[c for c in get_board_cards(...) if not c.get('isTemplate')]`.

  A template card still renders as a normal (badged) card in whatever list it
  lives in — it is **not** hidden from the board. To keep templates out of an
  active funnel, park them in a dedicated list (e.g. a "Templates" list). The
  list they sit in doesn't matter to `find_card_by_name` — it matches by name.

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
