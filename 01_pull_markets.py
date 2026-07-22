"""
01_pull_markets.py — Phase 1, built once, correctly, based on confirmed API
behavior rather than guesses.

Design (confirmed via check_events_structure.py):
- /events carries `category` directly, and paginates via a `cursor` field.
- /markets carries `event_ticker` directly (confirmed in early debugging),
  letting us join to the event's category without touching /series at all.
- We do NOT know yet whether /markets itself paginates via cursor the same
  way, or just respects `limit` for a single page. This script handles both
  cases (follows a cursor if present, stops cleanly if not) and PRINTS the
  total count it pulled -- if that number looks suspiciously small or round
  (e.g. exactly 100 or 1000), that's the signal /markets isn't paginating
  fully and we need to adjust. This run doubles as the verification.

Pipeline:
    /events (all, paginated) -> {event_ticker: category} lookup
    /markets (all, paginated) -> join category via event_ticker
    -> drop inactive, drop KXMVE* parlays, keep our 5 target categories
    -> rank by volume_fp within category, top 5 each
    -> data/raw_markets.xlsx

Run:
    python 01_pull_markets.py
"""

import time
import requests
import pandas as pd

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
OUTPUT_PATH = "data/raw_markets.xlsx"

# Kalshi's category strings -> our AFG category names
TARGET_CATEGORIES = {
    "Sports": "Sports",
    "Politics": "Politics",
    "Economics": "Economics",
    "Entertainment": "Culture",  # Kalshi API category "Entertainment" = site "Culture" tab (permanent swap, replaced Crypto July 2026)
    "Climate and Weather": "Weather",
}

EXCLUDED_PREFIXES = ("KXMVE",)
TOP_N_PER_CATEGORY = 5


def _get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_with_retry(path, params=None, max_retries=6):
    """
    Like _get, but retries on 429 (rate limited) with exponential backoff.
    Kalshi's API pushes back hard on concurrent requests -- without this,
    most of a large concurrent batch just silently fails and gets skipped,
    which is exactly what happened on the first run of the series-based pull.
    """
    delay = 1.0
    for attempt in range(max_retries):
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=30)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                time.sleep(wait)
                delay = min(delay * 2, 30)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"Exceeded retries for {path} (rate limited repeatedly)")


def paginate(path, item_key, params=None, reducer=None, page_limit=200, max_pages=3000, log_every=25):
    """
    Generic cursor-following pagination. Follows `cursor` in the response as
    long as one is present and non-empty.

    IMPORTANT: `reducer` is applied to each item AS SOON AS its page arrives,
    and only the reduced result is kept. This is the fix for the MemoryError
    we hit -- Kalshi's /events endpoint alone returned 100,000+ records with
    large nested fields (settlement_sources had 15-20 entries per event), and
    holding all of them as full raw dicts before reducing at the end exhausted
    memory. Reducing per-page keeps memory flat regardless of total record
    count. If no reducer is given, items are kept as-is (fine for smaller
    endpoints, but always pass a reducer for anything that might be large).
    """
    params = dict(params or {})
    params["limit"] = page_limit
    reducer = reducer or (lambda x: x)
    all_items = []
    cursor = None
    pages = 0

    while True:
        if cursor:
            params["cursor"] = cursor
        data = _get(path, params=params)
        items = data.get(item_key, [])
        all_items.extend(reducer(item) for item in items)  # reduce immediately, don't keep raw
        pages += 1

        if pages <= 5 or pages % log_every == 0:
            print(f"    page {pages}: +{len(items)} {item_key} (running total: {len(all_items)})", flush=True)

        cursor = data.get("cursor")
        if not cursor or not items or pages >= max_pages:
            break
        time.sleep(0.05)

    print(f"  {path}: pulled {len(all_items)} {item_key} across {pages} page(s)")
    return all_items

    print(f"  {path}: pulled {len(all_items)} {item_key} across {pages} page(s)")
    return all_items


