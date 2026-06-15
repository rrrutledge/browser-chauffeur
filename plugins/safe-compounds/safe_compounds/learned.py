"""Machine-local store of commands the AI judged safe.

Replaces the previous design where the hook rewrote its own source file. That
caused OneDrive sync-conflict copies and could not survive a plugin update
(plugin files are overwritten on update). Learned approvals now live in a
plain JSON file outside the plugin, one per machine, never synced.

Schema:
    {
      "commands":    ["webpack", ...],          # top-level CLI tools
      "subcommands": {"NPM_TRUSTED_SUBCOMMANDS": ["foo"], "GH_AI_TRUSTED_PAIRS": ["pr:merge"]}
    }
"""
import json
import os

from .log import log_debug

LEARNED_FILE = os.path.expanduser('~/.claude/safe-compounds-learned.json')


def _path():
    return os.environ.get('SAFE_COMPOUNDS_LEARNED_JSON', LEARNED_FILE)


def load_learned():
    try:
        with open(_path(), encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault('commands', [])
    data.setdefault('subcommands', {})
    return data


def _save(data):
    try:
        with open(_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        return True
    except Exception as e:
        log_debug(f"Failed to write learned store: {e}")
        return False


def learned_commands():
    return set(load_learned().get('commands', []))


def learned_subcommands(category):
    return set(load_learned().get('subcommands', {}).get(category, []))


def add_learned_command(name):
    data = load_learned()
    if name not in data['commands']:
        data['commands'].append(name)
        data['commands'].sort()
        _save(data)
        log_debug(f"Learned safe command: {name}")
    return True


def add_learned_subcommand(category, value):
    data = load_learned()
    bucket = data['subcommands'].setdefault(category, [])
    if value not in bucket:
        bucket.append(value)
        bucket.sort()
        _save(data)
        log_debug(f"Learned subcommand {category}: {value}")
    return True
