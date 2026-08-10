"""Tests for run-poller.py's triage() resilience to a single item's TriageUnavailable (a
subprocess timeout or launch failure) during an otherwise-working batch.

Run directly:
    python plugins/drainer/tests/test_triage_resilience.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "scripts")
POLLER = os.path.join(SCRIPTS, "run-poller.py")

sys.path.insert(0, SCRIPTS)  # run-poller imports its siblings by bare name
spec = importlib.util.spec_from_file_location("run_poller", POLLER)
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)

failures = []


def check(name, got, want):
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}\n         got:  {got!r}\n         want: {want!r}")
        failures.append(name)


def item(iid):
    return {"_id": iid, "_source": "demo", "from": "", "subject": "", "preview": ""}


# --- a mid-batch TriageUnavailable does not lose the other items' verdicts -----------------
print("one item unavailable, others still verdict")

ITEMS = [item("a"), item("b"), item("c"), item("d")]


def fake_triage_one(it, brain, repo, model, providers_by_name):
    if it["_id"] == "c":
        raise poller.TriageUnavailable(f"{it['_id']}: triage call timed out after 420s (likely a network drop)")
    return {"id": it["_id"], "bucket": "fyi", "kind": "read"}


poller._triage_brain = lambda items, repo, local_dir, providers_by_name: "BRAIN"
real_triage_one = poller._triage_one
poller._triage_one = fake_triage_one

verdicts, unavailable = poller.triage(ITEMS, repo="R", local_dir="L", model="M", providers_by_name={})

check("the 3 reachable items still got verdicts", sorted(verdicts.keys()), ["a", "b", "d"])
check("the unreachable item is NOT silently defaulted into verdicts", "c" in verdicts, False)
check("the unreachable item lands in unavailable, not verdicts", unavailable, {"c"})

# --- a TriageUnavailable on the FIRST (cache-priming) item still processes the rest ---------
print("\nfirst item unavailable")


def fake_first_fails(it, brain, repo, model, providers_by_name):
    if it["_id"] == "a":
        raise poller.TriageUnavailable("a: couldn't launch the triage call")
    return {"id": it["_id"], "bucket": "junk", "kind": "read"}


poller._triage_one = fake_first_fails
verdicts2, unavailable2 = poller.triage(ITEMS, repo="R", local_dir="L", model="M", providers_by_name={})
check("first item's failure is recorded, not raised", unavailable2, {"a"})
check("the rest still got triaged despite the first item failing", sorted(verdicts2.keys()), ["b", "c", "d"])

# --- everything unavailable (e.g. the network is fully down) yields no verdicts, no crash ---
print("\nall items unavailable")


def fake_all_fail(it, brain, repo, model, providers_by_name):
    raise poller.TriageUnavailable(f"{it['_id']}: triage call timed out after 420s (likely a network drop)")


poller._triage_one = fake_all_fail
verdicts3, unavailable3 = poller.triage(ITEMS, repo="R", local_dir="L", model="M", providers_by_name={})
check("no verdicts when every call is unavailable", verdicts3, {})
check("every item id is reported unavailable", unavailable3, {"a", "b", "c", "d"})

poller._triage_one = real_triage_one

# --- empty batch is unaffected ---------------------------------------------------------------
print("\nempty batch")
check("empty items returns empty verdicts and empty unavailable set", poller.triage([], "R", "L", "M", {}), ({}, set()))

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
