"""Regression tests for the zoom fan-out / cross-source dispatch starvation bug: a finalized meeting's
owner-assigned next steps must all reach a worker eventually, no matter how many newer items from any
source keep arriving.

The real incident (2026-08-14, ISC Treasurer Sync): a meeting produced 7 action items assigned to
Russell. zoom-adapter's `enumerate()` correctly rebuilt all 7 candidates every single poll cycle for a
full day - the fan-out in `_meeting_items` was never the bug. What actually happened is downstream, in
`run-poller.py`'s cross-source needs-you dispatch: every candidate from one meeting shares the meeting's
`received` (its start time), which never advances, so a plain (priority_band, received)-descending sort
re-ranks them below any fresher item from ANY source on every cycle - held items are left unrecorded and
re-ranked from scratch next time, with no memory of having waited. Under a steady trickle of newer
needs-you items (which is the common case for an active inbox), the backlog is outranked forever, not
just delayed.

The fix is `order_needs_you` + the persisted `dispatch-wait.json`: an item that's been waiting
`starvation_minutes` or more is promoted ahead of every fresher item, guaranteeing it eventually wins a
dispatch slot. These tests cover both halves: the fan-out (still correct, guarded against regressing)
and the starvation fix (the actual bug).

Run directly:
    python plugins/drainer/tests/test_zoom_starvation.py
"""
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "scripts")
PROVIDERS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "providers")
POLLER = os.path.join(SCRIPTS, "run-poller.py")
ZOOM_ADAPTER = os.path.join(PROVIDERS, "zoom-adapter.py")

sys.path.insert(0, SCRIPTS)  # run-poller and the adapters import their siblings by bare name

spec = importlib.util.spec_from_file_location("run_poller", POLLER)
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)

spec = importlib.util.spec_from_file_location("zoom_adapter", ZOOM_ADAPTER)
zoom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zoom)

failures = []


def check(name, got, want):
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}\n         got:  {got!r}\n         want: {want!r}")
        failures.append(name)


print("_meeting_items: one recap + one candidate per owner-assigned step (the fan-out, not the bug)")
inst = {"uuid": "D2xGGxsSTOyf03ILOnv3Hg==", "id": 987654321, "topic": "ISC Treasurer Sync",
        "start_time": "2026-08-14T15:00:00Z"}
seven_steps = [f"Russell: do thing number {i}" for i in range(7)]
summary = {
    "summary_overview": "The treasurer sync covered outstanding payments.",
    "next_steps": seven_steps + ["Someone Else: not assigned to Russell"],
    "summary_content": "",
    "summary_last_modified_time": "2026-08-14T15:12:00Z",
    "summary_doc_url": "https://zoom.example/doc",
}
provider = zoom.Provider()
items = provider._meeting_items(inst, summary, owner_tokens=["Russell"])
action_items = [it for it in items if it["kind"] == "action-item"]
recaps = [it for it in items if it["kind"] == "recap"]
check("8 total candidates (7 action items + 1 recap)", len(items), 8)
check("exactly 7 action-item candidates, one per owner-assigned step", len(action_items), 7)
check("exactly 1 recap candidate", len(recaps), 1)
check("every action-item candidate gets a distinct stable id",
      len({provider.stable_id(it) for it in action_items}), 7)
check("the non-owner step is excluded from action items",
      any("not assigned" in (it.get("stepText") or "") for it in action_items), False)

print("\n_meeting_items: the fan-out survives being rebuilt repeatedly from the same cached summary")
for _ in range(5):
    replay = provider._meeting_items(inst, summary, owner_tokens=["Russell"])
    replay_actions = [it for it in replay if it["kind"] == "action-item"]
    check("still 7 action items on a repeat rebuild", len(replay_actions), 7)
    check("stable ids match the first build", {provider.stable_id(it) for it in replay_actions},
          {provider.stable_id(it) for it in action_items})


