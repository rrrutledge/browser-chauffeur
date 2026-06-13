"""Unit tests for the learned->PR sync's text-insertion logic (no gh/network)."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(PLUGIN_DIR, "tools"))

import sync_learned  # noqa: E402


def test_insert_adds_new():
    text = "MY_SET = {'a', 'b'}\n"
    new_text, added, already = sync_learned.insert_into_text(text, "MY_SET", ["c", "a"])
    assert added == ["c"]
    assert already == ["a"]
    ns = {}
    exec(new_text, ns)
    assert ns["MY_SET"] == {"a", "b", "c"}


def test_insert_idempotent():
    text = "MY_SET = {'a', 'b'}\n"
    new_text, added, already = sync_learned.insert_into_text(text, "MY_SET", ["b"])
    assert added == []
    assert already == ["b"]
    assert new_text == text


def test_insert_multiline():
    text = "MY_SET = {\n    'a', 'b',\n    'c',\n}\n"
    new_text, added, _ = sync_learned.insert_into_text(text, "MY_SET", ["d"])
    assert added == ["d"]
    ns = {}
    exec(new_text, ns)
    assert ns["MY_SET"] == {"a", "b", "c", "d"}


def test_safe_commands_grouped_stays_valid():
    text = "SAFE_COMMANDS = {\n    'awk', 'cat',\n}\n"
    new_text, _, _ = sync_learned.insert_into_text(text, "SAFE_COMMANDS", ["curl", "ant"])
    ns = {}
    exec(new_text, ns)
    assert ns["SAFE_COMMANDS"] == {"awk", "cat", "curl", "ant"}
