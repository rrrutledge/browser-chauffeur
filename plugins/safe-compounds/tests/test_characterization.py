"""Characterization test: the refactored hook must reproduce, for every corpus
case, the canonical decision the legacy hook produced (committed in golden.json).

The hook is invoked exactly as the Claude Code harness invokes it — a fresh
`python hook.py` subprocess fed the tool payload on stdin — with AI disabled
and the trusted set pinned to the committed fixture, so results are hermetic.
"""
import json
import os
import subprocess
import sys

import pytest

from _runner import canonical, setup_case
from corpus_def import CASES

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
HOOK = os.path.join(PLUGIN_DIR, "hook.py")
FIX = os.path.join(TESTS_DIR, "fixtures")

with open(os.path.join(FIX, "golden.json"), encoding="utf-8") as f:
    GOLDEN = json.load(f)


def run_hook(payload, cwd_path, learned_path):
    env = dict(os.environ)
    env["CLAUDE_CWD"] = cwd_path
    env["SAFE_COMPOUNDS_DISABLE_AI"] = "1"
    env["SAFE_COMPOUNDS_TRUSTED_JSON"] = os.path.join(FIX, "trusted_commands.json")
    env["SAFE_COMPOUNDS_LEARNED_JSON"] = learned_path
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30,
    )
    return canonical(proc.stdout)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_matches_golden(case, tmp_path):
    cwd_path, payload = setup_case(str(tmp_path), case)
    learned = os.path.join(str(tmp_path), "learned.json")
    decision = run_hook(payload, cwd_path, learned)
    assert decision == GOLDEN[case["id"]], (
        f"{case['id']}: got {decision}, golden {GOLDEN[case['id']]}"
    )


def test_golden_covers_corpus():
    assert set(GOLDEN) == {c["id"] for c in CASES}
