"""
audit_final_scorecard.py  —  Show exactly which 27 positions the scorecard
is scoring, which call it picked as final, and how each resolved.

Run from C:\\Users\\qwhit\\AFG\\:
    python3 audit_final_scorecard.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Replicate 06_build_scorecard.py final-call logic:
# For each unique ticker with an outcome, pick the LAST published BUY YES/NO
# call (highest rowid) that is not Void/Superseded.

cur.execute("""
    SELECT DISTINCT ticker
    FROM predictions
    WHERE outcome IS NOT NULL AND outcome != ''
      AND status NOT IN ('Void','Superseded')
      AND recommendation IN ('BUY YES','BUY NO')
    ORDER BY ticker
""")
tickers = [r[0] for r in cur.fetchall()]

print(f"Unique scored tickers: {len(tickers)}\n")
print(f"{'TICKER':<45} {'REC':<10} {'AFG%':<6} {'OUT':<4} {'RESULT':<14} {'MARKET'}")
print("-" * 110)

correct = 0
incorrect = 0

for ticker in tickers:
    # Final call = last BUY YES/NO row by rowid
    cur.execute("""
        SELECT id, recommendation, afg_probability, outcome, market
        FROM predictions
        WHERE ticker = ?
          AND outcome IS NOT NULL AND outcome != ''
          AND status NOT IN ('Void','Superseded')
          AND recommendation IN ('BUY YES','BUY NO')
        ORDER BY id DESC LIMIT 1
    """, (ticker,))
    row = cur.fetchone()
    if not row:
        continue

    row_id, rec, afg_pct, outcome, market = row
    try:
        p = float(afg_pct)
        o = int(outcome)
    except (TypeError, ValueError):
        print(f"  ⚠  {ticker}: non-numeric afg_pct={afg_pct} or outcome={outcome}")
        continue

    if (rec == "BUY YES" and o == 1) or (rec == "BUY NO" and o == 0):
        result = "✓ Correct"
        correct += 1
    else:
        result = "✗ Incorrect"
        incorrect += 1

    mkt = (market or "")[:40]
    print(f"{ticker:<45} {rec:<10} {p:<6} {o:<4} {result:<14} {mkt}")

n = correct + incorrect
acc = correct / n * 100 if n else 0
print("-" * 110)
print(f"\nTotal: {n}  |  Correct: {correct}  |  Incorrect: {incorrect}  |  Accuracy: {acc:.1f}%\n")

# Also show any rows that might still have wrong outcomes
print("=" * 60)
print("SANITY CHECK — All resolved rows (including Superseded)")
print("=" * 60)
cur.execute("""
    SELECT id, ticker, recommendation, afg_probability, outcome, status
    FROM predictions
    WHERE outcome IS NOT NULL AND outcome != ''
    ORDER BY ticker, id
""")
for r in cur.fetchall():
    row_id, ticker, rec, afg_pct, outcome, status = r
    flag = " ← SUPERSEDED" if status in ('Void','Superseded') else ""
    print(f"  id={row_id:<4} {str(ticker):<45} {str(rec):<10} afg={afg_pct}  out={outcome}  [{status}]{flag}")

conn.close()
