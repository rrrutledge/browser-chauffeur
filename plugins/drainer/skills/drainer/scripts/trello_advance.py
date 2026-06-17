"""Advance one outreach card after the user has sent/handled the drafted message.

The outreach source's "advance the item" step (the analogue of deleting a handled
email). All Trello mutations go through here. No hardcoded identifiers — board ids
are passed in; credentials come from env (see trello_client).

Actions:
  nudge   --card <id> [--days N] --comment "..."          bump due out N days (default 3)
  advance --card <id> --board <id> --to-list NAME [--days N] --comment "..."
                                                          move to a later stage + set due
  stop    --card <id> --board <id> [--to-list NAME] --comment "..."
                                                          move to Abandoned (default) + clear due
"""
import argparse
import datetime
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from trello_client import add_comment, board_lists, request, update_card


def find_list_id(board_id, list_name):
    for l in board_lists(board_id):
        if l["name"].lower() == list_name.lower():
            return l["id"]
    raise SystemExit(f"FAILED: list '{list_name}' not found on board {board_id}")


def verify_card(card_id, expect_list=None, expect_due_present=None):
    c = None
    for _ in range(3):
        time.sleep(0.5)
        c = request("GET", f"/cards/{card_id}", params={"fields": "idList,due", "list": "true"})
        ok = True
        if expect_list is not None:
            ok = ok and (c.get("list", {}).get("name", "").lower() == expect_list.lower())
        if expect_due_present is not None:
            ok = ok and (bool(c.get("due")) == expect_due_present)
        if ok:
            return c
    return c


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["nudge", "advance", "stop"])
    p.add_argument("--card", required=True)
    p.add_argument("--board")
    p.add_argument("--to-list")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--comment", required=True)
    a = p.parse_args()

    today = datetime.datetime.now(datetime.timezone.utc)
    stamp = today.date().isoformat()

    if a.action == "nudge":
        new_due = (today + datetime.timedelta(days=a.days)).replace(hour=0, minute=0, second=0, microsecond=0)
        update_card(a.card, {"due": new_due.isoformat()})
        add_comment(a.card, f"[{stamp}] {a.comment} (follow-up due {new_due.date()})")
        verify_card(a.card, expect_due_present=True)
        print(f"NUDGE: due bumped to {new_due.date()}")

    elif a.action == "advance":
        if not (a.board and a.to_list):
            raise SystemExit("advance requires --board and --to-list")
        list_id = find_list_id(a.board, a.to_list)
        new_due = (today + datetime.timedelta(days=a.days)).replace(hour=0, minute=0, second=0, microsecond=0)
        update_card(a.card, {"idList": list_id, "due": new_due.isoformat()})
        add_comment(a.card, f"[{stamp}] {a.comment} (moved to {a.to_list}; next due {new_due.date()})")
        verify_card(a.card, expect_list=a.to_list, expect_due_present=True)
        print(f"ADVANCE: moved to '{a.to_list}', due {new_due.date()}")

    elif a.action == "stop":
        if not a.board:
            raise SystemExit("stop requires --board")
        target = a.to_list or "Abandoned"
        list_id = find_list_id(a.board, target)
        update_card(a.card, {"idList": list_id, "due": ""})
        add_comment(a.card, f"[{stamp}] {a.comment} (stopped — moved to {target})")
        verify_card(a.card, expect_list=target, expect_due_present=False)
        print(f"STOP: moved to '{target}', due cleared")


if __name__ == "__main__":
    main()