print("\norder_needs_you: with nothing stale, falls back to (priority_band, received) descending as before")
now_iso = "2026-08-14T20:00:00Z"
plain_items = [
    {"_id": "a", "received": "2026-08-14T18:00:00Z"},
    {"_id": "b", "received": "2026-08-14T19:00:00Z"},
    {"_id": "c", "received": "2026-08-14T17:00:00Z"},
]
ordered = poller.order_needs_you(plain_items, {}, now_iso, starvation_minutes=120)
check("newest-received sorts first when nothing has waited", [it["_id"] for it in ordered], ["b", "a", "c"])

print("\norder_needs_you: an item waiting past starvation_minutes jumps ahead of a fresher one")
wait_since = {"old": "2026-08-14T15:00:00Z"}  # waiting since well before now_iso
items = [{"_id": "old", "received": "2026-08-14T15:00:00Z"},
         {"_id": "new", "received": "2026-08-14T19:59:00Z"}]
ordered = poller.order_needs_you(items, wait_since, now_iso, starvation_minutes=120)
check("the long-waiting item is promoted ahead of the fresher one", [it["_id"] for it in ordered],
      ["old", "new"])

print("\norder_needs_you: an item NOT yet past starvation_minutes stays ranked by recency")
wait_since = {"old": "2026-08-14T19:30:00Z"}  # only 30 min ago, under the 120-min threshold
ordered = poller.order_needs_you(items, wait_since, now_iso, starvation_minutes=120)
check("the fresher item still wins before the threshold is crossed", [it["_id"] for it in ordered],
      ["new", "old"])


print("\nstarvation scenario: 7 same-received meeting candidates vs. an unbroken stream of newer items")
# Mirrors the real incident: a fixed-`received` backlog (every action item from one meeting shares the
# meeting's start time) competing every cycle against a brand-new item that always looks more recent.
# A cap of 1 dispatch slot per cycle is the worst case (target_open_tabs already saturated by other
# work) - under the OLD pure-recency sort this backlog would never win a slot and the loop below would
# never terminate (each fresh item is minted with a later `received` than the last, forever).
start = datetime(2026, 8, 14, 15, 12, tzinfo=timezone.utc)
backlog = [{"_id": f"zoom-treasurer-{i}", "received": "2026-08-14T15:00:00Z"} for i in range(7)]
wait_since = {}
dispatched = []
now = start
cycle = 0
STARVATION_MINUTES = 120
while len(dispatched) < len(backlog) and cycle < 200:
    cycle += 1
    now += timedelta(minutes=5)
    now_iso = now.isoformat()
    fresh = {"_id": f"fresh-{cycle}", "received": now_iso}
    pending = [it for it in backlog if it["_id"] not in dispatched] + [fresh]
    for it in pending:
        wait_since.setdefault(it["_id"], now_iso)
    winner = poller.order_needs_you(pending, wait_since, now_iso, STARVATION_MINUTES)[0]
    if winner["_id"].startswith("zoom-treasurer-"):
        dispatched.append(winner["_id"])
        wait_since.pop(winner["_id"], None)
    # else: the fresh item won this cycle (backlog hasn't aged past the threshold yet) - continue

print(f"  (took {cycle} simulated 5-minute cycles)")
check("every backlog item eventually dispatches despite an unbroken stream of newer arrivals",
      sorted(dispatched), sorted(it["_id"] for it in backlog))
check("dispatch completes within a bounded number of cycles (no indefinite starvation)",
      cycle < 200, True)
# 120 minutes / 5-minute cycles = 24 cycles before the backlog first becomes eligible to be promoted;
# then one backlog item wins per cycle (cap of 1) until all 7 are drained.
check("the backlog doesn't start winning before it crosses the starvation threshold",
      cycle >= 24, True)


print("\nload_wait / save_wait: round-trip through a runtime_dir like every other poller state file")
import tempfile

with tempfile.TemporaryDirectory() as rt:
    check("missing file reads as empty", poller.load_wait(rt), {})
    poller.save_wait(rt, {"zoom-a": "2026-08-14T15:00:00Z"})
    check("round-trips what was saved", poller.load_wait(rt), {"zoom-a": "2026-08-14T15:00:00Z"})


print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
