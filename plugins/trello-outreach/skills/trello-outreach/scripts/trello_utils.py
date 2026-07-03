"""
Shared Trello API utilities.

Board-specific settings (board ID, label names, colors, status-to-list mappings)
live in CLAUDE.local.md. This module provides the generic API operations.
"""

import ctypes
import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BASE_URL = 'https://api.trello.com/1'


def _read_windows_credential(target):
    """Read a credential from Windows Credential Manager via ctypes."""
    try:
        import ctypes.wintypes

        class _CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ('Flags', ctypes.wintypes.DWORD),
                ('Type', ctypes.wintypes.DWORD),
                ('TargetName', ctypes.c_wchar_p),
                ('Comment', ctypes.c_wchar_p),
                ('LastWritten', ctypes.c_ulonglong),
                ('CredentialBlobSize', ctypes.wintypes.DWORD),
                ('CredentialBlob', ctypes.c_void_p),
                ('Persist', ctypes.wintypes.DWORD),
                ('AttributeCount', ctypes.wintypes.DWORD),
                ('Attributes', ctypes.c_void_p),
                ('TargetAlias', ctypes.c_wchar_p),
                ('UserName', ctypes.c_wchar_p),
            ]

        advapi32 = ctypes.WinDLL('advapi32')
        cred_ptr = ctypes.c_void_p()
        if advapi32.CredReadW(target, 1, 0, ctypes.byref(cred_ptr)):
            cred = ctypes.cast(cred_ptr, ctypes.POINTER(_CREDENTIAL)).contents
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            advapi32.CredFree(cred_ptr)
            return blob.decode('utf-16-le')
    except Exception:
        pass
    return None


def get_trello_session():
    api_key = os.environ.get('TRELLO_API_KEY') or _read_windows_credential('TRELLO_API_KEY')
    token = os.environ.get('TRELLO_TOKEN') or _read_windows_credential('TRELLO_TOKEN')
    if not api_key or not token:
        raise RuntimeError(
            'Trello credentials not found. Set TRELLO_API_KEY and TRELLO_TOKEN env vars, '
            'or store them in Windows Credential Manager under those names.'
        )
    return api_key, token


def trello_request(method, path, session, params=None, body=None):
    api_key, token = session
    url = f'{BASE_URL}{path}'

    query = {'key': api_key, 'token': token}
    if params:
        query.update(params)

    if method == 'GET' or method == 'DELETE':
        url = f'{url}?{urllib.parse.urlencode(query)}'
        data = None
    else:
        url = f'{url}?{urllib.parse.urlencode(query)}'
        data = urllib.parse.urlencode(body).encode() if body else b''

    req = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(req) as response:
        raw = response.read().decode()
        if raw:
            return json.loads(raw)
        return None


def get_board_lists(board_id, session):
    return trello_request('GET', f'/boards/{board_id}/lists', session)


def resolve_board_id(board_id, session):
    """Return the full 24-char board id. Most read endpoints accept the short
    link (e.g. 'hpvdRw3G'), but some writes (POST /lists) reject it with
    400 'invalid value for idBoard'. Call this before such writes."""
    if len(board_id) == 24:
        return board_id
    return trello_request('GET', f'/boards/{board_id}', session, params={'fields': 'id'})['id']


def get_or_create_list(board_id, list_name, session):
    lists = get_board_lists(board_id, session)
    for lst in lists:
        if lst['name'] == list_name:
            return lst['id']
    result = trello_request('POST', '/lists', session, body={
        'name': list_name,
        'idBoard': resolve_board_id(board_id, session),
    })
    return result['id']


def reorder_lists(board_id, desired_order, session):
    lists = get_board_lists(board_id, session)
    lists_by_name = {lst['name']: lst for lst in lists}
    for i, name in enumerate(desired_order):
        if name in lists_by_name:
            trello_request('PUT', f'/lists/{lists_by_name[name]["id"]}', session,
                           params={'pos': str((i + 1) * 65536)})


def create_card(list_id, card_data, session):
    body = {
        'idList': list_id,
        'name': card_data['title'],
        'desc': card_data.get('description', ''),
    }
    # `due` is a real deadline; `start` is the next-action / ping-back date (the startable-task model).
    # Outreach cards typically set only `due` (their follow-up date); task cards set `start`.
    if card_data.get('due'):
        body['due'] = card_data['due']
    if card_data.get('start'):
        body['start'] = card_data['start']
    return trello_request('POST', '/cards', session, body=body)


