"""
fix_spiderman.py — reverts any false Spider-Man resolution.
The Spider-Man RT contract closes 2026-12-31. The film has not released.
Any Resolved row for this ticker is a false resolution and must be reverted.

Run: python3 fix_spiderman.py
"""
from db import get_conn

TICKER = "KXRT-SPI-90"

def main():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, status, outcome FROM predictions WHERE kalshi_ticker=?",
            (TICKER,)
        ).fetchall()
        if not rows:
            print(f"No rows found for {TICKER}.")
            return
        print(f"Found {len(rows)} row(s) for {TICKER}:")
        for r in rows:
            print(f"  id={r[0]}  status={r[1]}  outcome={r[2]}")
        resolved = [r for r in rows if r[1] == "Resolved"]
        if not resolved:
            print("None are Resolved — nothing to fix.")
            return
        conn.execute(
            """UPDATE predictions SET status='Open', outcome=NULL,
               brier_score=NULL, kalshi_brier_score=NULL
               WHERE kalshi_ticker=? AND status='Resolved'""",
            (TICKER,)
        )
        conn.commit()
        print(f"Reverted {len(resolved)} row(s) to Open. Spider-Man is gone.")

if __name__ == "__main__":
    main()
