"""
diagnose_outcomes.py  —  Show all resolved positions with full details
======================================================================
Run this BEFORE fix_scorecard_outcomes_v2.py to see exact market text
so the correction script can match correctly.

Run from C:\\Users\\qwhit\\AFG\\:
    python3 diagnose_outcomes.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute("""
    SELECT id, ticker, kalshi_ticker, market, recommendation,
           afg_probability, outcome, status, category
    FROM predictions
    WHERE outcome IS NOT NULL AND outcome != ''
      AND status NOT IN ('Void', 'Superseded')
    ORDER BY id
""")
rows = cur.fetchall()

print(f"Total resolved rows: {len(rows)}\n")
print(f"{'ID':<5} {'REC':<10} {'AFG%':<6} {'OUT':<4} {'CAT':<12} {'TICKER':<40}")
print("-" * 90)
for r in rows:
    row_id, ticker, kal_ticker, market, rec, afg_pct, outcome, status, cat = r
    t = ticker or kal_ticker or "(none)"
    print(f"{row_id:<5} {str(rec):<10} {str(afg_pct):<6} {str(outcome):<4} {str(cat):<12} {t:<40}")
    if market:
        print(f"      market: {market[:100]}")
    print()

conn.close()
