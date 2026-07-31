"""
fix_fed_brier.py — sets missing Brier scores on the Fed resolution row (id=6).

fix_fed_v3.py correctly marked it Resolved but left brier_score=NULL,
causing scorecard to crash silently and drop the row from the count.

Run:
    python3 fix_fed_brier.py
Then:
    python3 06_build_scorecard.py
    git add -A && git commit -m "scorecard fix Fed brier" && git push
"""
from db import get_conn

def main():
    afg_brier    = round((1 - 0.88) ** 2, 4)   # 0.0144
    kalshi_brier = round((1 - 0.75) ** 2, 4)   # 0.0625

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status, outcome, brier_score FROM predictions WHERE id=6"
        ).fetchone()

        if not row:
            print("ERROR: id=6 not found.")
            return

        print(f"Before: id=6  status={row[1]}  outcome={row[2]}  brier={row[3]}")

        conn.execute(
            "UPDATE predictions SET brier_score=?, kalshi_brier_score=? WHERE id=6",
            (afg_brier, kalshi_brier)
        )
        conn.commit()
        print(f"Fixed:  AFG Brier={afg_brier}  Kalshi Brier={kalshi_brier}")
        print("The Fed row will now appear correctly in the scorecard.")

    print("\nNow run:")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"scorecard fix Fed brier\" && git push")

if __name__ == "__main__":
    main()
