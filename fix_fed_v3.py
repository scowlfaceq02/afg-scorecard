"""
fix_fed_v3.py — resolves the 4 stuck Fed rows.
Marks the FIRST one (id=6) as Resolved with outcome=YES.
Marks the other three as Void so they don't skew scoring.

Run:
    python3 fix_fed_v3.py
Then:
    python3 check_resolved.py   <- should now show 4 rows including the Fed
    python3 06_build_scorecard.py
    git add -A && git commit -m "scorecard update Fed resolved" && git push
"""

from db import get_conn


def main():
    # IDs confirmed from your output: 6, 25, 43, 62
    first_id   = 6
    duplicate_ids = [25, 43, 62]

    kalshi_brier = round((1 - 0.75) ** 2, 4)   # market was 75%
    afg_brier    = round((1 - 0.88) ** 2, 4)   # AFG was 88%

    with get_conn() as conn:
        # Mark the first call Resolved: YES (Fed held)
        conn.execute(
            """UPDATE predictions
               SET status='Resolved', outcome=1,
                   brier_score=?, kalshi_brier_score=?
               WHERE id=?""",
            (afg_brier, kalshi_brier, first_id)
        )
        print(f"Marked id={first_id} as Resolved: outcome=YES  "
              f"AFG Brier={afg_brier}  Kalshi Brier={kalshi_brier}  -> CORRECT")

        # Mark the duplicates as Void so they are excluded from scoring
        for dup_id in duplicate_ids:
            conn.execute(
                "UPDATE predictions SET status='Void' WHERE id=?",
                (dup_id,)
            )
            print(f"Marked id={dup_id} as Void (duplicate — excluded from scoring)")

        conn.commit()

    print("\nDone. Now run:")
    print("  python3 check_resolved.py")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"scorecard update Fed resolved\" && git push")


if __name__ == "__main__":
    main()
