"""
fix_spiderman.py — URGENT: reverts the false Spider-Man resolution.

The Spider-Man RT contract (KXRT-SPI-90) has a close date of 2026-12-31.
The film has not released and the market has not settled. It was marked
Resolved in error and must be returned to Open before the scorecard is
published again.

Run:
    python3 fix_spiderman.py
    python3 check_resolved.py        <- should show 4 rows, no Spider-Man
    python3 06_build_scorecard.py
    git add -A && git commit -m "revert false Spider-Man resolution" && git push
"""

from db import get_conn

TICKER = "KXRT-SPI-90"


def main():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, status, outcome, contract_close_date "
            "FROM predictions WHERE kalshi_ticker = ?",
            (TICKER,)
        ).fetchall()

        if not rows:
            print(f"No rows found for {TICKER}. Nothing to do.")
            return

        print(f"Found {len(rows)} row(s) for {TICKER}:")
        for r in rows:
            print(f"  id={r[0]}  status={r[1]}  outcome={r[2]}  close={r[3]}")

        conn.execute(
            """UPDATE predictions
               SET status='Open', outcome=NULL,
                   brier_score=NULL, kalshi_brier_score=NULL
               WHERE kalshi_ticker = ?""",
            (TICKER,)
        )
        conn.commit()
        print(f"\nReverted all {TICKER} rows to Open. Outcome and Brier cleared.")

    print("\nNow run:")
    print("  python3 check_resolved.py")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"revert false resolution\" && git push")


if __name__ == "__main__":
    main()
