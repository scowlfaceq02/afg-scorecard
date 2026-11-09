"""
AFG Database Patch
Backfills the three new columns from their existing equivalents:
  ticker         ← kalshi_ticker
  published_date ← report_date
  close_date     ← contract_close_date

Also backfills resolved and resolution_date from status/outcome columns.

Run from C:\\Users\\qwhit\\AFG\\:
    python3 patch_db.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# 1. ticker ← kalshi_ticker
cur.execute("""
    UPDATE predictions
    SET ticker = kalshi_ticker
    WHERE (ticker IS NULL OR ticker = '')
      AND kalshi_ticker IS NOT NULL
      AND kalshi_ticker != ''
""")
print(f"ticker backfilled:         {cur.rowcount} rows")

# 2. published_date ← report_date
cur.execute("""
    UPDATE predictions
    SET published_date = report_date
    WHERE (published_date IS NULL OR published_date = '')
      AND report_date IS NOT NULL
      AND report_date != ''
""")
print(f"published_date backfilled: {cur.rowcount} rows")

# 3. close_date ← contract_close_date
cur.execute("""
    UPDATE predictions
    SET close_date = contract_close_date
    WHERE (close_date IS NULL OR close_date = '')
      AND contract_close_date IS NOT NULL
      AND contract_close_date != ''
""")
print(f"close_date backfilled:     {cur.rowcount} rows")

# 4. resolved ← status (resolved=1 where status IN ('resolved','closed','settled'))
cur.execute("""
    UPDATE predictions
    SET resolved = 1
    WHERE resolved = 0
      AND LOWER(status) IN ('resolved', 'closed', 'settled', 'won', 'lost', 'correct', 'incorrect')
""")
print(f"resolved backfilled:       {cur.rowcount} rows")

# 5. resolution_date ← afg_closed_date where resolved
cur.execute("""
    UPDATE predictions
    SET resolution_date = afg_closed_date
    WHERE (resolution_date IS NULL OR resolution_date = '')
      AND afg_closed_date IS NOT NULL
      AND afg_closed_date != ''
""")
print(f"resolution_date backfilled:{cur.rowcount} rows")

conn.commit()

# Spot-check
cur.execute("""
    SELECT COUNT(*) FROM predictions
    WHERE (ticker IS NULL OR ticker = '')
      AND (kalshi_ticker IS NOT NULL AND kalshi_ticker != '')
""")
remaining = cur.fetchone()[0]
print(f"\nRows still missing ticker: {remaining}")

cur.execute("SELECT COUNT(*) FROM predictions WHERE published_date IS NULL OR published_date = ''")
print(f"Rows still missing published_date: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM predictions WHERE close_date IS NULL OR close_date = ''")
print(f"Rows still missing close_date:     {cur.fetchone()[0]}")

conn.close()
print("\nPatch complete. Run verify_afg.py to confirm.")
