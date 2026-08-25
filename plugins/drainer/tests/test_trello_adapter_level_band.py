"""Test for providers/trello-adapter.py's level-band ranking (_level_band, and the
(priority_band, level_band, date) sort key used by both trello-adapter._enumerate and
run-poller.py's cross-source needs-you sort). No network/Trello credentials required —
_priority_band/_level_band are pure functions of a card dict.
Run directly:
    python plugins/drainer/tests/test_trello_adapter_level_band.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, ".."))
ADAPTER = os.path.join(PLUGIN_ROOT, "skills", "drainer", "providers", "trello-adapter.py")
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "drainer", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location("trello_adapter", ADAPTER)
adapter_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter_mod)

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def card(desc="", labels=None):
    return {"desc": desc, "labels": labels or []}


def test_level_band_reads_desc_line():
    print("test: _level_band parses the 'Priority: ... · <level>' desc line")
    Provider = adapter_mod.Provider
    check("Director/VP-level -> 0 (shared neutral level with email/Slack)",
          Provider._level_band(card("Priority: P1 · Developer enablement · Director/VP-level")) == 0)
    check("IC-level -> -1",
          Provider._level_band(card("Priority: P1 · Developer enablement · IC-level")) == -1)
    check("no priority line -> 0 (non-job-search board)", Provider._level_band(card("just a normal card")) == 0)
    check("empty desc -> 0", Provider._level_band(card(None)) == 0)


def test_sort_key_orders_level_within_band():
    print("test: (priority_band, level_band, date) sort puts Director/VP ahead of IC within the same band")
    Provider = adapter_mod.Provider
    # Mirrors the real-world case: SentinelOne (P1 Director/VP, older date) must outrank
    # eBay (P1 IC, newer date) even though eBay's date alone would sort first.
    p1_band = adapter_mod._PRIORITY_BAND[1]
    sentinelone = {
        "name": "SentinelOne", "_priority_band": p1_band,
        "_level_band": Provider._level_band(card("Priority: P1 · Eng leadership · Director/VP-level")),
        "_sort_dt": "2026-07-22",
    }
    ebay = {
        "name": "eBay", "_priority_band": p1_band,
        "_level_band": Provider._level_band(card("Priority: P1 · Platform · IC-level")),
        "_sort_dt": "2026-08-15",
    }
    ranked = sorted([ebay, sentinelone],
                     key=lambda it: (it["_priority_band"], it["_level_band"], it["_sort_dt"]),
                     reverse=True)
    check("Director/VP-level card dispatches before a same-band, newer-dated IC-level card",
          ranked[0]["name"] == "SentinelOne", [it["name"] for it in ranked])


def test_startable_gate_start_is_the_only_date():
    print("test: _startable - Start is the only date; a future Start is the sole way to defer a card")
    Provider = adapter_mod.Provider
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    past = now - timedelta(days=30)
    future = now + timedelta(days=6)

    # A future Start defers, full stop - nothing else can pull the card into play early. This is what
    # keeps a card deferred to "next Monday" from surfacing before then (the Huntress failure was a
    # stale Due dragging a future-Start card in early, which no longer exists as a concept).
    check("future Start -> deferred (not startable)", Provider._startable(future, now) is False)
    check("past Start -> startable", Provider._startable(past, now) is True)
    check("Start exactly now -> startable", Provider._startable(now, now) is True)
    check("no Start -> startable immediately (hungry to start)",
          Provider._startable(None, now) is True)


def test_priority_band_still_leads_level_band():
    print("test: a higher priority band still beats a lower band regardless of level")
    Provider = adapter_mod.Provider
    p1_ic = {"name": "P1 IC", "_priority_band": adapter_mod._PRIORITY_BAND[1], "_level_band": -1,
             "_sort_dt": "2026-01-01"}
    p2_director = {"name": "P2 Director", "_priority_band": adapter_mod._PRIORITY_BAND[2], "_level_band": 0,
                    "_sort_dt": "2026-08-01"}
    ranked = sorted([p2_director, p1_ic],
                     key=lambda it: (it["_priority_band"], it["_level_band"], it["_sort_dt"]),
                     reverse=True)
    check("P1 IC still outranks P2 Director/VP", ranked[0]["name"] == "P1 IC", [it["name"] for it in ranked])


if __name__ == "__main__":
    test_level_band_reads_desc_line()
    test_sort_key_orders_level_within_band()
    test_startable_gate_start_is_the_only_date()
    test_priority_band_still_leads_level_band()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        sys.exit(1)
    print("all tests passed")
