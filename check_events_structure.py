"""
check_events_structure.py — the one remaining unknown before 01_pull_markets.py
can be built correctly, instead of patched repeatedly.

Question: does /events expose category and an aggregate volume figure
directly? If yes, Phase 1 (pull -> categorize -> rank by volume) is a simple
two-call join. If no, we fall back to the series-cache-plus-join approach,
which is more code but equally buildable.

Run this once and send me the full output.
"""

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


print("=== Does /events respect a limit param? ===")
data = get("/events", params={"limit": 5, "status": "open"})
print("Top-level response keys:", list(data.keys()))
events = data.get("events", [])
print(f"Events returned: {len(events)} (requested limit=5)")

if events:
    e0 = events[0]
    print("\nFirst event's full keys:", list(e0.keys()))
    print("First event sample values:")
    for k in ("event_ticker", "series_ticker", "title", "category", "sub_title"):
        if k in e0:
            print(f"  {k}: {e0.get(k)}")

    # Does the event carry any volume-like field directly?
    volume_like_keys = [k for k in e0.keys() if "volume" in k.lower() or "liquidity" in k.lower()
                         or "notional" in k.lower() or "interest" in k.lower()]
    print("\nVolume-like fields found directly on the event object:", volume_like_keys or "NONE")

    # Check whether markets under this event carry the info needed to
    # aggregate volume ourselves, if the event doesn't have it directly.
    ticker = e0.get("event_ticker")
    print(f"\n=== Pulling markets under event_ticker={ticker} (does event_ticker filter work?) ===")
    mdata = get("/markets", params={"event_ticker": ticker})
    markets = mdata.get("markets", [])
    print(f"Markets returned: {len(markets)}")
    for m in markets[:6]:
        print(f"  {m.get('ticker')} | {m.get('title')} | volume_fp: {m.get('volume_fp')} | status: {m.get('status')}")

print("\n=== Checking pagination: is there a cursor for fetching ALL events? ===")
print("Response top-level keys (again, for cursor field):", list(data.keys()))
