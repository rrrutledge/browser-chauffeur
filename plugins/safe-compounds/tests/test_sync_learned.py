"""Unit tests for the learned->PR sync's source-insertion logic (no git/gh)."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(PLUGIN_DIR, "tools"))

import sync_learned  # noqa: E402


def _write(tmp_path, text):
    p = tmp_path / "src.py"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_add_items_inserts_new(tmp_path):
    path = _write(tmp_path, "MY_SET = {'a', 'b'}\n")
    new = sync_learned.add_items(path, "MY_SET", ["c", "a"])
    assert new == ["c"]
    content = tmp_path.joinpath("src.py").read_text(encoding="utf-8")
    assert "'c'" in content and "'a'" in content and "'b'" in content


def test_add_items_idempotent(tmp_path):
    path = _write(tmp_path, "MY_SET = {'a', 'b'}\n")
    assert sync_learned.add_items(path, "MY_SET", ["b"]) == []


def test_add_items_multiline_set(tmp_path):
    path = _write(tmp_path, "MY_SET = {\n    'a', 'b',\n    'c',\n}\n")
    new = sync_learned.add_items(path, "MY_SET", ["d"])
    assert new == ["d"]
    content = tmp_path.joinpath("src.py").read_text(encoding="utf-8")
    assert "'d'" in content
    # still a valid set literal
    ns = {}
    exec(content, ns)
    assert ns["MY_SET"] == {"a", "b", "c", "d"}


def test_safe_commands_grouped_format(tmp_path):
    path = _write(tmp_path, "SAFE_COMMANDS = {\n    'awk', 'cat',\n}\n")
    sync_learned.add_items(path, "SAFE_COMMANDS", ["curl", "ant"])
    content = tmp_path.joinpath("src.py").read_text(encoding="utf-8")
    ns = {}
    exec(content, ns)
    assert ns["SAFE_COMMANDS"] == {"awk", "cat", "curl", "ant"}
