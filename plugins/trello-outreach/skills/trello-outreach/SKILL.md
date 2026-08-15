---
skill: trello-outreach
description: The outreach-funnel process layer over Trello - when and why to open, advance, dedupe, and route cards across the outreach boards, plus the board registry and initiative model. The Trello API mechanics (card/comment/label/checklist CRUD, the client library) are the separate `trello` skill.
instructions: |-
  ## Trello outreach

  The process layer for running outreach on Trello boards: when and why to open a card, how to keep one
  card per entity, which board a card belongs on, and the initiative model behind the funnel. The Trello
  mechanics - card, comment, label, checklist, and list operations, the client library, and the API
  gotchas - are the **`trello`** skill. This skill decides *what* to do; `trello` carries it out through
  `trello_utils.py`. Every Trello read or write still goes through `trello`, never the REST API directly.

  Board configuration - board names, IDs, purposes, per-board lists and labels, and template-card notes -
  lives in the project's `trello-boards.yaml` registry, the single source of truth shared with the
  drainer's trello provider. Read it first.

  ---

  ## Before creating a card - search the boards first

  When the thing to track is a **named entity** - a sponsor, a company, a contact, a target role - it
  very likely already has a card somewhere in the funnel; that's what the outreach boards are. So before
  creating one, **search every board in `trello-boards.yaml` for an existing card for that entity, and
  update that card instead.** Creating is the fallback once the search comes up empty, never the first
  move. (This applies to any card keyed to a person or organization; a genuinely new one-off admin task
  with no entity behind it can skip straight to creating.)

  ```python
  # trello_utils comes from the `trello` skill's scripts/ directory
  from trello_utils import get_trello_session, get_board_cards
  s = get_trello_session()
  BOARDS = {  # from trello-boards.yaml - every board, so the search is complete
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
    advance/reschedule it, post a dated comment recording what happened (via `add_comment`), and set the
    next due date. The existing card is the source of truth and carries the entity's whole history - keep
    it there.
  - **Nothing matches → create on the entity's OWN board.** A sponsor/company or its contact belongs on
    that campaign's outreach board (match by the registry `purpose`/`initiative`), not as a generic
    reminder on a catch-all board. Put the card where that entity's funnel lives so it isn't orphaned
    from its history.

  **A freshly-created card with no Start/Due is eligible for drainer pickup on the very next cycle** -
  see the `trello` skill's "Guarding a new card against the drainer" for how to give it a date up front
  or, for the rare card that must stay undated while you keep working it, pre-register it as seen.

  ---

  ## Mechanics live in the `trello` skill

  Everything about *carrying out* a Trello change is in the **`trello`** skill: the `trello_utils.py`
  import pattern, card/comment/label CRUD, checklists, card templates, the ⛔ Blocked dependency model,
  read-after-write verification, and the label-color vocabulary. Open a card, advance one, post a comment,
  apply a template, or set a blocked relationship through that skill's wrappers.
---
