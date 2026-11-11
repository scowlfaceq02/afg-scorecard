"""
diag_kalshi.py  --  one-off diagnostic, November 11th, 2026
Shows exactly what Kalshi returns for the tickers check_settlements.py
reports as "not found". Changes nothing.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 diag_kalshi.py
"""
import json
import os
import urllib.error
import urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"
TICKERS = ["KXHMONTH-26JUL", "KXPGATOUR-TOC26-SSCH", "KXEARTHQUAKEM-26AUG-78", "KXFEDDECISION-26SEP-H0"]

print("1. Which check_settlements.py is in this folder?")
for name in sorted(os.listdir(".")):
    if name.startswith("check_settlements"):
        text = open(name, encoding="utf-8", errors="replace").read()
        print(f"   {name}: {'NEW (has archive lookup)' if 'KALSHI_HISTORICAL_URL' in text else 'OLD (live data only)'}")


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "AFG-settlement-check",
                                                       "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERROR", f"{type(e).__name__}: {e}"


print("\n2. Kalshi historical cutoff")
code, body = get("/historical/cutoff")
print(f"   HTTP {code}: {body[:300]}")

print("\n3. Each ticker, live endpoint then archive")
for t in TICKERS:
    for label, path in (("live   ", f"/markets/{t}"), ("archive", f"/historical/markets/{t}")):
        code, body = get(path)
        summary = body[:160]
        try:
            m = json.loads(body).get("market", {})
            if m:
                summary = f"status={m.get('status')} result={m.get('result')!r} ticker={m.get('ticker')}"
        except Exception:
            pass
        print(f"   {t:<28} {label} HTTP {code}: {summary}")

print("\n4. Archive search by series (in case the archive uses different tickers)")
code, body = get("/historical/markets?series_ticker=KXHMONTH&limit=20")
print(f"   HTTP {code}: {body[:600]}")