def fetch_target_category_series():
    """
    Uses /series instead of /events. This is the corrected design: /events
    turned out to include hundreds of thousands of historical records with
    no way to bound the pull (it kept climbing past 355,000 with no end in
    sight). /series, by contrast, returns its ENTIRE list in a single call
    regardless of the limit param (confirmed early in this project -- a
    request for limit=20 returned all ~11,918 series at once). No pagination
    loop, no runaway growth, just one fast call.
    """
    print("Fetching all series (single call, no pagination risk)...")
    data = _get("/series", params={"limit": 20})
    all_series = data.get("series", [])
    print(f"  Fetched {len(all_series)} total series.")

    kept = {
        s["ticker"]: TARGET_CATEGORIES[s["category"]]
        for s in all_series
        if s.get("category") in TARGET_CATEGORIES and s.get("ticker")
    }
    print(f"  {len(kept)} series kept (in target categories).")
    return kept


def fetch_markets_for_series(series_category, status="open", max_workers=5):
    """
    Fetches markets for each target-category series concurrently, using the
    series_ticker filter confirmed to work reliably (proven against KXEOWEEK,
    KXMENWORLDCUP, and others earlier in this project).

    max_workers is intentionally conservative (5, not 20) after the first
    real run showed Kalshi rate-limiting (429) heavily at higher concurrency.
    Each request also retries with backoff via _get_with_retry rather than
    giving up on the first 429 -- at 20 concurrent workers, most requests
    were failing and silently dropping data, which defeats the purpose.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    series_tickers = list(series_category.keys())
    print(f"Fetching markets for {len(series_tickers)} target-category series "
          f"({max_workers} at a time, with retry-on-rate-limit)...")

    all_rows = []
    done = 0
    failed = 0

    def fetch_one(series_ticker):
        data = _get_with_retry("/markets", params={"series_ticker": series_ticker, "status": status})
        return series_ticker, data.get("markets", [])

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for st in series_tickers:
            futures[executor.submit(fetch_one, st)] = st
            time.sleep(0.05)  # stagger submissions slightly, easier on the API

        for future in as_completed(futures):
            series_ticker = futures[future]
            done += 1
            try:
                _, markets = future.result()
            except Exception as e:
                failed += 1
                print(f"  WARNING: failed to fetch markets for {series_ticker}: {e}")
                continue

            category = series_category[series_ticker]
            for m in markets:
                ticker = m.get("ticker", "")
                if ticker.startswith(EXCLUDED_PREFIXES):
                    continue
                all_rows.append({
                    "ticker": ticker,
                    "series_ticker": series_ticker,
                    "title": m.get("title", ""),
                    "category": category,
                    "yes_ask_dollars": m.get("yes_ask_dollars"),
                    "yes_bid_dollars": m.get("yes_bid_dollars"),
                    "volume_fp": float(m.get("volume_fp") or 0),
                    "volume_24h_fp": float(m.get("volume_24h_fp") or 0),
                    "status": m.get("status"),
                    "close_time": m.get("close_time"),
                })

            if done <= 5 or done % 100 == 0 or done == len(series_tickers):
                print(f"    {done}/{len(series_tickers)} series done "
                      f"({failed} failed after retries), {len(all_rows)} markets collected so far", flush=True)

    print(f"  Done: {len(series_tickers) - failed}/{len(series_tickers)} series succeeded, {failed} failed after retries.")
    return all_rows


def build_raw_markets():
    series_category = fetch_target_category_series()
    rows = fetch_markets_for_series(series_category, status="open")

    df = pd.DataFrame(rows)
    print(f"\n{len(df)} markets collected across target categories (parlays already excluded).")

    if df.empty:
        print("WARNING: zero markets matched. Check TARGET_CATEGORIES against the real category")
        print("strings printed by check_events_structure.py, and confirm the join key is correct.")
        return df

    print("\nBreakdown by category (total markets found, before top-5 cut):")
    print(df.groupby("category").size().to_string())

    top5 = (
        df.sort_values("volume_fp", ascending=False)
        .groupby("category", group_keys=False)
        .head(TOP_N_PER_CATEGORY)
        .sort_values(["category", "volume_fp"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return top5


if __name__ == "__main__":
    result = build_raw_markets()
    if not result.empty:
        result.to_excel(OUTPUT_PATH, index=False)
        print(f"\nWrote top {TOP_N_PER_CATEGORY} per category to {OUTPUT_PATH}")
        print("\n--- Preview ---")
        print(result[["category", "title", "ticker", "yes_ask_dollars", "volume_fp"]].to_string(index=False))
