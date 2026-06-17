"""Today's outreach queue across the configured Trello boards (READ-ONLY).

A card is in the queue if its due date <= end of today (overdue counts) and it sits
in an active outreach list (not a terminal/parking list). Boards, skip-lists, and the
label vocabulary all come from the machine-local config.json -> "outreach"; this file
has no hardcoded identifiers.

Outputs a human summary to stdout and a machine queue to <runtime_dir>/outreach/queue.json.
Usage:  python utils/trello_queue.py
"""
import datetime
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from trello_client import board_cards, board_lists, load_config, local_dir


def classify_labels(labels, channels, features):
    channel, feats, contacts = None, [], []
    for l in labels:
        name = l.get("name")
        if not name:
            continue
        if name in channels:
            channel = name
        elif name in features:
            feats.append(name)
        else:
            contacts.append(name)
    return channel, feats, contacts


def slug(card):
    short = card["id"][-6:]
    base = "".join(ch if ch.isalnum() else "-" for ch in card["name"].lower()).strip("-")
    base = "-".join(p for p in base.split("-") if p)[:32]
    return f"{base}-{short}"


def build_queue(cfg):
    oc = cfg["outreach"]
    skip = set(oc.get("skip_lists", []))
    channels = set(oc["label_vocab"]["channels"])
    features = set(oc["label_vocab"]["features"])
    now = datetime.datetime.now(datetime.timezone.utc)
    end_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    queue = []
    for board in oc["boards"]:
        lists = {l["id"]: l["name"] for l in board_lists(board["id"])}
        for c in board_cards(board["id"]):
            list_name = lists.get(c.get("idList"), "?")
            if list_name in skip:
                continue
            d = c.get("due")
            if d:
                due_dt = datetime.datetime.fromisoformat(d.replace("Z", "+00:00"))
                if due_dt > end_today:
                    continue
            else:
                due_dt = None
            channel, feats, contacts = classify_labels(c.get("labels", []), channels, features)
            queue.append({
                "id": slug(c), "cardId": c["id"], "board": board["name"],
                "boardId": board["id"], "list": list_name, "name": c["name"],
                "due": due_dt.date().isoformat() if due_dt else None,
                "overdue": due_dt < now if due_dt else False,
                "url": c.get("shortUrl") or c.get("url"),
                "channel": channel, "features": feats, "contacts": contacts,
                "desc": c.get("desc", ""),
            })

    queue.sort(key=lambda x: (x["due"] is None, x["due"]))
    runtime = cfg.get("runtime_dir", ".tmp/drainer")
    if not os.path.isabs(runtime):
        runtime = os.path.join(local_dir(), runtime)
    out_dir = os.path.join(runtime, "outreach")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "queue.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    return queue, out_file


def main():
    cfg = load_config()
    queue, out_file = build_queue(cfg)
    print(f"Today's outreach queue ({len(queue)} cards):\n")
    for q in queue:
        flag = " (OVERDUE)" if q["overdue"] else ""
        who = ", ".join(q["contacts"]) or "?"
        print(f"  [{q['id']}]  {q['board']} / {q['list']}")
        print(f"     {q['name']}  | due {q['due'] or 'none'}{flag}")
        print(f"     channel: {q['channel'] or '?'}   contact: {who}   features: {', '.join(q['features']) or '-'}")
        print(f"     {q['url']}\n")
    print(f"Queue written to {out_file}")


if __name__ == "__main__":
    main()
