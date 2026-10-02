"""
fix_bigbrother.py  (v3 — final)
Schema detected: no resolved_date, requires edge_score.
"""
import datetime
from db import get_conn

today = str(datetime.date.today())

def brier(outcome, prob):
    return round((outcome - float(prob)) ** 2, 4)

with get_conn() as conn:

    # ── 1. Dee Valladares already resolved by previous run — skip if done ─────
    row = conn.execute(
        "SELECT id, status FROM predictions WHERE id=91"
    ).fetchone()
    if row and row[1] == "Resolved":
        print("  id=91 KXBIGBROTHER-26DEC31-DV already Resolved — skipping")
    elif row:
        conn.execute(
            "UPDATE predictions SET status='Resolved', outcome=0, "
            "brier_score=?, kalshi_brier_score=? WHERE id=91",
            (brier(0, 0.21), brier(0, 0.21))
        )
        print("  Resolved id=91 KXBIGBROTHER-26DEC31-DV -> NO")

    # ── 2. Insert missing rows ────────────────────────────────────────────────
    missing = [
        # ticker, market, afg_p, kalshi_p, outcome, report_date
        ("KXBIGBROTHER-26DEC31-YAS",
         "Big Brother S28 Winner — Yash Patel",
         0.22, 0.28, 0, "2026-09-09"),
        ("KXBIGBROTHER-26DEC31-RIC",
         "Big Brother S28 Winner — Rick Devens",
         0.42, 0.51, 1, "2026-09-28"),
        ("KXBIGBROTHER-26DEC31-DRE",
         "Big Brother S28 Winner — Drew Campbell",
         0.32, 0.39, 0, "2026-09-25"),
    ]

    for ticker, market, afg_p, kalshi_p, outcome, report_date in missing:
        exists = conn.execute(
            "SELECT id, status FROM predictions WHERE kalshi_ticker=?",
            (ticker,)
        ).fetchone()

        label = "YES (WINNER)" if outcome else "NO"

        if exists:
            conn.execute(
                "UPDATE predictions SET status='Resolved', outcome=?, "
                "brier_score=?, kalshi_brier_score=? WHERE id=?",
                (outcome, brier(outcome, afg_p), brier(outcome, kalshi_p),
                 exists[0])
            )
            print(f"  Updated id={exists[0]}  {ticker}  ->  {label}")
        else:
            edge = round(afg_p - kalshi_p, 4)
            conn.execute(
                """INSERT INTO predictions
                   (market, category, kalshi_ticker, report_date,
                    kalshi_price, afg_probability, edge_score,
                    conviction, recommendation, contract_close_date,
                    status, outcome, brier_score, kalshi_brier_score)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (market, "Culture", ticker, report_date,
                 kalshi_p, afg_p, edge,
                 "MEDIUM", "BUY NO", "2026-10-01",
                 "Resolved", outcome,
                 brier(outcome, afg_p), brier(outcome, kalshi_p))
            )
            print(f"  Inserted + resolved: {ticker}  ->  {label}")

    conn.commit()

print("\nAll done — 4 Big Brother rows resolved.")
print("Now run:")
print("  python3 06_build_scorecard.py")
print("  git add -A && git commit -m \"fix BB S28 all rows\" && git push")
