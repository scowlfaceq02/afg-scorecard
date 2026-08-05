"""
fix_duplicate_open_rows.py — keeps only the EARLIEST Open prediction
per kalshi_ticker, deletes all later duplicates.

This is safe: the scorecard already applies first-call-only dedup at
read time, so these extra rows are harmless clutter — but cleaning them
prevents 045_log_predictions.py from accumulating more in future cycles.

Run:
    python3 fix_duplicate_open_rows.py
"""

from db import get_conn


def main():
    with get_conn() as conn:
        # Find all tickers with more than one Open row
        dups = conn.execute(
            """SELECT kalshi_ticker, COUNT(*) as n
               FROM predictions
               WHERE status='Open' AND kalshi_ticker IS NOT NULL
               GROUP BY kalshi_ticker HAVING n > 1"""
        ).fetchall()

        if not dups:
            print("No duplicate Open rows found. Nothing to do.")
            return

        print(f"Found {len(dups)} ticker(s) with duplicates:")
        total_deleted = 0

        for ticker, count in dups:
            # Get all Open rows for this ticker, oldest first
            rows = conn.execute(
                """SELECT id, report_date FROM predictions
                   WHERE status='Open' AND kalshi_ticker=?
                   ORDER BY report_date ASC""",
                (ticker,)
            ).fetchall()

            # Keep the first (earliest), delete the rest
            keep_id = rows[0][0]
            delete_ids = [r[0] for r in rows[1:]]

            conn.execute(
                f"UPDATE predictions SET status='Void' WHERE id IN "
                f"({','.join('?' for _ in delete_ids)})",
                delete_ids
            )
            total_deleted += len(delete_ids)
            print(f"  {ticker}: kept id={keep_id}, voided {len(delete_ids)} duplicate(s)")

        conn.commit()
        print(f"\nDone. {total_deleted} duplicate Open rows voided.")
        print("Run python3 verify_afg.py to confirm clean.")


if __name__ == "__main__":
    main()
