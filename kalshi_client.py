"""
kalshi_client.py — talks directly to Kalshi's public REST API. No auth or
account needed for read access.

IMPORTANT, learned from live debugging (see debug_kalshi.py / debug_kalshi_2.py):
- Market objects have NO `category` field. Category only exists on `/series`.
- Neither `/markets` nor `/series` reliably honor a `limit` param — a request
  for limit=20 on /series returned nearly 12,000 records. Don't rely on it.
- `series_ticker` as a filter on /markets DOES work correctly and returns
  exactly the matching markets — this is the one filter you can trust.
- A single-ticker lookup (`/markets/{ticker}`) is a precise resource fetch,
  not a filter, so it isn't subject to the same problem.

Net effect: this client intentionally does NOT try to pull "top 5 by category
volume" automatically — doing that properly would mean caching all ~12,000
series locally and aggregating volume across events ourselves, which is a
separate project, not a quick fix. Keep doing the category-level Step 1 pull
the way you already do (Claude chat, reading the website directly) — it shows
you accurate event-level dollar volumes with zero guessing. Use this client
for the two things it's confirmed to do reliably: pulling a known series
(e.g. your stable crypto tickers), and checking a specific market's status
for the scorecard resolution job.

Docs: https://docs.kalshi.com
"""

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Synthetic combo/parlay tickers to exclude if you're ever scanning a series
# that might contain them (per AFG standing discipline).
EXCLUDED_PREFIXES = ("KXMVE",)


def _get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_markets_by_series(series_ticker, status="open"):
    """
    Pull all markets for a known series ticker (e.g. crypto: KXBTCY, KXETHY).
    Confirmed working: series_ticker is an honored filter, unlike category or limit.
    """
    data = _get("/markets", params={"series_ticker": series_ticker, "status": status})
    markets = data.get("markets", [])
    return [m for m in markets if not m["ticker"].startswith(EXCLUDED_PREFIXES)]


def get_market(ticker):
    """Full detail for a single market by its exact ticker. This is a precise
    resource lookup, not a filter, so it's reliable regardless of the /markets
    listing quirks above."""
    return _get(f"/markets/{ticker}").get("market", {})


def get_market_status(ticker):
    """
    Returns {'settled': bool, 'result': 'yes'/'no'/None}.
    This is what resolve.py calls for every logged prediction — it only needs
    a single known ticker, so it's unaffected by the category/limit issues.
    """
    market = get_market(ticker)
    status = market.get("status")  # e.g. "open", "closed", "settled", "finalized"
    result = market.get("result")  # e.g. "yes", "no", "" if not yet settled
    settled = status in ("settled", "finalized") and result in ("yes", "no")
    return {"settled": settled, "result": result if settled else None}


if __name__ == "__main__":
    # Smoke test using a series confirmed to work in live debugging.
    sample = get_markets_by_series("KXEOWEEK")
    print(f"Found {len(sample)} markets in KXEOWEEK:")
    for m in sample[:5]:
        print(" ", m.get("ticker"), "|", m.get("title"), "| vol:", m.get("volume_fp"))

