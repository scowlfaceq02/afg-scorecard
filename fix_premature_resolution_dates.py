"""
fix_premature_resolution_dates.py

06_build_scorecard.py stops if a Resolved row's contract_close_date is still
in the future. That check exists to catch markets marked settled by mistake.
It also fires on contracts that genuinely settled EARLY, because the stored
close date is Kalshi's latest possible expiry, not the date it settled.

For each contract below, Kalshi's own API reports it finalized on the date
given (verified against Kalshi's API on 12 and 14 Oct 2026).
This script sets contract_close_date to that real settlement date on every
row of the contract. It changes no outcome and no status.

  KXBIGBROTHER-26DEC31-DEE           2026-09-25  Dee did not win BB S28
  KXRT-SPI-91                        2026-08-12  Spider-Man RT score settled
  KXFIRSTHURRICANE-26DEC01ATL-FAY    2026-10-08  Isaias became first hurricane
  KXFIRSTHURRICANE-26DEC01ATL-GON    2026-10-08  (same)
  KXFIRSTHURRICANE-26DEC01ATL-HAN    2026-10-08  (same)
  KXFIRSTHURRICANE-26DEC01ATL-ISA    2026-10-08  (same)
  KXHURCTOTMAJ-26DEC01-T0            2026-10-12  Isaias reached Category 3

Safe to run more than once.

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_premature_resolution_dates.py
"""

import sqlite3
import db

FIXES = [
    # (ticker, actual settlement date, note)
    ("KXBIGBROTHER-26DEC31-DEE",        "2026-09-25", "BB S28 — Dee did not win"),
    ("KXRT-SPI-91",                     "2026-08-12", "Spider-Man Brand New Day RT score settled"),
    ("KXFIRSTHURRICANE-26DEC01ATL-FAY", "2026-10-08", "Isaias became the first Atlantic hurricane"),
    ("KXFIRSTHURRICANE-26DEC01ATL-GON", "2026-10-08", "Isaias became the first Atlantic hurricane"),
    ("KXFIRSTHURRICANE-26DEC01ATL-HAN", "2026-10-08", "Isaias became the first Atlantic hurricane"),
    ("KXFIRSTHURRICANE-26DEC01ATL-ISA", "2026-10-08", "Isaias became the first Atlantic hurricane"),
    ("KXHURCTOTMAJ-26DEC01-T0",         "2026-10-12", "Isaias reached Category 3; Kalshi settled YES 12 Oct"),
]

conn = sqlite3.connect(db.DB_PATH)
conn.row_factory = sqlite3.Row

for ticker, new_date, note in FIXES:
    rows = conn.execute(
        "SELECT id, status, contract_close_date FROM predictions WHERE kalshi_ticker=?",
        (ticker,)).fetchall()
    if not rows:
        print(f"SKIP  {ticker:34s} — no rows")
        continue
    if not any(r["status"] == "Resolved" for r in rows):
        print(f"SKIP  {ticker:34s} — not Resolved in the database; left unchanged")
        continue
    n = conn.execute(
        "UPDATE predictions SET contract_close_date=? WHERE kalshi_ticker=? "
        "AND (contract_close_date IS NULL OR contract_close_date<>?)",
        (new_date, ticker, new_date)).rowcount
    if n:
        print(f"FIXED {ticker:34s} -> {new_date}  ({n} row(s); {note})")
    else:
        print(f"OK    {ticker:34s} already {new_date}")

conn.commit()
conn.close()
print("\nDone. Now run:  python3 06_build_scorecard.py  and paste the output (do not push yet).")
