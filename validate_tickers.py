"""
validate_tickers.py — checks every open contract's ticker against Kalshi.

A ticker Kalshi does not recognise can never resolve automatically: the
scorecard will wait on it forever. Run this after the backfill and whenever a
contract seems stuck. It changes nothing in the database.

Run:
    python3 validate_tickers.py
"""

import time
import sqlite3

import requests

import db
from kalshi_client import get_market


def main():
    conn = sqlite3.connect(db.DB_PATH)
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT kalshi_ticker FROM predictions "
        "WHERE status='Open' AND kalshi_ticker IS NOT NULL ORDER BY kalshi_ticker")]
    conn.close()

    ok, settled, missing, errors = [], [], [], []
    for t in tickers:
        try:
            m = get_market(t)
            status, result = m.get("status"), m.get("result")
            if status in ("settled", "finalized") and result in ("yes", "no"):
                settled.append((t, result))
            else:
                ok.append((t, status))
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            (missing if code == 404 else errors).append((t, code))
        except Exception as e:
            errors.append((t, type(e).__name__))
        time.sleep(0.25)

    print(f"Checked {len(tickers)} open ticker(s)\n")
    print(f"FOUND, still open ({len(ok)})")
    for t, s in ok:
        print(f"  {t:36s} {s}")
    print(f"\nFOUND, already settled ({len(settled)}) — 05_update_scorecard.py will resolve these")
    for t, r in settled:
        print(f"  {t:36s} result={r}")
    print(f"\nNOT FOUND ON KALSHI ({len(missing)}) — these can never auto-resolve")
    for t, c in missing:
        print(f"  {t:36s} HTTP {c}")
    if errors:
        print(f"\nOTHER ERRORS ({len(errors)})")
        for t, c in errors:
            print(f"  {t:36s} {c}")
    if missing:
        print("\nPaste the NOT FOUND list back into the chat so the correct tickers can be mapped.")


if __name__ == "__main__":
    main()
