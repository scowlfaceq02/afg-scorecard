"""
fix_premature_resolution_dates.py

Two Resolved rows have contract_close_date = 2026-12-31, which is
the Kalshi contract expiry date — not the actual settlement date.
06_build_scorecard.py flags these because the expiry is in the future,
even though the contracts genuinely resolved earlier.

Fixes:
  KXBIGBROTHER-26DEC31-DV  Big Brother S28 finale: 2026-09-25
  KXRT-SPI-91              Spider-Man Brand New Day RT lock: 2026-08-12

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_premature_resolution_dates.py
"""

import sqlite3
import db

FIXES = [
    # (ticker, actual_settlement_date, note)
    ("KXBIGBROTHER-26DEC31-DV",
     "2026-09-25",
     "BB S28 finale — Dee did not win"),
    ("KXRT-SPI-91",
     "2026-08-12",
     "Spider-Man Brand New Day RT score settled on opening week"),
]

conn = sqlite3.connect(db.DB_PATH)
conn.row_factory = sqlite3.Row

for ticker, new_date, note in FIXES:
    row = conn.execute(
        "SELECT id, status, contract_close_date, outcome FROM predictions "
        "WHERE kalshi_ticker=? AND status='Resolved'", (ticker,)
    ).fetchone()
    if row is None:
        print(f"SKIP  {ticker} — no Resolved row found")
        continue
    if row["contract_close_date"] == new_date:
        print(f"OK    {ticker} — already {new_date}")
        continue
    conn.execute(
        "UPDATE predictions SET contract_close_date=? WHERE id=?",
        (new_date, row["id"])
    )
    print(f"FIXED {ticker}  {row['contract_close_date']} -> {new_date}  ({note})")

conn.commit()
conn.close()
print("\nDone. Now run:")
print("  python3 06_build_scorecard.py")
print("  git add -A && git commit -m \"fix premature resolution dates (DV, Spider-Man)\" && git push")
