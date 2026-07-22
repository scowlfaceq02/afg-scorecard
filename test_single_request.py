"""
test_single_request.py — the smallest possible test, to find exactly where
things stall. Every step prints and flushes immediately, so whichever letter
is the LAST one printed tells us precisely where it's getting stuck.

Usage:
    python test_single_request.py
"""

print("A: script started", flush=True)

import requests
print("B: requests library imported", flush=True)

print("C: about to send request (limit=5, matching your successful browser test)...", flush=True)
resp = requests.get(
    "https://api.elections.kalshi.com/trade-api/v2/events",
    params={"limit": 5},
    timeout=15,
)
print(f"D: got a response back! status code: {resp.status_code}", flush=True)

data = resp.json()
print(f"E: parsed JSON successfully. Top-level keys: {list(data.keys())}", flush=True)
print(f"F: number of events in this page: {len(data.get('events', []))}", flush=True)

print("\nG: now trying the LARGER page size (limit=200) that 01_pull_markets.py uses...", flush=True)
resp2 = requests.get(
    "https://api.elections.kalshi.com/trade-api/v2/events",
    params={"limit": 200},
    timeout=15,
)
print(f"H: got a response back! status code: {resp2.status_code}", flush=True)
data2 = resp2.json()
print(f"I: number of events with limit=200: {len(data2.get('events', []))}", flush=True)

print("\nALL STEPS COMPLETED SUCCESSFULLY.", flush=True)
