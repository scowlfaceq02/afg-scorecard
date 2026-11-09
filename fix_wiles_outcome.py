"""
Fix Wiles outcome in the database.

The contract KXTRUMPADMINLEAVE-26DEC31-SWIL is a departure market.
It resolves YES if Susie Wiles departs. She departed, so outcome = 1 (YES).
The database currently has outcome = 0 (NO), which incorrectly scores
AFG's BUY NO call as Correct.

Run from C:\\Users\\qwhit\\AFG\\:
    python3 fix_wiles_outcome.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"
TICKER  = "KXTRUMPADMINLEAVE-26DEC31-SWIL"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Show current state
cur.execute("""
    SELECT id, ticker, market, outcome, status, resolution_date
    FROM predictions
    WHERE ticker = ? OR kalshi_ticker = ?
    ORDER BY id
""", (TICKER, TICKER))
rows = cur.fetchall()
print("Current state:")
for r in rows:
    print(f"  id={r[0]}  outcome={r[3]}  status={r[4]}  resolution_date={r[5]}")
    print(f"  market: {r[2]}")

# Fix: outcome should be 1 (YES — she departed, contract resolved YES)
cur.execute("""
    UPDATE predictions
    SET outcome = 1,
        status  = 'Resolved'
    WHERE (ticker = ? OR kalshi_ticker = ?)
""", (TICKER, TICKER))
print(f"\nUpdated {cur.rowcount} row(s): outcome set to 1 (YES — departed)")
conn.commit()

# Confirm
cur.execute("""
    SELECT id, outcome, status, resolution_date
    FROM predictions
    WHERE ticker = ? OR kalshi_ticker = ?
""", (TICKER, TICKER))
print("\nAfter fix:")
for r in cur.fetchall():
    print(f"  id={r[0]}  outcome={r[1]}  status={r[2]}  resolution_date={r[3]}")

conn.close()
print("\nDone. Run 06_build_scorecard.py — Wiles will now show as ✗ Incorrect (BUY NO, outcome YES).")
print("This will reduce accuracy from 74.1% — the correct reflection of AFG's performance.")
