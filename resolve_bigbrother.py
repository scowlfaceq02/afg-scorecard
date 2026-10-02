"""
resolve_bigbrother.py
Manually resolves Big Brother Season 28 results in the AFG database.
Rick Devens won (YES). All other tracked houseguests resolve NO.
Run from C:\\Users\\qwhit\\AFG after dropping this file there.
"""
import datetime
from db import get_conn

today = str(datetime.date.today())

resolutions = [
    ("KXBIGBROTHER-26DEC31-RIC", 1),   # Rick Devens — WON
    ("KXBIGBROTHER-26DEC31-DEE", 0),   # Dee Valladares — NO
    ("KXBIGBROTHER-26DEC31-YAS", 0),   # Yash Patel — NO
    ("KXBIGBROTHER-26DEC31-DRE", 0),   # Drew Campbell — NO
]

with get_conn() as conn:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
    print("Columns:", cols)

    for ticker, outcome in resolutions:
        rows = conn.execute(
            "SELECT id, afg_probability, kalshi_price FROM predictions "
            "WHERE kalshi_ticker=? AND status='Open'",
            (ticker,)
        ).fetchall()

        if not rows:
            print(f"  No open rows found for {ticker} — skipping")
            continue

        for row in rows:
            row_id   = row[0]
            afg_p    = float(row[1]) if row[1] is not None else 0.5
            kalshi_p = float(row[2]) if row[2] is not None else 0.5
            afg_brier    = round((outcome - afg_p)    ** 2, 4)
            kalshi_brier = round((outcome - kalshi_p) ** 2, 4)

            conn.execute(
                "UPDATE predictions "
                "SET status='Resolved', outcome=?, brier_score=?, "
                "kalshi_brier_score=?, resolved_date=? "
                "WHERE id=?",
                (outcome, afg_brier, kalshi_brier, today, row_id)
            )
            label = "YES (WINNER)" if outcome else "NO"
            print(f"  Resolved id={row_id}  {ticker}  ->  {label}  "
                  f"AFG Brier={afg_brier}  Kalshi Brier={kalshi_brier}")

    conn.commit()

print("\nDone. Now run:")
print("  python3 06_build_scorecard.py")
print("  git add -A && git commit -m \"resolve BB S28\" && git push")
