"""
AFG Fix — Premature Resolutions
Reopens contracts that are marked resolved but whose settlement date is in the future.

Affected tickers from verify_afg.py output:
  KXNEXTAG-29-TBLA   (settles 2029-01-20)
  KXRT-SPI-90        (settles 2026-12-31)

Run from C:\\Users\\qwhit\\AFG\\:
    python3 fix_premature_resolutions.py
"""

import sqlite3
from datetime import date

DB_PATH = "afg_scorecard.db"
TODAY   = date.today().isoformat()   # 2026-11-09

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Show what we're about to change
cur.execute("""
    SELECT id, ticker, kalshi_ticker, market, status, resolved,
           close_date, contract_close_date, resolution_date, outcome
    FROM predictions
    WHERE resolved = 1
      AND (
            (close_date > ? AND close_date != '')
         OR (contract_close_date > ? AND contract_close_date != '')
      )
    ORDER BY ticker
""", (TODAY, TODAY))

rows = cur.fetchall()
print(f"Rows to reopen: {len(rows)}\n")
for r in rows:
    print(f"  id={r[0]}  ticker={r[1] or r[2]}  market={r[3][:60]}")
    print(f"    status={r[4]}  resolved={r[5]}  close_date={r[6]}  "
          f"contract_close_date={r[7]}  resolution_date={r[8]}  outcome={r[9]}\n")

if not rows:
    print("Nothing to fix — all resolved rows have past settlement dates.")
    conn.close()
    raise SystemExit(0)

# Reopen: set resolved=0, clear resolution_date and outcome, reset status to 'open'
cur.execute("""
    UPDATE predictions
    SET resolved        = 0,
        resolution_date = NULL,
        outcome         = NULL,
        status          = 'open'
    WHERE resolved = 1
      AND (
            (close_date > ? AND close_date != '')
         OR (contract_close_date > ? AND contract_close_date != '')
      )
""", (TODAY, TODAY))

print(f"Reopened {cur.rowcount} row(s).")
conn.commit()

# Confirm
cur.execute("""
    SELECT COUNT(*) FROM predictions
    WHERE resolved = 1
      AND (
            (close_date > ? AND close_date != '')
         OR (contract_close_date > ? AND contract_close_date != '')
      )
""", (TODAY, TODAY))
remaining = cur.fetchone()[0]
print(f"Remaining premature resolutions: {remaining}")

conn.close()
print("\nFix complete. Run verify_afg.py to confirm all 9 checks pass.")
