"""
backfill_ticker.py  --  fills the `ticker` column from `kalshi_ticker` on open rows.
045_log_predictions.py writes kalshi_ticker but not ticker, so every newly logged
call fails verify_afg.py Check 3. Safe to run every cycle until 045 is fixed.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 backfill_ticker.py
"""
import sqlite3

conn = sqlite3.connect("afg_scorecard.db")
cur = conn.cursor()
cur.execute("""
    SELECT id, kalshi_ticker, category FROM predictions
    WHERE (ticker IS NULL OR ticker = '')
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
""")
rows = cur.fetchall()
for rid, kt, cat in rows:
    if kt:
        cur.execute("UPDATE predictions SET ticker = ? WHERE id = ?", (kt, rid))
        print(f"  id={rid}: ticker <- {kt}  (category={cat})")
    else:
        print(f"  !! id={rid}: no kalshi_ticker either -- not changed, send this line to Claude")
conn.commit()

cur.execute("""
    SELECT id, ticker, category FROM predictions
    WHERE (ticker IS NULL OR ticker = '' OR category IS NULL OR category = '')
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
""")
left = cur.fetchall()
conn.close()
print(f"\n{len(rows)} row(s) examined. Open rows still missing ticker or category: {len(left)}")
for r in left:
    print(f"  id={r[0]} ticker={r[1]!r} category={r[2]!r}")
