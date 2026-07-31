"""
fix_fed_resolution.py  (v2 - fixed)
Logs the Fed July 29 decision and marks it Resolved in one step.

Run:
    python3 fix_fed_resolution.py
Then:
    python3 check_resolved.py
    python3 06_build_scorecard.py
    git add -A && git commit -m "scorecard update Fed resolved" && git push
"""

from db import get_conn


def main():
    ticker = "KXFEDDECISION-26JUL-H0"

    with get_conn() as conn:
        # Check for duplicate
        existing = conn.execute(
            "SELECT id, status FROM predictions WHERE kalshi_ticker = ?",
            (ticker,)
        ).fetchall()

        if existing:
            print(f"Already in database ({len(existing)} row):")
            for row in existing:
                print(f"  id={row[0]}  status={row[1]}")
            print("Nothing to do.")
            return

        # Insert the prediction
        conn.execute(
            """INSERT INTO predictions
               (market, category, kalshi_ticker, report_date, kalshi_price,
                afg_probability, edge_score, conviction, recommendation,
                contract_close_date)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("Fed decision in July - Maintains rate",
             "Economics",
             ticker,
             "2026-07-28",
             0.75, 0.88,
             round(0.88 - 0.75, 4),
             "HIGH", "BUY YES",
             "2026-07-29")
        )
        conn.commit()

        # Get the id just inserted
        pid = conn.execute(
            "SELECT id FROM predictions WHERE kalshi_ticker = ?",
            (ticker,)
        ).fetchone()[0]
        print(f"Logged prediction id={pid}")

        # Mark Resolved: outcome 1 = YES (Fed held rates)
        kalshi_brier = round((1 - 0.75) ** 2, 4)
        afg_brier    = round((1 - 0.88) ** 2, 4)
        conn.execute(
            """UPDATE predictions
               SET status='Resolved', outcome=1,
                   brier_score=?, kalshi_brier_score=?
               WHERE id=?""",
            (afg_brier, kalshi_brier, pid)
        )
        conn.commit()
        print(f"Resolved: outcome=YES  AFG Brier={afg_brier:.4f}  Kalshi Brier={kalshi_brier:.4f}  -> CORRECT")

    print("\nDone. Now run:")
    print("  python3 check_resolved.py    <- should show 4 rows including the Fed")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"scorecard update Fed resolved\" && git push")


if __name__ == "__main__":
    main()
