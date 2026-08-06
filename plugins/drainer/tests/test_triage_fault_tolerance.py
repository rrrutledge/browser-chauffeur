"""A failing per-item triage call must not crash the whole poller cycle.

Run directly:
    python plugins/drainer/tests/test_triage_fault_tolerance.py
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


def fake_triage_one(item, brain, repo, model, providers_by_name):
    if item["_id"] == "bad":
        raise RuntimeError("simulated triage failure (API blip / timeout / bad response)")
    return {"id": item["_id"], "bucket": "fyi"}


# --- _triage_one_safe: a failure is caught and downgraded, not raised ------
print("_triage_one_safe")
real = poller._triage_one
poller._triage_one = fake_triage_one
try:
    ok = poller._triage_one_safe({"_id": "good"}, "brain", "repo", "model", {})
    check("a successful item returns its verdict", ok, {"id": "good", "bucket": "fyi"})

    bad = poller._triage_one_safe({"_id": "bad"}, "brain", "repo", "model", {})
    check("a failing item returns {} instead of raising", bad, {})

    # --- triage(): one bad item must not cost the others their verdicts ---
    print("\ntriage() end to end")
    items = [{"_id": "good1"}, {"_id": "bad"}, {"_id": "good2"}]
    verdicts = poller.triage(items, "repo", "local_dir", "model", {})
    check("the failing item has no verdict", "bad" in verdicts, False)
    check("both surviving items still got verdicts", set(verdicts), {"good1", "good2"})

    # A batch that fails on its FIRST item (the one that primes the prompt cache) must not lose the rest.
    items_first_bad = [{"_id": "bad"}, {"_id": "good1"}, {"_id": "good2"}]
    verdicts_first_bad = poller.triage(items_first_bad, "repo", "local_dir", "model", {})
    check(
        "a first-item failure still lets the rest of the batch triage",
        set(verdicts_first_bad),
        {"good1", "good2"},
    )
finally:
    poller._triage_one = real

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
