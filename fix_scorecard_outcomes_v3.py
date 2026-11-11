"""
fix_scorecard_outcomes_v3.py  --  AFG scorecard correction, November 11th, 2026
================================================================================
Re-verification of all 27 scored positions against Kalshi's own settlement
records (API `result` field on finalized markets) and dated news sources found
four outcomes stored wrongly in afg_scorecard.db after the November 9th fixes,
plus one wrong resolution date.

  Ticker                            Call     Stored  Correct  Evidence
  KXATP-26USO-ALC                   BUY YES  1       0        Kalshi finalized NO; Zverev won the US Open, Sept 13th (Al Jazeera, AP)
  KXHMONTH-26JUL                    BUY YES  1       0        Kalshi finalized NO
  KXMLB-26-LAD                      BUY NO   1       0        Kalshi finalized NO
  KXFIRSTHURRICANE-26DEC01ATL-ISA   BUY NO   0       1        Isaias became the first Atlantic hurricane of 2026 on October 7th
                                                              (NPR/KJZZ, October 7th; AccuWeather). Kalshi settles at the
                                                              December 1st close; outcome is already certain.
  KXTRUMPADMINLEAVE-26DEC31-SWIL    BUY NO   1       1        resolution_date was set to 2026-10-30. Wiles's last day was
                                                              Friday, November 6th (CBS News, Business Today Nov 7th).

Effect: 16 Correct / 11 Incorrect (59.3%) becomes 14 Correct / 13 Incorrect (51.9%).

Two positions could NOT be confirmed against Kalshi this cycle (API returned no
record) and are left as stored -- the script prints them so they can be checked
by hand on kalshi.com before the next scorecard push:
  KXDROUGHTLEVEL-26JULLD4-OR   (stored 1)
  KXRT-SPI-91                  (stored 0)

Everything is matched by ticker AND current stored value, so re-running the
script is harmless. Run from C:\\Users\\qwhit\\AFG\\ :
    python3 fix_scorecard_outcomes_v3.py
    python3 verify_afg.py            (Check 12 must print 14/27 = 51.9%)
    python3 06_build_scorecard.py    (must also print 51.9%)
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "afg_scorecard.db"

OUTCOME_FIXES = [
    # ticker, wrong stored value, correct value, resolution_date, note
    ("KXATP-26USO-ALC", 1, 0, "2026-09-13",
     "Kalshi finalized NO -- Zverev beat Shelton in the final"),
    ("KXHMONTH-26JUL", 1, 0, None,
     "Kalshi finalized NO"),
    ("KXMLB-26-LAD", 1, 0, None,
     "Kalshi finalized NO"),
    ("KXFIRSTHURRICANE-26DEC01ATL-ISA", 0, 1, "2026-10-07",
     "Isaias became the first Atlantic hurricane of 2026 on October 7th"),
]

DATE_FIXES = [
    ("KXTRUMPADMINLEAVE-26DEC31-SWIL", "2026-11-06",
     "Wiles's last day as chief of staff was Friday, November 6th"),
]

UNCONFIRMED = ["KXDROUGHTLEVEL-26JULLD4-OR", "KXRT-SPI-91"]

if not os.path.exists(DB_PATH):
    raise SystemExit(f"{DB_PATH} not found -- run from C:\\Users\\qwhit\\AFG\\")

backup = f"{DB_PATH}.before_v3_fix_{datetime.now():%Y%m%d_%H%M%S}"
shutil.copy2(DB_PATH, backup)
print(f"Backup written: {backup}\n")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
ACTIVE = "status NOT IN ('Void','Superseded')"

print("STEP 1: outcome corrections")
for ticker, wrong, right, res_date, note in OUTCOME_FIXES:
    cur.execute(f"SELECT id, recommendation, afg_probability, outcome FROM predictions "
                f"WHERE ticker=? AND {ACTIVE} AND outcome IS NOT NULL AND outcome!=''", (ticker,))
    rows = cur.fetchall()
    if not rows:
        print(f"  !! {ticker}: no active resolved row found -- check by hand")
        continue
    for rid, rec, p, out in rows:
        if str(out).strip() == str(right):
            print(f"  -- id={rid} {ticker} already {right}, unchanged")
            continue
        if str(out).strip() != str(wrong):
            print(f"  !! id={rid} {ticker} stored {out!r}, expected {wrong} -- NOT changed, check by hand")
            continue
        if res_date:
            cur.execute("UPDATE predictions SET outcome=?, resolution_date=? WHERE id=?", (right, res_date, rid))
        else:
            cur.execute("UPDATE predictions SET outcome=? WHERE id=?", (right, rid))
        verdict = "Correct" if (rec == "BUY YES") == (right == 1) else "Incorrect"
        print(f"  FIXED id={rid} {ticker} {rec} AFG={p}: {out} -> {right} ({verdict}). {note}")

print("\nSTEP 2: resolution-date corrections")
for ticker, res_date, note in DATE_FIXES:
    cur.execute(f"UPDATE predictions SET resolution_date=? WHERE ticker=? AND {ACTIVE}", (res_date, ticker))
    print(f"  {ticker}: resolution_date -> {res_date} on {cur.rowcount} row(s). {note}")

print("\nSTEP 3: Wiles final-call check")
cur.execute(f"SELECT id, published_date, recommendation, afg_probability, kalshi_price FROM predictions "
            f"WHERE ticker='KXTRUMPADMINLEAVE-26DEC31-SWIL' AND {ACTIVE} ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]} published={r[1]} {r[2]} AFG={r[3]} Kalshi={r[4]}")
print("  The final published call was November 6th, BUY NO, 38% against 41%. If no row above")
print("  shows that call, the Brier score is being computed on the October 16th call (25%).")

conn.commit()

print("\nSTEP 4: rows that could not be confirmed against Kalshi this cycle")
for t in UNCONFIRMED:
    cur.execute(f"SELECT id, recommendation, afg_probability, outcome FROM predictions "
                f"WHERE ticker=? AND {ACTIVE} AND outcome IS NOT NULL AND outcome!='' ORDER BY id", (t,))
    for r in cur.fetchall():
        print(f"  id={r[0]} {t} {r[1]} AFG={r[2]} outcome={r[3]}  <- confirm on kalshi.com")

print("\nSTEP 5: final-call tally")
cur.execute(f"SELECT DISTINCT ticker FROM predictions WHERE outcome IS NOT NULL AND outcome!='' "
            f"AND {ACTIVE} AND recommendation IN ('BUY YES','BUY NO')")
correct = incorrect = 0
for (t,) in cur.fetchall():
    cur.execute(f"SELECT recommendation, outcome FROM predictions WHERE ticker=? AND outcome IS NOT NULL "
                f"AND outcome!='' AND {ACTIVE} AND recommendation IN ('BUY YES','BUY NO') "
                f"ORDER BY id DESC LIMIT 1", (t,))
    rec, out = cur.fetchone()
    if (rec == "BUY YES") == (int(str(out).strip()) == 1):
        correct += 1
    else:
        incorrect += 1
n = correct + incorrect
print(f"  {correct} Correct / {incorrect} Incorrect / {correct / n * 100:.1f}% on {n} positions")
print("  Expected: 14 Correct / 13 Incorrect / 51.9% on 27 positions")
conn.close()