def update_card(card_id, updates, session):
    return trello_request('PUT', f'/cards/{card_id}', session, body=updates)


def delete_card(card_id, session):
    return trello_request('DELETE', f'/cards/{card_id}', session)


def get_board_cards(board_id, session, fields=None):
    """List a board's open cards. Pass fields='all' (or a comma-separated list) to control which
    card fields come back — the default Trello card payload omits the newer `start` date, so callers
    that need Start/Due together (the startable-task model) should request fields='all'."""
    params = {'fields': fields} if fields else None
    return trello_request('GET', f'/boards/{board_id}/cards', session, params=params)


def find_card_by_name(board_id, name, session):
    """Return the first card on the board whose name matches exactly, else None.

    Template cards (isTemplate=true) are included in this listing, so this also
    finds template/source cards by name.
    """
    for card in get_board_cards(board_id, session):
        if card['name'] == name:
            return card
    return None


def create_card_from_template(list_id, template_card_id, name, session, keep='checklists'):
    """Create a card copying content from a template/source card.

    Uses Trello's idCardSource + keepFromSource. `keep` is 'all', 'none', or a
    comma-separated list e.g. 'checklists,labels,attachments,due'. Defaults to
    copying checklists only.
    """
    return trello_request('POST', '/cards', session, body={
        'idList': list_id,
        'name': name,
        'idCardSource': template_card_id,
        'keepFromSource': keep,
    })


def get_board_labels(board_id, session):
    return trello_request('GET', f'/boards/{board_id}/labels', session, params={'limit': '1000'})


def create_label(board_id, name, color, session):
    return trello_request('POST', '/labels', session, body={
        'name': name,
        'color': color,
        'idBoard': board_id,
    })


def add_label_to_card(card_id, label_id, session):
    return trello_request('POST', f'/cards/{card_id}/idLabels', session,
                          body={'value': label_id})


def remove_label_from_card(card_id, label_id, session):
    return trello_request('DELETE', f'/cards/{card_id}/idLabels/{label_id}', session)


def ensure_labels_exist(board_id, label_definitions, session):
    existing = get_board_labels(board_id, session)
    existing_names = {label['name'] for label in existing}
    created = []
    for name, info in label_definitions.items():
        if name not in existing_names:
            create_label(board_id, name, info['color'], session)
            created.append(name)
    return created


def extract_github_field_value(field_values, field_name):
    for fv in field_values:
        if 'field' in fv and fv['field'] and fv['field']['name'] == field_name:
            return fv.get('text') or fv.get('date') or fv.get('name')
    return None


# --------------------------------------------------------------------- startable-task dependency model
# A blocked card advertises its blockers in a `Blocked-by: <shortlink>, ...` line in its description
# (shortlinks are the 8-char code in a card's shortUrl, https://trello.com/c/<shortlink>). The unblock
# is a PUSH: finishing an upstream card runs cascade_unblock, which strips the blocked label and sets
# Start = today on every card whose LAST remaining blocker just cleared. Nothing polls the blocked card.

# A ⏳ Waiting card advertises who we're waiting on in a `Waiting-for: <name> · <channel>` line in its
# description — the watch spec Phase 2's reverse reply-matcher reads (see the drainer's reverse-unblock
# step). One card may name more than one person on separate lines. The `·` (middot) separates the
# person from the channel we expect their reply on (Email / Slack / Teams / LinkedIn); a line with no
# separator is taken as a bare name with an unspecified channel.
_WAITING_FOR_RE = re.compile(r'^\s*waiting-for\s*:(.*)$', re.IGNORECASE | re.MULTILINE)

_BLOCKED_BY_RE = re.compile(r'^\s*blocked-by\s*:(.*)$', re.IGNORECASE | re.MULTILINE)
# A shortlink is the 8-char code after /c/ in a card URL, or a bare 8-char token delimited by
# whitespace/commas — the delimiter guard keeps 8-letter slug words (…/12-ping-kristine) from matching.
_URL_SHORTLINK_RE = re.compile(r'trello\.com/c/([A-Za-z0-9]{8})')
_BARE_SHORTLINK_RE = re.compile(r'(?:^|[\s,])([A-Za-z0-9]{8})(?=[\s,]|$)')


