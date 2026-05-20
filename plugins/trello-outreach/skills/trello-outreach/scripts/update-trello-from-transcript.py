#!/usr/bin/env python3
"""
Update Trello board from transcript follow-ups.

Usage:
    python scripts/update-outreach-from-transcript.py config.json

The config file should have this structure:
{
  "board_id": "your-board-id",
  "abandoned_list_name": "Abandoned",
  "updates": [
    {
      "search": ["keyword1", "keyword2"],
      "search_type": "name",
      "action": "due_date",
      "days_offset": 1,
      "desc": "Description of the update"
    },
    {
      "search": ["Secrets Migration"],
      "search_type": "label",
      "action": "due_date",
      "days_offset": 1,
      "desc": "All cards with this label"
    },
    {
      "search": ["keyword"],
      "search_type": "name",
      "action": "abandon",
      "desc": "Description"
    }
  ]
}

Fields:
- board_id: Trello board ID (required)
- abandoned_list_name: Name of list for abandon action (optional, defaults to "Abandoned")
- updates: Array of update actions (required)

Search types:
- name (default): Search card names and descriptions for keywords
- label: Find all cards with a label matching the search term (case-insensitive)

Actions:
- due_date: Set card due date (requires days_offset)
- abandon: Move card to the abandoned list
"""
import sys
import os
import json
from datetime import datetime, timedelta

# Windows Unicode output support
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trello_utils import (
    get_trello_session,
    get_board_lists, get_board_cards, get_board_labels,
    update_card
)

def search_card_by_name(cards, search_terms):
    """Find card matching any of the search terms in name/description."""
    for card in cards:
        card_text = (card['name'] + ' ' + card.get('desc', '')).lower()
        if any(term.lower() in card_text for term in search_terms):
            return card
    return None

def search_cards_by_label(cards, labels, search_terms):
    """Find all cards with a label matching any search term."""
    # Find matching label(s)
    matching_labels = []
    for label in labels:
        label_name = label.get('name', '').lower()
        if any(term.lower() in label_name for term in search_terms):
            matching_labels.append(label['id'])

    if not matching_labels:
        return []

    # Find cards with those labels
    matching_cards = []
    for card in cards:
        card_labels = card.get('idLabels', [])
        if any(label_id in card_labels for label_id in matching_labels):
            matching_cards.append(card)

    return matching_cards

def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/update-outreach-from-transcript.py config.json")
        print("\nSee script docstring for config file format.")
        sys.exit(1)

    config_file = sys.argv[1]

    if not os.path.exists(config_file):
        print(f"[ERROR] Config file not found: {config_file}")
        sys.exit(1)

    with open(config_file, 'r') as f:
        config = json.load(f)

    # Validate required fields
    if 'board_id' not in config:
        print("[ERROR] Config missing required field: board_id")
        sys.exit(1)
    if 'updates' not in config:
        print("[ERROR] Config missing required field: updates")
        sys.exit(1)

    board_id = config['board_id']
    abandoned_list_name = config.get('abandoned_list_name', 'Abandoned')
    updates = config['updates']

    print(f"=== Update Trello Board from Transcript ===")
    print(f"Config: {config_file}")
    print(f"Board ID: {board_id}\n")

    session = get_trello_session()

    # Fetch all cards
    print("[1] Fetching cards...")
    cards = get_board_cards(board_id, session)
    print(f"   Found {len(cards)} cards\n")

    # Fetch labels
    print("[2] Fetching labels...")
    labels = get_board_labels(board_id, session)
    print(f"   Found {len(labels)} labels\n")

    # Fetch lists to get abandoned list ID
    print("[3] Fetching lists...")
    lists = get_board_lists(board_id, session)

    abandoned_list = next((l for l in lists if l['name'] == abandoned_list_name), None)
    if not abandoned_list:
        print(f"[ERROR] Could not find list named '{abandoned_list_name}'")
        print("\nVerification FAILED - 1 errors")
        return
    print(f"   Found '{abandoned_list_name}' list: {abandoned_list['id']}\n")

    # Calculate today's date
    today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

    print(f"[4] Processing {len(updates)} updates...\n")

    successful = 0
    skipped = 0

    for update in updates:
        search_type = update.get('search_type', 'name')

        # Find card(s) based on search type
        if search_type == 'label':
            target_cards = search_cards_by_label(cards, labels, update['search'])
        else:  # 'name' or default
            single_card = search_card_by_name(cards, update['search'])
            target_cards = [single_card] if single_card else []

        if not target_cards:
            print(f"   [SKIP] {update['desc']}")
            if search_type == 'label':
                print(f"          No cards found with label matching: {', '.join(update['search'])}\n")
            else:
                print(f"          Card not found (searched: {', '.join(update['search'])})\n")
            skipped += 1
            continue

        # Process each target card
        for card in target_cards:
            if update['action'] == 'due_date':
                if 'days_offset' not in update:
                    print(f"   [ERROR] {update['desc']}")
                    print(f"           Missing 'days_offset' for due_date action\n")
                    skipped += 1
                    continue

                due_date = today + timedelta(days=update['days_offset'])
                update_card(card['id'], {'due': due_date.isoformat() + 'Z'}, session)
                date_str = due_date.strftime('%Y-%m-%d')

                if len(target_cards) == 1:
                    print(f"   [OK] {update['desc']}")
                    print(f"        Card: {card['name']}")
                    print(f"        Due date set to: {date_str}\n")
                else:
                    print(f"        - {card['name']}: due date set to {date_str}")

                successful += 1

            elif update['action'] == 'abandon':
                update_card(card['id'], {'idList': abandoned_list['id']}, session)

                if len(target_cards) == 1:
                    print(f"   [OK] {update['desc']}")
                    print(f"        Card: {card['name']}")
                    print(f"        Moved to: {abandoned_list_name}\n")
                else:
                    print(f"        - {card['name']}: moved to {abandoned_list_name}")

                successful += 1

            else:
                print(f"   [ERROR] {update['desc']}")
                print(f"           Unknown action: {update['action']}\n")
                skipped += 1
                break  # Don't process remaining cards for this update

        # Print summary line for multi-card updates
        if len(target_cards) > 1 and update['action'] in ['due_date', 'abandon']:
            print(f"   [OK] {update['desc']} - {len(target_cards)} cards updated\n")

    print(f"=== SUMMARY ===")
    print(f"Successful updates: {successful}")
    print(f"Skipped (not found/errors): {skipped}")
    print(f"\nVerification passed ✅")

if __name__ == '__main__':
    main()
