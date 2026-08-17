"""Tests for archive-fyi/junk-at-triage: ProviderBase.clear's default, the poller's pollCleared stamp,
and the two inbox adapters' clear() calling their reversible-archive CLEAR.

Run directly:
    python plugins/drainer/tests/test_poll_clear.py
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "scripts")
PROVIDERS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "providers")
POLLER = os.path.join(SCRIPTS, "run-poller.py")

sys.path.insert(0, SCRIPTS)  # run-poller and the adapters import their siblings by bare name


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


poller = _load("run_poller", POLLER)
import provider_base  # noqa: E402  (on sys.path via SCRIPTS)
outlook = _load("outlook_graph_adapter", os.path.join(PROVIDERS, "outlook-graph-adapter.py"))
gmail = _load("gmail_adapter", os.path.join(PROVIDERS, "gmail-adapter.py"))

failures = []


def check(name, got, want):
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}\n         got:  {got!r}\n         want: {want!r}")
        failures.append(name)


class _Res:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


print("\nProviderBase.clear default is None (a provider with no safe poll-time archive)")
check("base clear -> None", provider_base.ProviderBase().clear({"id": "x"}), None)


print("\n_mark_poll_cleared stamps the captured json, best-effort")
with tempfile.TemporaryDirectory() as d:
    jf = os.path.join(d, "item.json")
    with open(jf, "w", encoding="utf-8") as f:
        json.dump({"id": "a", "triage": "junk"}, f)
    poller._mark_poll_cleared(jf)
    with open(jf, encoding="utf-8") as f:
        rec = json.load(f)
    check("pollCleared set true", rec.get("pollCleared"), True)
    check("existing fields kept", rec.get("triage"), "junk")
    # A missing file must not raise (best-effort).
    try:
        poller._mark_poll_cleared(os.path.join(d, "nope.json"))
        check("missing file is a no-op (no raise)", True, True)
    except Exception as e:  # noqa: BLE001
        check("missing file is a no-op (no raise)", repr(e), "no exception")


print("\noutlook-graph adapter clear() archives via mail.js --delete and reports success/failure")
og = outlook.Provider.__new__(outlook.Provider)  # skip __init__ (which locates mail.js)
og.mailjs = "MAILJS"
calls = []
outlook.run_node = lambda args, **kw: (calls.append(args) or _Res(0))
check("clear -> True on rc 0", og.clear({"id": "MID1"}), True)
check("called mail.js --delete=<id>", calls and calls[0], ["MAILJS", "--delete=MID1"])
outlook.run_node = lambda args, **kw: _Res(1)
check("clear -> False on rc 1", og.clear({"id": "MID1"}), False)


print("\ngmail adapter clear() archives via gmail.js --archive and reports success/failure")
gm = gmail.Provider.__new__(gmail.Provider)
gm.gmailjs = "GMAILJS"
gcalls = []
gmail.run_node = lambda args, **kw: (gcalls.append(args) or _Res(0))
check("clear -> True on rc 0", gm.clear({"id": "GID1"}), True)
check("called gmail.js --archive=<id>", gcalls and gcalls[0], ["GMAILJS", "--archive=GID1"])
gmail.run_node = lambda args, **kw: _Res(2)
check("clear -> False on nonzero rc", gm.clear({"id": "GID1"}), False)


print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
