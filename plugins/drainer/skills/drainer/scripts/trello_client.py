"""Tiny self-contained Trello REST client for the drainer outreach source.

No external deps, no hardcoded identifiers. Credentials come from the environment:
  TRELLO_KEY, TRELLO_TOKEN
Board IDs, skip-lists, and label vocab come from the machine's local config.json
(see templates/config.example.json -> "outreach"). This file is engine-generic and
safe to commit; everything user/org-specific is injected via config + env.
"""
import json
import os
import urllib.parse
import urllib.request

API = "https://api.trello.com/1"


def _creds():
    key, token = os.environ.get("TRELLO_KEY"), os.environ.get("TRELLO_TOKEN")
    if not key or not token:
        raise SystemExit("Set TRELLO_KEY and TRELLO_TOKEN in the environment.")
    return key, token


def request(method, path, params=None, body=None):
    key, token = _creds()
    params = dict(params or {})
    params.update({"key": key, "token": token})
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else None


def board_lists(board_id):
    return request("GET", f"/boards/{board_id}/lists")


def board_cards(board_id):
    return request("GET", f"/boards/{board_id}/cards",
                   params={"fields": "name,due,idList,labels,shortUrl,url,desc"})


def update_card(card_id, fields):
    return request("PUT", f"/cards/{card_id}", body=fields)


def add_comment(card_id, text):
    return request("POST", f"/cards/{card_id}/actions/comments", body={"text": text})


# Per-machine settings come from .claude/drainer.local.md — see drainer_settings.py.
from drainer_settings import load_settings, local_dir  # noqa: E402,F401


def load_config():
    """Load per-machine settings from .claude/drainer.local.md."""
    return load_settings()
