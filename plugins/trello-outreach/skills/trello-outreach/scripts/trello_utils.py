"""
Shared Trello API utilities.

Board-specific settings (board ID, label names, colors, status-to-list mappings)
live in CLAUDE.local.md. This module provides the generic API operations.
"""

import ctypes
import json
import os
import urllib.request
import urllib.parse

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


def get_or_create_list(board_id, list_name, session):
    lists = get_board_lists(board_id, session)
    for lst in lists:
        if lst['name'] == list_name:
            return lst['id']
    result = trello_request('POST', '/lists', session, body={
        'name': list_name,
        'idBoard': board_id,
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
    if card_data.get('due'):
        body['due'] = card_data['due']
    return trello_request('POST', '/cards', session, body=body)


def update_card(card_id, updates, session):
    return trello_request('PUT', f'/cards/{card_id}', session, body=updates)


def delete_card(card_id, session):
    return trello_request('DELETE', f'/cards/{card_id}', session)


def get_board_cards(board_id, session):
    return trello_request('GET', f'/boards/{board_id}/cards', session)


def get_board_labels(board_id, session):
    return trello_request('GET', f'/boards/{board_id}/labels', session)


def create_label(board_id, name, color, session):
    return trello_request('POST', '/labels', session, body={
        'name': name,
        'color': color,
        'idBoard': board_id,
    })


def add_label_to_card(card_id, label_id, session):
    return trello_request('POST', f'/cards/{card_id}/idLabels', session,
                          body={'value': label_id})


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
