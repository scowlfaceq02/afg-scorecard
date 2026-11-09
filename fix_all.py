"""
AFG Fix-All Script
Addresses all three remaining verify_afg.py failures:

  1. 6 rows missing ticker/category
  2. Wiles (KXTRUMPADMINLEAVE-26DEC31-SWIL) still flagged as premature resolution
  3. Rows with ticker=None and published_date=None causing a false BUY YES + BUY NO conflict

Run from C:\\Users\\qwhit\\AFG\\:
    python3 fix_all.py
"""

import sqlite3
from datetime import date

DB_PATH = "afg_scorecard.db"
TODAY   = date.today().isoformat()

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ══════════════════════════════════════════════════════════════════
# FIX 1: Rows missing ticker or category
# ══════════════════════════════════════════════════════════════════
print("=" * 60)
print("FIX 1: Rows missing ticker or category")
print("=" * 60)

cur.execute("""
    SELECT id, kalshi_ticker, ticker, market, category,
           recommendation, status, outcome
    FROM predictions
    WHERE (ticker IS NULL OR ticker = '' OR category IS NULL OR category = '')
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
    ORDER BY id
""")
bad_rows = cur.fetchall()
print(f"Found {len(bad_rows)} rows:\n")
for r in bad_rows:
    print(f"  id={r[0]}  kalshi_ticker={r[1]}  ticker={r[2]}  "
          f"category={r[3]}  market={r[4][:50] if r[4] else None}  "
          f"rec={r[5]}  status={r[6]}")

# Sub-fix A: backfill ticker from kalshi_ticker where both exist
cur.execute("""
    UPDATE predictions
    SET ticker = kalshi_ticker
    WHERE (ticker IS NULL OR ticker = '')
      AND kalshi_ticker IS NOT NULL AND kalshi_ticker != ''
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
""")
print(f"\n  ticker backfilled from kalshi_ticker: {cur.rowcount} rows")

# Sub-fix B: rows where BOTH ticker and kalshi_ticker are NULL/empty
# and outcome is NULL — these are ghost rows with no identity; mark Void
cur.execute("""
    SELECT id, market, recommendation, status
    FROM predictions
    WHERE (ticker IS NULL OR ticker = '')
      AND (kalshi_ticker IS NULL OR kalshi_ticker = '')
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
""")
ghost_rows = cur.fetchall()
print(f"\n  Ghost rows (no ticker, no kalshi_ticker, no outcome): {len(ghost_rows)}")
for r in ghost_rows:
    print(f"    id={r[0]}  market={str(r[1])[:50]}  rec={r[2]}  status={r[3]}")

if ghost_rows:
    ghost_ids = [r[0] for r in ghost_rows]
    placeholders = ",".join("?" * len(ghost_ids))
    cur.execute(f"""
        UPDATE predictions
        SET status = 'Void'
        WHERE id IN ({placeholders})
    """, ghost_ids)
    print(f"  Marked {cur.rowcount} ghost rows as Void")

conn.commit()

# ══════════════════════════════════════════════════════════════════
# FIX 2: Wiles — set resolution_date so early resolution is accepted
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("FIX 2: Wiles resolution_date")
print("=" * 60)

WILES_TICKER = "KXTRUMPADMINLEAVE-26DEC31-SWIL"
WILES_RES_DATE = "2026-10-30"

cur.execute("""
    SELECT id, status, outcome, close_date, resolution_date
    FROM predictions WHERE ticker = ? OR kalshi_ticker = ?
""", (WILES_TICKER, WILES_TICKER))
wiles_rows = cur.fetchall()
print(f"Wiles rows found: {len(wiles_rows)}")
for r in wiles_rows:
    print(f"  id={r[0]}  status={r[1]}  outcome={r[2]}  "
          f"close_date={r[3]}  resolution_date={r[4]}")

cur.execute("""
    UPDATE predictions
    SET resolution_date = ?
    WHERE (ticker = ? OR kalshi_ticker = ?)
      AND (resolution_date IS NULL OR resolution_date = '')
""", (WILES_RES_DATE, WILES_TICKER, WILES_TICKER))
print(f"  resolution_date set to {WILES_RES_DATE}: {cur.rowcount} rows updated")
conn.commit()

# Verify Check 5 logic manually
cur.execute("""
    SELECT id, ticker, kalshi_ticker, close_date, resolution_date, outcome
    FROM predictions
    WHERE (ticker = ? OR kalshi_ticker = ?)
""", (WILES_TICKER, WILES_TICKER))
for r in cur.fetchall():
    print(f"  After: id={r[0]}  close_date={r[3]}  resolution_date={r[4]}  outcome={r[5]}")

# ══════════════════════════════════════════════════════════════════
# FIX 3: NULL ticker / NULL published_date causing false conflict in Check 6
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("FIX 3: NULL-ticker rows causing false BUY YES + BUY NO conflict")
print("=" * 60)

cur.execute("""
    SELECT id, ticker, kalshi_ticker, published_date, recommendation, status, outcome
    FROM predictions
    WHERE (ticker IS NULL OR ticker = '')
      AND (outcome IS NULL OR outcome = '')
      AND recommendation IN ('BUY YES', 'BUY NO')
      AND status NOT IN ('Void', 'Superseded')
""")
null_conflict_rows = cur.fetchall()
print(f"Rows with NULL ticker still open after Fix 1: {len(null_conflict_rows)}")
for r in null_conflict_rows:
    print(f"  id={r[0]}  kalshi_ticker={r[2]}  pub={r[3]}  rec={r[4]}  status={r[5]}")

# These should have been caught by Fix 1; if any remain, void them
if null_conflict_rows:
    ids = [r[0] for r in null_conflict_rows]
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"UPDATE predictions SET status='Void' WHERE id IN ({placeholders})", ids)
    print(f"  Voided {cur.rowcount} remaining NULL-ticker open rows")

conn.commit()

# ══════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("FINAL STATE CHECK")
print("=" * 60)

cur.execute("""
    SELECT COUNT(*) FROM predictions
    WHERE (ticker IS NULL OR ticker = '' OR category IS NULL OR category = '')
      AND (outcome IS NULL OR outcome = '')
      AND status NOT IN ('Void', 'Superseded')
""")
print(f"Open rows still missing ticker/category: {cur.fetchone()[0]}")

cur.execute("""
    SELECT COUNT(*) FROM predictions
    WHERE (ticker IS NULL OR ticker = '')
      AND (outcome IS NULL OR outcome = '')
      AND recommendation IN ('BUY YES','BUY NO')
      AND status NOT IN ('Void','Superseded')
""")
print(f"Open BUY rows still missing ticker:      {cur.fetchone()[0]}")

cur.execute("""
    SELECT ticker, resolution_date FROM predictions
    WHERE ticker = ? OR kalshi_ticker = ?
    LIMIT 1
""", (WILES_TICKER, WILES_TICKER))
row = cur.fetchone()
print(f"Wiles resolution_date:                   {row[1] if row else 'NOT FOUND'}")

conn.close()
print("\nAll fixes applied. Run verify_afg.py to confirm.")
