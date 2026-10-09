"""
fix_duplicate_open_rows.py — removes TRUE duplicate Open rows only.

Since the October 2026 logging rules, one contract can legitimately carry
more than one Open row:
  * the first call plus a later reversal (opposite direction), and
  * a first call plus a reopened call after AFG closed the position.
Both tracks of the Forecast Accuracy Index and the Position Changes table
depend on those rows, so they must NEVER be voided.

A true duplicate is the same call recorded twice: same ticker, same
report date and same recommendation. This script keeps the earliest row
(lowest id) of each such group and marks the rest Void.

The previous version of this script voided every Open row after the first
for each ticker. Running that version now would delete reversals and
reopened positions from the scorecard.

Run (preview first, then apply):
    python3 fix_duplicate_open_rows.py
    python3 fix_duplicate_open_rows.py --apply
"""

import sys

from db import get_conn

DUP_SQL = """
    SELECT kalshi_ticker, report_date, recommendation, COUNT(*) AS n,
           MIN(id) AS keep_id
    FROM predictions
    WHERE status='Open' AND kalshi_ticker IS NOT NULL
    GROUP BY kalshi_ticker, report_date, recommendation
    HAVING n > 1
"""


def main():
    apply = "--apply" in sys.argv
    with get_conn() as conn:
        groups = conn.execute(DUP_SQL).fetchall()
        if not groups:
            print("No true duplicate Open rows found. Nothing to do.")
            return
        print(f"Found {len(groups)} true duplicate group(s):")
        total = 0
        for ticker, rdate, rec, n, keep_id in groups:
            print(f"  {ticker:38s} {rdate}  {rec:8s}  {n} rows (keeping id {keep_id})")
            if apply:
                total += conn.execute(
                    "UPDATE predictions SET status='Void' WHERE status='Open' "
                    "AND kalshi_ticker=? AND report_date=? AND recommendation=? AND id<>?",
                    (ticker, rdate, rec, keep_id)).rowcount
        if apply:
            conn.commit()
            print(f"Voided {total} duplicate row(s).")
        else:
            print("\nPreview only. To apply:  python3 fix_duplicate_open_rows.py --apply")


if __name__ == "__main__":
    main()
