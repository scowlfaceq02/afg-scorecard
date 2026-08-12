"""
fix_blanche_revert.py — restores the correct Blanche scorecard state.

The scorecard should show the July 31 BUY NO as INCORRECT (first-call rule).
The August 7 BUY YES row added by fix_blanche_score.py should be voided.
The original July 31 row (id=83) should be restored as Resolved/INCORRECT.

Run:
    python3 fix_blanche_revert.py
    python3 check_blanche.py
    python3 06_build_scorecard.py
    git add -A && git commit -m "scorecard Blanche first-call rule restored" && git push
"""

from db import get_conn

TICKER = "KXNEXTAG-29-TB"


def brier(prob, outcome):
    return round((outcome - prob) ** 2, 4)


def main():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, report_date, recommendation, kalshi_price, "
            "afg_probability, status FROM predictions "
            "WHERE kalshi_ticker=? ORDER BY id",
            (TICKER,)
        ).fetchall()

        print("Current rows:")
        for r in rows:
            print(f"  id={r[0]}  date={r[1]}  call={r[2]}  status={r[5]}")

        # Find the July 31 row (id=83, BUY NO) — this is the first call
        jul31 = [r for r in rows if "7/31" in str(r[1]) or "2026-07-31" in str(r[1])]
        # Find any Aug 7 rows that were inserted by the fix script
        aug7  = [r for r in rows if "8/7" in str(r[1]) or "2026-08-07" in str(r[1])
                 or (r[2] == "BUY YES" and r[5] == "Resolved")]

        if not jul31:
            print("\nWARNING: July 31 BUY NO row not found by date.")
            print("Looking for the earliest BUY NO row instead...")
            buy_no_rows = [r for r in rows if r[2] == "BUY NO"]
            if buy_no_rows:
                jul31 = [min(buy_no_rows, key=lambda r: r[0])]

        # Void any Aug 7 / BUY YES resolved rows
        for r in aug7:
            conn.execute(
                "UPDATE predictions SET status='Void', outcome=NULL, "
                "brier_score=NULL, kalshi_brier_score=NULL WHERE id=?",
                (r[0],)
            )
            print(f"\nVoided Aug 7 BUY YES row id={r[0]}")

        # Restore the July 31 BUY NO as Resolved with outcome=YES (INCORRECT)
        for r in jul31:
            afg_brier    = brier(float(r[4]), 1)   # outcome 1 (YES), AFG said BUY NO
            kalshi_brier = brier(float(r[3]), 1)
            conn.execute(
                """UPDATE predictions
                   SET status='Resolved', outcome=1,
                       brier_score=?, kalshi_brier_score=?
                   WHERE id=?""",
                (afg_brier, kalshi_brier, r[0])
            )
            print(f"\nRestored id={r[0]} (July 31 BUY NO) as Resolved:")
            print(f"  outcome=YES (confirmed)  AFG Brier={afg_brier}  -> INCORRECT")
            print("  This is correct — first-call rule, AFG was wrong at 65%.")

        conn.commit()

    print("\nDone. Now run:")
    print("  python3 check_blanche.py")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m 'scorecard Blanche first-call rule' && git push")


if __name__ == "__main__":
    main()
