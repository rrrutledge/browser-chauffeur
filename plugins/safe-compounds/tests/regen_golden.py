"""Regenerate fixtures/golden.json and fixtures/trusted_commands.json from the
frozen legacy hook (tests/oracle/legacy_hook.py).

Run this only when intentionally changing behavior: it re-derives the expected
decisions from the ORIGINAL hook, so it must be run from a checkout where the
oracle still represents the desired baseline. The characterization test then
proves the refactored hook reproduces these decisions.

    python tests/regen_golden.py

AI is disabled and the trusted set is frozen, so output is deterministic.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

TESTS = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(TESTS, "fixtures")
ORACLE = os.path.join(TESTS, "oracle", "legacy_hook.py")

sys.path.insert(0, TESTS)
import _runner  # noqa: E402
from corpus_def import CASES  # noqa: E402


def load_oracle():
    spec = importlib.util.spec_from_file_location("legacy_hook", ORACLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def neutralize_ai(mod):
    mod.call_ai = lambda *a, **k: None
    mod.ask_ai_if_temp_file = lambda *a, **k: None
    mod.ask_ai_about_subcommand = lambda *a, **k: None
    mod.ask_ai_about_script = lambda *a, **k: None


def run_oracle(mod, payload, cwd_path):
    os.environ["CLAUDE_CWD"] = cwd_path
    mod._ALLOWED_EDIT_DIRS = None
    mod._pending_worktree_paths = set()
    stdin_backup = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            try:
                mod.main()
            except SystemExit:
                pass
    finally:
        sys.stdin = stdin_backup
    return _runner.canonical(buf.getvalue())


def main():
    os.makedirs(FIX, exist_ok=True)
    mod = load_oracle()
    neutralize_ai(mod)

    trusted = sorted(t for t in mod.TRUSTED_COMMANDS if t != mod.ASSIGNMENT_ONLY)
    with open(os.path.join(FIX, "trusted_commands.json"), "w", encoding="utf-8") as f:
        json.dump(trusted, f, indent=2)
    frozen = set(trusted)

    golden = {}
    with tempfile.TemporaryDirectory() as root:
        for case in CASES:
            cwd_path, payload = _runner.setup_case(root, case)
            mod.TRUSTED_COMMANDS = frozen
            golden[case["id"]] = run_oracle(mod, payload, cwd_path)

    with open(os.path.join(FIX, "golden.json"), "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, sort_keys=True)

    for cid in sorted(golden):
        print(f"{golden[cid]:8} {cid}")
    print(f"\n{len(golden)} cases, {len(trusted)} trusted commands")


if __name__ == "__main__":
    main()
