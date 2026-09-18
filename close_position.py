"""
close_position.py — marks an AFG position as CLOSED (exited before resolution).

A closed position means AFG withdrew its recommendation before the contract
settled. Subscribers following AFG held nothing at resolution.

Scoring treatment (dual-track rule, amended September 2026):
  - FIRST-CALL track      : still scores the original call. It was published,
                            subscribers may have acted on it, and closing later
                            does not erase it.
  - UPDATED-POSITION track: EXCLUDED. AFG's last published position was NO
                            TRADE, so there was no live recommendation.
  - CLOSED POSITIONS table: discloses the original call, the closure date, and
                            the eventual outcome. Nothing is hidden.

Usage:
    python3 close_position.py KXFEDDECISION-26SEP-H0 2026-08-31 "Four consecutive wrong cycles; no demonstrated edge"

Arguments:
    ticker       Kalshi ticker of the contract AFG exited
    close_date   YYYY-MM-DD, the report date on which AFG published NO TRADE
    reason       Short reason, published in the Closed Positions table
"""

import sys
from db import get_conn


def ensure_columns(conn):
    """Adds the closed-position columns if this database predates them."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    if "afg_closed" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed INTEGER DEFAULT 0")
    if "afg_closed_date" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed_date TEXT")
    if "afg_closed_reason" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed_reason TEXT")
    conn.commit()


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    ticker, close_date, reason = sys.argv[1], sys.argv[2], sys.argv[3]

    with get_conn() as conn:
        ensure_columns(conn)

        rows = conn.execute(
            "SELECT id, market, report_date, recommendation, afg_probability, status "
            "FROM predictions WHERE kalshi_ticker = ? ORDER BY report_date",
            (ticker,)
        ).fetchall()

        if not rows:
            print(f"No rows found for ticker {ticker}.")
            return

        print(f"Found {len(rows)} row(s) for {ticker}:")
        for r in rows:
            print(f"  id={r[0]}  {r[2]}  {r[3]} @ {r[4]:.0%}  status={r[5]}")

        conn.execute(
            """UPDATE predictions
               SET afg_closed = 1,
                   afg_closed_date = ?,
                   afg_closed_reason = ?
               WHERE kalshi_ticker = ?""",
            (close_date, reason, ticker)
        )
        conn.commit()

        print(f"\nMarked {len(rows)} row(s) CLOSED as of {close_date}.")
        print(f"Reason: {reason}")
        print("\nScoring effect:")
        print("  First-Call track       : original call still scores")
        print("  Updated-Position track : EXCLUDED (no live recommendation at resolution)")
        print("  Closed Positions table : disclosed with outcome")

    print("\nNow run:")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"closed position disclosure\" && git push")


if __name__ == "__main__":
    main()
