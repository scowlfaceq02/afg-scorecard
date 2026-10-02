"""
fix_bigbrother.py
Fixes all Big Brother Season 28 rows in the AFG database.

What this does:
  1. Resolves the existing Dee Valladares row (ID 91) to NO
  2. Inserts the three missing rows (Yash Patel, Rick Devens, Drew Campbell)
     and immediately resolves them — Rick YES (winner), others NO

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_bigbrother.py
Then:
    python3 06_build_scorecard.py
    git add -A && git commit -m "fix BB S28 all rows" && git push
"""

import datetime
from db import get_conn

today = str(datetime.date.today())


def brier(outcome, prob):
    return round((outcome - float(prob)) ** 2, 4)


with get_conn() as conn:

    # ── 1. Resolve the existing Dee Valladares row ────────────────────────────
    row = conn.execute(
        "SELECT id, afg_probability, kalshi_price FROM predictions WHERE id=91"
    ).fetchone()

    if row:
        outcome = 0  # Dee did NOT win
        conn.execute(
            "UPDATE predictions SET status='Resolved', outcome=?, "
            "brier_score=?, kalshi_brier_score=?, resolved_date=? "
            "WHERE id=?",
            (outcome,
             brier(outcome, row[1] or 0.5),
             brier(outcome, row[2] or 0.5),
             today, row[0])
        )
        print(f"  Resolved id=91 KXBIGBROTHER-26DEC31-DV -> NO")
    else:
        print("  WARNING: id=91 not found — skipping Dee row")

    # ── 2. Insert and resolve missing rows ────────────────────────────────────
    missing = [
        # (ticker, houseguest, afg_prob, kalshi_price, outcome, report_date)
        ("KXBIGBROTHER-26DEC31-YAS", "Big Brother S28 Winner — Yash Patel",
         0.22, 0.28, 0, "2026-09-09"),
        ("KXBIGBROTHER-26DEC31-RIC", "Big Brother S28 Winner — Rick Devens",
         0.42, 0.51, 1, "2026-09-28"),   # Rick WON
        ("KXBIGBROTHER-26DEC31-DRE", "Big Brother S28 Winner — Drew Campbell",
         0.32, 0.39, 0, "2026-09-25"),
    ]

    for ticker, market, afg_p, kalshi_p, outcome, report_date in missing:
        # Check it doesn't already exist
        exists = conn.execute(
            "SELECT id FROM predictions WHERE kalshi_ticker=?", (ticker,)
        ).fetchone()
        if exists:
            print(f"  Already exists: {ticker} (id={exists[0]}) — resolving")
            conn.execute(
                "UPDATE predictions SET status='Resolved', outcome=?, "
                "brier_score=?, kalshi_brier_score=?, resolved_date=? "
                "WHERE kalshi_ticker=?",
                (outcome, brier(outcome, afg_p), brier(outcome, kalshi_p),
                 today, ticker)
            )
        else:
            conn.execute(
                """INSERT INTO predictions
                   (market, category, kalshi_ticker, report_date,
                    kalshi_price, afg_probability, conviction, recommendation,
                    contract_close_date, status, outcome,
                    brier_score, kalshi_brier_score, resolved_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (market, "Culture", ticker, report_date,
                 kalshi_p, afg_p, "MEDIUM", "BUY NO",
                 "2026-10-01", "Resolved", outcome,
                 brier(outcome, afg_p), brier(outcome, kalshi_p), today)
            )
            label = "YES (WINNER)" if outcome else "NO"
            print(f"  Inserted + resolved: {ticker} -> {label}")

    conn.commit()

print("\nAll done. Now run:")
print("  python3 06_build_scorecard.py")
print("  git add -A && git commit -m \"fix BB S28 all rows\" && git push")
