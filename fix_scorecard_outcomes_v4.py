"""
fix_scorecard_outcomes_v4.py  --  AFG scorecard correction, November 11th, 2026
Kalshi's historical archive (read by check_settlements.py on November 11th)
shows KXDROUGHTLEVEL-26JULLD4-OR -- exceptional drought in Oregon, June 4th to
July 30th -- settled NO. Both active rows store outcome 1. The November 9th v1
fix set this outcome to 1 without Kalshi's record; this restores Kalshi's result.

Final call (id=76, BUY YES 72%) becomes Incorrect.
Expected tally afterwards: 13 Correct / 14 Incorrect / 48.1% on 27 positions.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 fix_scorecard_outcomes_v4.py
    python3 check_settlements.py      (must end "All 27 resolved outcomes match")
"""
import os
import shutil
import sqlite3
from datetime import datetime

DB = "afg_scorecard.db"
TICKER = "KXDROUGHTLEVEL-26JULLD4-OR"
ACTIVE = "status NOT IN ('Void','Superseded')"

if not os.path.exists(DB):
    raise SystemExit(f"{DB} not found -- run from C:\\Users\\qwhit\\AFG\\")
backup = f"{DB}.before_v4_fix_{datetime.now():%Y%m%d_%H%M%S}"
shutil.copy2(DB, backup)
print(f"Backup written: {backup}\n")

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute(f"SELECT id, recommendation, afg_probability, outcome FROM predictions "
            f"WHERE ticker=? AND {ACTIVE} AND outcome IS NOT NULL AND outcome!='' ORDER BY id", (TICKER,))
for rid, rec, p, out in cur.fetchall():
    if str(out).strip() == "0":
        print(f"  -- id={rid} already 0, unchanged")
    elif str(out).strip() == "1":
        cur.execute("UPDATE predictions SET outcome=0 WHERE id=?", (rid,))
        print(f"  FIXED id={rid} {TICKER} {rec} AFG={p}: 1 -> 0 (Kalshi settled NO, historical archive)")
    else:
        print(f"  !! id={rid} stored {out!r} -- not changed, check by hand")
conn.commit()

cur.execute(f"SELECT DISTINCT ticker FROM predictions WHERE outcome IS NOT NULL AND outcome!='' "
            f"AND {ACTIVE} AND recommendation IN ('BUY YES','BUY NO')")
c = i = 0
for (t,) in cur.fetchall():
    cur.execute(f"SELECT recommendation, outcome FROM predictions WHERE ticker=? AND outcome IS NOT NULL "
                f"AND outcome!='' AND {ACTIVE} AND recommendation IN ('BUY YES','BUY NO') "
                f"ORDER BY id DESC LIMIT 1", (t,))
    rec, out = cur.fetchone()
    if (rec == "BUY YES") == (int(str(out).strip()) == 1):
        c += 1
    else:
        i += 1
conn.close()
print(f"\n  {c} Correct / {i} Incorrect / {c / (c + i) * 100:.1f}% on {c + i} positions")
print("  Expected: 13 Correct / 14 Incorrect / 48.1% on 27 positions")
