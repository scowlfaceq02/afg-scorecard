"""
Sets the resolution_date for the Wiles contract so verify_afg.py
recognizes it as a legitimate early resolution (not premature).

Run from C:\\Users\\qwhit\\AFG\\:
    python3 set_wiles_resolution.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"
TICKER  = "KXTRUMPADMINLEAVE-26DEC31-SWIL"
RESOLUTION_DATE = "2026-10-30"   # Date Susie Wiles departure was confirmed

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Show current state
cur.execute("""
    SELECT id, ticker, status, outcome, close_date, resolution_date
    FROM predictions WHERE ticker = ?
""", (TICKER,))
rows = cur.fetchall()
print("Before:")
for r in rows:
    print(f"  id={r[0]}  status={r[2]}  outcome={r[3]}  close_date={r[4]}  resolution_date={r[5]}")

# Set resolution_date
cur.execute("""
    UPDATE predictions
    SET resolution_date = ?
    WHERE ticker = ?
      AND (resolution_date IS NULL OR resolution_date = '')
""", (RESOLUTION_DATE, TICKER))
print(f"\nUpdated {cur.rowcount} row(s).")
conn.commit()

# Confirm
cur.execute("""
    SELECT id, ticker, status, outcome, close_date, resolution_date
    FROM predictions WHERE ticker = ?
""", (TICKER,))
rows = cur.fetchall()
print("After:")
for r in rows:
    print(f"  id={r[0]}  status={r[2]}  outcome={r[3]}  close_date={r[4]}  resolution_date={r[5]}")

conn.close()
print("\nDone. Run verify_afg.py to confirm.")