def parse_blocked_by(desc):
    """Return the list of upstream card shortlinks named on a card's `Blocked-by:` line(s)."""
    out = []
    for m in _BLOCKED_BY_RE.finditer(desc or ''):
        seg = m.group(1)
        out.extend(_URL_SHORTLINK_RE.findall(seg))
        out.extend(_BARE_SHORTLINK_RE.findall(_URL_SHORTLINK_RE.sub(' ', seg)))
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def parse_waiting_for(desc):
    """Return the people a ⏳ card is waiting on: a list of {"name", "channel"} from its
    `Waiting-for: <name> · <channel>` line(s). `channel` is None when the line names no channel.
    Empty list when the card carries no Waiting-for line."""
    out = []
    for m in _WAITING_FOR_RE.finditer(desc or ''):
        seg = m.group(1).strip()
        if not seg:
            continue
        # The middot separates person from channel; also tolerate a plain '|' or ' - ' as a fallback.
        parts = re.split(r'\s*[·|]\s*|\s+-\s+', seg, maxsplit=1)
        name = parts[0].strip()
        channel = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if name:
            out.append({"name": name, "channel": channel})
    return out


def _card_is_done(card, lists_by_id, done_substrs):
    """A blocker counts as resolved when its card is archived (closed) or sits in a terminal list
    (Finished / Abandoned / Adopted / Done) — the same lists the drainer already treats as parked."""
    if card.get('closed'):
        return True
    name = (lists_by_id.get(card.get('idList')) or '').lower()
    return any(t in name for t in done_substrs)


def cascade_unblock(board_ids, finished_card_id, session,
                    blocked_label_substr='blocked',
                    done_substrs=('finished', 'abandoned', 'adopted', 'done')):
    """Push-unblock downstream cards after `finished_card_id` is completed.

    `board_ids` is normally the full board registry (every board in `trello-boards.yaml`), not just
    the finished card's own board — a blocker and the card(s) it blocks are often on different boards
    (e.g. a one-time admin task blocking an outreach card). A single board id/shortlink is also
    accepted for the common same-board case. Trello shortlinks are globally unique, so a card is
    matched by shortlink (or id) across the whole passed-in set regardless of which board it's on;
    the finished card and every blocker just need to live on ONE of the given boards.

    Fetches every given board's cards once, finds cards anywhere in that set whose `Blocked-by:`
    names the finished card, and for each — if ALL of its blockers are now done — strips its blocked
    label and sets Start = today so it surfaces on the next drain. Multi-blocker cards and chains fall
    out of the all-blockers-done check for free. Returns the list of unblocked card ids. Read-heavy
    (N board fetches) but runs only at completion time.
    """
    if isinstance(board_ids, str):
        board_ids = [board_ids]

    all_cards, lists_by_id = [], {}
    for board_id in board_ids:
        all_cards.extend(get_board_cards(board_id, session, fields='all'))
        lists_by_id.update({l['id']: l['name'] for l in get_board_lists(board_id, session)})

    by_key = {}
    for c in all_cards:
        by_key[c['id']] = c
        if c.get('shortLink'):
            by_key[c['shortLink']] = c

    finished = by_key.get(finished_card_id)
    if not finished:
        return []
    finished_keys = {finished.get('id'), finished.get('shortLink')}
    today = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    unblocked = []
    for card in all_cards:
        blockers = parse_blocked_by(card.get('desc'))
        if not blockers or finished_keys.isdisjoint(blockers):
            continue
        # Only unblock once every blocker this card names is resolved (handles multi-blocker + chains).
        all_done = True
        for sl in blockers:
            blk = by_key.get(sl)
            if blk is None or not _card_is_done(blk, lists_by_id, done_substrs):
                all_done = False
                break
        if not all_done:
            continue
        for label in card.get('labels', []):
            if blocked_label_substr in (label.get('name') or '').lower():
                remove_label_from_card(card['id'], label['id'], session)
        update_card(card['id'], {'start': today}, session)
        unblocked.append(card['id'])
    return unblocked
